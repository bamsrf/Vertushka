"""
Разовый бэкфилл records.blurhash по УЖЕ зеркалированным локальным обложкам.

Читает файлы с диска (uploads/covers/...), считает blurhash тем же
_compute_blurhash, что и живой путь зеркалирования, и проставляет колонку.
Ни одного скачивания — значит мимо Discogs/CDN rate-limit. Ограничен строками
records с cover_local_path IS NOT NULL AND blurhash IS NULL (~10.9K на 2026-08).

Usage (в контейнере scheduler/api):
  python -m app.scripts.backfill_blurhash [--limit N] [--dry-run] [--concurrency 4]
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys
from pathlib import Path

from sqlalchemy import text

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from app.config import get_settings
from app.database import async_session_maker
from app.services.cover_storage import _compute_blurhash

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("backfill_blurhash")

_BATCH = 500


def _uploads_root() -> Path:
    # covers_dir = "uploads/covers" → корень uploads = его родитель.
    return Path(get_settings().covers_dir).parent


def _hash_one(uploads_root: Path, rel_path: str) -> str | None:
    """Sync: прочитать файл, декодировать, посчитать blurhash. Из threadpool."""
    from io import BytesIO

    from PIL import Image

    fpath = uploads_root / rel_path
    if not fpath.is_file():
        return None
    try:
        with open(fpath, "rb") as f:
            raw = f.read()
        img = Image.open(BytesIO(raw)).convert("RGB")
        return _compute_blurhash(img)
    except Exception:
        logger.debug("hash failed for %s", rel_path, exc_info=True)
        return None


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=None, help="Максимум строк")
    parser.add_argument("--dry-run", action="store_true", help="Считать, но не писать")
    parser.add_argument("--concurrency", type=int, default=4, help="Параллельных воркеров (CPU-bound)")
    args = parser.parse_args()

    uploads_root = _uploads_root()
    sem = asyncio.Semaphore(max(1, args.concurrency))
    done = skipped = failed = 0

    async with async_session_maker() as db:
        total = (await db.execute(text(
            "SELECT count(*) FROM records "
            "WHERE cover_local_path IS NOT NULL AND blurhash IS NULL"
        ))).scalar() or 0
    logger.info("Кандидатов на бэкфилл: %d (uploads_root=%s)", total, uploads_root)
    if not total:
        return

    processed = 0
    while True:
        async with async_session_maker() as db:
            rows = (await db.execute(text(
                "SELECT id::text AS id, cover_local_path FROM records "
                "WHERE cover_local_path IS NOT NULL AND blurhash IS NULL "
                "ORDER BY cover_cached_at DESC NULLS LAST LIMIT :lim"
            ), {"lim": _BATCH})).mappings().all()

        if not rows:
            break

        async def _work(row) -> tuple[str, str | None]:
            async with sem:
                bhash = await asyncio.to_thread(_hash_one, uploads_root, row["cover_local_path"])
                return row["id"], bhash

        results = await asyncio.gather(*[_work(r) for r in rows])

        if not args.dry_run:
            async with async_session_maker() as db:
                for rid, bhash in results:
                    if bhash:
                        await db.execute(text(
                            "UPDATE records SET blurhash = :b WHERE id = :id"
                        ), {"b": bhash, "id": rid})
                    else:
                        # Файл пропал/битый → метим пустой строкой, чтобы не
                        # перевыбирать вечно (пустая ≠ NULL для условия WHERE).
                        await db.execute(text(
                            "UPDATE records SET blurhash = '' WHERE id = :id"
                        ), {"id": rid})
                await db.commit()

        for _, bhash in results:
            if bhash:
                done += 1
            else:
                failed += 1
        processed += len(rows)
        logger.info("Прогресс: %d/%d (ok=%d, битых=%d)", processed, total, done, failed)

        if args.dry_run:
            # В dry-run строки не помечаются → тот же batch выберется снова.
            # Останавливаемся после первого прохода.
            break
        if args.limit and processed >= args.limit:
            break

    logger.info("Готово: проставлено=%d, битых/пропущено=%d", done, failed)


if __name__ == "__main__":
    asyncio.run(main())
