"""
Фоновые задачи парсинга магазинов винила.

Регистрируются в main.py через APScheduler, под env SCRAPERS_ENABLED=true.
Все задачи идемпотентны и не валят друг друга при ошибке отдельного магазина.
"""
from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime, timedelta

from sqlalchemy import select, update
from sqlalchemy.exc import SQLAlchemyError

from app.database import async_session_maker
from app.models.record import Record
from app.models.store import Store
from app.models.store_listing import StoreListing, ListingStatus
from app.services.scrapers.runner import crawl_store, refresh_store_listings
from app.services.scrapers.shops import *  # noqa: F401,F403  — auto-register parsers
from app.services.listing_matcher import (
    match_unmatched_batch,
    rematch_store_native_batch,
    rematch_format_conflicts_batch,
    rematch_album_with_barcode_batch,
)
from app.api.offers import invalidate_record_offers
from app.api.records import _ensure_record_artist_data
from app.services import app_config

logger = logging.getLogger(__name__)


# ---- Полный обход (раскидан по дням недели для не перегрузки сети) ---- #


# Сколько магазинов обходим одновременно. Rate-limit per-domain живёт в
# http_client, так что параллельные магазины друг другу не мешают.
SCRAPER_CONCURRENCY = int(os.environ.get("SCRAPER_CONCURRENCY", "5"))


async def _crawl_active_stores(filter_browser: bool | None = None, mode: str = "full") -> dict:
    """Прогнать все активные магазины параллельно (Semaphore=SCRAPER_CONCURRENCY).

    filter_browser: True/False/None — фильтр по requires_browser.

    Единая воронка всех crawl-джоб: гейт `shop_scrapers` стоит здесь, чтобы
    выключение рубильником остановило обход, не дожидаясь передеплоя.
    """
    counters = {"stores": 0, "ok": 0, "failed": 0, "total_upserted": 0}

    if not await app_config.is_enabled("shop_scrapers"):
        logger.info("Crawl пропущен: kill-switch shop_scrapers выключен")
        counters["skipped"] = True
        return counters

    async with async_session_maker() as db:
        stmt = select(Store).where(Store.is_active.is_(True))
        if filter_browser is not None:
            stmt = stmt.where(Store.requires_browser.is_(filter_browser))
        stores = list((await db.execute(stmt)).scalars().all())

    counters["stores"] = len(stores)
    sem = asyncio.Semaphore(SCRAPER_CONCURRENCY)

    async def _one(slug: str) -> tuple[str, dict]:
        async with sem:
            try:
                return slug, await crawl_store(slug, mode=mode)
            except Exception:
                logger.exception("crawl_store failed for %s", slug)
                return slug, {"status": "failed", "upserted": 0}

    results = await asyncio.gather(*(_one(s.slug) for s in stores))
    failed_slugs: list[str] = []
    for slug, res in results:
        counters["total_upserted"] += res.get("upserted", 0)
        # Судим по `status`, а не по «вызов не бросил»: crawl_store гасит
        # исключения парсера внутри и всегда возвращает словарь, поэтому старый
        # счётчик структурно не мог показать провал (ночь 08-11: ok:7 при двух
        # магазинах с ошибкой в БД).
        if res.get("status") == "ok":
            counters["ok"] += 1
        else:
            counters["failed"] += 1
            failed_slugs.append(f"{slug}:{res.get('status')}")

    if failed_slugs:
        counters["failed_stores"] = failed_slugs
        logger.error("scraper batch: магазины не досчитаны — %s", ", ".join(failed_slugs))
    logger.info("scraper batch done: %s", counters)
    return counters


async def daily_full_crawl_http() -> dict:
    """Каждый день — полный обход магазинов БЕЗ requires_browser.

    Если магазинов > 20 — лучше разбить на группы, но для старта проще одной задачей.
    """
    return await _crawl_active_stores(filter_browser=False, mode="full")


async def weekly_full_crawl_browser() -> dict:
    """Раз в неделю — магазины с requires_browser=True (тяжелее, реже)."""
    return await _crawl_active_stores(filter_browser=True, mode="full")


async def daily_incremental_crawl() -> dict:
    """Ежедневно — инкрементальный обход (для магазинов с поддержкой)."""
    return await _crawl_active_stores(filter_browser=False, mode="incremental")


async def daily_incremental_crawl_browser() -> dict:
    """Ежедневно — инкрементальный обход browser-магазинов.

    Полный браузерный обход остаётся еженедельным (тяжёлый), но новинки
    и так доезжают каждый день — иначе browser-магазины отставали на неделю.
    """
    return await _crawl_active_stores(filter_browser=True, mode="incremental")


# ---- Цепочка «crawl → match → invalidate → covers» --------------------- #


async def _market_sync(filter_browser: bool, mode: str) -> dict:
    """Один прогон всего пайплайна маркета без межзадачных лагов.

    Раньше матчинг ждал hourly-задачу, обложки — interval 2h: новинка доезжала
    до маркета за 1–3 часа после crawl. Цепочка убирает лаг — каждый шаг
    стартует сразу после предыдущего; ошибка шага не валит остальные.
    """
    out: dict = {"crawl": await _crawl_active_stores(filter_browser=filter_browser, mode=mode)}
    try:
        out["match"] = await match_unmatched_batch(batch_size=2000)
    except Exception:
        logger.exception("market sync: match_unmatched failed")
    try:
        out["offers_invalidated"] = await invalidate_offers_for_recently_updated(window_minutes=240)
    except Exception:
        logger.exception("market sync: invalidate offers failed")
    try:
        from app.tasks.discogs_tasks import enrich_market_covers
        out["covers"] = await enrich_market_covers()
    except Exception:
        logger.exception("market sync: enrich covers failed")
    logger.info("market sync done: %s", out)
    return out


async def daily_market_sync() -> dict:
    """Ночной полный цикл HTTP-магазинов: crawl → match → offers → covers."""
    return await _market_sync(filter_browser=False, mode="full")


async def incremental_market_sync() -> dict:
    """Дневной цикл новинок HTTP-магазинов той же цепочкой."""
    return await _market_sync(filter_browser=False, mode="incremental")


# ---- Stock-refresh для активных матчей --------------------------------- #


async def stock_refresh_active(per_store_limit: int = 200, stale_hours: int = 6) -> dict:
    """Точечно перепроверить листинги, привязанные к Record и протухшие > stale_hours.

    Берёт именно stale-листинги (oldest first), группирует по магазину и
    перепарсивает их URL через parser.refresh_urls(). 404/410 → removed.
    Магазины обходятся параллельно (SCRAPER_CONCURRENCY).
    """
    counters = {"stores": 0, "checked": 0, "removed": 0, "errors": 0}

    if not await app_config.is_enabled("shop_scrapers"):
        logger.info("Stock-refresh пропущен: kill-switch shop_scrapers выключен")
        counters["skipped"] = True
        return counters

    # Магазины, у которых цена и наличие приезжают вместе с обходом каталога,
    # точечный refresh не нужен: он тратит 800 запросов в сутки на то, что
    # ночной crawl уже обновил, и в ночь 08-10 именно он клал сессии БД
    # (QueryCanceledError → PendingRollbackError каскадом на 200 итераций).
    from app.services.scrapers.registry import all_parsers
    listing_stock_slugs = {
        slug for slug, cls in all_parsers().items()
        if getattr(cls, "stock_from_listing", False)
    }

    cutoff = datetime.utcnow() - timedelta(hours=stale_hours)
    async with async_session_maker() as db:
        res = await db.execute(
            select(Store.slug, StoreListing.id, StoreListing.url)
            .join(Store, Store.id == StoreListing.store_id)
            .where(Store.is_active.is_(True))
            .where(Store.requires_browser.is_(False))
            .where(Store.parser_class.notin_(listing_stock_slugs or {""}))
            .where(StoreListing.matched_record_id.is_not(None))
            .where(StoreListing.status == ListingStatus.IN_STOCK)
            .where(StoreListing.last_seen_at < cutoff)
            .order_by(StoreListing.last_seen_at.asc())
        )
        rows = res.all()

    by_store: dict[str, list[tuple]] = {}
    for slug, listing_id, url in rows:
        bucket = by_store.setdefault(slug, [])
        if len(bucket) < per_store_limit:
            bucket.append((listing_id, url))

    counters["stores"] = len(by_store)
    sem = asyncio.Semaphore(SCRAPER_CONCURRENCY)

    async def _one(slug: str, items: list[tuple]) -> dict | None:
        async with sem:
            try:
                return await refresh_store_listings(slug, items)
            except Exception:
                logger.exception("stock_refresh failed for %s", slug)
                return None

    results = await asyncio.gather(*(_one(s, items) for s, items in by_store.items()))
    for res_one in results:
        if res_one is None:
            counters["errors"] += 1
        else:
            counters["checked"] += res_one.get("checked", 0)
            counters["removed"] += res_one.get("removed", 0)
            counters["errors"] += res_one.get("errors", 0)

    logger.info("stock refresh done: %s", counters)
    return counters


# ---- Матчинг unmatched ------------------------------------------------- #


async def hourly_match_unmatched() -> dict:
    """Раз в час — матчим до 2000 unmatched листингов.

    Cap равен DISCOGS_FETCH_HOURLY_LIMIT — больше за час всё равно не пройдёт
    через on-demand, а matched-через-existing-records и accessory-skip успеют.
    """
    return await match_unmatched_batch(batch_size=2000)


async def daily_market_health_report() -> dict:
    """Раз в сутки — сводка здоровья Маркета в лог.

    Единственная задача: сделать застой видимым без ручного похода в БД. Все три
    поломки, найденные 12.08, молчали неделями именно потому, что их некому было
    заметить. При проблемах пишем ERROR — его видно в логах отдельно от рутины.
    """
    from app.services.market_health import build_market_health_report

    report = await build_market_health_report()
    summary = {
        "stores": len(report["stores"]),
        "queue_never_tried": report["match_queue"]["never_tried"],
        "harvestable_covers": report["covers"]["harvestable"],
    }
    if report["problems"]:
        logger.error("market health: %d проблем | %s | %s",
                     len(report["problems"]), summary, "; ".join(report["problems"]))
    else:
        logger.info("market health: ок | %s", summary)
    return report


async def hourly_enrich_artist_thumbs(batch_size: int = 100) -> dict:
    """Раз в час — догружает artist_thumb_image_url для discogs-записей.

    Сейчас artist_thumb тянется лениво при первом детальном просмотре
    (_ensure_record_artist_data), а это требует доп. Discogs API запроса к
    /artists/{id}. Если первый юзер попал на пустую квоту — артист молча
    остаётся без аватара, и следующие пользователи видят дырку, пока кто-то
    другой не откроет деталь повторно.

    Эта задача обходит «брошенные» записи фоном: берёт source='discogs' без
    artist_thumb_image_url в discogs_data, и обогащает их через тот же
    _ensure_record_artist_data. batch_size=100/час → 2400/сутки, безопасный
    уровень относительно Discogs rate-limit (60 req/min).

    JSONB-проверка: записи без discogs_data → пропускаем (нечего обогащать).
    """
    counters = {"processed": 0, "enriched": 0, "errors": 0, "skipped": 0}
    async with async_session_maker() as db:
        # Записи без artist_thumb_image_url в discogs_data. Используем JSONB
        # оператор `?` через text() — SQLAlchemy не имеет нативной поддержки
        # для NOT EXISTS-key в JSONB.
        res = await db.execute(
            select(Record)
            .where(Record.source == "discogs")
            .where(Record.discogs_id.is_not(None))
            .where(Record.discogs_data.is_not(None))
            .where(~Record.discogs_data.has_key("artist_thumb_image_url"))  # type: ignore[attr-defined]
            .order_by(Record.updated_at.asc())
            .limit(batch_size)
        )
        records = list(res.scalars().all())

        for rec in records:
            counters["processed"] += 1
            try:
                before = (rec.discogs_data or {}).get("artist_thumb_image_url")
                await _ensure_record_artist_data(rec, db)
                after = (rec.discogs_data or {}).get("artist_thumb_image_url")
                if after and not before:
                    counters["enriched"] += 1
                else:
                    counters["skipped"] += 1
            except Exception:
                counters["errors"] += 1
                logger.exception("enrich artist thumb failed for record %s", rec.id)

    logger.info("enrich artist thumbs batch: %s", counters)
    return counters


async def daily_rematch_store_native() -> dict:
    """Раз в сутки — store-native записи прогоняются через Discogs search.

    Если релиз появился на Discogs, в records.discogs_id_candidate записывается
    кандидат + счётчик подтверждений. При 2-м подтверждении подряд срабатывает
    safe_merge_store_native_into → листинги перепривязываются на Discogs-запись,
    store-native soft-delete'ится через merged_into_id. См. listing_matcher.

    batch_size 300/день × 7 = 2100/нед, при ~5500 листингов и ~30% store-native
    полный круг ≤ недели. Discogs API нагрузка ≈ 12 req/час (лимит 2000/час).
    """
    return await rematch_store_native_batch(batch_size=300)


async def daily_rematch_format_conflicts() -> dict:
    """Раз в сутки — сброс листингов с конфликтом носителя (винил↔CD).

    Чинит исторические fuzzy-привязки винил-листинга к CD-релизу (хедер врал
    «CD»). Сбрасывает matched_record_id=NULL → hourly_match_unmatched
    пере-привяжет с format-penalty. batch 500/день покрывает весь каталог
    (~5500 листингов) за ≤2 недели; конфликтов кратно меньше.
    """
    return await rematch_format_conflicts_batch(batch_size=500)


async def daily_rematch_album_with_barcode() -> dict:
    """Раз в сутки — перематч album-tier листингов, у которых появился barcode.

    §A WS-A4.5: после фикса normalize_barcode (SKU-паддинг) у листингов в
    raw_payload появляется barcode, опознающий конкретный пресс. Слабые
    (fuzzy/dump/discogs_fetch <0.95) исторические матчи перепривязываются на
    верный пресс по barcode. Inline-rematch со сравнением → без loop/churn.
    batch 300/день покрывает каталог за ≤2 недели.
    """
    return await rematch_album_with_barcode_batch(batch_size=300)


# ---- Чистка stale ------------------------------------------------------ #


async def weekly_cleanup_stale(days: int = 30) -> dict:
    """Помечаем как 'removed' листинги, которые не видели больше N дней."""
    cutoff = datetime.utcnow() - timedelta(days=days)
    async with async_session_maker() as db:
        try:
            res = await db.execute(
                update(StoreListing)
                .where(StoreListing.last_seen_at < cutoff)
                .where(StoreListing.status != ListingStatus.REMOVED)
                .values(status=ListingStatus.REMOVED, updated_at=datetime.utcnow())
            )
            await db.commit()
            return {"updated": res.rowcount or 0}
        except SQLAlchemyError:
            await db.rollback()
            logger.exception("cleanup_stale failed")
            return {"updated": 0, "error": True}


# ---- Прогрев кэша offers ---------------------------------------------- #


async def invalidate_offers_for_recently_updated(window_minutes: int = 60) -> dict:
    """После обхода парсеров — сбросить offers-кэш для записей, чьи листинги
    обновились в последний час. Чтобы юзеры видели свежие цены, не дожидаясь TTL.
    """
    since = datetime.utcnow() - timedelta(minutes=window_minutes)
    async with async_session_maker() as db:
        from app.models.record import Record
        res = await db.execute(
            select(Record.discogs_id)
            .join(StoreListing, StoreListing.matched_record_id == Record.id)
            .where(StoreListing.last_seen_at >= since)
            .where(Record.discogs_id.is_not(None))
            .distinct()
        )
        ids = [r[0] for r in res.fetchall() if r[0]]

    for did in ids:
        await invalidate_record_offers(did)
    return {"invalidated": len(ids)}
