"""Лечение обложек, которые были скачаны и потеряны ночной очисткой.

Признак потери однозначный: `blurhash IS NOT NULL AND cover_local_path IS NULL`.
Blurhash считается ТОЛЬКО с уже лежащего на диске файла (см. backfill_blurhash),
поэтому его наличие при отсутствии файла означает ровно одно — файл был и его
удалили.

Почему такие записи не чинятся сами. Логика self-heal редиректит на
`cover_image_url`, а у пострадавших он вёл на discogs.com: их ссылки подписаны
и протухают, редирект получает 403, и плитка остаётся размытой навсегда.

Инцидент 18.08.2026: в коллекции из 172 позиций 63 (37%) выглядели именно так.
Причина в cleanup_lru — правило отбора кандидатов чинится тем же PR, здесь
разбираем последствия.

Лечение: прогнать бесплатную лестницу источников (CAA → Deezer → iTunes), взять
стабильный URL и зеркалировать. Discogs НЕ трогаем — он и привёл к проблеме.

Запуск:
  python -m app.scripts.heal_lost_covers [--limit N] [--dry-run]
"""
from __future__ import annotations

import argparse
import asyncio
import logging

from sqlalchemy import text

from app.database import async_session_maker
from app.services.cover_demand import TRIGGER_SWEEP
from app.services.cover_quality import is_thumb_grade

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger("heal_lost")


async def _candidates(limit: int) -> list[dict]:
    """Записи с blurhash, но без файла. Библиотечные первыми — их видно людям."""
    async with async_session_maker() as s:
        rows = (await s.execute(text(
            """
            SELECT r.discogs_id, r.title, r.artist,
                   EXISTS (SELECT 1 FROM collection_items ci WHERE ci.record_id = r.id)
                OR EXISTS (SELECT 1 FROM wishlist_items wi WHERE wi.record_id = r.id)
                   AS in_library
            FROM records r
            WHERE r.blurhash IS NOT NULL
              AND r.cover_local_path IS NULL
              AND r.discogs_id ~ '^[0-9]+$'
              AND r.merged_into_id IS NULL
            ORDER BY in_library DESC, r.updated_at DESC NULLS LAST
            LIMIT :lim
            """
        ), {"lim": limit})).mappings().all()
    return [dict(r) for r in rows]


async def _meta(ids: list[str]) -> dict[str, dict]:
    """Метаданные из дамп-индекса для 2-4 ступеней лестницы."""
    if not ids:
        return {}
    async with async_session_maker() as s:
        rows = (await s.execute(text(
            "SELECT discogs_id::text AS did, barcode_norm, year, label "
            "FROM discogs_releases_index WHERE discogs_id = ANY(:ids)"
        ), {"ids": [int(i) for i in ids]})).mappings().all()
    return {r["did"]: dict(r) for r in rows}


async def heal(limit: int = 500, dry_run: bool = False) -> dict:
    from app.services.cover_storage import CoverStorageService
    from app.services.cover_warm import resolve_cover_url

    stats = {"candidates": 0, "resolved": 0, "healed": 0, "no_source": 0, "library": 0}
    rows = await _candidates(limit)
    stats["candidates"] = len(rows)
    stats["library"] = sum(1 for r in rows if r["in_library"])
    if not rows:
        logger.info("потерянных обложек нет")
        return stats

    meta = await _meta([r["discogs_id"] for r in rows])
    service = CoverStorageService()

    async with async_session_maker() as session:
        for row in rows:
            did = row["discogs_id"]
            payload = {**row, **meta.get(did, {})}
            try:
                # discogs_probe=None: их подписанные ссылки и привели к проблеме.
                url = await resolve_cover_url(session, payload, discogs_probe=None)
            except Exception:
                logger.debug("resolve failed for %s", did, exc_info=True)
                url = None

            if not url or is_thumb_grade(url):
                stats["no_source"] += 1
                continue
            stats["resolved"] += 1

            if dry_run:
                continue
            try:
                if await service.download_and_store(did, url, session, trigger=TRIGGER_SWEEP):
                    stats["healed"] += 1
            except Exception:
                logger.debug("download failed for %s", did, exc_info=True)

    logger.info("вылечено %d из %d (в библиотеках %d, источник не нашёлся у %d)",
                stats["healed"], stats["candidates"], stats["library"], stats["no_source"])
    return stats


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=500)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    logger.info("итог: %s", await heal(args.limit, args.dry_run))


if __name__ == "__main__":
    asyncio.run(main())
