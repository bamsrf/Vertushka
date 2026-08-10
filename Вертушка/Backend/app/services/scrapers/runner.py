"""
Оркестрация одного прохода парсера для одного магазина:
discover_urls → parse_listing → upsert StoreListing.

Не запускает матчинг — это делает отдельная задача (listing_matcher.match_unmatched_batch).
"""
from __future__ import annotations

import logging
from datetime import datetime
from decimal import Decimal
from typing import Literal

from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import SQLAlchemyError

from app.database import async_session_maker
from app.models.store import Store
from app.models.store_listing import StoreListing, ListingStatus
from app.models.listing_price_history import ListingPriceHistory
from app.services.scrapers.base import (
    BaseStoreParser,
    ListingDTO,
    ParserBlocked,
    ParserNeedsBrowser,
)
from app.services.scrapers.browser import browser_pool
from app.services.scrapers.http_client import http_client
from app.services.scrapers.registry import get_parser

logger = logging.getLogger(__name__)


CrawlMode = Literal["full", "incremental", "stock"]

# Доля листингов из БД, которую обязан увидеть полный обход. Ниже — считаем
# прогон битым и не проставляем last_successful_scrape_at.
_SMOKE_MIN_COVERAGE = 0.5

# Сколько подряд идущих ошибок записи терпит refresh, прежде чем бросить магазин.
_REFRESH_MAX_CONSECUTIVE_ERRORS = 10


async def crawl_store(slug: str, *, mode: CrawlMode = "full", limit: int | None = None) -> dict:
    """Прогнать парсер для магазина в указанном режиме.

    Возвращает счётчики: discovered/upserted/errors/skipped.
    """
    counters = {"discovered": 0, "upserted": 0, "errors": 0, "skipped": 0}

    async with async_session_maker() as db:
        store = await _get_active_store(db, slug)
        if not store:
            logger.warning("Store %s: not found or inactive", slug)
            return counters

        parser = _make_parser(store)
        http_client.configure_domain(
            store.domain,
            rate_per_sec=parser.rate_limit_per_sec,
            burst=parser.rate_burst,
        )

        try:
            iterator = _select_iterator(parser, mode, store)
            async for dto in iterator:
                counters["discovered"] += 1
                try:
                    upserted = await _upsert_listing(db, store.id, dto)
                    # Коммит на КАЖДЫЙ листинг: транзакция живёт только на время
                    # одного INSERT и не переживает следующий сетевой fetch в
                    # `async for`. Раньше одна транзакция висела на весь краул
                    # (часы) → idle-in-transaction держал локи store_listings →
                    # api-upserts блокировались, воркер вставал (инцидент 07-10).
                    await db.commit()
                    if upserted:
                        counters["upserted"] += 1
                    else:
                        counters["skipped"] += 1
                except SQLAlchemyError:
                    counters["errors"] += 1
                    logger.exception("[%s] upsert failed for %s", slug, dto.url)
                    await db.rollback()

                if limit and counters["upserted"] >= limit:
                    break

            await db.commit()
            smoke_msg = await _smoke_check(db, store, counters, mode, limit)
            if smoke_msg:
                logger.error("[%s] smoke check failed: %s", slug, smoke_msg)
                await _mark_error(db, store, smoke_msg)
            else:
                await _mark_success(db, store)
        except ParserNeedsBrowser as e:
            await _mark_needs_browser(db, store, str(e))
            counters["errors"] += 1
        except ParserBlocked as e:
            await _mark_error(db, store, f"blocked: {e}")
            counters["errors"] += 1
        except Exception as e:
            await _mark_error(db, store, f"crash: {e}")
            counters["errors"] += 1
            logger.exception("[%s] crawl failed", slug)
        finally:
            await db.commit()

    logger.info("[%s] crawl(%s) done: %s", slug, mode, counters)
    return counters


async def refresh_store_listings(slug: str, items: list[tuple[object, str]]) -> dict:
    """Точечный refresh конкретных листингов: перепарсить их URL, обновить
    цену/наличие. items = [(listing_id, url)]. 404/410 → status='removed'.

    В отличие от crawl_full с limit — обновляет именно протухшие листинги,
    а не первые попавшиеся из sitemap.
    """
    counters = {"checked": 0, "removed": 0, "errors": 0}
    async with async_session_maker() as db:
        store = await _get_active_store(db, slug)
        if not store:
            logger.warning("Store %s: not found or inactive", slug)
            return counters

        parser = _make_parser(store)
        http_client.configure_domain(
            store.domain,
            rate_per_sec=parser.rate_limit_per_sec,
            burst=parser.rate_burst,
        )
        url_to_id = {url: listing_id for listing_id, url in items}
        consecutive_errors = 0

        try:
            async for url, dto in parser.refresh_urls(list(url_to_id)):
                counters["checked"] += 1
                try:
                    if dto is None:
                        await db.execute(
                            update(StoreListing)
                            .where(StoreListing.id == url_to_id[url])
                            .values(status=ListingStatus.REMOVED, updated_at=datetime.utcnow())
                        )
                        counters["removed"] += 1
                    else:
                        await _upsert_listing(db, store.id, dto)
                    # Коммит на каждый URL — транзакция не переживает следующий
                    # `refresh_urls` fetch (см. crawl_store, инцидент 07-10).
                    await db.commit()
                except SQLAlchemyError:
                    counters["errors"] += 1
                    consecutive_errors += 1
                    logger.exception("[%s] refresh upsert failed for %s", slug, url)
                    await db.rollback()
                    # Один statement timeout ломает сессию, и дальше каждая
                    # итерация падает на PendingRollbackError — в ночь 08-10
                    # так набежало 200 ошибок из 200. Рвём рано и честно.
                    if consecutive_errors >= _REFRESH_MAX_CONSECUTIVE_ERRORS:
                        logger.error(
                            "[%s] refresh прерван: %d ошибок подряд",
                            slug, consecutive_errors,
                        )
                        break
                else:
                    consecutive_errors = 0
            await db.commit()
        except ParserBlocked as e:
            await _mark_error(db, store, f"blocked: {e}")
            counters["errors"] += 1
            await db.commit()
        except Exception as e:
            await _mark_error(db, store, f"refresh crash: {e}")
            counters["errors"] += 1
            logger.exception("[%s] refresh failed", slug)
            await db.commit()

    logger.info("[%s] refresh done: %s", slug, counters)
    return counters


# ---- helpers ----------------------------------------------------------- #


async def _get_active_store(db, slug: str) -> Store | None:
    res = await db.execute(select(Store).where(Store.slug == slug, Store.is_active.is_(True)))
    return res.scalar_one_or_none()


def _make_parser(store: Store) -> BaseStoreParser:
    cls = get_parser(store.parser_class)
    use_browser = store.requires_browser or cls.requires_js
    return cls(http=http_client, browser=browser_pool if use_browser else None)


def _select_iterator(parser: BaseStoreParser, mode: CrawlMode, store: Store):
    if mode == "incremental":
        since = store.last_successful_scrape_at or datetime(2000, 1, 1)
        return parser.crawl_incremental(since)
    # mode in ("full", "stock") — по дефолту используем full
    return parser.crawl_full()


async def _upsert_listing(db, store_id, dto: ListingDTO) -> bool:
    """INSERT ... ON CONFLICT(store_id, external_id) DO UPDATE SET ...

    Возвращает True если запись была вставлена/обновлена.

    Волна B: одним roundtrip через prev-CTE забираем СТАРЫЕ price/status
    (снапшот до апдейта — data-modifying CTE видит строку до INSERT) плюс
    id/matched_record_id новой строки. Если price или status изменились —
    пишем снапшот в listing_price_history (источник для price_drop-producer
    и графика динамики).
    """
    now = datetime.utcnow()
    payload = {
        "store_id": store_id,
        "external_id": dto.external_id,
        "url": dto.url,
        "title_raw": dto.title_raw,
        "artist_raw": dto.artist_raw,
        "year_raw": dto.year_raw,
        "format_raw": dto.format_raw,
        "vinyl_color_raw": dto.vinyl_color_raw,
        "condition": dto.condition,
        "price_rub": dto.price_rub,
        "price_currency": dto.price_currency,
        "status": dto.status,
        "first_seen_at": now,
        "last_seen_at": now,
        "raw_payload": _serialize_raw(dto),
    }

    prev = (
        select(
            StoreListing.price_rub.label("price_rub"),
            StoreListing.status.label("status"),
        )
        .where(
            StoreListing.store_id == store_id,
            StoreListing.external_id == dto.external_id,
        )
        .cte("prev")
    )
    old_price = select(prev.c.price_rub).scalar_subquery()
    old_status = select(prev.c.status).scalar_subquery()

    stmt = pg_insert(StoreListing).values(**payload)
    stmt = stmt.on_conflict_do_update(
        index_elements=["store_id", "external_id"],
        set_={
            "url": stmt.excluded.url,
            "title_raw": stmt.excluded.title_raw,
            "artist_raw": stmt.excluded.artist_raw,
            "year_raw": stmt.excluded.year_raw,
            "format_raw": stmt.excluded.format_raw,
            "vinyl_color_raw": stmt.excluded.vinyl_color_raw,
            "condition": stmt.excluded.condition,
            "price_rub": stmt.excluded.price_rub,
            "price_currency": stmt.excluded.price_currency,
            "status": stmt.excluded.status,
            "last_seen_at": stmt.excluded.last_seen_at,
            "raw_payload": stmt.excluded.raw_payload,
            "updated_at": now,
        },
    )
    stmt = stmt.add_cte(prev).returning(
        StoreListing.id,
        StoreListing.matched_record_id,
        StoreListing.price_rub,
        StoreListing.status,
        old_price.label("old_price"),
        old_status.label("old_status"),
    )
    row = (await db.execute(stmt)).one()

    # old_* = None → строки раньше не было (первый показ листинга).
    price_changed = row.old_price != row.price_rub
    status_changed = row.old_status != row.status
    if row.old_status is None or price_changed or status_changed:
        db.add(
            ListingPriceHistory(
                listing_id=row.id,
                record_id=row.matched_record_id,
                price_rub=row.price_rub,
                status=row.status,
                captured_at=now,
            )
        )
    return True


def _serialize_raw(dto: ListingDTO) -> dict:
    out = dict(dto.raw_payload or {})
    if dto.barcode:
        out["barcode"] = dto.barcode
    if dto.catalog_number:
        out["catalog_number"] = dto.catalog_number
    if dto.discogs_release_url:
        out["discogs_release_url"] = dto.discogs_release_url
    if dto.image_url:
        out["image_url"] = dto.image_url
    if dto.variants:
        out["variants_count"] = len(dto.variants)
    return out


async def _smoke_check(
    db, store: Store, counters: dict, mode: CrawlMode, limit: int | None = None
) -> str | None:
    """None = crawl выглядит здоровым. Иначе текст проблемы.

    Ловит «магазин сменил HTML → парсер тихо отдаёт ноль/мусор»: сравниваем
    результат прохода с историей листингов в БД. Для incremental пустой
    результат — норма (новинок нет), деградацию там не детектим. Прогон с
    limit искусственно обрезан — объёмные проверки для него тоже пропускаем.
    """
    existing = await db.scalar(
        select(func.count()).select_from(StoreListing).where(StoreListing.store_id == store.id)
    )
    if not existing:
        return None
    if mode != "incremental" and limit is None:
        if counters["discovered"] == 0:
            return f"smoke: 0 discovered при {existing} листингах в БД"
        # Порог был 10% — он пропускал обрыв обхода на четверти каталога
        # (doctorhead 08-10: взято 696 из 3548, магазин помечен успешным).
        # Полный обход обязан увидеть большую часть того, что уже в БД;
        # ниже половины — это либо обрыв, либо сломанный парсер.
        if counters["discovered"] < existing * _SMOKE_MIN_COVERAGE:
            return (
                f"smoke: discovered {counters['discovered']} < "
                f"{int(_SMOKE_MIN_COVERAGE * 100)}% от {existing} в БД"
            )
    if counters["discovered"] >= 10 and counters["errors"] > counters["discovered"] * 0.5:
        return f"smoke: errors {counters['errors']}/{counters['discovered']}"
    return None


async def _mark_success(db, store: Store) -> None:
    store.last_successful_scrape_at = datetime.utcnow()
    store.last_error = None


async def _mark_needs_browser(db, store: Store, msg: str) -> None:
    if not store.requires_browser:
        store.requires_browser = True
        logger.warning("[%s] marked requires_browser=True (%s)", store.slug, msg)
    store.last_error = msg


async def _mark_error(db, store: Store, msg: str) -> None:
    store.last_error = msg[:1000]
