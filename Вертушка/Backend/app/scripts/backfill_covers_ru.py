"""Обложки постсоветского винила: Deezer → Yandex, по РЕЛИЗАМ.

Зачем отдельный канал. Дыра здесь зияющая и структурная (замер 18.08.2026):

    страна        без обложки   доля дыры
    Russia            178 879       82.6%
    USSR               74 464       97.1%
    Ukraine            30 403       80.7%
    Прибалтика         25 548       86.1%
                      -------
                      314 246

USSR практически не покрыт, потому что офлайн-канал CAA, давший нам 1.28 млн
обложек, советский винил не знает: в MusicBrainz его почти нет. UPC-канал тоже
бессилен — у «Мелодии» штрихкодов не было вовсе (87 кодов на 74 464 релиза).

ПО РЕЛИЗАМ, а не по мастерам — это главное отличие от backfill_covers.py.
141 576 из 314 246 записей (45%) вообще не имеют master_id и потому не попадали
НИ В ОДНУ очередь: весь Deezer-бэкфилл работал по `master_id IS NOT NULL`.
Остальные стоят за 78 792 мастерами, где представителем брали версию с
наименьшим годом, — метаданные конкретного советского пресса в запрос не шли.
Отсюда парадокс: Deezer в живой пробе находит 33% того, что «уже искал». Он
этого не искал.

Лестница Deezer → Yandex, замер на 200 случайных релизах этой популяции:

    бакет      n     Yandex        Deezer     только Yandex
    USSR      47   3 ( 6.4%)    3 ( 6.4%)      1 (2.1%)
    Russia   111  37 (33.3%)   37 (33.3%)      7 (6.3%)
    прочее    42   7 (16.7%)   13 (31.0%)      0
    ИТОГО    200  47 (23.5%)   53 (26.5%)      8 (4.0%)
    объединение 30.5%

Deezer первым: он вдвое быстрее (0.13 с против 0.25 с) и чуть точнее. Yandex
вторым — только для промахов Deezer, добирает 4 п.п. за счёт транслит-моста
(Discogs пишет `Kino`, Yandex отдаёт `КИНО`).

Честная граница канала: по USSR оба дают 6.4% и больше не дадут — «Мелодию» в
стриминг не переиздавали. Советский слой закрывается не отсюда.

Запуск на проде:
  docker exec -d vertushka_api_blue sh -c \
    "python -m app.scripts.backfill_covers_ru > /app/uploads/ru_covers.log 2>&1"
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import os
import time

from sqlalchemy import text

from app.database import async_session_maker
from app.services.cover_quality import is_thumb_grade
from app.services.deezer import DeezerQuotaExceeded, cover_by_meta as dz_cover
from app.services.yandex_music import YandexThrottled, cover_by_meta as ya_cover

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger("backfill_ru")

WORKLIST = "cover_backfill_ru"
MARKER = "/app/uploads/.backfill_ru_enabled"

COUNTRIES = ("USSR", "Russia", "Russia & CIS", "Ukraine",
             "Belarus", "Estonia", "Latvia", "Lithuania")

_CONCURRENCY = 3
_RUN_BUDGET = 300

# Сторож нулевого выхлопа — см. инцидент с ведущим нулём в UPC-канале
# (backfill_covers_upc._ZERO_STREAK_ABORT). Волна защищает от потери элементов,
# но не от систематически неверного запроса, выглядящего честным промахом.
# Порог выше, чем у UPC: базовый хит-рейт здесь 30%, но бакет USSR даёт 6%, и
# длинная советская серия — законный повод для промахов.
_ZERO_STREAK_ABORT = 800


async def _ensure_infra() -> None:
    async with async_session_maker() as s:
        await s.execute(text(
            f"CREATE TABLE IF NOT EXISTS {WORKLIST} ("
            "  discogs_id BIGINT PRIMARY KEY, artist TEXT, title TEXT,"
            "  year INT, country TEXT,"
            "  done BOOLEAN NOT NULL DEFAULT FALSE)"
        ))
        await s.execute(text(
            f"CREATE INDEX IF NOT EXISTS ix_{WORKLIST}_todo "
            f"ON {WORKLIST} (discogs_id) WHERE NOT done"
        ))
        await s.commit()


async def _build_worklist(rebuild: bool = False) -> int:
    async with async_session_maker() as s:
        await s.execute(text("SET statement_timeout = 900000"))
        if rebuild:
            await s.execute(text(f"TRUNCATE {WORKLIST}"))
            await s.commit()
        have = (await s.execute(text(f"SELECT count(*) FROM {WORKLIST}"))).scalar()
        if have and not rebuild:
            return int(have)
        logger.info("строю очередь по постсоветской популяции...")
        await s.execute(text(
            f"INSERT INTO {WORKLIST} (discogs_id, artist, title, year, country) "
            "SELECT discogs_id, artist, title, year, country "
            "FROM discogs_releases_index "
            "WHERE cover_image_url IS NULL AND country = ANY(:cc) "
            "  AND artist IS NOT NULL AND title IS NOT NULL "
            "ON CONFLICT (discogs_id) DO NOTHING"
        ), {"cc": list(COUNTRIES)})
        await s.commit()
        total = (await s.execute(text(f"SELECT count(*) FROM {WORKLIST}"))).scalar()
        logger.info("очередь: %d релизов", total)
        return int(total)


async def _resolve(row: dict) -> str | None:
    """Deezer, затем Yandex для его промахов. Пробрасывает троттлинг наверх."""
    artist, title, year = row["artist"], row["title"], row["year"]

    cover = await dz_cover(artist, title, year=year)
    if cover and not is_thumb_grade(cover.url):
        return cover.url

    yc = await ya_cover(artist, title, year=year)
    if yc and not is_thumb_grade(yc.url):
        return yc.url
    return None


async def _lookup_wave(rows: list[dict], budget_s: float) -> tuple[list[tuple[int, str | None]], bool]:
    """Опросить партию. Возвращает (результаты ОПРОШЕННЫХ, упёрлись_в_лимит).

    В результат попадает только реально спрошенное: дедлайн проверяется перед
    взятием следующей записи. Вызывающий метит `done` ровно по этому списку,
    поэтому незаданный вопрос не может получить вердикт «обложки нет».
    """
    queue: asyncio.Queue[dict] = asyncio.Queue()
    for r in rows:
        queue.put_nowait(r)

    done: list[tuple[int, str | None]] = []
    deadline = time.monotonic() + budget_s
    blocked = asyncio.Event()

    async def worker() -> None:
        while not blocked.is_set() and time.monotonic() < deadline:
            try:
                row = queue.get_nowait()
            except asyncio.QueueEmpty:
                return
            try:
                url = await _resolve(row)
            except (DeezerQuotaExceeded, YandexThrottled) as e:
                logger.warning("источник закрылся (%s) — прерываем волну, "
                               "%d записей вернутся в очередь", e, queue.qsize() + 1)
                blocked.set()
                return
            except Exception:
                logger.debug("resolve failed for %s", row["discogs_id"], exc_info=True)
                url = None
            done.append((row["discogs_id"], url))

    await asyncio.gather(*(worker() for _ in range(_CONCURRENCY)))
    return done, blocked.is_set()


async def _persist(results: list[tuple[int, str | None]]) -> int:
    hits = [(d, u) for d, u in results if u]
    written = 0
    async with async_session_maker() as s:
        for did, url in hits:
            res = await s.execute(text(
                "UPDATE discogs_releases_index "
                "SET cover_image_url = :u, cover_checked_at = now() "
                "WHERE discogs_id = :d AND cover_image_url IS NULL"
            ), {"u": url, "d": did})
            written += res.rowcount or 0
        await s.execute(text(
            f"UPDATE {WORKLIST} SET done = TRUE WHERE discogs_id = ANY(:ids)"
        ), {"ids": [d for d, _ in results]})
        await s.commit()
    return written


async def run(batch: int = 150, budget_s: float = _RUN_BUDGET,
              max_items: int | None = None) -> dict:
    stats = {"asked": 0, "hits": 0, "written": 0, "blocked": False, "zero_streak": False}
    started = time.monotonic()
    streak = 0

    if not await _build_worklist():
        logger.info("очередь пуста")
        return stats

    while True:
        left = budget_s - (time.monotonic() - started)
        if left <= 1:
            break
        if max_items is not None and stats["asked"] >= max_items:
            break

        async with async_session_maker() as s:
            rows = (await s.execute(text(
                f"SELECT discogs_id, artist, title, year, country FROM {WORKLIST} "
                "WHERE NOT done ORDER BY discogs_id LIMIT :b"
            ), {"b": batch})).mappings().all()
        if not rows:
            logger.info("очередь пройдена целиком")
            break

        results, blocked = await _lookup_wave([dict(r) for r in rows], left)
        if not results:
            logger.error("волна без единого ответа — прерываем проход")
            break

        stats["written"] += await _persist(results)
        stats["asked"] += len(results)
        stats["hits"] += sum(1 for _, u in results if u)

        for _, u in results:
            streak = 0 if u else streak + 1
        if streak >= _ZERO_STREAK_ABORT:
            stats["zero_streak"] = True
            logger.error("%d промахов подряд — прерываем прогон, похоже на "
                         "систематически неверный запрос", streak)
            from app.services import alerts
            alerts.fire_and_forget(
                key="cover_ru_zero_yield",
                title=f"RU-обход обложек: {streak} промахов подряд",
                body=(f"Прогон остановлен на {stats['asked']} записях, "
                      f"попаданий {stats['hits']}. Проверить формы запросов "
                      f"к Deezer и Yandex."),
            )
            break
        if blocked:
            stats["blocked"] = True
            break

        logger.info("ru covers: asked=%d hits=%d (%.1f%%) записано=%d",
                    stats["asked"], stats["hits"],
                    100 * stats["hits"] / max(stats["asked"], 1), stats["written"])

    stats["elapsed_s"] = round(time.monotonic() - started, 1)
    return stats


async def run_scheduled_batch() -> None:
    if not os.path.exists(MARKER):
        return
    await _ensure_infra()
    await run()


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--batch", type=int, default=150)
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
