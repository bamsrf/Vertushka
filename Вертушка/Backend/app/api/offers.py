"""
API: предложения магазинов для конкретной пластинки.

GET  /api/records/{discogs_id}/offers?sort=price|rating
POST /api/offers/{listing_id}/click                  ← фаза A affiliate (см. SHOPS_PARSING.md §affiliate)
"""
from __future__ import annotations

import hashlib
import logging
from datetime import datetime, timedelta
from typing import Literal, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import select, text
from sqlalchemy.orm import joinedload
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_current_user_optional
from app.config import get_settings
from app.database import get_db
from app.models.offer_click import OfferClick
from app.models.record import Record
from app.models.store import Store
from app.models.store_listing import StoreListing, ListingStatus
from app.models.user import User
from app.schemas.offer import (
    MarketCarouselItem,
    OfferClickResponse,
    OfferResponse,
    RecordOffersFullResponse,
    RecordOffersSummary,
    RecordOffersSummaryRequest,
    StoreInfo,
)
from app.services.affiliate import wrap_url
from app.services.cache import cache
from app.services.vinyl_color import (
    PRESSING_EXACT_METHODS,
    color_family,
    sql_pressing_tier,
)

logger = logging.getLogger(__name__)

router = APIRouter()

OFFERS_CACHE_NS = "offers"
OFFERS_CACHE_TTL = 1800  # 30 мин — синхронизировано с Mobile useCacheStore
STALE_AFTER_DAYS = 7

MARKET_CACHE_NS = "market"
MARKET_CACHE_TTL = 900  # 15 мин — карусель не критична к мгновенному обновлению


@router.get(
    "/records/{discogs_id}/offers",
    response_model=list[OfferResponse],
    summary="Предложения магазинов для записи",
)
async def get_record_offers(
    discogs_id: str,
    sort: Literal["price", "rating"] = Query("price"),
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
) -> list[OfferResponse]:
    cache_key = f"{discogs_id}:{sort}:{limit}"
    cached = await cache.get(OFFERS_CACHE_NS, cache_key)
    if cached is not None:
        return [OfferResponse.model_validate(item) for item in cached]

    rec_res = await db.execute(
        select(Record.id, Record.discogs_data["vinyl_color_raw"].astext).where(
            Record.discogs_id == discogs_id
        )
    )
    rec_row = rec_res.first()
    if rec_row is None:
        return []
    record_id, record_color_raw = rec_row
    record_color_fam = color_family(record_color_raw)

    cutoff = datetime.utcnow() - timedelta(days=STALE_AFTER_DAYS)

    stmt = (
        select(StoreListing)
        .options(
            joinedload(StoreListing.store),
            joinedload(StoreListing.record),  # для record_discogs_id в response (relationship называется record, не matched_record)
        )
        .where(StoreListing.matched_record_id == record_id)
        .where(StoreListing.status.in_((ListingStatus.IN_STOCK, ListingStatus.PREORDER)))
        .where(StoreListing.last_seen_at >= cutoff)
    )
    if sort == "price":
        stmt = stmt.order_by(StoreListing.price_rub.asc().nulls_last())
    else:
        stmt = stmt.order_by(Store.rating.desc()).join(Store, Store.id == StoreListing.store_id)
    stmt = stmt.limit(limit)

    res = await db.execute(stmt)
    listings = list(res.unique().scalars().all())

    offers = [
        _to_response(li, pressing_match=pressing_tier(li, record_color_fam))
        for li in listings
        if li.store and li.store.is_active
    ]

    await cache.set(
        OFFERS_CACHE_NS,
        cache_key,
        [o.model_dump(mode="json") for o in offers],
        ttl=OFFERS_CACHE_TTL,
    )
    return offers


def pressing_tier(listing: StoreListing, record_color_fam: str | None) -> str:
    """'exact' | 'album' — тот ли это пресс или просто тот же альбом.

    Зеркало sql_pressing_tier() (vinyl_color.py). Конфликт семьи цвета (обе
    стороны известны и разные) перебивает всё → 'album'. Иначе exact-методы →
    'exact', fuzzy → 'album', остальные (dump/discogs_fetch) — по confidence.
    """
    lf = color_family(listing.vinyl_color_raw)
    if lf and record_color_fam and lf != record_color_fam:
        return "album"
    method = listing.match_method
    if method in PRESSING_EXACT_METHODS:
        return "exact"
    if method == "fuzzy":
        return "album"
    try:
        conf = float(listing.match_confidence or 0)
    except (TypeError, ValueError):
        conf = 0.0
    return "exact" if conf >= 0.95 else "album"


def _to_response(
    listing: StoreListing,
    *,
    is_alt_version: bool = False,
    pressing_match: str = "exact",
) -> OfferResponse:
    """Preview-URL для GET /offers — без subid (он создаётся при клике).

    `is_alt_version` — пробрасывается в response для бейджа «АЛТ» в
    Mobile OfferDetailCard (Phase 5). True если у listing'а тот же
    discogs_master_id, что у запрошенной записи, но другой discogs_id.

    `pressing_match` — 'exact'/'album' (см. pressing_tier). alt-version всегда
    'album'.
    """
    store = listing.store
    return OfferResponse(
        listing_id=listing.id,
        store=StoreInfo(
            slug=store.slug,
            name=store.name,
            logo_url=store.logo_url,
            rating=float(store.rating or 0),
        ),
        price_rub=listing.price_rub,
        condition=listing.condition,
        vinyl_color=listing.vinyl_color_raw,
        format=listing.format_raw,
        # Preview-URL: только UTM, без affiliate-subid. Полный wrapped URL с
        # subid Mobile получит из POST /offers/{id}/click.
        url=wrap_url(store, listing.url),
        status=listing.status,
        last_seen_at=listing.last_seen_at,
        # catalog_number / image_url не хранятся отдельными колонками в БД —
        # парсеры кладут их в raw_payload JSONB. Достаём оттуда safe-fallback'ом.
        catalog_number=_get_payload_str(listing, 'catalog_number'),
        is_alt_version=is_alt_version,
        pressing_match="album" if is_alt_version else pressing_match,
        image_url=_get_payload_str(listing, 'image_url'),
        # discogs_id записи, к которой матчен листинг (для navigation на
        # детальную alt-pressing'а). relationship называется `record`.
        record_discogs_id=(
            listing.record.discogs_id
            if listing.record is not None
            else None
        ),
    )


def _get_payload_str(listing: StoreListing, key: str) -> str | None:
    """Safe-getter из raw_payload JSONB. None если ключа нет / payload не dict."""
    payload = listing.raw_payload
    if not isinstance(payload, dict):
        return None
    value = payload.get(key)
    return str(value) if value else None


# ============================================================================
# Affiliate Phase A — клик-трекинг и финальный wrapped URL
# ============================================================================


@router.post(
    "/offers/{listing_id}/click",
    response_model=OfferClickResponse,
    status_code=status.HTTP_200_OK,
    summary="Записать клик «Купить» и получить финальный URL для перехода",
)
async def track_offer_click(
    listing_id: UUID,
    request: Request,
    current_user: Optional[User] = Depends(get_current_user_optional),
    db: AsyncSession = Depends(get_db),
) -> OfferClickResponse:
    """
    Mobile/Web вызывают этот эндпоинт ПЕРЕД открытием URL магазина.
    Эндпоинт:
        1. Создаёт запись OfferClick с ip_hash + user_agent + (опц.) user_id
        2. Использует click.id как `subid` для аффилиат-обёртки
        3. Возвращает финальный URL → клиент делает Linking.openURL(url)

    Идемпотентность: каждый клик = новая строка (это нужно для отчётов).
    Anti-fraud делается отдельно (rate-limit / DB-аналитика), не здесь.
    """
    stmt = (
        select(StoreListing)
        .options(
            joinedload(StoreListing.store),
            joinedload(StoreListing.record),  # для record_discogs_id в response (relationship называется record, не matched_record)
        )
        .where(StoreListing.id == listing_id)
    )
    listing = (await db.execute(stmt)).unique().scalar_one_or_none()
    if listing is None or listing.store is None or not listing.store.is_active:
        raise HTTPException(status_code=404, detail="Listing not found or store inactive")

    click = OfferClick(
        listing_id=listing.id,
        user_id=current_user.id if current_user else None,
        ip_hash=_hash_ip(request),
        user_agent=(request.headers.get("user-agent") or "")[:500] or None,
        surface="mobile",
    )
    db.add(click)
    await db.flush()  # получаем click.id для subid
    final_url = wrap_url(
        listing.store,
        listing.url,
        subid=str(click.id),
        user_id=str(current_user.id) if current_user else None,
    )
    await db.commit()

    return OfferClickResponse(click_id=click.id, url=final_url)


# ============================================================================
# Market carousel (OFFERS_UX.md Фича 4 — «В наличии сейчас» на search.tsx)
# ============================================================================


@router.get(
    "/market/new-arrivals",
    response_model=list[MarketCarouselItem],
    summary="Свежие предложения магазинов для карусели в поиске",
)
async def get_market_new_arrivals(
    limit: int = Query(24, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
) -> list[MarketCarouselItem]:
    """
    Возвращает последние N листингов со статусом in_stock из всех активных магазинов.

    Дедуп по `matched_record_id`: на одну запись отдаём только самый дешёвый листинг
    из всех магазинов. Сортировка — по дате появления листинга в БД (новинки в продаже
    сверху). Это даёт «N разных пластинок» в карусели, а не «N дублей одной обложки».

    Кэш — Redis, TTL 15 минут. Инвалидируется при `parse_listing` через
    `invalidate_market_feed` (по аналогии с `invalidate_record_offers`).
    """
    cache_key = f"new_arrivals:{limit}"
    cached = await cache.get(MARKET_CACHE_NS, cache_key)
    if cached is not None:
        return [MarketCarouselItem.model_validate(item) for item in cached]

    cutoff = datetime.utcnow() - timedelta(days=STALE_AFTER_DAYS)

    # Сначала находим минимальную цену на каждую matched запись — это
    # дешевле, чем тянуть все листинги и группировать в Python.
    # DISTINCT ON по matched_record_id + ORDER BY price даёт нам по
    # одному (самому дешёвому) листингу на запись.
    sql = text(
        """
        WITH ranked AS (
            SELECT DISTINCT ON (sl.matched_record_id)
                sl.matched_record_id AS record_id,
                sl.price_rub,
                sl.first_seen_at,
                s.slug AS store_slug,
                r.discogs_id,
                r.artist,
                r.title,
                r.year,
                -- Формат: приоритет у records.format_type (богаче, из Discogs),
                -- fallback на sl.format_raw (что определил парсер магазина).
                -- Без fallback почти все карточки приходили с NULL format_type
                -- т.к. Discogs API search не возвращает формат в search-результате,
                -- а matcher._save_discogs_result создаёт Record без format_type.
                COALESCE(r.format_type, sl.format_raw) AS format_type,
                -- Обложка: симметрично с format_type. Discogs search возвращает
                -- cover_image не для всех релизов (особенно re-issues и нишевые
                -- лейблы). Парсер магазина сохраняет og:image в raw_payload —
                -- используем его как fallback, чтобы карточка не была пустой
                -- (фиолетовый placeholder в AutoRail).
                COALESCE(r.cover_image_url, sl.raw_payload->>'image_url') AS cover_image_url
            FROM store_listings sl
            JOIN stores s ON s.id = sl.store_id
            JOIN records r ON r.id = sl.matched_record_id
            WHERE sl.status = 'in_stock'
              AND sl.matched_record_id IS NOT NULL
              AND sl.price_rub IS NOT NULL
              AND sl.last_seen_at >= :cutoff
              AND s.is_active = true
            ORDER BY sl.matched_record_id, sl.price_rub ASC NULLS LAST
        )
        SELECT *
        FROM ranked
        ORDER BY first_seen_at DESC
        LIMIT :limit
        """
    )
    rows = (await db.execute(sql, {"cutoff": cutoff, "limit": limit})).mappings().all()

    items = [
        MarketCarouselItem(
            record_id=row["record_id"],
            discogs_id=row["discogs_id"],
            artist=row["artist"],
            title=row["title"],
            year=row["year"],
            format_type=row["format_type"],
            cover_image_url=row["cover_image_url"],
            min_price_rub=row["price_rub"],
            store_slug=row["store_slug"],
            first_seen_at=row["first_seen_at"],
        )
        for row in rows
    ]

    await cache.set(
        MARKET_CACHE_NS,
        cache_key,
        [item.model_dump(mode="json") for item in items],
        ttl=MARKET_CACHE_TTL,
    )
    return items


async def invalidate_market_feed() -> None:
    """Хелпер для scraper_tasks: сбросить кэш карусели после новых листингов."""
    if not cache.available:
        return
    try:
        assert cache._pool is not None
        prefix = cache._key(MARKET_CACHE_NS, "new_arrivals:")
        async for key in cache._pool.scan_iter(match=f"{prefix}*"):
            await cache._pool.delete(key)
    except Exception:
        logger.debug("invalidate market cache failed", exc_info=True)


def _hash_ip(request: Request) -> str | None:
    """sha256(ip + SECRET_KEY) — для anti-fraud аналитики без хранения PII."""
    # Уважаем X-Forwarded-For (за nginx). Берём первый адрес из цепочки.
    fwd = request.headers.get("x-forwarded-for") or ""
    ip = fwd.split(",")[0].strip() if fwd else (request.client.host if request.client else "")
    if not ip:
        return None
    secret = get_settings().secret_key
    return hashlib.sha256(f"{ip}|{secret}".encode("utf-8")).hexdigest()


async def invalidate_record_offers(discogs_id: str) -> None:
    """Хелпер для scraper_tasks: сбросить кэш всех вариантов sort/limit для записи."""
    if not cache.available:
        return
    try:
        assert cache._pool is not None
        prefix = cache._key(OFFERS_CACHE_NS, f"{discogs_id}:")
        # SCAN по префиксу
        async for key in cache._pool.scan_iter(match=f"{prefix}*"):
            await cache._pool.delete(key)
    except Exception:
        logger.debug("invalidate offers cache failed for %s", discogs_id, exc_info=True)


# ============================================================================
# Hot Stock pill — batch summary endpoint (Mobile Phase 1)
# MARKET_AND_PRICE_DRAWER.md §1.15
# ============================================================================


OFFERS_SUMMARY_CACHE_NS = "offers_summary"
OFFERS_SUMMARY_CACHE_TTL = 600  # 10 мин — summary держится дольше чем offers (короче TTL)


@router.post(
    "/records/offers/summary",
    response_model=dict[str, RecordOffersSummary],
    summary="Batch-аггрегат офферов для сетки карточек (Hot Stock pill)",
)
async def get_records_offers_summary(
    body: RecordOffersSummaryRequest,
    db: AsyncSession = Depends(get_db),
) -> dict[str, RecordOffersSummary]:
    """
    Mobile делает один запрос на всю видимую сетку (20 карточек поиска /
    60 карточек коллекции), мапит summary к карточкам и рисует HotStockTag.

    Возвращает dict {discogs_id: RecordOffersSummary} — discogs_id'ы которые
    не нашлись или у которых нет offers будут отсутствовать в map'е (Mobile
    рендерит для них variant='none' = null).
    """
    if not body.discogs_ids:
        return {}

    cutoff = datetime.utcnow() - timedelta(days=STALE_AFTER_DAYS)

    # Tier-выражение (exact/album) — зеркало pressing_tier() в SQL. tr.rcolor =
    # цвет записи из discogs_data, sl.* — листинг. Static-строка (нет user input).
    tier = sql_pressing_tier(
        method_col="sl.match_method",
        confidence_col="sl.match_confidence",
        listing_color_col="sl.vinyl_color_raw",
        record_color_expr="tr.rcolor",
    )

    # Один SQL — JOIN records → store_listings, agg по discogs_id, GROUP BY.
    # in_stock_count = ТОЛЬКО exact-pressing; album-level (fuzzy/конфликт цвета)
    # на этой записи + alt-version'ы другого мастера → alt_version_count.
    sql = text(
        f"""
        WITH target_records AS (
            SELECT id, discogs_id, discogs_master_id,
                   discogs_data->>'vinyl_color_raw' AS rcolor
            FROM records
            WHERE discogs_id = ANY(:discogs_ids)
        ),
        exact_stats AS (
            SELECT
                tr.discogs_id,
                COUNT(*) FILTER (
                    WHERE sl.status = 'in_stock' AND sl.last_seen_at >= :cutoff
                      AND ({tier}) = 'exact'
                ) AS in_stock_count,
                COUNT(*) FILTER (
                    WHERE sl.status = 'in_stock' AND sl.last_seen_at >= :cutoff
                      AND ({tier}) = 'album'
                ) AS album_in_stock_count,
                COUNT(*) FILTER (
                    WHERE sl.status = 'preorder' AND sl.last_seen_at >= :cutoff
                ) AS preorder_count,
                MIN(sl.price_rub) FILTER (
                    WHERE sl.status = 'in_stock' AND sl.last_seen_at >= :cutoff
                      AND sl.price_rub IS NOT NULL AND ({tier}) = 'exact'
                ) AS min_price_rub,
                MIN(sl.price_rub) FILTER (
                    WHERE sl.status = 'in_stock' AND sl.last_seen_at >= :cutoff
                      AND sl.price_rub IS NOT NULL AND ({tier}) = 'album'
                ) AS min_price_album_rub,
                COUNT(DISTINCT sl.store_id) FILTER (
                    WHERE sl.status = 'in_stock' AND sl.last_seen_at >= :cutoff
                      AND ({tier}) = 'exact'
                ) AS stores_with_stock
            FROM target_records tr
            LEFT JOIN store_listings sl ON sl.matched_record_id = tr.id
            GROUP BY tr.discogs_id
        ),
        alt_stats AS (
            -- Другой pressing того же master_id: r2.discogs_id != tr.discogs_id
            -- но r2.discogs_master_id = tr.discogs_master_id (если есть master_id)
            SELECT
                tr.discogs_id,
                COUNT(*) FILTER (
                    WHERE sl.status = 'in_stock' AND sl.last_seen_at >= :cutoff
                ) AS alt_version_count,
                MIN(sl.price_rub) FILTER (
                    WHERE sl.status = 'in_stock' AND sl.last_seen_at >= :cutoff
                      AND sl.price_rub IS NOT NULL
                ) AS min_price_alt_rub
            FROM target_records tr
            LEFT JOIN records r2
                ON r2.discogs_master_id = tr.discogs_master_id
               AND r2.discogs_master_id IS NOT NULL
               AND r2.discogs_id != tr.discogs_id
            LEFT JOIN store_listings sl ON sl.matched_record_id = r2.id
            GROUP BY tr.discogs_id
        )
        SELECT
            es.discogs_id,
            COALESCE(es.in_stock_count, 0)      AS in_stock_count,
            COALESCE(es.preorder_count, 0)      AS preorder_count,
            -- alt = другой пресс мастера + album-level на этой записи
            COALESCE(als.alt_version_count, 0)
              + COALESCE(es.album_in_stock_count, 0)  AS alt_version_count,
            es.min_price_rub,
            LEAST(als.min_price_alt_rub, es.min_price_album_rub) AS min_price_alt_rub,
            FALSE AS has_last_one,
            COALESCE(es.stores_with_stock, 0)   AS stores_with_stock
        FROM exact_stats es
        LEFT JOIN alt_stats als ON als.discogs_id = es.discogs_id
        """
    )
    rows = (await db.execute(sql, {"discogs_ids": body.discogs_ids, "cutoff": cutoff})).mappings().all()

    return {
        row["discogs_id"]: RecordOffersSummary(
            in_stock_count=row["in_stock_count"],
            preorder_count=row["preorder_count"],
            alt_version_count=row["alt_version_count"],
            min_price_rub=row["min_price_rub"],
            min_price_alt_rub=row["min_price_alt_rub"],
            has_last_one=row["has_last_one"],
            stores_with_stock=row["stores_with_stock"],
        )
        for row in rows
    }


# ============================================================================
# Full offers (с alt-version) для детального экрана + bottom-sheet (Mobile Phase 5)
# MARKET_AND_PRICE_DRAWER.md §2.3
# ============================================================================


@router.get(
    "/records/{discogs_id}/offers/full",
    response_model=RecordOffersFullResponse,
    summary="Полные офферы (exact + alt) + summary одним запросом",
)
async def get_record_offers_full(
    discogs_id: str,
    include_master_versions: bool = Query(
        True,
        description=(
            "Если true (default) — добавляем offers других pressing'ов того же "
            "master_id с пометкой is_alt_version=true. Используется в Mobile "
            "OffersBottomSheet для секции «Другая версия мастера»."
        ),
    ),
    db: AsyncSession = Depends(get_db),
) -> RecordOffersFullResponse:
    cutoff = datetime.utcnow() - timedelta(days=STALE_AFTER_DAYS)

    rec_res = await db.execute(
        select(
            Record.id,
            Record.discogs_master_id,
            Record.discogs_data["vinyl_color_raw"].astext,
        ).where(Record.discogs_id == discogs_id)
    )
    rec_row = rec_res.first()
    if rec_row is None:
        return RecordOffersFullResponse(
            summary=RecordOffersSummary(),
            offers=[],
        )
    record_id, master_id, record_color_raw = rec_row
    record_color_fam = color_family(record_color_raw)

    # Exact offers
    exact_stmt = (
        select(StoreListing)
        .options(
            joinedload(StoreListing.store),
            joinedload(StoreListing.record),  # для record_discogs_id в response (relationship называется record, не matched_record)
        )
        .where(StoreListing.matched_record_id == record_id)
        .where(StoreListing.status.in_((ListingStatus.IN_STOCK, ListingStatus.PREORDER)))
        .where(StoreListing.last_seen_at >= cutoff)
        .order_by(StoreListing.price_rub.asc().nulls_last())
        .limit(50)
    )
    exact_listings = list((await db.execute(exact_stmt)).unique().scalars().all())

    # Alt-version offers (другой pressing того же мастера)
    alt_listings: list[StoreListing] = []
    if include_master_versions and master_id and master_id != '0':
        alt_stmt = (
            select(StoreListing)
            .options(
            joinedload(StoreListing.store),
            joinedload(StoreListing.record),  # для record_discogs_id в response (relationship называется record, не matched_record)
        )
            .join(Record, Record.id == StoreListing.matched_record_id)
            .where(Record.discogs_master_id == master_id)
            .where(Record.id != record_id)
            .where(StoreListing.status == ListingStatus.IN_STOCK)
            .where(StoreListing.last_seen_at >= cutoff)
            .order_by(StoreListing.price_rub.asc().nulls_last())
            .limit(20)
        )
        alt_listings = list((await db.execute(alt_stmt)).unique().scalars().all())

    # Тиры для exact-листингов (на этой же записи). alt-листинги всегда album.
    exact_tier = {li.id: pressing_tier(li, record_color_fam) for li in exact_listings}

    offers = [
        _to_response(li, pressing_match=exact_tier[li.id])
        for li in exact_listings
        if li.store and li.store.is_active
    ] + [
        _to_response(li, is_alt_version=True)
        for li in alt_listings
        if li.store and li.store.is_active
    ]

    # Summary — pill «N в наличии» считает ТОЛЬКО exact-pressing. Album-level
    # (fuzzy/конфликт цвета) на этой записи + alt-version'ы другого пресса
    # сворачиваются в alt_version_count, чтобы не врать про «этот пресс».
    pressing_in_stock = [
        li for li in exact_listings
        if li.status == ListingStatus.IN_STOCK and exact_tier[li.id] == "exact"
    ]
    album_in_stock = [
        li for li in exact_listings
        if li.status == ListingStatus.IN_STOCK and exact_tier[li.id] == "album"
    ] + [li for li in alt_listings if li.status == ListingStatus.IN_STOCK]
    preorder = [li for li in exact_listings if li.status == ListingStatus.PREORDER]

    summary = RecordOffersSummary(
        in_stock_count=len(pressing_in_stock),
        preorder_count=len(preorder),
        alt_version_count=len(album_in_stock),
        min_price_rub=min(
            (li.price_rub for li in pressing_in_stock if li.price_rub is not None),
            default=None,
        ),
        min_price_alt_rub=min(
            (li.price_rub for li in album_in_stock if li.price_rub is not None),
            default=None,
        ),
        has_last_one=False,
        stores_with_stock=len({li.store_id for li in pressing_in_stock}),
    )

    return RecordOffersFullResponse(summary=summary, offers=offers)


# ============================================================================
# /records/by-id/{record_id}/offers/full
# ============================================================================
# Параллельный endpoint для store-native записей (source='store'),
# у которых discogs_id=NULL → /records/{discogs_id}/offers/full не работает.
# Принимает UUID Record и возвращает в том же формате, что обычный endpoint.
# alt-version'ы недоступны (нет master_id), только exact-match.


@router.get(
    "/records/by-id/{record_id}/offers/full",
    response_model=RecordOffersFullResponse,
    summary="Полные офферы по record_id (для store-native записей без discogs_id)",
)
async def get_record_offers_full_by_id(
    record_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> RecordOffersFullResponse:
    cutoff = datetime.utcnow() - timedelta(days=STALE_AFTER_DAYS)

    # Проверяем существование записи (по UUID, без фильтра по source —
    # endpoint можно дёргать и для discogs-записей если уж нашли по id).
    rec_res = await db.execute(
        select(Record.id, Record.discogs_data["vinyl_color_raw"].astext).where(
            Record.id == record_id
        )
    )
    rec_row = rec_res.first()
    if rec_row is None:
        return RecordOffersFullResponse(summary=RecordOffersSummary(), offers=[])
    record_color_fam = color_family(rec_row[1])

    exact_stmt = (
        select(StoreListing)
        .options(
            joinedload(StoreListing.store),
            joinedload(StoreListing.record),
        )
        .where(StoreListing.matched_record_id == record_id)
        .where(StoreListing.status.in_((ListingStatus.IN_STOCK, ListingStatus.PREORDER)))
        .where(StoreListing.last_seen_at >= cutoff)
        .order_by(StoreListing.price_rub.asc().nulls_last())
    )
    exact_listings = list((await db.execute(exact_stmt)).unique().scalars().all())

    tier = {li.id: pressing_tier(li, record_color_fam) for li in exact_listings}

    offers = [
        _to_response(li, pressing_match=tier[li.id])
        for li in exact_listings
        if li.store and li.store.is_active
    ]

    pressing_in_stock = [
        li for li in exact_listings
        if li.status == ListingStatus.IN_STOCK and tier[li.id] == "exact"
    ]
    album_in_stock = [
        li for li in exact_listings
        if li.status == ListingStatus.IN_STOCK and tier[li.id] == "album"
    ]
    preorder = [li for li in exact_listings if li.status == ListingStatus.PREORDER]

    summary = RecordOffersSummary(
        in_stock_count=len(pressing_in_stock),
        preorder_count=len(preorder),
        # store-native: master_id нет → alt'ов другого пресса нет, но album-level
        # на этой же записи (низкая confidence) всё равно демоутим из «в наличии».
        alt_version_count=len(album_in_stock),
        min_price_rub=min(
            (li.price_rub for li in pressing_in_stock if li.price_rub is not None),
            default=None,
        ),
        min_price_alt_rub=min(
            (li.price_rub for li in album_in_stock if li.price_rub is not None),
            default=None,
        ),
        has_last_one=False,
        stores_with_stock=len({li.store_id for li in pressing_in_stock}),
    )

    return RecordOffersFullResponse(summary=summary, offers=offers)
