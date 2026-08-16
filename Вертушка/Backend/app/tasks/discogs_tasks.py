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

BATCH_PAUSE_SECONDS = 60

# Раньше все задачи этого модуля делили одну константу BATCH_SIZE = 50. Ценам
# этого мало (см. _price_batch_size), а обложкам и артистам — ровно столько,
# сколько нужно: у них свой профиль нагрузки (детальные вызовы + скачивание
# картинок), и разгонять их заодно с ценами нечего.
ARTIST_ENRICH_BATCH = 50
MARKET_COVER_BATCH = 50


def _price_batch_size() -> int:
    """Потолок записей за один проход ценовой задачи. Читается на каждом
    прогоне, а не при импорте модуля: PRICE_BATCH_SIZE меняется через env без
    пересборки образа."""
    return get_settings().price_batch_size


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
                .limit(ARTIST_ENRICH_BATCH)
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
    Размер батча — PRICE_BATCH_SIZE (по умолчанию 200), запуск раз в 30 минут.

    Это «широкая» задача под общим app-токеном: она держит в тонусе всю базу.
    Свежеимпортированную коллекцию конкретного юзера разгребает не она, а
    run_price_backfill_jobs — под личным токеном и сразу.
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
                .limit(_price_batch_size())
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
                .limit(_price_batch_size())
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
                .limit(MARKET_COVER_BATCH)
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


# ----------------------------------------------------------------------
# Дозагрузка цен после импорта коллекции (discogs_price_jobs)
# ----------------------------------------------------------------------


async def run_price_backfill_jobs():
    """Разгребает очередь `discogs_price_jobs` — по одной задаче за прогон.

    Отличие от update_prices_batch: запросы идут под OAuth-токеном самого
    юзера, то есть в его личный бакет rate-limiter'а (60 req/min). Импортнувший
    коллекцию получает цены за минуты, а не за недели, и не соревнуется за
    общий лимит приложения с остальной базой.

    По одной задаче за прогон намеренно: две параллельные и так уткнулись бы в
    общий пул httpx-соединений, а последовательность даёт предсказуемый расход
    лимита и внятный лог.
    """
    from sqlalchemy import or_

    from app.models.discogs_price_job import (
        STATUS_FAILED,
        STATUS_PENDING,
        STATUS_RUNNING,
        DiscogsPriceJob,
    )
    from app.models.user import User
    from app.services.discogs_oauth import user_creds
    from app.services.price_backfill import STALE_RUNNING_AFTER

    now = datetime.utcnow()
    stale_cutoff = now - STALE_RUNNING_AFTER

    async with async_session_maker() as session:
        # pending — либо running, брошенный упавшим контейнером. Второе условие
        # обязательно: без него единственный неудачный деплой посреди прогона
        # оставлял бы задачу в running навсегда, а юзера — без цен и без ошибки.
        job = await session.scalar(
            select(DiscogsPriceJob)
            .where(
                or_(
                    DiscogsPriceJob.status == STATUS_PENDING,
                    # heartbeat_at IS NULL обязателен отдельным условием:
                    # в SQL `NULL < timestamp` даёт NULL, то есть строка не
                    # прошла бы фильтр и висела в running вечно. Сейчас running
                    # без heartbeat не создаётся, но цена ошибки — навсегда
                    # застрявшая задача, а стоимость страховки — одна строка.
                    (DiscogsPriceJob.status == STATUS_RUNNING)
                    & (
                        DiscogsPriceJob.heartbeat_at.is_(None)
                        | (DiscogsPriceJob.heartbeat_at < stale_cutoff)
                    ),
                )
            )
            .order_by(DiscogsPriceJob.created_at)
            .limit(1)
            .with_for_update(skip_locked=True)
        )
        if job is None:
            return

        job_id = job.id
        user_id = job.user_id

        # Креды достаём здесь же, пока сессия жива: после commit атрибуты
        # инстанса истекают (expire_on_commit), а за пределами блока сессия
        # закрыта и ленивая подгрузка упала бы DetachedInstanceError.
        user = await session.get(User, job.user_id)
        creds = user_creds(user) if user is not None else None

        job.status = STATUS_RUNNING
        job.heartbeat_at = now
        if job.started_at is None:
            job.started_at = now
        await session.commit()

    if creds is None:
        # Токен отозван или протух между импортом и прогоном. Задачу закрываем
        # с ошибкой, а не оставляем висеть: цены доедут ночным update_prices_batch,
        # просто медленнее, и мобилка перестанет крутить прогресс.
        async with async_session_maker() as session:
            job = await session.get(DiscogsPriceJob, job_id)
            if job is not None:
                job.status = STATUS_FAILED
                job.error = "Discogs отключён — цены обновятся в общем порядке"
                job.finished_at = datetime.utcnow()
                await session.commit()
        logger.info("price_backfill: no creds for user %s, job failed", user_id)
        return

    try:
        processed, updated, remaining = await _process_price_backfill_batch(
            job_id, user_id, creds
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("price_backfill: batch failed for user %s", user_id)
        async with async_session_maker() as session:
            job = await session.get(DiscogsPriceJob, job_id)
            if job is not None:
                job.status = STATUS_FAILED
                job.error = str(exc)[:500]
                job.finished_at = datetime.utcnow()
                await session.commit()
        return

    logger.info(
        "price_backfill: user=%s processed=%d updated=%d remaining=%d",
        user_id, processed, updated, remaining,
    )


async def _process_price_backfill_batch(
    job_id, user_id, creds: tuple[str, str]
) -> tuple[int, int, int]:
    """Один батч задачи. Возвращает (обработано, с ценой, осталось).

    Задача не закрывается, пока остались записи без цены: следующий прогон
    шедулера возьмёт её снова. Это и есть механика «долгой» работы без долгого
    HTTP-запроса.
    """
    from app.models.discogs_price_job import STATUS_DONE, DiscogsPriceJob
    from app.services.discogs import DiscogsService
    from app.services.exchange import get_usd_rub_rate
    from app.services.price_backfill import (
        count_records_without_price,
        records_without_price_query,
    )
    from app.services.pricing import PricingParams, estimate_rub

    settings = get_settings()
    params = PricingParams.from_settings(settings)
    usd_rub = await get_usd_rub_rate()
    discogs = DiscogsService()
    limit = settings.price_backfill_batch_size

    processed = 0
    updated = 0

    async with async_session_maker() as session:
        result = await session.execute(records_without_price_query(user_id).limit(limit))
        records = result.scalars().all()

        for record in records:
            processed += 1
            try:
                stats = await discogs._get_price_stats(record.discogs_id, creds=creds)
            except Exception:
                logger.exception(
                    "price_backfill: stats failed for %s", record.discogs_id
                )
                continue
            if not stats:
                continue

            lowest = _price_value(stats.get("lowest_price"))
            median = _price_value(stats.get("median_price"))
            highest = _price_value(stats.get("highest_price"))
            if not (lowest or median):
                continue

            record.estimated_price_min = lowest
            record.estimated_price_median = median
            record.estimated_price_max = highest
            record.price_currency = "USD"
            updated += 1

        # Рубли по свежим ценам — в той же транзакции: иначе полка показывала бы
        # «цена есть, рубли пустые» до ближайшего ночного backfill'а.
        if updated:
            priced_ids = [r.id for r in records if r.estimated_price_min]
            items_result = await session.execute(
                select(CollectionItem)
                .options(selectinload(CollectionItem.record))
                .where(CollectionItem.record_id.in_(priced_ids))
            )
            for item in items_result.scalars().all():
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

        remaining = await count_records_without_price(session, user_id)

        job = await session.get(DiscogsPriceJob, job_id)
        if job is not None:
            job.processed += processed
            job.updated += updated
            job.heartbeat_at = datetime.utcnow()
            # Пустой батч при ненулевом remaining означает, что оставшиеся
            # записи Discogs ценой не снабжает (нет лотов). Крутить их вечно
            # незачем — закрываем.
            if remaining == 0 or processed == 0:
                job.status = STATUS_DONE
                job.finished_at = datetime.utcnow()
            await session.commit()

    return processed, updated, remaining


def _price_value(raw) -> float | None:
    """Discogs отдаёт цену то объектом {value, currency}, то голым числом."""
    if isinstance(raw, dict):
        return raw.get("value")
    return raw
