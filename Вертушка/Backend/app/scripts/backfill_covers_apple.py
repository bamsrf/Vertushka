"""Bulk-backfill обложек по ШТРИХКОДУ через Apple Music API (MusicKit).

Клон рельсов backfill_covers_upc (Deezer) — та же волновая механика, тот же
контракт «done только у реально спрошенных», тот же сторож нулевого выхлопа
(инцидент 18.08.2026 с ведущим нулём; здесь обе формы кода спрашиваются одним
запросом — filter[upc] принимает список). Отличия:

- своя очередь cover_backfill_apple: строится из релизов, ВСЁ ЕЩЁ без обложки
  к моменту постройки — то есть из промахов всех предыдущих каналов
  (CAA map/barcode/catno, Deezer-UPC, магазины);
- источник — Apple Music каталог US, артворк альбом-левел до 1200px;
- гейты запуска: маркер + APPLE_MUSIC_-конфиг (см. services/apple_music.py —
  там же инструкция по получению ключа).

Запуск на проде (фоном, переживает разрыв ssh):
  docker exec -d vertushka_api_blue sh -c \
    "python -m app.scripts.backfill_covers_apple > /app/uploads/backfill_apple.log 2>&1"

Тест на N штрихкодах: --max-requests 200
Scheduled-режим: touch /app/uploads/.backfill_apple_enabled
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import os
import time

from sqlalchemy import text

from app.database import async_session_maker
from app.services.apple_music import AppleMusicQuotaExceeded, configured, cover_by_upc

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logger = logging.getLogger("backfill_apple")

WORKLIST = "cover_backfill_apple"
MARKER = "/app/uploads/.backfill_apple_enabled"

# Темп держит глобальный пейсер apple_music (0.5 с/запрос) — воркеры лишь
# перекрывают сетевую латентность. Два, не четыре: Apple реагирует 429 не на
# темп стартов, а на глубину in-flight (замер 31.08.2026).
_CONCURRENCY = 2
_MAX_FANOUT = 20          # мусорные штрихкоды-паровозы, как в UPC-канале
_RUN_BUDGET = 240         # бюджет scheduled-прогона, с
_QUOTA_BACKOFF = 60
_ZERO_STREAK_ABORT = 500  # порог систематической ошибки, не пустого блока


async def _ensure_infra() -> None:
    async with async_session_maker() as s:
        await s.execute(text(
            f"CREATE TABLE IF NOT EXISTS {WORKLIST} ("
            "  barcode_norm TEXT PRIMARY KEY,"
            "  done BOOLEAN NOT NULL DEFAULT FALSE)"
        ))
        await s.execute(text(
            f"CREATE INDEX IF NOT EXISTS ix_{WORKLIST}_todo "
            f"ON {WORKLIST} (barcode_norm) WHERE NOT done"
        ))
        await s.commit()


async def _build_worklist(rebuild: bool = False) -> int:
    """Уникальные штрихкоды релизов без обложки. Идемпотентно."""
    async with async_session_maker() as s:
        await s.execute(text("SET statement_timeout = 900000"))
        if rebuild:
            await s.execute(text(f"TRUNCATE {WORKLIST}"))
            await s.commit()
        have = (await s.execute(text(f"SELECT count(*) FROM {WORKLIST}"))).scalar()
        if have and not rebuild:
            return int(have)

        logger.info("building Apple worklist (heavy agg, ~1-2 min)...")
        await s.execute(text(
            f"INSERT INTO {WORKLIST} (barcode_norm) "
            "SELECT barcode_norm FROM discogs_releases_index "
            "WHERE cover_image_url IS NULL "
            "  AND barcode_norm ~ '^[0-9]{8,14}$' "
            "GROUP BY barcode_norm "
            f"HAVING count(*) <= {_MAX_FANOUT} "
            "ON CONFLICT (barcode_norm) DO NOTHING"
        ))
        await s.commit()
        total = (await s.execute(text(f"SELECT count(*) FROM {WORKLIST}"))).scalar()
        logger.info("Apple worklist: %d штрихкодов", total)
        return int(total)


async def _lookup_wave(barcodes: list[str], budget_s: float) -> tuple[list[tuple[str, str | None]], bool]:
    """Волна опроса. В результат попадает только реально спрошенное: дедлайн
    проверяется ДО взятия элемента — незаданный вопрос не получает вердикт."""
    queue: asyncio.Queue[str] = asyncio.Queue()
    for bc in barcodes:
        queue.put_nowait(bc)

    done: list[tuple[str, str | None]] = []
    deadline = time.monotonic() + budget_s
    quota_hit = asyncio.Event()

    async def worker() -> None:
        while not quota_hit.is_set() and time.monotonic() < deadline:
            try:
                bc = queue.get_nowait()
            except asyncio.QueueEmpty:
                return
            try:
                cover = await cover_by_upc(bc)
            except AppleMusicQuotaExceeded as e:
                logger.warning("Apple stop: %s — прерываем волну, %s вернутся в очередь",
                               e, queue.qsize() + 1)
                quota_hit.set()
                return
            except Exception:
                logger.debug("apple lookup failed: %s", bc, exc_info=True)
                cover = None
            done.append((bc, cover))

    await asyncio.gather(*(worker() for _ in range(_CONCURRENCY)))
    return done, quota_hit.is_set()


async def _persist(results: list[tuple[str, str | None]]) -> int:
    hits = [(bc, url) for bc, url in results if url]
    touched = 0
    async with async_session_maker() as s:
        for bc, url in hits:
            res = await s.execute(text(
                "UPDATE discogs_releases_index "
                "SET cover_image_url = :u, cover_checked_at = now() "
                "WHERE barcode_norm = :b AND cover_image_url IS NULL"
            ), {"u": url, "b": bc})
            touched += res.rowcount or 0
        await s.execute(text(
            f"UPDATE {WORKLIST} SET done = TRUE WHERE barcode_norm = ANY(:ids)"
        ), {"ids": [bc for bc, _ in results]})
        await s.commit()
    return touched


async def run(batch: int = 200, max_requests: int | None = None,
              budget_s: float = _RUN_BUDGET) -> dict:
    stats = {"asked": 0, "hits": 0, "releases": 0, "quota": False, "zero_streak": False}
    started = time.monotonic()
    streak = 0

    if not await _build_worklist():
        logger.info("Apple worklist пуст — нечего делать")
        return stats

    while True:
        left = budget_s - (time.monotonic() - started)
        if left <= 1:
            break
        if max_requests is not None and stats["asked"] >= max_requests:
            break

        async with async_session_maker() as s:
            rows = (await s.execute(text(
                f"SELECT barcode_norm FROM {WORKLIST} WHERE NOT done "
                "ORDER BY barcode_norm LIMIT :b"
            ), {"b": batch})).scalars().all()
        if not rows:
            logger.info("очередь пройдена целиком")
            break

        results, quota = await _lookup_wave(list(rows), left)
        if results:
            stats["releases"] += await _persist(results)
            stats["asked"] += len(results)
            stats["hits"] += sum(1 for _, url in results if url)
        for _, url in results:
            streak = 0 if url else streak + 1
        if streak >= _ZERO_STREAK_ABORT:
            stats["zero_streak"] = True
            logger.error(
                "apple: %d промахов подряд — прерываем прогон; последний "
                "штрихкод %s", streak, results[-1][0] if results else "?",
            )
            from app.services import alerts
            alerts.fire_and_forget(
                key="cover_apple_zero_yield",
                title=f"Apple-обход: {streak} промахов подряд",
                body=(
                    f"Прогон остановлен. Обработано {stats['asked']}, попаданий "
                    f"{stats['hits']}. Проверить форму filter[upc] около "
                    f"{results[-1][0] if results else '?'} и валидность ключа."
                ),
            )
            break
        if quota:
            stats["quota"] = True
            break
        if not results:
            logger.error("волна без единого ответа — прерываем проход")
            break

        logger.info("apple: asked=%d hits=%d (%.1f%%) releases=%d",
                    stats["asked"], stats["hits"],
                    100 * stats["hits"] / max(stats["asked"], 1), stats["releases"])

    stats["elapsed_s"] = round(time.monotonic() - started, 1)
    return stats


async def run_scheduled_batch() -> None:
    """Гейты: маркер-файл + заполненный APPLE_MUSIC_-конфиг."""
    if not os.path.exists(MARKER) or not configured():
        return
    await _ensure_infra()
    stats = await run()
    if stats.get("quota"):
        await asyncio.sleep(_QUOTA_BACKOFF)


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--batch", type=int, default=200)
    ap.add_argument("--max-requests", type=int, default=None)
    ap.add_argument("--budget", type=float, default=3600.0)
    ap.add_argument("--rebuild-worklist", action="store_true")
    args = ap.parse_args()

    if not configured():
        raise SystemExit("APPLE_MUSIC_TEAM_ID/KEY_ID/PRIVATE_KEY_B64 не заданы")
    await _ensure_infra()
    if args.rebuild_worklist:
        await _build_worklist(rebuild=True)
    stats = await run(args.batch, args.max_requests, args.budget)
    logger.info("готово: %s", stats)


if __name__ == "__main__":
    asyncio.run(main())
