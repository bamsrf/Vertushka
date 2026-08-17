"""
Оркестрация одного прохода парсера для одного магазина:
discover_urls → parse_listing → upsert StoreListing.

Не запускает матчинг — это делает отдельная задача (listing_matcher.match_unmatched_batch).
"""
from __future__ import annotations

import logging
import time
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
    TransientParserError,
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

# То же для полного обхода. Битая сессия сама не чинится, а каталог большой:
# без отсечки один сбой превращается в тысячи одинаковых трейсбеков.
_CRAWL_MAX_CONSECUTIVE_ERRORS = 20


async def crawl_store(slug: str, *, mode: CrawlMode = "full", limit: int | None = None) -> dict:
    """Прогнать парсер для магазина в указанном режиме.

    Возвращает счётчики: discovered/upserted/errors/skipped + `status`.

    `status` — единственный достоверный признак исхода для вызывающего:
    исключения парсера ловятся здесь, поэтому «не бросило» ≠ «прошло»
    (батч рапортовал ok:7 при двух упавших магазинах, ночь 08-11).
    """
    counters: dict = {
        "discovered": 0, "upserted": 0, "errors": 0, "skipped": 0,
        "status": "skipped",
    }

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

        # Скаляр, а не ORM-атрибут: обход держит сессию открытой часами, и если
        # соединение за это время умрёт (магазин отвечал 10 минут на страницу —
        # ночь 08-12), SQLAlchemy пометит `store` протухшим. Тогда `store.id`
        # уходит в ленивую перечитку → синхронный IO в async-контексте →
        # MissingGreenlet на КАЖДОМ листинге: 8 956 позиций, 0 записанных.
        store_id = store.id
        store_slug = store.slug
        consecutive_errors = 0
        started = time.monotonic()
        deadline = started + parser.max_crawl_seconds

        try:
            iterator = _select_iterator(parser, mode, store)
            async for dto in iterator:
                # Потолок на весь магазин. Дедлайн одной страницы (см.
                # `fetch_page`) ловит зависший запрос, но не ловит обход,
                # который просто ползёт: 94 страницы по минуте — это полтора
                # часа, и остальным магазинам ночного окна уже не хватит.
                if time.monotonic() > deadline:
                    raise TransientParserError(
                        f"обход прерван по времени: {parser.max_crawl_seconds:.0f} c, "
                        f"взято {counters['upserted']} позиций"
                    )
                counters["discovered"] += 1
                try:
                    upserted = await _upsert_listing(db, store_id, dto)
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
                    consecutive_errors += 1
                    logger.exception("[%s] upsert failed for %s", slug, dto.url)
                    await db.rollback()
                    # Сломанную сессию не чинит следующая итерация: в ночь
                    # 08-12 так набежало 8 957 одинаковых трейсбеков подряд.
                    # Рвём рано — smoke-check всё равно не даст зелёный статус.
                    if consecutive_errors >= _CRAWL_MAX_CONSECUTIVE_ERRORS:
                        raise RuntimeError(
                            f"обход прерван: {consecutive_errors} ошибок записи подряд"
                        )
                else:
                    consecutive_errors = 0

                if limit and counters["upserted"] >= limit:
                    break

            await db.commit()
            smoke_msg = await _smoke_check(db, store_id, counters, mode, limit)
            if smoke_msg:
                logger.error("[%s] smoke check failed: %s", slug, smoke_msg)
                await _mark_error(db, store_id, smoke_msg)
                counters["status"] = "failed"
            else:
                await _mark_success(db, store_id)
                counters["status"] = "ok"
        except ParserNeedsBrowser as e:
            await _mark_needs_browser(db, store_id, store_slug, str(e))
            counters["errors"] += 1
            counters["status"] = "needs_browser"
        except ParserBlocked as e:
            await _mark_error(db, store_id, f"blocked: {e}")
            counters["errors"] += 1
            counters["status"] = "blocked"
        except Exception as e:
            await _mark_error(db, store_id, f"crash: {e}")
            counters["errors"] += 1
            counters["status"] = "failed"
            logger.exception("[%s] crawl failed", slug)
        finally:
            await db.commit()

        counters["elapsed_sec"] = round(time.monotonic() - started, 1)

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
        store_id = store.id  # см. crawl_store: ORM-атрибут в долгом цикле опасен

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
                        await _upsert_listing(db, store_id, dto)
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
            await _mark_error(db, store_id, f"blocked: {e}")
            counters["errors"] += 1
            await db.commit()
        except Exception as e:
            await _mark_error(db, store_id, f"refresh crash: {e}")
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
    db, store_id, counters: dict, mode: CrawlMode, limit: int | None = None
) -> str | None:
    """None = crawl выглядит здоровым. Иначе текст проблемы.

    Ловит «магазин сменил HTML → парсер тихо отдаёт ноль/мусор»: сравниваем
    результат прохода с историей листингов в БД. Для incremental пустой
    результат — норма (новинок нет), деградацию там не детектим. Прогон с
    limit искусственно обрезан — объёмные проверки для него тоже пропускаем.

    Принимает `store_id` скаляром, а НЕ ORM-объект: вызывается сразу после
    цикла обхода, где любая сбойная запись делает `db.rollback()` и протухляет
    `store`. Читать с него `store.id` = ленивая перечитка = синхронный IO в
    async-контексте (ночь 08-17, doctorhead: 3 358 позиций записаны, но обход
    помечен провалившимся из-за MissingGreenlet в этой строке).
    """
    existing = await db.scalar(
        select(func.count()).select_from(StoreListing).where(StoreListing.store_id == store_id)
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


async def _mark_success(db, store_id) -> None:
    """UPDATE по id, а не мутация ORM-объекта — см. `_smoke_check`.

    Успешный обход тоже мог пережить единичный сбой записи (сбойная страница →
    rollback → `store` протух), а мутация протухшего атрибута уронила бы уже
    сам финал: магазин остался бы без `last_successful_scrape_at` при полностью
    собранном каталоге.
    """
    await db.execute(
        update(Store)
        .where(Store.id == store_id)
        .values(last_successful_scrape_at=datetime.utcnow(), last_error=None)
    )


async def _mark_needs_browser(db, store_id, slug: str, msg: str) -> None:
    """UPDATE по id — см. `_mark_error`.

    `requires_browser` выставляем безусловно: прочитать текущее значение с
    протухшего ORM-объекта нельзя, а UPDATE идемпотентен.
    """
    await db.rollback()
    await db.execute(
        update(Store)
        .where(Store.id == store_id)
        .values(requires_browser=True, last_error=msg[:1000])
    )
    logger.warning("[%s] marked requires_browser=True (%s)", slug, msg)


async def _mark_error(db, store_id, msg: str) -> None:
    """UPDATE по id, а не мутация ORM-объекта.

    Этот путь вызывается именно тогда, когда всё сломалось: сессия могла
    остаться в failed-состоянии, а `store` — протухнуть после инвалидации
    соединения. Мутация атрибута тогда уронит сам обработчик ошибки, и магазин
    останется с зелёным статусом при мёртвом обходе.
    """
    await db.rollback()
    await db.execute(
        update(Store).where(Store.id == store_id).values(last_error=msg[:1000])
    )
