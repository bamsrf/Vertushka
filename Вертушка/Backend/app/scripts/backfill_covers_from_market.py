"""Обратный поток обложек из маркета в дамп-индекс Discogs.

Самый дешёвый канал из всех: данные УЖЕ в нашей базе. Магазины фотографируют
свой товар, парсеры складывают ссылку в `store_listings.raw_payload->>'image_url'`,
но дальше витрины маркета она не идёт — в `discogs_releases_index` не попадает
никогда. На 18.08.2026 таких релизов 8 250, из них 512 постсоветских.

Почему это лучший источник для русского винила: это фотография НАСТОЯЩЕГО
конверта конкретного издания, а не стриминговый арт цифрового релиза. Плюс
канал растёт сам с каждым обходом магазинов, а магазины у нас русские.

ГЛАВНОЕ — тир. Разрешение фото сильно зависит от магазина (замер на проде,
по 12 картинок с хоста):

    plastinka.com    медиана  600   100% мастер-тира
    doctorhead.ru    медиана  600   100%
    tildacdn         медиана 1000    92%
    long-play.ru     медиана  599    75%
    rotaryrecords    медиана  591    75%
    stoprobotvinyl   медиана  450     0%
    skifmusic.ru     медиана  270     0%
    vinyl.ru         медиана  318     0%

Писать вслепую нельзя: мелкая картинка в `cover_image_url` навсегда закрывает
строку для лучших источников — ровно так мы получили 54% пиксельных мастеров
(см. cover_quality). Поэтому КАЖДУЮ картинку измеряем по декодированным
пикселям и раскладываем по тирам: >=MASTER_MIN_SIDE → `cover_image_url`,
меньше → `thumb_image_url` (плейсхолдер, строку не закрывает).

У релиза бывает несколько листингов в разных магазинах — пробуем по очереди и
берём первый мастер-тира. Пластинка из vinyl.ru (320px) и plastinka.com (600px)
получит вторую.

Запуск на проде:
  docker exec -d vertushka_api_blue sh -c \
    "python -m app.scripts.backfill_covers_from_market > /app/uploads/market_covers.log 2>&1"
"""
from __future__ import annotations

import argparse
import asyncio
import io
import logging
import os
import time

import httpx
from PIL import Image
from sqlalchemy import text

from app.database import async_session_maker
from app.services.cover_quality import MASTER_MIN_SIDE
from app.utils.url_guard import is_safe_redirect_target

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger("market_covers")

WORKLIST = "cover_backfill_market"
MARKER = "/app/uploads/.backfill_market_enabled"

# Размер картинки читаем из заголовка, не качая её целиком: Pillow берёт .size
# из первых килобайт JPEG/PNG/WebP. На 8 тысячах кандидатов это разница между
# ~1.5 ГБ трафика и десятками мегабайт.
_HEADER_BYTES = 65536
_MAX_BYTES = 4 * 1024 * 1024

# Кандидатов на релиз: у популярной пластинки листингов бывает десяток, но
# перебирать все ради обложки незачем — первые три покрывают разброс магазинов.
_MAX_CANDIDATES = 3

_CONCURRENCY = 4
_RUN_BUDGET = 600


async def _ensure_infra() -> None:
    async with async_session_maker() as s:
        await s.execute(text(
            f"CREATE TABLE IF NOT EXISTS {WORKLIST} ("
            "  discogs_id BIGINT PRIMARY KEY,"
            "  done BOOLEAN NOT NULL DEFAULT FALSE)"
        ))
        await s.execute(text(
            f"CREATE INDEX IF NOT EXISTS ix_{WORKLIST}_todo "
            f"ON {WORKLIST} (discogs_id) WHERE NOT done"
        ))
        await s.commit()


async def _build_worklist(rebuild: bool = False) -> int:
    """Релизы дампа без обложки, у которых есть фото хотя бы в одном магазине."""
    async with async_session_maker() as s:
        await s.execute(text("SET statement_timeout = 900000"))
        if rebuild:
            await s.execute(text(f"TRUNCATE {WORKLIST}"))
            await s.commit()
        # Не выходим рано даже при непустой таблице: маркет растёт, новые
        # листинги должны доезжать. ON CONFLICT DO NOTHING сохраняет done.
        await s.execute(text(
            f"INSERT INTO {WORKLIST} (discogs_id) "
            "SELECT DISTINCT d.discogs_id "
            "FROM store_listings sl "
            "JOIN records r ON r.id = sl.matched_record_id "
            "JOIN discogs_releases_index d "
            "  ON d.discogs_id = CASE WHEN r.discogs_id ~ '^[0-9]+$' "
            "                         THEN r.discogs_id::bigint END "
            "WHERE sl.raw_payload->>'image_url' IS NOT NULL "
            "  AND sl.raw_payload->>'image_url' <> '' "
            "  AND d.cover_image_url IS NULL "
            "ON CONFLICT (discogs_id) DO NOTHING"
        ))
        await s.commit()
        total = (await s.execute(text(
            f"SELECT count(*) FROM {WORKLIST} WHERE NOT done"))).scalar()
        logger.info("worklist: %d релизов ждут обложки из маркета", total)
        return int(total)


async def _candidates(ids: list[int]) -> dict[int, list[str]]:
    """discogs_id → до _MAX_CANDIDATES ссылок на фото, разными магазинами."""
    async with async_session_maker() as s:
        rows = (await s.execute(text(
            "SELECT d.discogs_id AS did, sl.raw_payload->>'image_url' AS url "
            "FROM store_listings sl "
            "JOIN records r ON r.id = sl.matched_record_id "
            "JOIN discogs_releases_index d "
            "  ON d.discogs_id = CASE WHEN r.discogs_id ~ '^[0-9]+$' "
            "                         THEN r.discogs_id::bigint END "
            "WHERE d.discogs_id = ANY(:ids) "
            "  AND sl.raw_payload->>'image_url' <> ''"
        ), {"ids": ids})).mappings().all()

    out: dict[int, list[str]] = {}
    for r in rows:
        urls = out.setdefault(r["did"], [])
        if r["url"] not in urls and len(urls) < _MAX_CANDIDATES:
            urls.append(r["url"])
    return out


async def _min_side(client: httpx.AsyncClient, url: str) -> int | None:
    """Меньшая сторона картинки, либо None. Качаем только заголовок."""
    try:
        async with client.stream("GET", url) as resp:
            if resp.status_code != 200:
                return None
            buf = b""
            async for chunk in resp.aiter_bytes(16384):
                buf += chunk
                if len(buf) >= _HEADER_BYTES or len(buf) > _MAX_BYTES:
                    break
                try:
                    return min(Image.open(io.BytesIO(buf)).size)
                except Exception:
                    continue  # заголовок ещё не целиком — добираем
            return min(Image.open(io.BytesIO(buf)).size)
    except Exception:
        return None


async def _pick_best(client: httpx.AsyncClient, urls: list[str]) -> tuple[str, int] | None:
    """Первый мастер-тира; если такого нет — самый крупный из измеренных."""
    best: tuple[str, int] | None = None
    for url in urls:
        # URL приехал из парсера чужой витрины: без проверки наше зеркало
        # начнёт ходить куда попало (та же логика, что в covers.py::_safe).
        if not is_safe_redirect_target(url):
            continue
        side = await _min_side(client, url)
        if side is None:
            continue
        if side >= MASTER_MIN_SIDE:
            return url, side
        if best is None or side > best[1]:
            best = (url, side)
    return best


async def _persist(found: list[tuple[int, str, int]], asked: list[int]) -> dict:
    """Мастер-тир → cover_image_url, мелочь → thumb_image_url."""
    stats = {"master": 0, "thumb": 0}
    async with async_session_maker() as s:
        for did, url, side in found:
            col = "cover_image_url" if side >= MASTER_MIN_SIDE else "thumb_image_url"
            res = await s.execute(text(
                f"UPDATE discogs_releases_index "
                f"SET {col} = :u, cover_checked_at = now() "
                f"WHERE discogs_id = :d AND {col} IS NULL"
            ), {"u": url, "d": did})
            if res.rowcount:
                stats["master" if col == "cover_image_url" else "thumb"] += 1
        await s.execute(text(
            f"UPDATE {WORKLIST} SET done = TRUE WHERE discogs_id = ANY(:ids)"
        ), {"ids": asked})
        await s.commit()
    return stats


async def run(batch: int = 200, budget_s: float = _RUN_BUDGET,
              max_items: int | None = None) -> dict:
    stats = {"asked": 0, "master": 0, "thumb": 0, "no_image": 0}
    started = time.monotonic()
    await _build_worklist()

    async with httpx.AsyncClient(
        timeout=20.0, follow_redirects=True,
        headers={"User-Agent": "Vertushka/1.0 (+https://vinyl-vertushka.ru)"},
    ) as client:
        while True:
            if time.monotonic() - started > budget_s:
                break
            if max_items is not None and stats["asked"] >= max_items:
                break

            async with async_session_maker() as s:
                ids = (await s.execute(text(
                    f"SELECT discogs_id FROM {WORKLIST} WHERE NOT done "
                    "ORDER BY discogs_id LIMIT :b"
                ), {"b": batch})).scalars().all()
            if not ids:
                logger.info("очередь пройдена целиком")
                break

            cand = await _candidates(list(ids))
            sem = asyncio.Semaphore(_CONCURRENCY)
            done: list[tuple[int, str, int]] = []
            asked: list[int] = []

            async def work(did: int) -> None:
                async with sem:
                    picked = await _pick_best(client, cand.get(did, []))
                # В asked попадает только реально обработанный релиз: вызывающий
                # метит `done` ровно по этому списку.
                asked.append(did)
                if picked:
                    done.append((did, picked[0], picked[1]))

            await asyncio.gather(*(work(i) for i in ids))

            res = await _persist(done, asked)
            stats["asked"] += len(asked)
            stats["master"] += res["master"]
            stats["thumb"] += res["thumb"]
            stats["no_image"] += len(asked) - len(done)
            logger.info("market covers: asked=%d master=%d thumb=%d без картинки=%d",
                        stats["asked"], stats["master"], stats["thumb"], stats["no_image"])

    stats["elapsed_s"] = round(time.monotonic() - started, 1)
    return stats


async def run_scheduled_batch() -> None:
    """Гейт-маркер + ограниченный проход. Маркет растёт, канал живёт постоянно."""
    if not os.path.exists(MARKER):
        return
    await _ensure_infra()
    await run(budget_s=300)


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--batch", type=int, default=200)
    ap.add_argument("--max-items", type=int, default=None)
    ap.add_argument("--budget", type=float, default=3600.0)
    ap.add_argument("--rebuild-worklist", action="store_true")
    args = ap.parse_args()
    await _ensure_infra()
    if args.rebuild_worklist:
        await _build_worklist(rebuild=True)
    logger.info("готово: %s", await run(args.batch, args.budget, args.max_items))


if __name__ == "__main__":
    asyncio.run(main())
