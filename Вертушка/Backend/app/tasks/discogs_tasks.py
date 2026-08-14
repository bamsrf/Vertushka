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
    from app.services.pricing import PricingParams, estimate_rub

    discogs = DiscogsService()
    settings = get_settings()
    params = PricingParams.from_settings(settings)
    updated = 0

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
                .order_by(Record.estimated_price_min.asc().nullsfirst())  # без цен первыми
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
                            item.estimated_price_rub = estimate_rub(
                                float(rec.estimated_price_min),
                                rec.country,
                                usd_rub,
                                params,
                                format_type=rec.format_type,
                                format_description=rec.format_description,
                                discogs_data=rec.discogs_data,
                            )

                await session.commit()
                logger.info("Updated prices for %d records", updated)

            # Backfill: CollectionItems с NULL estimated_price_rub где Record уже имеет цену
            backfill_result = await session.execute(
                select(CollectionItem)
                .options(selectinload(CollectionItem.record))
                .join(Record, CollectionItem.record_id == Record.id)
                .where(
                    CollectionItem.estimated_price_rub.is_(None),
                    Record.estimated_price_min.isnot(None)
                )
                .limit(BATCH_SIZE)
            )
            backfill_items = backfill_result.scalars().all()
            if backfill_items:
                for item in backfill_items:
                    rec = item.record
                    if rec and rec.estimated_price_min:
                        item.estimated_price_rub = estimate_rub(
                            float(rec.estimated_price_min),
                            rec.country,
                            usd_rub,
                            params,
                            format_type=rec.format_type,
                            format_description=rec.format_description,
                            discogs_data=rec.discogs_data,
                        )
                await session.commit()
                logger.info("Backfilled estimated_price_rub for %d collection items", len(backfill_items))

    except Exception:
        logger.exception("update_prices_batch failed")


async def enrich_market_covers():
    """WS2.2 — лечит обложки записей, активно показываемых в Маркете.

    Цель: in_stock matched записи с discogs_master_id, но без локального
    зеркала (cover_local_path IS NULL) — у них cover_image_url либо пуст,
    либо протух (signed Discogs URL → 403 → серый квадрат). По каждому
    уникальному мастеру 1 вызов get_master → свежий cover_image_url →
    зеркалируем на диск (download_and_store ставит cover_local_path).

    Дедуп по master: один fetch на мастер за прогон. Батч ограничен, чтобы
    не упереться в Discogs rate limit; добивается за несколько прогонов.
    """
    from app.services.discogs import DiscogsService
    from app.services.cover_storage import CoverStorageService
    from app.models.store_listing import StoreListing

    discogs = DiscogsService()
    cover_service = CoverStorageService()
    cutoff = datetime.utcnow() - timedelta(days=7)
    master_cover_cache: dict[str, str | None] = {}
    enriched = 0

    try:
        async with async_session_maker() as session:
            active_in_stock = (
                select(StoreListing.id)
                .where(
                    StoreListing.matched_record_id == Record.id,
                    StoreListing.status == "in_stock",
                    StoreListing.last_seen_at >= cutoff,
                )
                .exists()
            )
            result = await session.execute(
                select(Record)
                .where(
                    Record.cover_local_path.is_(None),
                    Record.discogs_id.isnot(None),
                    Record.discogs_master_id.isnot(None),
                    active_in_stock,
                )
                .limit(BATCH_SIZE)
            )
            records = result.scalars().all()

            for record in records:
                master_id = record.discogs_master_id
                if master_id in master_cover_cache:
                    cover_url = master_cover_cache[master_id]
                else:
                    try:
                        master = await discogs.get_master(master_id)
                        cover_url = master.cover_image_url
                    except Exception:
                        logger.exception("enrich_market_covers: get_master %s failed", master_id)
                        cover_url = None
                    master_cover_cache[master_id] = cover_url

                if not cover_url:
                    continue

                record.cover_image_url = cover_url
                try:
                    rel_path = await cover_service.download_and_store(
                        record.discogs_id, cover_url, session
                    )
                    if rel_path:
                        enriched += 1
                except Exception:
                    logger.exception(
                        "enrich_market_covers: mirror failed for %s", record.discogs_id
                    )

            await session.commit()
            if enriched:
                logger.info("enrich_market_covers: mirrored %d covers", enriched)

    except Exception:
        logger.exception("enrich_market_covers failed")


async def refresh_market_store_stats():
    """WS4.1 — REFRESH matview market_store_stats (витрина магазинов).

    CONCURRENTLY: не блокирует читателей эндпоинта /market/stores. Требует
    уникальный индекс (ix_market_store_stats_store_id, создан в миграции).
    """
    from sqlalchemy import text

    try:
        async with async_session_maker() as db:
            await db.execute(
                text("REFRESH MATERIALIZED VIEW CONCURRENTLY market_store_stats")
            )
            await db.commit()
        logger.info("refresh_market_store_stats: matview refreshed")
    except Exception:
        logger.exception("refresh_market_store_stats failed")


async def refresh_new_releases():
    """Недельный сброс витрины новинок (гибрид свежесть×want) — по понедельникам.

    Удаляет Redis-ключ namespace `new_releases` и сразу прогревает заново с
    `warm=True`: глубокий want-пул и бюджет в сотни detail-вызовов. Это минуты
    работы — ровно поэтому они идут здесь, в шедулере, а не у первого юзера.
    Ключ совпадает с DiscogsService.search_new_releases: `hybrid_w{window}_l{limit}`.
    Приложение зовёт limit=40 с дефолтным окном.

    Раз в неделю, а не в месяц: 12 обновлений в год для рейла с подписью
    «свежие релизы» — это не витрина, а фотография.
    """
    from app.services.cache import cache
    from app.services.discogs import DiscogsService

    try:
        discogs = DiscogsService()
        window = discogs.NEW_RELEASES_WINDOW_DAYS
        await cache.delete("new_releases", f"hybrid_w{window}_l40")
        pool = await discogs.search_new_releases(limit=40, warm=True)
        logger.info("refresh_new_releases: warmed %d items (window=%dd)", len(pool), window)
    except Exception:
        logger.exception("refresh_new_releases failed")
