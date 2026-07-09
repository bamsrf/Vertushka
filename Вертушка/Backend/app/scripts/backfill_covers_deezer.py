"""Проактивный bulk-backfill URL обложек хвоста дампа через Deezer.

Цель: закрыть непокрытые мастера и release-only синглы, у которых нет обложки
ни в индексе, ни в master_covers. Пишем ТОЛЬКО URL (cover_xl) — картинки
материализуются на диск лениво при просмотре (mirror-on-view), поэтому БД
растёт лишь на строки-URL (≤1GB на весь хвост), а не на терабайты изображений.

Deezer — единственный bulk-источник (iTunes 20/min не тянет 7M и остаётся
ленивым на просмотре). Матч через app.services.deezer.cover_by_meta с
нормализацией метаданных.

Resumable: мастера — worklist-таблица с done-флагом; release-only — checkpoint
по discogs_id. Kill/restart безопасен (идемпотентно). Rate-limit: глобальный
throttle Deezer (~7.7/s) × пул воркеров с перекрытием латентности.

Запуск на проде (фоном, переживает разрыв ssh):
  docker compose -f docker-compose.prod.yml exec -T -d api \
    python -m app.scripts.backfill_covers_deezer --kind both \
    >/app/uploads/backfill_covers.log 2>&1

Прогресс: tail -f uploads/backfill_covers.log
"""
import argparse
import asyncio
import logging
import time

from sqlalchemy import text

from app.database import async_session_maker
from app.services.deezer import cover_by_meta

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
# httpx логирует КАЖДЫЙ запрос INFO-строкой — за многодневный прогон 7M
# запросов = ~1.4GB лога, забьёт uploads-volume. Оставляем только наши
# per-batch summary-строки.
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logger = logging.getLogger("backfill_covers")

_WORKLIST_DDL = """
CREATE TABLE IF NOT EXISTS cover_backfill_masters (
    master_id BIGINT PRIMARY KEY,
    artist    TEXT,
    title     TEXT,
    year      INT,
    done      BOOLEAN NOT NULL DEFAULT FALSE
);
CREATE INDEX IF NOT EXISTS ix_cbm_todo ON cover_backfill_masters (master_id) WHERE NOT done;

CREATE TABLE IF NOT EXISTS cover_backfill_progress (
    kind       TEXT PRIMARY KEY,
    last_id    BIGINT NOT NULL DEFAULT 0,
    seen       BIGINT NOT NULL DEFAULT 0,
    covered    BIGINT NOT NULL DEFAULT 0,
    updated_at TIMESTAMP NOT NULL DEFAULT now()
);
"""

# Пул воркеров: перекрывает сетевую латентность Deezer. Глобальный throttle в
# app.services.deezer сериализует запросы (~7.7/s) — потолок держится им, пул
# лишь не даёт латентности простаивать.
_CONCURRENCY = 6


async def _ensure_infra() -> None:
    async with async_session_maker() as s:
        for stmt in _WORKLIST_DDL.strip().split(";\n"):
            if stmt.strip():
                await s.execute(text(stmt))
        await s.commit()


async def _build_masters_worklist(rebuild: bool = False) -> int:
    async with async_session_maker() as s:
        if rebuild:
            await s.execute(text("TRUNCATE cover_backfill_masters"))
            await s.commit()
        have = (await s.execute(text("SELECT count(*) FROM cover_backfill_masters"))).scalar()
        if have and not rebuild:
            return int(have)
        logger.info("building masters worklist (heavy agg, ~30s)...")
        # Представитель artist/title — из версии с наименьшим годом (обычно
        # оригинальное издание). HAVING bool_and — только мастера, где ВСЕ версии
        # без обложки. Уже покрытые в master_covers исключаем анти-джойном.
        await s.execute(text(
            "INSERT INTO cover_backfill_masters (master_id, artist, title, year) "
            "SELECT i.master_id, "
            "       (array_agg(i.artist ORDER BY i.year NULLS LAST))[1], "
            "       (array_agg(i.title  ORDER BY i.year NULLS LAST))[1], "
            "       min(i.year) "
            "FROM discogs_releases_index i "
            "WHERE i.master_id IS NOT NULL AND i.master_id <> 0 "
            "GROUP BY i.master_id "
            "HAVING bool_and(i.cover_image_url IS NULL) "
            "ON CONFLICT (master_id) DO NOTHING"
        ))
        await s.commit()
        await s.execute(text(
            "DELETE FROM cover_backfill_masters w "
            "USING discogs_master_covers mc WHERE mc.master_id = w.master_id"
        ))
        await s.commit()
        total = (await s.execute(text("SELECT count(*) FROM cover_backfill_masters"))).scalar()
        logger.info("masters worklist: %d rows", total)
        return int(total)


# Watchdog батча: одиночный зависший Deezer-вызов (несмотря на httpx timeout)
# морозил весь прогон на часы (инцидент 07-08: 34ч тишины). Батч дольше этого →
# считаем непокрытым и идём дальше (self-heal, не хэнг и не бесконечный цикл).
_BATCH_TIMEOUT = 240


async def _gather_batch(items: list[dict], sem: asyncio.Semaphore) -> list[dict]:
    try:
        return await asyncio.wait_for(
            asyncio.gather(*(_lookup(it, sem) for it in items)),
            timeout=_BATCH_TIMEOUT,
        )
    except asyncio.TimeoutError:
        logger.warning("batch timeout (%ds) — помечаем miss, продолжаем", _BATCH_TIMEOUT)
        for it in items:
            it.setdefault("cover", None)
        return items


async def _lookup(item: dict, sem: asyncio.Semaphore) -> dict:
    """Один Deezer-матч под семафором. Возвращает item + cover(dict|None)."""
    async with sem:
        try:
            dz = await cover_by_meta(item["artist"], item["title"], year=item.get("year"))
        except Exception:
            dz = None
        item["cover"] = dz
        return item


async def _run_masters(batch: int, max_requests: int | None) -> None:
    total = await _build_masters_worklist()
    if not total:
        logger.info("masters worklist empty — nothing to do")
        return
    sem = asyncio.Semaphore(_CONCURRENCY)
    seen = covered = 0
    t0 = time.monotonic()

    while True:
        if max_requests is not None and seen >= max_requests:
            break
        async with async_session_maker() as s:
            rows = (await s.execute(text(
                "SELECT master_id, artist, title, year FROM cover_backfill_masters "
                "WHERE NOT done ORDER BY master_id LIMIT :b"
            ), {"b": batch})).mappings().all()
        if not rows:
            break

        items = [dict(r) for r in rows]
        results = await _gather_batch(items, sem)

        hits = [r for r in results if r["cover"]]
        done_ids = [r["master_id"] for r in results]
        seen += len(results)
        covered += len(hits)

        async with async_session_maker() as s:
            if hits:
                await s.execute(text(
                    "INSERT INTO discogs_master_covers "
                    "(master_id, cover_image_url, source, deezer_album_id, image_md5) "
                    "SELECT * FROM unnest("
                    "  CAST(:ids AS bigint[]), CAST(:urls AS text[]), "
                    "  CAST(:src AS text[]), CAST(:dz AS bigint[]), CAST(:md5 AS text[])) "
                    "ON CONFLICT (master_id) DO NOTHING"
                ), {
                    "ids": [h["master_id"] for h in hits],
                    "urls": [h["cover"].url for h in hits],
                    "src": ["deezer"] * len(hits),
                    "dz": [h["cover"].album_id for h in hits],
                    "md5": [h["cover"].md5_image for h in hits],
                })
            await s.execute(text(
                "UPDATE cover_backfill_masters SET done = TRUE WHERE master_id = ANY(:ids)"
            ), {"ids": done_ids})
            await s.execute(text(
                "INSERT INTO cover_backfill_progress (kind, seen, covered, updated_at) "
                "VALUES ('masters', :seen, :cov, now()) "
                "ON CONFLICT (kind) DO UPDATE SET seen = :seen, covered = :cov, updated_at = now()"
            ), {"seen": seen, "cov": covered})
            await s.commit()

        rate = seen / max(time.monotonic() - t0, 1e-9)
        logger.info(
            "masters: seen=%d covered=%d (%.0f%%) rate=%.1f/s",
            seen, covered, 100 * covered / max(seen, 1), rate,
        )


async def _run_releases(batch: int, max_requests: int | None) -> None:
    async with async_session_maker() as s:
        row = (await s.execute(text(
            "SELECT last_id, seen, covered FROM cover_backfill_progress WHERE kind='releases'"
        ))).first()
        last_id = row.last_id if row else 0
        seen = row.seen if row else 0
        covered = row.covered if row else 0
    sem = asyncio.Semaphore(_CONCURRENCY)
    t0 = time.monotonic()

    while True:
        if max_requests is not None and seen >= max_requests:
            break
        async with async_session_maker() as s:
            rows = (await s.execute(text(
                "SELECT discogs_id, artist, title, year FROM discogs_releases_index "
                "WHERE (master_id IS NULL OR master_id = 0) AND cover_image_url IS NULL "
                "AND discogs_id > :last ORDER BY discogs_id LIMIT :b"
            ), {"last": last_id, "b": batch})).mappings().all()
        if not rows:
            break

        items = [dict(r) for r in rows]
        results = await _gather_batch(items, sem)
        hits = [r for r in results if r["cover"]]
        seen += len(results)
        covered += len(hits)
        last_id = max(r["discogs_id"] for r in results)  # checkpoint по id — мимо промахов

        async with async_session_maker() as s:
            if hits:
                await s.execute(text(
                    "UPDATE discogs_releases_index d SET cover_image_url = v.url "
                    "FROM (SELECT unnest(CAST(:ids AS bigint[])) AS did, "
                    "             unnest(CAST(:urls AS text[])) AS url) v "
                    "WHERE d.discogs_id = v.did AND d.cover_image_url IS NULL"
                ), {
                    "ids": [h["discogs_id"] for h in hits],
                    "urls": [h["cover"].url for h in hits],
                })
            await s.execute(text(
                "INSERT INTO cover_backfill_progress (kind, last_id, seen, covered, updated_at) "
                "VALUES ('releases', :last, :seen, :cov, now()) "
                "ON CONFLICT (kind) DO UPDATE SET last_id=:last, seen=:seen, covered=:cov, updated_at=now()"
            ), {"last": last_id, "seen": seen, "cov": covered})
            await s.commit()

        rate = seen / max(time.monotonic() - t0, 1e-9)
        logger.info(
            "releases: last_id=%d seen=%d covered=%d (%.0f%%) rate=%.1f/s",
            last_id, seen, covered, 100 * covered / max(seen, 1), rate,
        )


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--kind", choices=["masters", "releases", "both"], default="both")
    ap.add_argument("--batch", type=int, default=300)
    ap.add_argument("--max-requests", type=int, default=None,
                    help="Остановиться после N матчей (для теста)")
    ap.add_argument("--rebuild-worklist", action="store_true")
    args = ap.parse_args()

    await _ensure_infra()
    if args.rebuild_worklist:
        await _build_masters_worklist(rebuild=True)

    if args.kind in ("masters", "both"):
        await _run_masters(args.batch, args.max_requests)
    if args.kind in ("releases", "both"):
        await _run_releases(args.batch, args.max_requests)

    logger.info("backfill done")


if __name__ == "__main__":
    asyncio.run(main())
