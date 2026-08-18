"""Возврат обложек конкретного пресса после ошибочной подмены.

ЧТО ПРОИЗОШЛО (18.08.2026). Ночная очистка удалила зеркала обложек из коллекций
(починено отдельно). Лечилка последствий `heal_lost_covers` пыталась вернуть их
через ОБЩУЮ лестницу источников — и подменила сканы конкретных прессов на
album-level арт стриминга. Пострадало 119 пластинок: у Tatsuro Yamashita вместо
японского конверта с оби приехал CAA, у Baile и Ryo Fukui — Deezer 1000×1000.

ОШИБКА В РАССУЖДЕНИИ была не в коде, а в выборе инструмента. Лестница создана
искать обложку там, где её НЕТ: тогда любой приличный арт — выигрыш. Здесь
обложка БЫЛА, и точный ответ всё время лежал в `records.cover_image_url` —
ссылка на скан нужного пресса. Ей не хватало только свежей подписи.

КАК ВОЗВРАЩАЕМ. Источник берём из самой записи, а не угадываем:

  - адрес ведёт на discogs.com → подпись протухла, просим у API свежую по
    ЭТОМУ ЖЕ release_id. Вернётся скан того же пресса. Кэш перед запросом
    сбрасываем: в нём лежит payload с уже мёртвой подписью.
  - адрес ведёт на магазин или CAA → он стабильный, качаем прямо с него.

Discogs здесь уместен, хотя в целом мы от него уходим: их лимит 60 запросов в
минуту, а речь о сотне пластинок в чьей-то коллекции — это две минуты. Уход от
зависимости имеет смысл для 13 млн каталога, а не для точечного восстановления.

Список пострадавших зафиксирован в таблице `cover_heal_rollback` СРАЗУ после
инцидента — чтобы набор не поплыл, пока фоновые джобы трогают те же поля.

Usage:
  python -m app.scripts.restore_pressing_covers [--limit N] [--dry-run]
"""
from __future__ import annotations

import argparse
import asyncio
import logging
from pathlib import Path

from sqlalchemy import text

from app.database import async_session_maker

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger("restore_covers")

TABLE = "cover_heal_rollback"


async def _pending(limit: int) -> list[dict]:
    async with async_session_maker() as s:
        rows = (await s.execute(text(
            f"SELECT discogs_id, bad_path, orig_discogs_url FROM {TABLE} "
            "WHERE NOT restored ORDER BY discogs_id LIMIT :lim"
        ), {"lim": limit})).mappings().all()
    return [dict(r) for r in rows]


async def _fresh_url(discogs_id: str, orig: str) -> str | None:
    """Рабочая ссылка на обложку ИМЕННО этого пресса."""
    if "discogs.com" not in (orig or ""):
        # Магазин или CAA — ссылки стабильные, годятся как есть.
        return orig

    from app.services.cache import cache
    from app.services.discogs import DiscogsService

    # Сбрасываем кэш: там лежит payload с протухшей подписью, и без этого
    # get_release_cover честно вернёт ту же мёртвую ссылку.
    for ns in ("release", "release_cover"):
        try:
            await cache.delete(ns, discogs_id)
        except Exception:
            pass
    try:
        return await DiscogsService().get_release_cover(discogs_id)
    except Exception:
        logger.debug("discogs cover fetch failed for %s", discogs_id, exc_info=True)
        return None


async def restore(limit: int = 500, dry_run: bool = False) -> dict:
    from app.services.cover_storage import CoverStorageService

    stats = {"pending": 0, "restored": 0, "no_url": 0, "download_failed": 0}
    rows = await _pending(limit)
    stats["pending"] = len(rows)
    if not rows:
        logger.info("возвращать нечего")
        return stats

    service = CoverStorageService()
    async with async_session_maker() as session:
        for row in rows:
            did, bad_path = row["discogs_id"], row["bad_path"]
            url = await _fresh_url(did, row["orig_discogs_url"])
            if not url:
                stats["no_url"] += 1
                logger.warning("%s: свежая ссылка не получена — оставляем как есть", did)
                continue
            if dry_run:
                logger.info("%s → %s", did, url[:70])
                continue

            # Старый файл убираем во ВРЕМЕННОЕ имя, а не удаляем: если новая
            # обложка не встанет, надо вернуть то, что было. В первом прогоне
            # этого не было — 4 пластинки со сканом мельче MASTER_MIN_SIDE
            # (224-494px) остались вообще без файла: гейт тира отверг скан, а
            # прежний уже был стёрт.
            old_file = Path("uploads", bad_path) if bad_path else None
            stash = old_file.with_suffix(old_file.suffix + ".rollback") if old_file else None
            if old_file and old_file.exists():
                old_file.replace(stash)

            await session.execute(text(
                "UPDATE records SET cover_local_path = NULL, cover_cached_at = NULL, "
                "cover_min_side = NULL, cover_image_url = :u WHERE discogs_id = :d"
            ), {"u": url, "d": did})
            await session.commit()

            try:
                ok = await service.download_and_store(did, url, session)
            except Exception:
                ok = None
                logger.debug("download failed for %s", did, exc_info=True)

            if not ok:
                # Не встало — возвращаем прежнее состояние целиком. Пусть обложка
                # неправильная, но она лучше пустого места, а `cover_image_url`
                # теперь верный: отдача пойдёт редиректом на нужный скан.
                stats["download_failed"] += 1
                if stash and stash.exists():
                    stash.replace(old_file)
                    await session.execute(text(
                        "UPDATE records SET cover_local_path = :p WHERE discogs_id = :d"
                    ), {"p": bad_path, "d": did})
                    await session.commit()
                    logger.warning("%s: новая обложка не встала — вернул прежний файл", did)
                continue

            if stash and stash.exists():
                stash.unlink(missing_ok=True)

            await session.execute(text(
                f"UPDATE {TABLE} SET restored = true WHERE discogs_id = :d"), {"d": did})
            await session.commit()
            stats["restored"] += 1
            if stats["restored"] % 20 == 0:
                logger.info("возвращено %d из %d", stats["restored"], len(rows))

    logger.info("итог: %s", stats)
    return stats


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=500)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    await restore(args.limit, args.dry_run)


if __name__ == "__main__":
    asyncio.run(main())
