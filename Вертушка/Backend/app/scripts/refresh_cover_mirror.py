"""Точечный возврат обложки пресса из `records.cover_image_url` для заданных id.

Для чего. Матчинг по метаданным (Deezer / iTunes) до 12.09.2026 принимал
подстроку названия и подменял зеркала чужими альбомами: «SVN» → «SVN Session
#3», «Flower of Devotion» → «… Remixed». Гейт ужесточён (deezer.titles_match),
но уже лежащие на диске и в S3 файлы сами не вылечатся: `download_and_store`
не перезаписывает мастер ≥ MASTER_MIN_SIDE, а подмены как раз 1000×1000.

Что делает для каждого discogs_id:
  1. берёт `records.cover_image_url` — ссылку на скан ИМЕННО этого пресса
     (Discogs-подпись освежает через API, как restore_pressing_covers);
  2. убирает старый файл во временное имя, обнуляет cover_local_path /
     cover_min_side, качает заново — файл попадает в S3 через _encode_and_place;
  3. если в `discogs_releases_index.cover_image_url` сидит стриминговый URL
     (dzcdn / mzstatic) — обнуляет его, иначе ручка /covers/{id}.jpg после
     эвикции снова притащит чужую картинку;
  4. не встало — возвращает прежний файл, чтобы не оставить пустое место.

Usage:
  python -m app.scripts.refresh_cover_mirror 19674628 32246619 [--dry-run]
"""
from __future__ import annotations

import argparse
import asyncio
import logging
from pathlib import Path

from sqlalchemy import text

from app.database import async_session_maker
from app.scripts.restore_pressing_covers import _fresh_url

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger("refresh_cover_mirror")

_STREAMING_HOSTS = ("dzcdn.net", "mzstatic.com")


async def refresh(ids: list[str], dry_run: bool = False) -> dict:
    from app.services.cover_storage import CoverStorageService

    stats = {"asked": len(ids), "refreshed": 0, "no_record": 0, "no_url": 0, "failed": 0}
    service = CoverStorageService()
    async with async_session_maker() as s:
        for did in ids:
            row = (await s.execute(text(
                "SELECT cover_image_url, cover_local_path FROM records WHERE discogs_id = :d"
            ), {"d": did})).mappings().first()
            if row is None:
                stats["no_record"] += 1
                logger.warning("%s: записи нет", did)
                continue
            url = await _fresh_url(did, row["cover_image_url"])
            if not url:
                stats["no_url"] += 1
                logger.warning("%s: свежая ссылка не получена", did)
                continue
            if dry_run:
                logger.info("%s → %s", did, url[:80])
                continue

            old = Path("uploads", row["cover_local_path"]) if row["cover_local_path"] else None
            stash = old.with_suffix(old.suffix + ".rollback") if old else None
            if old and old.exists():
                old.replace(stash)
            await s.execute(text(
                "UPDATE records SET cover_local_path = NULL, cover_cached_at = NULL, "
                "cover_min_side = NULL, cover_image_url = :u WHERE discogs_id = :d"
            ), {"u": url, "d": did})
            if did.isdigit():
                await s.execute(text(
                    "UPDATE discogs_releases_index SET cover_image_url = NULL "
                    "WHERE discogs_id = :d AND (" + " OR ".join(
                        f"cover_image_url LIKE '%{h}%'" for h in _STREAMING_HOSTS
                    ) + ")"
                ), {"d": int(did)})
            await s.commit()

            try:
                ok = await service.download_and_store(did, url, s)
            except Exception:
                ok = None
                logger.debug("download failed for %s", did, exc_info=True)
            if not ok:
                stats["failed"] += 1
                if stash and stash.exists():
                    stash.replace(old)
                    await s.execute(text(
                        "UPDATE records SET cover_local_path = :p WHERE discogs_id = :d"
                    ), {"p": row["cover_local_path"], "d": did})
                    await s.commit()
                logger.warning("%s: новая обложка не встала — вернул прежний файл", did)
                continue
            if stash and stash.exists():
                stash.unlink(missing_ok=True)
            stats["refreshed"] += 1
            logger.info("%s: обложка возвращена из %s", did, url[:80])

    logger.info("итог: %s", stats)
    return stats


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("ids", nargs="+")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    await refresh(args.ids, args.dry_run)


if __name__ == "__main__":
    asyncio.run(main())
