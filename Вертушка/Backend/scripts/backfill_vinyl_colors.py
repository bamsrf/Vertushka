"""
Бэкфилл vinyl_color_raw для существующих записей.

Читает discogs_data из БД, проверяет есть ли там vinyl_color_raw.
Если нет — запрашивает Discogs API, добирает formats[0].text,
и обновляет discogs_data в БД без новых колонок и миграций.

Запуск:
    cd Вертушка/Backend
    python -m scripts.backfill_vinyl_colors

Флаги:
    --batch-size N   Записей за одну транзакцию (по умолчанию 50)
    --delay S        Секунд между запросами к Discogs (по умолчанию 1.6)
    --dry-run        Только посчитать записи, ничего не менять
    --limit N        Остановиться после N обработанных записей
    --force          Перезаписать даже те, где vinyl_color_raw уже есть
"""
import argparse
import asyncio
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import httpx
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database import async_session_maker, init_db, close_db
from app.models.record import Record

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

settings = get_settings()


def _make_headers() -> dict:
    headers = {"User-Agent": settings.discogs_user_agent}
    if settings.discogs_token:
        headers["Authorization"] = f"Discogs token={settings.discogs_token}"
    elif settings.discogs_api_key:
        headers["Authorization"] = (
            f"Discogs key={settings.discogs_api_key}, secret={settings.discogs_api_secret}"
        )
    return headers


async def _fetch_vinyl_color(client: httpx.AsyncClient, discogs_id: str) -> str | None:
    """Один запрос к Discogs /releases/{id} — возвращает formats[0].text или None."""
    url = f"https://api.discogs.com/releases/{discogs_id}"
    for attempt in range(3):
        try:
            resp = await client.get(url, headers=_make_headers(), timeout=20.0)
            if resp.status_code == 429:
                retry_after = int(resp.headers.get("Retry-After", "5"))
                logger.warning("429 rate limit — ждём %ds", retry_after)
                await asyncio.sleep(retry_after)
                continue
            if resp.status_code == 404:
                return None
            resp.raise_for_status()
            data = resp.json()
            formats = data.get("formats", [])
            if formats:
                return formats[0].get("text")  # может быть None — это нормально
            return None
        except (httpx.TimeoutException, httpx.NetworkError) as e:
            logger.warning("Попытка %d: сетевая ошибка для %s: %s", attempt + 1, discogs_id, e)
            await asyncio.sleep(3)
    return None


async def _count_pending(db: AsyncSession, force: bool) -> int:
    q = select(func.count()).select_from(Record).where(Record.discogs_id.isnot(None))
    if not force:
        # Пропускаем те, у кого ключ уже есть в discogs_data (даже если значение None)
        q = q.where(
            (Record.discogs_data.is_(None))
            | (~Record.discogs_data.has_key("vinyl_color_raw"))  # noqa: W601
        )
    result = await db.execute(q)
    return result.scalar_one()


async def run(batch_size: int, delay: float, dry_run: bool, limit: int | None, force: bool) -> None:
    await init_db()

    async with async_session_maker() as db:
        total = await _count_pending(db, force)

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

    processed = 0
    updated = 0
    skipped = 0

    async with httpx.AsyncClient() as client:
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
                if not force:
                    q = q.where(
                        (Record.discogs_data.is_(None))
                        | (~Record.discogs_data.has_key("vinyl_color_raw"))  # noqa: W601
                    )

                result = await db.execute(q)
                records = result.scalars().all()

                if not records:
                    break

                for record in records:
                    if limit and processed >= limit:
                        break

                    color = await _fetch_vinyl_color(client, record.discogs_id)

                    existing = record.discogs_data or {}
                    if "vinyl_color_raw" in existing and not force:
                        skipped += 1
                        processed += 1
                        continue

                    record.discogs_data = {**existing, "vinyl_color_raw": color}
                    processed += 1
                    if color is not None:
                        updated += 1
                        logger.info(
                            "[%d/%d] %s — %s → \"%s\"",
                            processed, effective,
                            record.discogs_id,
                            f"{record.artist} - {record.title}"[:50],
                            color,
                        )
                    else:
                        logger.debug(
                            "[%d/%d] %s — %s → нет цвета",
                            processed, effective,
                            record.discogs_id,
                            f"{record.artist} - {record.title}"[:50],
                        )

                    await asyncio.sleep(delay)

                await db.commit()
                logger.info("Батч сохранён. Итого: %d обработано, %d с цветом", processed, updated)

                if limit and processed >= limit:
                    break

                offset += batch_size

    logger.info(
        "Готово. Всего: %d | С цветом: %d | Без цвета (null): %d | Пропущено: %d",
        processed, updated, processed - updated - skipped, skipped,
    )
    await close_db()


def main() -> None:
    parser = argparse.ArgumentParser(description="Бэкфилл vinyl_color_raw из Discogs")
    parser.add_argument("--batch-size", type=int, default=50)
    parser.add_argument("--delay", type=float, default=1.6,
                        help="Секунд между запросами (default 1.6 = ~37 req/min)")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--force", action="store_true",
                        help="Перезаписать записи где vinyl_color_raw уже стоит")
    args = parser.parse_args()

    asyncio.run(run(
        batch_size=args.batch_size,
        delay=args.delay,
        dry_run=args.dry_run,
        limit=args.limit,
        force=args.force,
    ))


if __name__ == "__main__":
    main()
