"""
API раздела «Маркет» (MARKET_AND_PRICE_DRAWER.md §1.15).

Endpoints:
  GET  /api/market/stores                          — витрина магазинов с метриками
  GET  /api/market/stores/{slug}/listings          — карусель листингов магазина
  GET  /api/market/stores/{slug}/all               — пагинированная витрина магазина
  GET  /api/market/search                          — глобальный поиск по in_stock

`/api/market/new-arrivals` исторически живёт в `api/offers.py` (legacy «В наличии
сейчас» карусель в search.tsx) — оставляем как есть, новый endpoint не дублирует.

Format-mapping (для query-param `format`):
  - vinyl     → LP, 2xLP, EP, Single, 12", 7", 10", Box Set
  - cd        → CD, SACD
  - cassette  → Cassette
"""
from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime, timedelta
from typing import Iterable, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import async_session_maker, get_db
from app.models.record import Record
from app.schemas.offer import (
    MarketSearchItem,
    MarketStoreInfo,
    MarketCarouselItem,
    MarketFacetItem,
    MarketFacetsResponse,
)
from app.services.cache import cache
from app.services.cover_storage import (
    _download_cover_background,
    schedule_store_native_cover_cache,
)
from app.services.vinyl_color import sql_color_family

logger = logging.getLogger(__name__)

router = APIRouter()

STALE_AFTER_DAYS = 7
NEW_TODAY_HOURS = 24
NEW_ARRIVAL_DAYS = 30  # окно «недавно появился в продаже» (first_seen_at)
NEW_RELEASE_LOOKBACK_YEARS = 1  # «свежий релиз»: год ≥ текущий − 1

# ────────────────────────────────────────────────────────────────────────
# Фасеты фильтров: жанр (data-driven) + особенности.
#
# Жанр — канонический ключ (что шлёт Mobile) → ILIKE-паттерны. Порядок списка
# больше не диктует порядок чипов: /facets сортирует их по count DESC, чтобы
# сверху лежало то, чего на складе реально много. Правишь тут — фронт
# подхватит через /facets, клиент про ключи ничего не знает.
# ────────────────────────────────────────────────────────────────────────
# ЖАНР МАТЧИМ ПО r.genre, СТИЛЬ — ТОЛЬКО КАК ЗАПАСНОЙ ВАРИАНТ.
#
# Верхний уровень Discogs — закрытый словарь из 15 значений («Rock»,
# «Folk, World, & Country», …), и в r.genre лежит именно он (склейка через
# ", "). Внутри этого словаря ни одно имя не является подстрокой другого,
# поэтому один ILIKE по r.genre разводит чипы без пересечений.
#
# Раньше матч шёл «genre OR style» ради recall на записях, у которых жанр не
# заполнен. Ценой была протечка: `%pop%` ловил стили Pop Rock / Synth-pop и
# затягивал в Pop половину рока, а `%contemporary%` приводил в Classical
# Beyoncé. После бэкфилла жанров из дампа r.genre есть почти у всех, и recall
# по стилю нужен только там, где жанра нет вовсе — туда он и убран.
#
# style_pats пустой список = у чипа нет запасного варианта (Classical: его
# суб-жанры Discogs и так всегда ставит вместе с верхним «Classical», а вот
# мусора стили тянут; это бывший GENRE_STRICT, выраженный данными).
GENRES: list[tuple[str, str, list[str], list[str]]] = [
    # key, label, genre_pats (по r.genre), style_pats (fallback, если жанра нет)
    ("rock",       "Рок",              ["%rock%"],
     ["%rock%", "%punk%", "%metal%", "%grunge%", "%shoegaze%", "%hardcore%"]),
    ("electronic", "Электроника",      ["%electronic%"],
     ["%electronic%", "%techno%", "%house%", "%ambient%", "%idm%", "%drum%bass%",
      "%synth%", "%downtempo%", "%trance%", "%dubstep%", "%electro%"]),
    ("pop",        "Поп",              ["%pop%"],
     ["%pop%", "%ballad%"]),
    ("hiphop",     "Хип-хоп",          ["%hip hop%", "%hip-hop%"],
     ["%hip hop%", "%hip-hop%", "%boom bap%", "%trap%", "%g-funk%", "%gangsta%", "%rap%"]),
    ("jazz",       "Джаз",             ["%jazz%"],
     ["%jazz%", "%bebop%", "%swing%", "%fusion%", "%bossa%"]),
    ("funk",       "Фанк / Соул",      ["%funk%", "%soul%"],
     ["%funk%", "%soul%", "%disco%", "%rhythm & blues%", "%r&b%"]),
    ("classical",  "Классика",         ["%classical%"],
     []),
    # Ниже — остальной верхний уровень Discogs. До бэкфилла жанров эти чипы
    # почти пустые и /facets их просто не отдаёт (count > 0), поэтому завести
    # их можно заранее: лишних чипов в UI не появится, а как только жанры
    # приедут — распределение станет честным, без «прочего» на четверть склада.
    ("folk",       "Фолк / Кантри",    ["%folk%", "%country%"],
     ["%folk%", "%country%", "%bluegrass%", "%singer%songwriter%"]),
    ("reggae",     "Регги",            ["%reggae%"],
     ["%reggae%", "%dub%", "%ska%", "%rocksteady%", "%dancehall%"]),
    ("blues",      "Блюз",             ["%blues%"],
     ["%delta blues%", "%chicago blues%", "%electric blues%", "%country blues%"]),
    ("latin",      "Латина",           ["%latin%"],
     ["%salsa%", "%samba%", "%tango%", "%cumbia%", "%mambo%", "%son %"]),
    ("soundtrack", "Саундтреки",       ["%stage%"],
     ["%soundtrack%", "%score%", "%musical%", "%theme%"]),
    ("children",   "Детское",          ["%children%"],
     ["%nursery%", "%story%"]),
    ("brass",      "Духовые / Марши",  ["%brass%", "%military%"],
     ["%marches%", "%big band%"]),
    ("nonmusic",   "Не музыка",        ["%non-music%"],
     ["%spoken word%", "%comedy%", "%field recording%", "%poetry%"]),
]
_GENRE_PATTERNS: dict[str, list[str]] = {key: pats for key, _l, pats, _s in GENRES}
_GENRE_STYLE_PATTERNS: dict[str, list[str]] = {key: pats for key, _l, _g, pats in GENRES}
_GENRE_LABELS: dict[str, str] = {key: label for key, label, _g, _s in GENRES}


def _genre_match_sql(
    key: str,
    param: str,
    style_param: str,
    genre_col: str = "r.genre",
    style_col: str = "r.style",
) -> str:
    """Предикат «запись относится к жанру `key`».

    Жанр заполнен → решает только он. Пусто → пробуем стиль (если у чипа есть
    запасные паттерны). Две ветки взаимоисключающие, поэтому запись не может
    попасть в чип и по жанру, и по стилю — двойного счёта в фасетах нет.
    """
    has_genre = f"({genre_col} IS NOT NULL AND {genre_col} <> '')"
    by_genre = f"{has_genre} AND {genre_col} ILIKE ANY(:{param})"
    if not _GENRE_STYLE_PATTERNS.get(key):
        return f"({by_genre})"
    by_style = f"NOT {has_genre} AND {style_col} ILIKE ANY(:{style_param})"
    return f"(({by_genre}) OR ({by_style}))"

# Особенности: ключ → (label, SQL-предикат). Предикаты — доверенные строки (не
# пользовательский ввод), sql_color_family подставляет только имя колонки.
_COLORED_PRED = (
    f"(({sql_color_family('sl.vinyl_color_raw')}) IS NOT NULL "
    f"AND ({sql_color_family('sl.vinyl_color_raw')}) <> 'black')"
)
# «Новинки» (вариант C): свежий релиз (r.year ≥ текущий−1) И недавно появился в
# продаже (first_seen ≤ 30д). Только first_seen мало: при онбординге магазина ВСЕ
# его листинги (включая советское старьё) получают свежий first_seen → в
# «Новинках» висело бы старьё. Двойное условие оставляет реально новое.
_NEW_PRED = "sl.first_seen_at >= :new_cutoff AND r.year >= :new_year"
FEATURES: list[tuple[str, str, str]] = [
    ("colored", "Цветной винил", _COLORED_PRED),
    ("limited", "Лимитка",       "r.is_limited = true"),
    ("new",     "Новинки",       _NEW_PRED),
]
_FEATURE_LABELS: dict[str, str] = {key: label for key, label, _pred in FEATURES}
_FEATURE_PREDS: dict[str, str] = {key: pred for key, _label, pred in FEATURES}


def _filters_clause(
    genre: Optional[list[str]],
    colored: bool,
    limited: bool,
    new: bool,
) -> tuple[str, dict]:
    """(SQL fragment, bind params) для фильтров жанра и особенностей.

    Пустые фильтры → ("", {}) → поведение как без фильтров. Неизвестные ключи
    жанра тихо игнорируются (нет паттернов → не в clause).
    """
    sql = ""
    params: dict = {}
    if genre:
        # По жанру — OR предикатов, а не один общий массив паттернов: у каждого
        # чипа свои наборы для genre и для style, склеить их в один ILIKE ANY
        # нельзя. Неизвестные ключи отсеиваются здесь же.
        preds: list[str] = []
        for key in genre:
            pats = _GENRE_PATTERNS.get(key)
            if not pats:
                continue
            param = f"genre_pats_{key}"
            style_param = f"style_pats_{key}"
            preds.append(_genre_match_sql(key, param, style_param))
            params[param] = pats
            style_pats = _GENRE_STYLE_PATTERNS.get(key)
            if style_pats:
                params[style_param] = style_pats
        if preds:
            sql += " AND (" + " OR ".join(preds) + ")"
    if colored:
        sql += f" AND {_FEATURE_PREDS['colored']}"
    if limited:
        sql += f" AND {_FEATURE_PREDS['limited']}"
    if new:
        sql += f" AND {_FEATURE_PREDS['new']}"
        params["new_cutoff"] = datetime.utcnow() - timedelta(days=NEW_ARRIVAL_DAYS)
        params["new_year"] = datetime.utcnow().year - NEW_RELEASE_LOOKBACK_YEARS
    return sql, params

# Cache-namespace зашит с версией: при изменении формы ответа (например,
# дедупа по master_id вместо record_id) бампаем суффикс — старые ключи
# в Redis самотухнут по TTL, а свежие запросы сразу получают новую логику.
CACHE_NS_STORES = "market_stores:v3"
CACHE_NS_STORE_LISTINGS = "market_store_listings:v4"
CACHE_NS_SEARCH = "market_search:v10"  # v10: жанр матчится по r.genre, style — только fallback
CACHE_TTL_STORES = 1800       # 30 мин — список магазинов меняется редко
CACHE_TTL_LISTINGS = 600      # 10 мин — карусели чаще обновляем
CACHE_TTL_SEARCH = 300        # 5 мин — поиск свежее

# Cover URL prefer-local: если cover уже зеркалирован на сервер
# (cover_local_path заполнен через bulk_mirror / _download_cover_background),
# отдаём /uploads/covers/{id}.jpg — nginx раздаёт мгновенно. Иначе fallback:
# на Discogs CDN из record, на raw_payload листинга. Используется во всех
# 3 market-эндпоинтах (carousel / store-all / global search). При смене
# выражения бампать cache namespace versions выше.
#
# WS1.2: для discogs-записей отдаём self-healing путь `/covers/{discogs_id}.jpg`
# (nginx `/covers/` location: disk-hit → отдаёт мгновенно; disk-miss →
# @covers_fallback → FastAPI get_cover → 302 + фоновое зеркалирование). Это
# чинит (а) серые квадраты после LRU-эвикции зеркала, (б) проактивно зеркалит
# записи у которых cover_image_url ещё живой но зеркала нет. Мостим только когда
# есть источник (local ИЛИ cover_image_url) — иначе get_cover вернёт 404 и мы
# потеряем store-фото. Store-native (discogs_id IS NULL) отдаём по
# `/covers/store/{uuid}.jpg` (== '/' || cover_local_path). При смене выражения
# бампать cache namespace versions выше.
_COVER_BRIDGE = (
    "CASE "
    "WHEN r.discogs_id IS NOT NULL "
    "AND (r.cover_local_path IS NOT NULL OR r.cover_image_url IS NOT NULL) "
    "THEN '/covers/' || r.discogs_id || '.jpg' "
    "WHEN r.cover_local_path IS NOT NULL "
    "THEN '/' || r.cover_local_path END"
)
_COVER_EXPR_LISTING = (
    f"COALESCE({_COVER_BRIDGE}, r.cover_image_url, sl.raw_payload->>'image_url')"
)
# Для /market/search финальный SELECT идёт по agg-CTE (нет `sl` в scope) —
# store-фото самого дешёвого листинга тащим через agg.chosen_store_photo,
# чтобы записи только со store-фото (проходят фильтр) не отдавались с NULL
# cover (баг серых квадратов в search).
_COVER_EXPR_SEARCH_FINAL = (
    f"COALESCE({_COVER_BRIDGE}, r.cover_image_url, agg.chosen_store_photo)"
)


# ────────────────────────────────────────────────────────────────────────
# Format-filter — нормализованные значения формата → SQL LIKE pattern.
# Бэкап если infer_format не нормализовал — ловим самые частые написания.
# ────────────────────────────────────────────────────────────────────────


# ────────────────────────────────────────────────────────────────────────
# Прелоад обложек: после ответа Маркета сразу пускаем фоновую корутину,
# которая зеркалит обложки на наш сервер. Эффект:
#   • при следующем визите nginx найдёт covers/{discogs_id}.jpg → отдаст
#     без обращения к Discogs (если URL когда-нибудь перейдёт на наш прокси);
#   • store-native обложки страхуются от 404 со стороны CDN магазина —
#     даже если он удалит товар, у нас останется зеркало;
#   • в моменте юзер ничего не теряет: download fire-and-forget,
#     ответ Маркета не блокируется.
# Идемпотентно — _download_cover_background / schedule_store_native_cover_cache
# проверяют существование файла перед скачиванием. Burst-защита: дедупа по
# record_id нет, но дешёво — повторные вызовы быстро возвращаются.
# ────────────────────────────────────────────────────────────────────────


def schedule_market_cover_preload(record_ids: Iterable[uuid.UUID]) -> None:
    """fire-and-forget зеркалирование обложек после market-эндпоинтов."""
    ids = [r for r in record_ids if r is not None]
    if not ids:
        return
    asyncio.create_task(_preload_covers_background(ids))


async def _preload_covers_background(record_ids: list[uuid.UUID]) -> None:
    """Берёт записи одним SELECT и пускает download per-record."""
    async with async_session_maker() as db:
        res = await db.execute(
            select(
                Record.id, Record.discogs_id, Record.source,
                Record.cover_image_url, Record.cover_local_path,
            ).where(Record.id.in_(record_ids))
        )
        rows = res.all()

    for row in rows:
        if row.cover_local_path or not row.cover_image_url:
            continue
        try:
            if row.source == "store":
                schedule_store_native_cover_cache(row.id, row.cover_image_url)
            elif row.discogs_id:
                asyncio.create_task(
                    _download_cover_background(row.discogs_id, row.cover_image_url)
                )
        except Exception:
            logger.exception("market preload cover failed for record %s", row.id)


def _format_clause(fmt: Optional[str]) -> tuple[str, dict]:
    """Возвращает (SQL fragment, bind params) для фильтра формата."""
    if not fmt:
        return ("", {})
    if fmt == "vinyl":
        # LP / 2xLP / 3xLP / EP / Single / Box Set + raw 12"/7"/10".
        # Двойной гейт: listing format_raw (что распарсил магазин) И, если у
        # записи есть discogs format_type, он тоже должен быть vinyl. Иначе
        # vinyl-листинг, ошибочно смэтченный на CD-запись, всплывал бы под
        # фильтром «Винил» с подписью «CD» (баг рассинхрона listing↔record).
        return (
            " AND (sl.format_raw ILIKE ANY(:vinyl_fmts) OR sl.format_raw ~ :vinyl_re)"
            " AND (r.format_type IS NULL OR r.format_type ILIKE '%vinyl%')",
            {
                "vinyl_fmts": ["LP", "2xLP", "3xLP", "EP", "Single", "Box Set"],
                "vinyl_re": r'^(\d+x?LP|12"|10"|7")',
            },
        )
    if fmt == "cd":
        return (
            " AND sl.format_raw ILIKE ANY(:cd_fmts)"
            " AND (r.format_type IS NULL OR r.format_type ILIKE '%cd%')",
            {"cd_fmts": ["CD", "2CD", "SACD"]},
        )
    if fmt == "cassette":
        return (
            " AND sl.format_raw ILIKE 'cassette%'"
            " AND (r.format_type IS NULL OR r.format_type ILIKE '%cassette%')",
            {},
        )
    raise HTTPException(400, f"Unknown format filter: {fmt}")


# ────────────────────────────────────────────────────────────────────────
# GET /api/market/stores — витрина магазинов
# ────────────────────────────────────────────────────────────────────────


@router.get(
    "/market/stores",
    response_model=list[MarketStoreInfo],
    summary="Витрина активных магазинов с метриками (для разделов Маркета)",
)
async def list_market_stores(
    min_in_stock: int = Query(
        1,
        ge=0,
        description=(
            "Минимум in_stock МАТЧЕННЫХ листингов с обложкой чтобы магазин "
            "показывался. По умолчанию 1 — даже только что подключённый магазин "
            "с парой матчей попадает в витрину. Карусель сама обрежется до "
            "доступных карточек."
        ),
    ),
    db: AsyncSession = Depends(get_db),
) -> list[MarketStoreInfo]:
    cache_key = f"stores:{min_in_stock}"
    cached = await cache.get(CACHE_NS_STORES, cache_key)
    if cached is not None:
        return [MarketStoreInfo.model_validate(item) for item in cached]

    # WS4.1 — читаем из matview market_store_stats (per-request агрегация
    # оффлоадится туда; REFRESH каждые ~15м фоновым джобом). FILTER-условия и
    # временные пороги (7d stale / 24h new) зашиты в саму matview, поэтому
    # консистентны с каруселями/сеткой. min_in_stock фильтруем при чтении.
    sql = text(
        """
        SELECT slug, name, logo_url, rating,
               in_stock_count, avg_price_rub, new_today_count
        FROM market_store_stats
        WHERE in_stock_count >= :min_in_stock
        ORDER BY rating DESC NULLS LAST, name ASC
        """
    )
    rows = (
        await db.execute(sql, {"min_in_stock": min_in_stock})
    ).mappings().all()

    items = [
        MarketStoreInfo(
            slug=row["slug"],
            name=row["name"],
            logo_url=row["logo_url"],
            rating=float(row["rating"] or 0),
            in_stock_count=row["in_stock_count"],
            avg_price_rub=row["avg_price_rub"],
            new_today_count=row["new_today_count"],
        )
        for row in rows
    ]

    await cache.set(
        CACHE_NS_STORES,
        cache_key,
        [it.model_dump(mode="json") for it in items],
        ttl=CACHE_TTL_STORES,
    )
    return items


# ────────────────────────────────────────────────────────────────────────
# GET /api/market/stores/{slug}/listings — горизонтальная карусель магазина
# ────────────────────────────────────────────────────────────────────────


@router.get(
    "/market/stores/{slug}/listings",
    response_model=list[MarketCarouselItem],
    summary="Карусель листингов магазина (горизонтальная витрина в Маркете)",
)
async def get_store_listings(
    slug: str,
    limit: int = Query(20, ge=1, le=50),
    sort: Literal["newest", "price_asc"] = Query("newest"),
    db: AsyncSession = Depends(get_db),
) -> list[MarketCarouselItem]:
    cache_key = f"listings:{slug}:{sort}:{limit}"
    cached = await cache.get(CACHE_NS_STORE_LISTINGS, cache_key)
    if cached is not None:
        return [MarketCarouselItem.model_validate(item) for item in cached]

    cutoff = datetime.utcnow() - timedelta(days=STALE_AFTER_DAYS)
    # Outer ORDER BY работает с колонками CTE — без `sl.` префикса.
    order_clause = (
        "first_seen_at DESC" if sort == "newest"
        else "price_rub ASC NULLS LAST"
    )

    # DISTINCT ON по дедуп-ключу: discogs_master_id если есть, иначе r.id.
    # Discogs группирует пресс-версии (EU/US, цвета винила) под один master_id —
    # без этого карусель показывала бы 3-4 идентичные карточки RHCP «Californication
    # 2024». Внутри master выбираем самый дешёвый листинг.
    # Опирается на функциональный индекс ix_records_dedup_key (см. миграцию
    # 20260526_dedup_idx). Без него Postgres делает sort-by-all-rows → таймаут.
    sql = text(
        f"""
        WITH ranked AS (
            SELECT DISTINCT ON (COALESCE(r.discogs_master_id, r.id::text))
                sl.matched_record_id AS record_id,
                sl.price_rub,
                sl.first_seen_at,
                s.slug AS store_slug,
                r.discogs_id, r.artist, r.title, r.year,
                COALESCE(r.format_type, sl.format_raw) AS format_type,
                {_COVER_EXPR_LISTING} AS cover_image_url
            FROM store_listings sl
            JOIN stores s ON s.id = sl.store_id
            JOIN records r ON r.id = sl.matched_record_id
            WHERE s.slug = :slug
              AND s.is_active = true
              AND sl.status = 'in_stock'
              AND sl.matched_record_id IS NOT NULL
              AND sl.price_rub IS NOT NULL
              AND sl.last_seen_at >= :cutoff
              AND r.merged_into_id IS NULL
              AND COALESCE(r.cover_local_path, r.cover_image_url, sl.raw_payload->>'image_url') IS NOT NULL
            ORDER BY COALESCE(r.discogs_master_id, r.id::text), sl.price_rub ASC NULLS LAST
        )
        SELECT * FROM ranked
        ORDER BY {order_clause}
        LIMIT :limit
        """
    )
    rows = (await db.execute(sql, {"slug": slug, "cutoff": cutoff, "limit": limit})).mappings().all()

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
        CACHE_NS_STORE_LISTINGS,
        cache_key,
        [it.model_dump(mode="json") for it in items],
        ttl=CACHE_TTL_LISTINGS,
    )
    schedule_market_cover_preload(it.record_id for it in items)
    return items


# ────────────────────────────────────────────────────────────────────────
# GET /api/market/stores/{slug}/all — полная витрина магазина (paginated)
# ────────────────────────────────────────────────────────────────────────


@router.get(
    "/market/stores/{slug}/all",
    response_model=list[MarketSearchItem],
    summary="Полная витрина магазина (/market/store/[slug] экран)",
)
async def get_store_all(
    slug: str,
    q: str | None = Query(None, description="Текстовый поиск по artist/title"),
    format: str | None = Query(None, description="vinyl | cd | cassette"),
    genre: str | None = Query(None, description="Ключи жанров через запятую (мульти): rock,jazz"),
    colored: bool = Query(False, description="Только цветной винил"),
    limited: bool = Query(False, description="Только лимитки (r.is_limited)"),
    new: bool = Query(False, description="Только новинки (свежий релиз + first_seen ≤ 30 дней)"),
    sort: Literal["newest", "price_asc"] = Query("price_asc"),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
) -> list[MarketSearchItem]:
    """Витрина одного магазина. Набор фильтров тот же, что у `/market/search`
    (формат + жанр + особенности) — чтобы «провалившись» в магазин юзер не терял
    фильтрацию, доступную на общей витрине."""
    genre_list = [g for g in (genre.split(",") if genre else []) if g]
    fmt_sql, fmt_params = _format_clause(format)
    filt_sql, filt_params = _filters_clause(genre_list, colored, limited, new)
    cutoff = datetime.utcnow() - timedelta(days=STALE_AFTER_DAYS)

    # Outer ORDER BY ссылается на CTE-колонки — без `sl.` префикса.
    # dedup_key — уникальный tiebreaker (см. комментарий в /market/search):
    # без него страницы offset-пагинации перемешиваются на равных ценах.
    order_clause = (
        "price_rub ASC NULLS LAST, dedup_key" if sort == "price_asc"
        else "first_seen_at DESC, dedup_key"
    )

    q_clause = ""
    q_params: dict = {}
    if q:
        q_clause = " AND (r.artist ILIKE :q OR r.title ILIKE :q)"
        q_params["q"] = f"%{q}%"

    # /all — пагинированная витрина. Дедуп по master_id (см. /listings),
    # filter NULL cover — дырки портят сетку 2-колонок.
    sql = text(
        f"""
        WITH ranked AS (
            SELECT DISTINCT ON (COALESCE(r.discogs_master_id, r.id::text))
                COALESCE(r.discogs_master_id, r.id::text) AS dedup_key,
                sl.matched_record_id AS record_id,
                sl.price_rub,
                sl.first_seen_at,
                s.slug AS store_slug,
                r.discogs_id, r.artist, r.title, r.year,
                COALESCE(r.format_type, sl.format_raw) AS format_type,
                {_COVER_EXPR_LISTING} AS cover_image_url
            FROM store_listings sl
            JOIN stores s ON s.id = sl.store_id
            JOIN records r ON r.id = sl.matched_record_id
            WHERE s.slug = :slug
              AND s.is_active = true
              AND sl.status = 'in_stock'
              AND sl.matched_record_id IS NOT NULL
              AND sl.price_rub IS NOT NULL
              AND sl.last_seen_at >= :cutoff
              AND r.merged_into_id IS NULL
              AND COALESCE(r.cover_local_path, r.cover_image_url, sl.raw_payload->>'image_url') IS NOT NULL
              {fmt_sql}
              {filt_sql}
              {q_clause}
            ORDER BY COALESCE(r.discogs_master_id, r.id::text), sl.price_rub ASC NULLS LAST
        )
        SELECT * FROM ranked
        ORDER BY {order_clause}
        LIMIT :limit OFFSET :offset
        """
    )

    params = {
        "slug": slug, "cutoff": cutoff,
        "limit": limit, "offset": offset,
        **fmt_params, **filt_params, **q_params,
    }
    rows = (await db.execute(sql, params)).mappings().all()

    items = [
        MarketSearchItem(
            record_id=row["record_id"],
            discogs_id=row["discogs_id"],
            artist=row["artist"],
            title=row["title"],
            year=row["year"],
            format_type=row["format_type"],
            cover_image_url=row["cover_image_url"],
            min_price_rub=row["price_rub"],
            stores_with_stock=1,  # для one-store endpoint всегда 1
            cheapest_store_slug=row["store_slug"],
            first_seen_at=row["first_seen_at"],
        )
        for row in rows
    ]
    schedule_market_cover_preload(it.record_id for it in items)
    return items


# ────────────────────────────────────────────────────────────────────────
# GET /api/market/search — глобальный поиск по in-stock-листингам всех магазинов
# ────────────────────────────────────────────────────────────────────────


@router.get(
    "/market/search",
    response_model=list[MarketSearchItem],
    summary="Поиск по in-stock листингам всех активных магазинов",
)
async def search_market(
    q: str | None = Query(None, description="Текстовый поиск по artist/title"),
    format: str | None = Query(None, description="vinyl | cd | cassette"),
    genre: str | None = Query(None, description="Ключи жанров через запятую (мульти): rock,jazz"),
    colored: bool = Query(False, description="Только цветной винил"),
    limited: bool = Query(False, description="Только лимитки (r.is_limited)"),
    new: bool = Query(False, description="Только новинки (first_seen ≤ 30 дней)"),
    sort: Literal["price_asc", "newest"] = Query("price_asc"),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0, description="Сдвиг страницы (infinite scroll)"),
    db: AsyncSession = Depends(get_db),
) -> list[MarketSearchItem]:
    """
    Дедупликация: на один record_id — одна карточка с min_price + N магазинов.
    Если у юзера пустой `q` — возвращаем последние new-arrivals (sort=newest
    или sort=price_asc по дефолту самые дешёвые сверху).

    Пагинация — limit/offset. Клиент листает до пустой страницы; счётчики по
    каждой опции фильтра отдаёт `/market/facets`.
    """
    # genre приходит строкой «rock,jazz» — надёжнее array-сериализации на клиенте.
    genre_list = [g for g in (genre.split(",") if genre else []) if g]
    fmt_sql, fmt_params = _format_clause(format)
    filt_sql, filt_params = _filters_clause(genre_list, colored, limited, new)
    cutoff = datetime.utcnow() - timedelta(days=STALE_AFTER_DAYS)

    # Tiebreaker agg.dedup_key ОБЯЗАТЕЛЕН при offset-пагинации: у цены и даты
    # массово совпадают значения, а без уникального добивочного ключа Postgres
    # волен возвращать связанные строки в любом порядке → соседние страницы
    # дублируют одни карточки и теряют другие. dedup_key = GROUP BY-ключ, уникален.
    order_clause = (
        "min_price ASC NULLS LAST, agg.dedup_key" if sort == "price_asc"
        else "first_seen_at DESC, agg.dedup_key"
    )

    q_clause = ""
    q_params: dict = {}
    if q and len(q.strip()) >= 2:
        q_clause = " AND (r.artist ILIKE :q OR r.title ILIKE :q)"
        q_params["q"] = f"%{q.strip()}%"

    # Cache-key ОБЯЗАН включать все фильтры — иначе отфильтрованный результат
    # прилетит из кэша нефильтрованного запроса (или наоборот). genre сортируем
    # для стабильности ключа независимо от порядка чипов.
    genre_key = ",".join(sorted(genre_list)) if genre_list else ""
    cache_key = (
        # v2 в префиксе — версия жанровых паттернов: правишь GENRES/GENRE_STRICT,
        # бампаешь версию, иначе старые (неверные) выдачи доживут в кэше до TTL.
        f"search:v2:{q or ''}:{format or 'all'}:{sort}:{limit}:{offset}"
        f":g={genre_key}:c={int(colored)}:l={int(limited)}:n={int(new)}"
    )
    cached = await cache.get(CACHE_NS_SEARCH, cache_key)
    if cached is not None:
        return [MarketSearchItem.model_validate(item) for item in cached]

    # Дедуп: группируем по master_id (с fallback на r.id), чтобы разные
    # пресс-версии одного альбома не выдавались как идентичные карточки.
    # Внутри группы выбираем самый дешёвый record через ARRAY_AGG ORDER BY price → [1].
    sql = text(
        f"""
        WITH agg AS (
            SELECT
                COALESCE(r.discogs_master_id, r.id::text) AS dedup_key,
                MIN(sl.price_rub) AS min_price,
                COUNT(DISTINCT sl.store_id) AS stores_with_stock,
                MAX(sl.first_seen_at) AS first_seen_at,
                (ARRAY_AGG(s.slug ORDER BY sl.price_rub ASC NULLS LAST))[1] AS cheapest_store_slug,
                (ARRAY_AGG(r.id ORDER BY sl.price_rub ASC NULLS LAST))[1] AS chosen_record_id,
                (ARRAY_AGG(sl.raw_payload->>'image_url' ORDER BY sl.price_rub ASC NULLS LAST))[1] AS chosen_store_photo
            FROM store_listings sl
            JOIN stores s ON s.id = sl.store_id
            JOIN records r ON r.id = sl.matched_record_id
            WHERE s.is_active = true
              AND sl.status = 'in_stock'
              AND sl.matched_record_id IS NOT NULL
              AND sl.price_rub IS NOT NULL
              AND sl.last_seen_at >= :cutoff
              AND r.merged_into_id IS NULL
              AND COALESCE(r.cover_local_path, r.cover_image_url, sl.raw_payload->>'image_url') IS NOT NULL
              {fmt_sql}
              {filt_sql}
              {q_clause}
            GROUP BY COALESCE(r.discogs_master_id, r.id::text)
        )
        SELECT
            agg.chosen_record_id AS record_id, agg.min_price, agg.stores_with_stock,
            agg.first_seen_at, agg.cheapest_store_slug,
            r.discogs_id, r.artist, r.title, r.year, r.format_type,
            {_COVER_EXPR_SEARCH_FINAL} AS cover_image_url
        FROM agg
        JOIN records r ON r.id = agg.chosen_record_id
        ORDER BY {order_clause}
        LIMIT :limit OFFSET :offset
        """
    )

    params = {
        "cutoff": cutoff, "limit": limit, "offset": offset,
        **fmt_params, **filt_params, **q_params,
    }
    rows = (await db.execute(sql, params)).mappings().all()

    items = [
        MarketSearchItem(
            record_id=row["record_id"],
            discogs_id=row["discogs_id"],
            artist=row["artist"],
            title=row["title"],
            year=row["year"],
            format_type=row["format_type"],
            cover_image_url=row["cover_image_url"],
            min_price_rub=row["min_price"],
            stores_with_stock=row["stores_with_stock"],
            cheapest_store_slug=row["cheapest_store_slug"],
            first_seen_at=row["first_seen_at"],
        )
        for row in rows
    ]

    await cache.set(
        CACHE_NS_SEARCH,
        cache_key,
        [it.model_dump(mode="json") for it in items],
        ttl=CACHE_TTL_SEARCH,
    )
    schedule_market_cover_preload(it.record_id for it in items)
    return items


@router.get(
    "/market/facets",
    response_model=MarketFacetsResponse,
    summary="Доступные фильтры Маркета (жанры + особенности) со счётчиками",
)
async def market_facets(
    store: str | None = Query(
        None,
        description=(
            "Slug магазина — считать фасеты только по его складу (для экрана "
            "/market/store/[slug]). Без параметра — по всем активным магазинам."
        ),
    ),
    db: AsyncSession = Depends(get_db),
) -> MarketFacetsResponse:
    """Считает, сколько карточек в наличии под каждой опцией фильтра.

    База — та же, что у /market/search (active-магазин, in_stock, matched, есть
    обложка, не stale), дедуп по master_id. Возвращаем только опции с count > 0,
    чтобы Mobile не рисовал пустые чипы. Гранулярность:
      • genre / limited — на уровне записи (репрезентативный / bool_or);
      • colored / new    — на уровне листинга (bool_or) — группа считается, если
        ХОТЯ БЫ один её листинг цветной / свежий (так же, как фильтрует search).

    `store` сужает базу до одного магазина — иначе на его витрине рисовались бы
    чипы жанров, которых у него нет, и фильтр вёл бы в пустоту.
    """
    store_clause = " AND s.slug = :store" if store else ""
    cache_key = f"facets:v4:{store or 'all'}"
    cached = await cache.get(CACHE_NS_SEARCH, cache_key)
    if cached is not None:
        return MarketFacetsResponse.model_validate(cached)

    cutoff = datetime.utcnow() - timedelta(days=STALE_AFTER_DAYS)
    new_cutoff = datetime.utcnow() - timedelta(days=NEW_ARRIVAL_DAYS)
    new_year = datetime.utcnow().year - NEW_RELEASE_LOOKBACK_YEARS

    genre_selects = ",\n            ".join(
        f"count(*) FILTER (WHERE {_genre_match_sql(key, f'g_{key}', f's_{key}', 'genre', 'style')}) AS g_{key}"
        for key, _label, _pats, _spats in GENRES
    )
    genre_params: dict = {}
    for key, _label, pats, style_pats in GENRES:
        genre_params[f"g_{key}"] = pats
        if style_pats:
            genre_params[f"s_{key}"] = style_pats

    sql = text(
        f"""
        WITH agg AS (
            SELECT
                COALESCE(r.discogs_master_id, r.id::text) AS dedup_key,
                MIN(r.genre) AS genre,
                MIN(r.style) AS style,
                bool_or(r.is_limited) AS is_limited,
                bool_or({_COLORED_PRED}) AS colored,
                bool_or({_NEW_PRED}) AS is_new
            FROM store_listings sl
            JOIN stores s ON s.id = sl.store_id
            JOIN records r ON r.id = sl.matched_record_id
            WHERE s.is_active = true
              AND sl.status = 'in_stock'
              AND sl.matched_record_id IS NOT NULL
              AND sl.price_rub IS NOT NULL
              AND sl.last_seen_at >= :cutoff
              AND r.merged_into_id IS NULL
              AND COALESCE(r.cover_local_path, r.cover_image_url, sl.raw_payload->>'image_url') IS NOT NULL
              {store_clause}
            GROUP BY COALESCE(r.discogs_master_id, r.id::text)
        )
        SELECT
            {genre_selects},
            count(*) FILTER (WHERE colored) AS f_colored,
            count(*) FILTER (WHERE is_limited) AS f_limited,
            count(*) FILTER (WHERE is_new) AS f_new
        FROM agg
        """
    )
    sql_params: dict = {
        "cutoff": cutoff, "new_cutoff": new_cutoff, "new_year": new_year, **genre_params,
    }
    if store:
        sql_params["store"] = store
    row = (await db.execute(sql, sql_params)).mappings().one()

    # Сортировка по count DESC, а не по порядку GENRES: чипов теперь 15 (весь
    # верхний уровень Discogs), они не влезают в экран и скроллятся вбок —
    # значит первым должно лежать то, чего на складе больше всего. Ключ
    # сортировки дополняем `key`, иначе при равных count порядок между
    # запросами плавал бы и чипы перескакивали. У `?store=` порядок свой —
    # ровно то, что нужно: у джазовой лавки сверху джаз.
    genres = sorted(
        (
            MarketFacetItem(key=key, label=label, count=row[f"g_{key}"])
            for key, label, _pats, _spats in GENRES
            if (row[f"g_{key}"] or 0) > 0
        ),
        key=lambda item: (-item.count, item.key),
    )
    features = [
        MarketFacetItem(key=key, label=_FEATURE_LABELS[key], count=row[col])
        for key, col in (("colored", "f_colored"), ("limited", "f_limited"), ("new", "f_new"))
        if (row[col] or 0) > 0
    ]

    resp = MarketFacetsResponse(genres=genres, features=features)
    await cache.set(CACHE_NS_SEARCH, cache_key, resp.model_dump(mode="json"), ttl=CACHE_TTL_SEARCH)
    return resp
