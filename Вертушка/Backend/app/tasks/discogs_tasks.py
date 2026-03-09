"""
Фоновые задачи для Discogs: очистка search_cache, обогащение артистов, обновление цен.
Запускаются через APScheduler в main.py.
"""
import asyncio
import logging
from datetime import datetime, timedelta

from sqlalchemy import select, func
from sqlalchemy.orm import selectinload

from app.database import async_session_maker
from app.models.record import Record
from app.models.collection import CollectionItem
from app.services.search_cache_db import cleanup_expired_search_cache
from app.config import get_settings

logger = logging.getLogger(__name__)

BATCH_SIZE = 50
BATCH_PAUSE_SECONDS = 60


async def cleanup_search_cache():
    """Периодическая очистка expired записей search_cache."""
    deleted = await cleanup_expired_search_cache()
    logger.info("search_cache cleanup: deleted %d entries", deleted)


async def enrich_records_artist_data():
    """Обогащение записей без artist_thumb_image_url.
    Работает батчами по 50 записей, пауза между батчами 60 сек.
    """
    from app.services.discogs import DiscogsService

    discogs = DiscogsService()
    enriched = 0

    try:
        async with async_session_maker() as session:
            # Записи в коллекциях без artist_thumb, у которых есть discogs_id
            result = await session.execute(
                select(Record)
                .join(CollectionItem, CollectionItem.record_id == Record.id)
                .where(
                    Record.discogs_id.isnot(None),
                )
                .distinct()
                .limit(BATCH_SIZE)
            )
            records = result.scalars().all()

            for record in records:
                discogs_data = record.discogs_data or {}
                if discogs_data.get("artist_thumb_image_url"):
                    continue

                artist_id = discogs_data.get("artist_id")

                if not artist_id and record.discogs_id:
                    try:
                        release_raw = await discogs._get(
                            f"{discogs.BASE_URL}/releases/{record.discogs_id}"
                        )
                        artists = release_raw.get("artists", [])
                        if artists:
                            artist_id = str(artists[0].get("id"))
                    except Exception:
                        logger.exception("enrich: failed to fetch artist_id for %s", record.discogs_id)
                        continue

                if not artist_id:
                    continue

                try:
                    artist_thumb = await discogs._get_artist_thumb(artist_id)
                    if artist_thumb:
                        updated_data = {**discogs_data, "artist_id": artist_id, "artist_thumb_image_url": artist_thumb}
                        record.discogs_data = updated_data
                        enriched += 1
                except Exception:
                    logger.exception("enrich: failed to get thumb for artist %s", artist_id)
                    continue

            if enriched:
                await session.commit()
                logger.info("Enriched %d records with artist data", enriched)

    except Exception:
        logger.exception("enrich_records_artist_data failed")


async def update_prices_batch():
    """Фоновое обновление цен для записей в активных коллекциях.
    Приоритет: записи без цен -> записи с ценами старше 7 дней.
    Обрабатывает батч из 50 записей за запуск.
    """
    from app.services.discogs import DiscogsService
    from app.services.exchange import get_usd_rub_rate

    discogs = DiscogsService()
    settings = get_settings()
    updated = 0

    _LOCAL_COUNTRIES = {'Russia', 'USSR', 'Россия', 'СССР'}

    try:
        usd_rub = await get_usd_rub_rate()
    except Exception:
        logger.exception("update_prices: failed to get exchange rate")
        return

    try:
        async with async_session_maker() as session:
            # Записи в коллекциях без цен или с устаревшими ценами (updated > 7 дней)
            stale_cutoff = datetime.utcnow() - timedelta(days=7)

            result = await session.execute(
                select(Record)
                .join(CollectionItem, CollectionItem.record_id == Record.id)
                .where(Record.discogs_id.isnot(None))
                .where(
                    (Record.estimated_price_min.is_(None)) |
                    (Record.updated_at < stale_cutoff)
                )
                .distinct()
                .order_by(Record.estimated_price_min.is_(None).desc())  # без цен первыми
                .limit(BATCH_SIZE)
            )
            records = result.scalars().all()

            for record in records:
                try:
                    stats = await discogs._get_price_stats(record.discogs_id)
                    if stats:
                        lowest = stats.get("lowest_price", {}).get("value") if isinstance(stats.get("lowest_price"), dict) else stats.get("lowest_price")
                        median = stats.get("median_price", {}).get("value") if isinstance(stats.get("median_price"), dict) else stats.get("median_price")
                        highest = stats.get("highest_price", {}).get("value") if isinstance(stats.get("highest_price"), dict) else stats.get("highest_price")
                        if lowest or median:
                            record.estimated_price_min = lowest
                            record.estimated_price_median = median
                            record.estimated_price_max = highest
                            record.price_currency = "USD"
                            updated += 1
                except Exception:
                    logger.exception("update_prices: failed for record %s", record.discogs_id)
                    continue

            # Пересчитываем рубли для обновлённых записей
            if updated:
                # Получаем CollectionItems для обновлённых записей
                record_ids = [r.id for r in records if r.estimated_price_min]
                if record_ids:
                    items_result = await session.execute(
                        select(CollectionItem)
                        .options(selectinload(CollectionItem.record))
                        .where(CollectionItem.record_id.in_(record_ids))
                    )
                    items = items_result.scalars().all()
                    for item in items:
                        rec = item.record
                        if rec and rec.estimated_price_min:
                            is_local = rec.country and rec.country in _LOCAL_COUNTRIES
                            effective_markup = 1.0 if is_local else settings.ru_vinyl_markup
                            item.estimated_price_rub = round(
                                float(rec.estimated_price_min) * usd_rub * effective_markup, 2
                            )

                await session.commit()
                logger.info("Updated prices for %d records", updated)

    except Exception:
        logger.exception("update_prices_batch failed")
