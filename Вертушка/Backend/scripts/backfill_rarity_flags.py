"""
Бэкфилл rarity-флагов (is_first_press / is_limited / is_hot) для существующих записей.

Для каждой записи с discogs_id:
  1. Удаляет Redis-кэш релиза (чтобы не вернулась устаревшая запись без флагов).
  2. Зовёт DiscogsService.get_release() — он сам сходит за мастером,
     посчитает все три флага и положит свежий payload в кэш.
  3. Обновляет три булевы колонки в Record.

Запуск (на проде, в контейнере api):
    docker compose -f docker-compose.prod.yml exec api \\
        python -m scripts.backfill_rarity_flags

Флаги:
    --batch-size N   Записей за одну транзакцию (default 50)
    --delay S        Секунд между запросами к Discogs (default 1.6 ≈ 37 req/min)
    --dry-run        Только посчитать записи, ничего не менять
    --limit N        Остановиться после N обработанных записей
"""
import argparse
import asyncio
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import async_session_maker, init_db, close_db
from app.models.record import Record
from app.services.discogs import DiscogsService
from app.services.cache import cache
from app.services.rate_limiter import discogs_limiter

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


async def _count_total(db: AsyncSession) -> int:
    q = select(func.count()).select_from(Record).where(Record.discogs_id.isnot(None))
    return (await db.execute(q)).scalar_one()


async def _refresh_one(discogs: DiscogsService, record: Record) -> dict | None:
    """Drop release cache and re-fetch — returns dict with three flag keys, or None on failure."""
    try:
        await cache.delete("release", record.discogs_id)
    except Exception:
        logger.exception("Cache delete failed for %s", record.discogs_id)

    try:
        data = await discogs.get_release(record.discogs_id)
        return {
            "is_first_press": bool(data.get("is_first_press")),
            "is_canon": bool(data.get("is_canon")),
            "is_limited": bool(data.get("is_limited")),
            "is_hot": bool(data.get("is_hot")),
        }
    except Exception as e:
        logger.warning("get_release failed for %s (%s): %s", record.discogs_id, record.title[:40], e)
        return None


async def run(batch_size: int, delay: float, dry_run: bool, limit: int | None) -> None:
    await init_db()

    async with async_session_maker() as db:
        total = await _count_total(db)

    effective = min(total, limit) if limit else total
    logger.info(
        "Записей для обработки: %d%s%s",
        effective,
        f" (из {total})" if limit and limit < total else "",
        " [DRY RUN]" if dry_run else "",
    )

    if dry_run or effective == 0:
        await close_db()
        return

    # Лимитер обычно стартует в FastAPI lifespan — в скрипте надо стартануть руками
    discogs_limiter.start()
    discogs = DiscogsService()

    processed = 0
    failed = 0
    counts = {"first_press": 0, "canon": 0, "limited": 0, "hot": 0}

    offset = 0
    while True:
        async with async_session_maker() as db:
            q = (
                select(Record)
                .where(Record.discogs_id.isnot(None))
                .order_by(Record.created_at)
                .offset(offset)
                .limit(batch_size)
            )
            result = await db.execute(q)
            records = result.scalars().all()

            if not records:
                break

            for record in records:
                if limit and processed >= limit:
                    break

                flags = await _refresh_one(discogs, record)
                processed += 1

                if flags is None:
                    failed += 1
                    await asyncio.sleep(delay)
                    continue

                record.is_first_press = flags["is_first_press"]
                record.is_canon = flags["is_canon"]
                record.is_limited = flags["is_limited"]
                record.is_hot = flags["is_hot"]

                tags = []
                if flags["is_first_press"]:
                    tags.append("1ST")
                    counts["first_press"] += 1
                if flags["is_canon"]:
                    tags.append("CAN")
                    counts["canon"] += 1
                if flags["is_limited"]:
                    tags.append("LIM")
                    counts["limited"] += 1
                if flags["is_hot"]:
                    tags.append("HOT")
                    counts["hot"] += 1
                tag_str = " ".join(tags) if tags else "—"

                logger.info(
                    "[%d/%d] %s · %s → %s",
                    processed, effective,
                    record.discogs_id,
                    f"{record.artist} — {record.title}"[:55],
                    tag_str,
                )

                await asyncio.sleep(delay)

            await db.commit()
            logger.info(
                "Батч сохранён. %d processed · %d 1st · %d canon · %d lim · %d hot · %d failed",
                processed, counts["first_press"], counts["canon"], counts["limited"], counts["hot"], failed,
            )

            if limit and processed >= limit:
                break

            offset += batch_size

    logger.info(
        "Готово. Всего: %d | 1-й пресс: %d | Канон: %d | Лимитка: %d | Популярно: %d | Ошибок: %d",
        processed, counts["first_press"], counts["canon"], counts["limited"], counts["hot"], failed,
    )
    discogs_limiter.stop()
    await close_db()


def main() -> None:
    parser = argparse.ArgumentParser(description="Бэкфилл rarity-флагов из Discogs")
    parser.add_argument("--batch-size", type=int, default=50)
    parser.add_argument("--delay", type=float, default=1.6,
                        help="Секунд между запросами (default 1.6 = ~37 req/min)")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()

    asyncio.run(run(
        batch_size=args.batch_size,
        delay=args.delay,
        dry_run=args.dry_run,
        limit=args.limit,
    ))


if __name__ == "__main__":
    main()
