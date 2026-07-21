"""
API для работы с пластинками
"""
import asyncio
import logging
import re
from datetime import datetime
from uuid import UUID

import httpx

logger = logging.getLogger(__name__)

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status, Query, Response
from sqlalchemy import select, text, func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.cache import cache, TTL_MASTER_VERSIONS

from app.database import get_db
from app.models.user import User
from app.models.record import Record
from app.api.auth import get_current_user, get_current_user_optional
from app.services.exchange import get_usd_rub_rate
from app.services.pricing import PricingParams, estimate_rub, effective_markup, is_local_country
from app.services.marketplace_pricing import marketplace_price_range
from app.config import get_settings
from app.schemas.record import (
    RecordCreate,
    RecordResponse,
    RecordSearchResult,
    RecordSearchResponse,
    ReleaseSearchResult,
    CoverScanRequest,
    CoverScanResponse,
    MasterSearchResponse,
    MasterRelease,
    MasterVersion,
    MasterVersionsResponse,
    ReleaseSearchResponse,
    ArtistSearchResponse,
    Artist,
    PreflightRequest,
    PreflightResponse,
    SpotifyAlbumCandidate,
    SpotifySearchResponse,
    UserRecordCreate,
    UserRecordUpdate,
)
from app.services.discogs import DiscogsService
from app.services.discogs_oauth import user_creds
from app.services.rate_limiter import Priority
from app.services.artist_name import clean_artist_name
from app.services.openai_vision import OpenAIVisionService, CoverRecognitionError
from app.database import async_session_maker

router = APIRouter()


async def _enrich_search_results_with_rarity(
    items: list,
    db: AsyncSession,
    *,
    id_attr: str,
    format_attr: str,
) -> None:
    """
    Cheap rarity enrichment for search/release lists:
      - parses is_limited from format string token match
      - pulls is_canon/is_collectible/is_limited/is_hot from local Record table
        for any release the backend has previously seen.

    Items without a DB row still get is_limited if the format string matches.
    No external Discogs calls — bounded cost (single SQL IN-query).
    """
    if not items:
        return

    for item in items:
        fmt_lower = (getattr(item, format_attr, None) or "").lower()
        if any(tok in fmt_lower for tok in DiscogsService.LIMITED_TOKENS):
            item.is_limited = True

    ids = [getattr(item, id_attr) for item in items if getattr(item, id_attr, None)]
    if not ids:
        return
    rows = await db.execute(
        select(
            Record.discogs_id,
            Record.is_canon,
            Record.is_collectible,
            Record.is_limited,
            Record.is_hot,
        ).where(Record.discogs_id.in_(ids))
    )
    flags_by_id = {
        row.discogs_id: (row.is_canon, row.is_collectible, row.is_limited, row.is_hot)
        for row in rows
    }
    for item in items:
        f = flags_by_id.get(getattr(item, id_attr, None))
        if f:
            item.is_canon = item.is_canon or f[0]
            item.is_collectible = item.is_collectible or f[1]
            item.is_limited = item.is_limited or f[2]
            item.is_hot = item.is_hot or f[3]


async def _enrich_response_with_rub(
    response: RecordResponse,
    record: Record | None = None,
    db: AsyncSession | None = None,
) -> RecordResponse:
    """Заполняет рублёвые цены и `price_source` в ответе.

    Для локальных (РФ/СССР) релизов:
      1. marketplace_active     — активные офферы в RU-магазинах
      2. marketplace_historical — архивные офферы за 365 дней (только median)
      3. discogs_raw            — USD × курс ЦБ без коэффициента (fallback)

    Для импорта остаётся компонентная формула из pricing.py (discogs_import_estimate).
    """
    # Цвет прототипа/чипа — резолвим из реального оффера (Вариант B), чтобы Mobile
    # отрисовал верный цвет с первого кадра без «моргания». Делаем ДО ценовых
    # early-return'ов, чтобы поле было на всех путях. Фолбэк — Discogs-цвет; ошибку
    # глотаем, ответ не блокируем.
    response.display_vinyl_color = response.vinyl_color_raw
    if record is not None and db is not None:
        try:
            from app.api.offers import resolve_display_vinyl_color

            resolved = await resolve_display_vinyl_color(
                record.id, response.vinyl_color_raw, db
            )
            if resolved:
                response.display_vinyl_color = resolved
        except Exception:
            logger.exception("Failed to resolve display vinyl color")

    base_price = response.estimated_price_median or response.estimated_price_min
    if not base_price:
        # Discogs-оценки нет — единственный случай, когда цена уходит пустой:
        # store-native релиз (discogs_id=NULL, напр. «Антоха МС – Родня») либо
        # РФ-пресс, которого нет в маркетплейсе Discogs. СТРОГО здесь, не трогая
        # пути с уже существующей ценой, пробуем реальные листинги магазинов.
        # Медиана по matched_record_id уже учитывает «качество версии» (разные
        # прессы матчер разводит в разные Record). Ничего не нашли — возвращаем
        # как раньше, пусто. Работает для любой страны: marketplace_price_range
        # фильтрует по matched_record_id, не по country.
        if record is not None and db is not None:
            try:
                market = await marketplace_price_range(record.id, db)
                if market:
                    response.price_source = market.source
                    response.price_offers_count = market.offers_count
                    response.estimated_price_min_rub = market.min_rub
                    response.estimated_price_median_rub = market.median_rub
                    response.estimated_price_max_rub = market.max_rub
                    # base_price нет → markup относительно Discogs-оценки не определён
                    response.ru_markup = None
            except Exception:
                logger.exception(
                    "Failed to fetch marketplace price for base-less record %s",
                    getattr(record, "id", None),
                )
        return response
    try:
        rate = await get_usd_rub_rate()
        params = PricingParams.from_settings(get_settings())
        discogs_data = record.discogs_data if record else None
        response.usd_rub_rate = rate

        # Локальный релиз — пробуем marketplace, потом fallback на USD × курс
        if is_local_country(response.country):
            market = None
            if record and db is not None:
                market = await marketplace_price_range(record.id, db)

            if market:
                response.price_source = market.source
                response.price_offers_count = market.offers_count
                response.estimated_price_min_rub = market.min_rub
                response.estimated_price_median_rub = market.median_rub
                response.estimated_price_max_rub = market.max_rub
                # markup относительно "честной" USD × rate — показывает, насколько
                # реальная RU-цена выше Discogs-оценки
                median_rub = market.median_rub
                if median_rub and base_price and rate > 0:
                    response.ru_markup = round(
                        median_rub / (float(base_price) * rate), 2
                    )
                else:
                    response.ru_markup = 1.0
                return response

            # fallback: USD × курс без коэффициента
            response.price_source = "discogs_raw"
            response.ru_markup = 1.0
            response.estimated_price_min_rub = (
                round(float(response.estimated_price_min) * rate, 0)
                if response.estimated_price_min else None
            )
            response.estimated_price_median_rub = (
                round(float(response.estimated_price_median) * rate, 0)
                if response.estimated_price_median else None
            )
            response.estimated_price_max_rub = (
                round(float(response.estimated_price_max) * rate, 0)
                if response.estimated_price_max else None
            )
            return response

        # Импорт — компонентная формула как было
        def _calc(price) -> float | None:
            if price is None:
                return None
            return estimate_rub(
                float(price),
                response.country,
                rate,
                params,
                format_type=response.format_type,
                format_description=response.format_description,
                discogs_data=discogs_data,
            )

        response.price_source = "discogs_import_estimate"
        response.ru_markup = effective_markup(
            float(base_price),
            response.country,
            rate,
            params,
            format_type=response.format_type,
            format_description=response.format_description,
            discogs_data=discogs_data,
        )
        response.estimated_price_min_rub = _calc(response.estimated_price_min)
        response.estimated_price_median_rub = _calc(response.estimated_price_median)
        response.estimated_price_max_rub = _calc(response.estimated_price_max)
    except Exception:
        logger.exception("Failed to enrich response with RUB prices")
    return response


async def _ensure_record_price_data(record: Record, db: AsyncSession) -> None:
    """Подтягивает цены из Discogs, если они отсутствуют в записи."""
    if record.estimated_price_min or record.estimated_price_median:
        return
    if not record.discogs_id:
        return
    try:
        discogs = DiscogsService()
        stats = await discogs._get_price_stats(record.discogs_id)
        if stats:
            lowest = stats.get("lowest_price", {}).get("value") if isinstance(stats.get("lowest_price"), dict) else stats.get("lowest_price")
            median = stats.get("median_price", {}).get("value") if isinstance(stats.get("median_price"), dict) else stats.get("median_price")
            highest = stats.get("highest_price", {}).get("value") if isinstance(stats.get("highest_price"), dict) else stats.get("highest_price")
            if lowest or median:
                record.estimated_price_min = lowest
                record.estimated_price_median = median
                record.estimated_price_max = highest
                await db.commit()
                await db.refresh(record)
    except Exception:
        logger.exception("Failed to ensure price data for record %s", record.discogs_id)


async def _ensure_record_price_data_bg(record_id: UUID, discogs_id: str) -> None:
    """Fire-and-forget версия — открывает собственную DB-сессию.

    Вызывается через asyncio.create_task() чтобы не блокировать ответ на
    детальную карточку: цены нужны для отображения, но не критичны для
    первого рендера — юзер получает карточку быстро, цены подтягиваются
    фоном (следующее открытие карточки уже покажет их из БД).
    """
    from app.database import async_session_maker
    try:
        async with async_session_maker() as db:
            from sqlalchemy import select as _select
            res = await db.execute(_select(Record).where(Record.id == record_id))
            rec = res.scalar_one_or_none()
            if rec and not rec.estimated_price_min and not rec.estimated_price_median:
                await _ensure_record_price_data(rec, db)
    except Exception:
        logger.exception("Background price fetch failed for record %s", record_id)


async def _enrich_stub_bg(record_id: UUID, discogs_id: str) -> None:
    """Фоновое обогащение stub-записи созданной из discogs_releases_index.

    Открывает собственную сессию чтобы не зависеть от lifetime request-сессии.
    Последовательно: payload (tracklist, master_id, cover) → artist (thumb) → price.
    Вызывается через asyncio.create_task() — не блокирует ответ.
    """
    from app.database import async_session_maker
    try:
        async with async_session_maker() as db:
            res = await db.execute(select(Record).where(Record.id == record_id))
            rec = res.scalar_one_or_none()
            if not rec:
                return
            await _ensure_record_discogs_payload(rec, db)
            await _ensure_record_artist_data(rec, db)
            await _ensure_record_price_data(rec, db)
    except Exception:
        logger.exception("_enrich_stub_bg failed for record %s (discogs_id=%s)", record_id, discogs_id)


# Various-artists маркеры: compilation, НЕ один артист. Name-search по ним
# подцепляет случайного Discogs-артиста (напр. 'V/A' → мис-атрибутированный
# 'A.V. Mittelstedt'), и карточка релиза ведёт на чужого человека. По таким
# токенам артиста не линкуем вовсе.
_VA_ARTIST_TOKENS = {
    "v/a", "va", "v.a", "v.a.", "various", "various artists",
    "разные исполнители", "сборник",
}


def _is_various_artist(name: str | None) -> bool:
    return bool(name) and name.strip().lower().rstrip(".") in _VA_ARTIST_TOKENS


async def _ensure_record_artist_data(record: Record, db: AsyncSession) -> None:
    """
    Обогащает запись данными артиста (artist_id, artist_thumb_image_url),
    если они отсутствуют в discogs_data. Обновляет запись в БД для кэширования.
    Для store-native (нет discogs_id) пробует найти артиста через text-search.
    """
    discogs_data = record.discogs_data or {}

    # Уже есть данные артиста — ничего не делаем
    if discogs_data.get("artist_thumb_image_url"):
        return

    artist_id = discogs_data.get("artist_id")

    # Если artist_id нет — достаём из Discogs по release ID
    if not artist_id and record.discogs_id:
        try:
            discogs = DiscogsService()
            release_raw = await discogs._get(
                f"{discogs.BASE_URL}/releases/{record.discogs_id}"
            )
            artists = release_raw.get("artists", [])
            if artists:
                artist_id = str(artists[0].get("id"))
        except Exception:
            logger.exception("Failed to fetch artist_id from Discogs for record %s", record.discogs_id)
            return

    # Store-native fallback: ищем артиста по имени через /database/search?type=artist.
    # Берём первый результат только если имя совпадает после нормализации,
    # иначе можем подцепить рандомного однофамильца. Various-artists (V/A и т.п.)
    # пропускаем — это compilation, не один артист.
    if not artist_id and record.artist and not _is_various_artist(record.artist):
        try:
            discogs = DiscogsService()
            search_resp = await discogs.search_artists(record.artist, per_page=5)
            wanted = record.artist.strip().lower()
            for r in search_resp.results:
                if r.name.strip().lower() == wanted:
                    artist_id = r.artist_id
                    break
        except Exception:
            logger.exception(
                "Failed to search artist for store-native record %s (artist=%s)",
                record.id, record.artist,
            )

    if not artist_id:
        return

    # Получаем миниатюру артиста
    try:
        discogs = DiscogsService()
        artist_thumb = await discogs._get_artist_thumb(artist_id)
        if artist_thumb:
            # Обновляем discogs_data — переприсваиваем для корректного отслеживания SQLAlchemy
            updated_data = {**discogs_data, "artist_id": artist_id, "artist_thumb_image_url": artist_thumb}
            record.discogs_data = updated_data
            await db.commit()
            await db.refresh(record)
    except Exception:
        logger.exception("Failed to get artist thumb for artist %s", artist_id)


async def _ensure_record_discogs_payload(record: Record, db: AsyncSession) -> None:
    """
    Подтягивает полный Discogs-release payload, если запись минтилась без него.

    Сценарий: market-matcher создал Record из листинга магазина с минимальным
    набором полей (artist/title/barcode/cover) — без tracklist, label,
    catalog_number, master_id. Юзер открывает детальную → видит обложку,
    но нет треклиста и других версий релиза.

    Эта функция один раз тянет полный release из Discogs и обновляет запись.
    Дальше всё в БД, повторных Discogs-вызовов не будет.

    Условие срабатывания: tracklist пустой/null И есть discogs_id.
    """
    if not record.discogs_id:
        return
    if record.tracklist:  # уже есть — пропускаем
        return

    # Бесплатные источники треклиста ДО Discogs (rate-limited): MB per-release
    # (точно, винил-позиции) → Deezer album-level (приблизительно). Мгновенный
    # треклист без токена Discogs; остальной payload (кредиты/цены) добьёт
    # Discogs фоном. Discogs остаётся точным источником прессинга.
    free_tl = await _free_tracklist(record, db)
    if free_tl:
        record.tracklist = free_tl
        await db.commit()
        # Фоновый Discogs-энрич для кредитов/цен/точного прессинга — не блокирует.
        _schedule_discogs_payload_enrich(record.discogs_id)
        return

    try:
        discogs = DiscogsService()
        data = await discogs.get_release(record.discogs_id, priority=Priority.DETAIL)
    except Exception:
        logger.exception("Failed to enrich record %s with Discogs payload", record.discogs_id)
        return

    if not data:
        return

    await _apply_discogs_release(record, data, db)


async def _apply_discogs_release(record: Record, data: dict, db: AsyncSession) -> None:
    """Заполняет пустые поля записи из Discogs release payload. Переиспользуется
    inline-путём _ensure и фоновым _schedule_discogs_payload_enrich (после того
    как треклист уже проставлен из бесплатного источника — здесь он не трогается,
    т.к. guard `if not record.tracklist`)."""
    # Заполняем поля только если они пустые — не затираем уже существующие
    # (например, label из листинга магазина может быть точнее чем Discogs).
    changed = False
    if not record.tracklist and data.get("tracklist"):
        record.tracklist = data["tracklist"]
        changed = True
    if not record.discogs_master_id and data.get("master_id"):
        record.discogs_master_id = data["master_id"]
        changed = True
    if not record.label and data.get("label"):
        record.label = data["label"]
        changed = True
    if not record.catalog_number and data.get("catalog_number"):
        record.catalog_number = data["catalog_number"]
        changed = True
    if not record.year and data.get("year"):
        record.year = data["year"]
        changed = True
    if not record.country and data.get("country"):
        record.country = data["country"]
        changed = True
    if not record.genre and data.get("genre"):
        record.genre = data["genre"]
        changed = True
    if not record.style and data.get("style"):
        record.style = data["style"]
        changed = True
    if not record.format_type and data.get("format"):
        record.format_type = data["format"]
        changed = True
    # Обложка — ключевое поле для UI. Записи из dump-индекса создаются с NULL,
    # здесь добираем из полного Discogs payload (cover_image / thumb_image).
    if not record.cover_image_url and data.get("cover_image"):
        record.cover_image_url = data["cover_image"]
        changed = True
    if not record.thumb_image_url and data.get("thumb_image"):
        record.thumb_image_url = data["thumb_image"]
        changed = True

    # Discogs не дал обложку → бесплатный fallback через Cover Art Archive
    # (barcode → MusicBrainz MBID → CAA). Не тратит Discogs rate-limit.
    if not record.cover_image_url and record.barcode:
        from app.services.cover_fallback import cover_url_by_barcode
        caa_url = await cover_url_by_barcode(record.barcode)
        if caa_url:
            record.cover_image_url = caa_url
            changed = True

    # discogs_data МЕРДЖИМ, не перезаписываем — иначе теряем поля, которые
    # уже положил _ensure_record_artist_data (artist_id, artist_thumb_image_url).
    # data — свежий Discogs payload, может НЕ содержать artist_thumb_image_url
    # (он вычисляется отдельным запросом /artists/{id}). При перезаписи бы
    # обнулил аватар артиста на детальной — что я заметил в проде.
    if not record.discogs_data or "tracklist" not in (record.discogs_data or {}):
        existing = record.discogs_data or {}
        # Сразу извлекаем artist_id из data.artists[0].id чтобы потом
        # _ensure_record_artist_data НЕ делал отдельный HTTP-запрос для
        # повторного fetch'а того же release'а. Это reduces /releases/{id}
        # с 2 запросов до 1 (payload-load).
        extras: dict = {}
        artists_list = data.get("artists") if isinstance(data, dict) else None
        if isinstance(artists_list, list) and len(artists_list) > 0:
            first_artist = artists_list[0]
            if isinstance(first_artist, dict) and first_artist.get("id"):
                extras["artist_id"] = str(first_artist["id"])
        # Existing идёт ПОСЛЕДНИМ — приоритет у уже сохранённых ценных полей
        # (artist_id, artist_thumb_image_url, vinyl_color_raw).
        record.discogs_data = {**data, **extras, **existing}
        changed = True

    if changed:
        try:
            await db.commit()
            await db.refresh(record)
        except Exception:
            logger.exception("Failed to persist Discogs payload for record %s", record.discogs_id)
            await db.rollback()


async def _free_tracklist(record: Record, db: AsyncSession) -> list[dict] | None:
    """Треклист из бесплатных источников без токена Discogs.

    Локальная таблица треклистов (Tier 2, ноль внешних вызовов) → MB (per-release
    по MBID из mb_discogs_map) → Deezer (album-level по deezer_album_id мастера).
    """
    # 0) Локальная таблица (Tier 2) — спарсено из дампа, мгновенно, без сети.
    try:
        local_tl = (await db.execute(
            text("SELECT tracklist FROM discogs_release_tracklists WHERE discogs_id = :did"),
            {"did": int(record.discogs_id)},
        )).scalar()
        if local_tl:
            return local_tl  # JSONB → уже list[dict]
    except (ValueError, TypeError):
        pass

    # 1) MusicBrainz per-release по MBID.
    try:
        mbid = (await db.execute(
            text("SELECT mbid FROM mb_discogs_map WHERE discogs_id = :did"),
            {"did": int(record.discogs_id)},
        )).scalar()
    except (ValueError, TypeError):
        mbid = None
    if mbid:
        from app.services.cover_fallback import tracklist_by_mbid
        tl = await tracklist_by_mbid(str(mbid))
        if tl:
            return tl

    # 2) Deezer album-level по deezer_album_id мастера.
    if record.discogs_master_id and str(record.discogs_master_id).isdigit():
        dz_album = (await db.execute(
            text(
                "SELECT deezer_album_id FROM discogs_master_covers "
                "WHERE master_id = :mid AND deezer_album_id IS NOT NULL"
            ),
            {"mid": int(record.discogs_master_id)},
        )).scalar()
        if dz_album:
            from app.services.deezer import tracklist_by_album_id
            tl = await tracklist_by_album_id(dz_album)
            if tl:
                return tl

    return None


_payload_enrich_tasks: set[asyncio.Task] = set()


def _schedule_discogs_payload_enrich(discogs_id: str) -> None:
    """Фоновый добор полного Discogs payload (кредиты/цены/точный прессинг) после
    того как треклист уже отдан из бесплатного источника. Не блокирует ответ."""
    async def _run() -> None:
        try:
            from app.database import async_session_maker
            from sqlalchemy import select as _select
            async with async_session_maker() as session:
                rec = (await session.execute(
                    _select(Record).where(Record.discogs_id == discogs_id)
                )).scalar_one_or_none()
                if rec is None:
                    return
                discogs = DiscogsService()
                data = await discogs.get_release(discogs_id, priority=Priority.ENRICHMENT)
                if data:
                    await _apply_discogs_release(rec, data, session)
        except Exception:
            logger.debug("bg discogs payload enrich failed: %s", discogs_id, exc_info=True)

    task = asyncio.create_task(_run())
    _payload_enrich_tasks.add(task)
    task.add_done_callback(_payload_enrich_tasks.discard)


async def get_or_create_record_by_discogs_id(
    discogs_id: str,
    db: AsyncSession
) -> Record:
    """
    Найти или создать Record по discogs_id.
    Используется в других endpoints для получения Record перед добавлением в коллекцию/вишлист.

    Защищён от concurrent INSERT: если два запроса одновременно не нашли запись
    и оба попытались её создать, проигравший ловит IntegrityError, делает rollback
    и читает запись, созданную победителем.
    """
    # Проверяем локальную БД
    result = await db.execute(
        select(Record).where(Record.discogs_id == discogs_id)
    )
    record = result.scalar_one_or_none()

    if record:
        return record

    # Запрос в Discogs (отдельный try — отделяем сетевые ошибки от ошибок БД).
    discogs = DiscogsService()
    try:
        record_data = await discogs.get_release(discogs_id)
    except Exception:
        logger.exception("Failed to fetch Discogs release %s", discogs_id)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Не удалось получить данные из Discogs. Попробуйте позже."
        )

    # Создаём запись в БД
    record = Record(
        discogs_id=record_data.get("id"),
        discogs_master_id=record_data.get("master_id"),
        title=record_data.get("title", "Unknown"),
        artist=record_data.get("artist", "Unknown"),
        label=record_data.get("label"),
        catalog_number=record_data.get("catalog_number"),
        year=record_data.get("year"),
        country=record_data.get("country"),
        genre=record_data.get("genre"),
        style=record_data.get("style"),
        format_type=record_data.get("format"),
        barcode=record_data.get("barcode"),
        cover_image_url=record_data.get("cover_image"),
        thumb_image_url=record_data.get("thumb_image"),
        estimated_price_min=record_data.get("price_min"),
        estimated_price_max=record_data.get("price_max"),
        estimated_price_median=record_data.get("price_median"),
        is_first_press=bool(record_data.get("is_first_press")),
        is_canon=bool(record_data.get("is_canon")),
        is_collectible=bool(record_data.get("is_collectible")),
        is_limited=bool(record_data.get("is_limited")),
        is_hot=bool(record_data.get("is_hot")),
        discogs_data=record_data,
        tracklist=record_data.get("tracklist"),
    )
    db.add(record)
    try:
        await db.commit()
        await db.refresh(record)
    except IntegrityError:
        # Параллельный запрос вставил Record с тем же discogs_id раньше нас —
        # откатываем и читаем существующую запись.
        await db.rollback()
        result = await db.execute(
            select(Record).where(Record.discogs_id == discogs_id)
        )
        existing = result.scalar_one_or_none()
        if existing is None:
            logger.error(
                "IntegrityError on Record insert but no existing row for discogs_id=%s",
                discogs_id,
            )
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Не удалось сохранить пластинку"
            )
        record = existing

    # Self-enriching search-индекс: релиз, добытый из live Discogs (нет в дампе),
    # кладём в discogs_releases_index → /records/search найдёт его в следующий раз.
    # Идемпотентно (ON CONFLICT DO NOTHING), ошибки глотает сам helper.
    from app.services.discogs_index import upsert_release_into_index
    await upsert_release_into_index(db, record_data)
    await db.commit()

    # Fire-and-forget mirror обложки на наш сервер: следующие запросы Mobile
    # получат cover_url='/uploads/covers/{id}.jpg' и грузят с nginx мгновенно,
    # минуя нестабильный Discogs CDN (часть пресс-обложек 403 без referer).
    if record.cover_image_url and not record.cover_local_path:
        from app.services.cover_storage import _download_cover_background
        asyncio.create_task(
            _download_cover_background(str(record.discogs_id), record.cover_image_url)
        )

    return record


async def _search_local_index(
    db: AsyncSession,
    q: str,
    artist: str | None,
    year: int | None,
    year_min: int | None,
    year_max: int | None,
    label: str | None,
    page: int,
    per_page: int,
) -> list[RecordSearchResult]:
    """Поиск в локальном discogs_releases_index через pg_trgm.

    Использует GIN trgm-индексы на artist/title (см. ingest_discogs_dump.py).
    Возвращает ≤ per_page результатов, отсортированных по similarity DESC.
    Если q короткий или нет matches — возвращает [] (caller сделает fallback).
    """
    conds: list[str] = []
    params: dict = {}

    # ILIKE %q% активирует GIN trgm-индекс (gin_trgm_ops) для filter —
    # возвращает small candidate-set за <100ms даже на 13M строках. Similarity
    # потом используется ТОЛЬКО для ранжирования на этом малом наборе.
    # Чистый `artist % :q` сканировал миллионы для "Beatles" (32s cold).
    if q and len(q.strip()) >= 3:
        conds.append("(dri.artist ILIKE :q_pat OR dri.title ILIKE :q_pat)")
        params["q"] = q.strip()
        params["q_pat"] = f"%{q.strip()}%"
    else:
        # Слишком короткое — пусть Discogs API разбирается
        return []

    if artist:
        conds.append("dri.artist ILIKE :artist_like")
        params["artist_like"] = f"%{artist}%"
    if year is not None:
        conds.append("dri.year = :year_eq")
        params["year_eq"] = year
    else:
        if year_min is not None:
            conds.append("dri.year >= :year_min")
            params["year_min"] = year_min
        if year_max is not None:
            conds.append("dri.year <= :year_max")
            params["year_max"] = year_max
    if label:
        conds.append("dri.label ILIKE :label_like")
        params["label_like"] = f"%{label}%"

    where = " AND ".join(conds)
    offset = (page - 1) * per_page

    # Ранжирование: artist match × 2, title match × 1. Prefix-match
    # (artist начинается с q) добавляет +1 чтобы "Beatles" находил
    # "The Beatles" поверх случайных альбомов где title содержит "beatles".
    # LEFT JOIN records: подтягиваем обложки из локального кэша. Дамп Discogs
    # не несёт image URLs (dri.cover_image_url в основном NULL), но
    # records.cover_local_path / cover_image_url заполнены для релизов, которые
    # уже открывали — так каждый detail-view улучшает будущие списки.
    sql = text(
        f"""
        SELECT
            dri.discogs_id::text AS discogs_id,
            dri.artist, dri.title, dri.year, dri.country,
            dri.format_type, dri.label,
            COALESCE(
                CASE WHEN r.cover_local_path IS NOT NULL
                     THEN '/uploads/' || r.cover_local_path END,
                r.cover_image_url,
                dri.cover_image_url
            ) AS cover_image_url,
            (
              similarity(dri.artist, :q) * 2.0
              + similarity(dri.title, :q)
              + CASE WHEN dri.artist ILIKE :q_pref THEN 1.0 ELSE 0.0 END
            ) AS sim
        FROM discogs_releases_index dri
        LEFT JOIN records r
            ON r.discogs_id = dri.discogs_id::text
            AND r.merged_into_id IS NULL
        WHERE {where}
        ORDER BY sim DESC, dri.year DESC NULLS LAST
        LIMIT :limit OFFSET :offset
        """
    )
    params["q_pref"] = f"%{q.strip()}%"
    params["limit"] = per_page
    params["offset"] = offset

    rows = (await db.execute(sql, params)).mappings().all()
    return [
        RecordSearchResult(
            discogs_id=row["discogs_id"],
            title=row["title"],
            artist=row["artist"],
            label=row["label"],
            year=row["year"],
            country=row["country"],
            cover_image_url=row["cover_image_url"],
            thumb_image_url=None,
            format_type=row["format_type"],
        )
        for row in rows
    ]


async def _search_store_native_releases(
    db: AsyncSession,
    q: str,
    format: str | None,
    year: int | None,
    year_min: int | None,
    year_max: int | None,
    limit: int,
) -> list[ReleaseSearchResult]:
    """Store-native записи (source='store', нет на Discogs) для /releases/search.

    Discogs API про эти релизы не знает — но они живут в нашей БД и уже доступны
    в Маркете. Подмешиваем их в поиск, чтобы юзер находил то, что лежит в нашей
    же базе, и мог добавить в коллекцию (см. whitelist в collections/wishlists).

    release_id = record.id (UUID), НЕ discogs_id: фронт открывает карточку через
    /record/{id}, а get_record резолвит и UUID. Ранжирование/нормализация
    зеркалят _search_local_index: ILIKE %q% активирует GIN trgm-индекс, similarity
    используется только для сортировки малого кандидат-сета.
    """
    if not q or len(q.strip()) < 3:
        return []

    conds = ["r.source = 'store'", "r.merged_into_id IS NULL"]
    params: dict = {"q": q.strip(), "q_pat": f"%{q.strip()}%", "limit": limit}
    conds.append("(r.artist ILIKE :q_pat OR r.title ILIKE :q_pat)")

    if format:
        conds.append("r.format_type ILIKE :fmt_like")
        params["fmt_like"] = f"%{format}%"
    if year is not None:
        conds.append("r.year = :year_eq")
        params["year_eq"] = year
    else:
        if year_min is not None:
            conds.append("r.year >= :year_min")
            params["year_min"] = year_min
        if year_max is not None:
            conds.append("r.year <= :year_max")
            params["year_max"] = year_max

    where = " AND ".join(conds)
    sql = text(
        f"""
        SELECT
            r.id::text AS id,
            r.artist, r.title, r.year, r.country, r.label,
            r.catalog_number, r.format_type,
            COALESCE(
                CASE WHEN r.cover_local_path IS NOT NULL
                     THEN '/uploads/' || r.cover_local_path END,
                r.cover_image_url
            ) AS cover_image_url,
            (
              similarity(r.artist, :q) * 2.0
              + similarity(r.title, :q)
            ) AS sim
        FROM records r
        WHERE {where}
        ORDER BY sim DESC, r.year DESC NULLS LAST
        LIMIT :limit
        """
    )
    rows = (await db.execute(sql, params)).mappings().all()
    return [
        ReleaseSearchResult(
            release_id=row["id"],
            title=row["title"],
            artist=row["artist"],
            label=row["label"],
            catalog_number=row["catalog_number"],
            country=row["country"],
            year=row["year"],
            format=row["format_type"],
            cover_image_url=row["cover_image_url"],
            thumb_image_url=None,
        )
        for row in rows
    ]


@router.get("/search", response_model=RecordSearchResponse)
async def search_records(
    response: Response,
    q: str = Query(..., min_length=1, description="Поисковый запрос"),
    artist: str | None = Query(None, description="Фильтр по артисту"),
    year: int | None = Query(None, description="Фильтр по году (точный)"),
    year_min: int | None = Query(None, description="Минимальный год (включительно)"),
    year_max: int | None = Query(None, description="Максимальный год (включительно)"),
    label: str | None = Query(None, description="Фильтр по лейблу"),
    page: int = Query(1, ge=1, description="Номер страницы"),
    per_page: int = Query(20, ge=1, le=100, description="Записей на страницу"),
    current_user: User | None = Depends(get_current_user_optional),
    db: AsyncSession = Depends(get_db)
):
    """
    Поиск пластинок: local-first по discogs_releases_index (offline-дамп),
    fallback на Discogs API если ничего не найдено локально.

    Не требует авторизации, но с авторизацией может сохранять историю.
    """
    response.headers["Cache-Control"] = "public, max-age=300"

    # Local-first: 19M записей в discogs_releases_index покрывают подавляющее
    # большинство запросов. API hit только если local пусто (свежие релизы,
    # опечатки за порогом trigram).
    try:
        local = await _search_local_index(
            db, q, artist, year, year_min, year_max, label, page, per_page
        )
    except Exception as exc:
        logger.warning("local search failed, fallback to API: %s", exc)
        local = []

    if local:
        await _enrich_search_results_with_rarity(
            local, db, id_attr="discogs_id", format_attr="format_type"
        )
        # Прогрев обложек для топ-результатов без cover: CAA по barcode
        # (бесплатно) + капнутый Discogs ENRICHMENT. Пишет в dump-индекс —
        # следующая выдача уже с обложками. Fire-and-forget, поиск не ждёт.
        from app.services.cover_warm import schedule_warm_dump_covers
        schedule_warm_dump_covers(
            [r.discogs_id for r in local[:10] if not r.cover_image_url]
        )
        # Обложки — через своё зеркало /covers/{discogs_id}.jpg: nginx-статика
        # после первого обращения, вместо прямых ссылок на медленные из РФ CDN.
        covers_base = get_settings().public_covers_base
        for r in local:
            if r.cover_image_url and not r.cover_image_url.startswith(covers_base):
                r.cover_image_url = f"{covers_base}/{r.discogs_id}.jpg"
        # Неполные обложки → no-store: warm уже запущен, повторный запрос
        # должен дойти до бэкенда, а не получить запиненную nginx копию.
        if any(not r.cover_image_url for r in local):
            response.headers["Cache-Control"] = "no-store"
        # total известен только приблизительно — отдаём len(local) + offset как
        # минимум. Mobile-pager работает с has_next по len(results)==per_page.
        return RecordSearchResponse(
            results=local,
            total=(page - 1) * per_page + len(local),
            page=page,
            per_page=per_page,
        )

    # Fallback на Discogs API
    discogs = DiscogsService()
    try:
        results = await discogs.search(
            query=q,
            artist=artist,
            year=year,
            year_min=year_min,
            year_max=year_max,
            label=label,
            page=page,
            per_page=per_page,
            creds=user_creds(current_user),
        )
        await _enrich_search_results_with_rarity(
            results.results, db, id_attr="discogs_id", format_attr="format_type"
        )
        return results
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Ошибка при поиске в Discogs: {str(e)}"
        )


@router.post("/scan/barcode", response_model=list[RecordSearchResult])
async def scan_barcode(
    barcode: str = Query(..., min_length=8, max_length=20, description="Штрихкод"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Поиск пластинки по штрихкоду.
    Требует авторизации.
    """
    # Сначала проверяем локальную БД. barcode НЕ уникален (store-native + user +
    # пресс-дубли делят один код) → scalar_one_or_none() падал в
    # MultipleResultsFound → 500 → клиент показывал «не найдено» (баг скана
    # 602478091186). Берём один не-merged матч.
    result = await db.execute(
        select(Record)
        .where(Record.barcode == barcode, Record.merged_into_id.is_(None))
        .limit(1)
    )
    local_record = result.scalars().first()
    
    if local_record:
        return [RecordSearchResult(
            discogs_id=local_record.discogs_id or "",
            title=local_record.title,
            artist=local_record.artist,
            label=local_record.label,
            year=local_record.year,
            country=local_record.country,
            cover_image_url=local_record.cover_image_url,
            thumb_image_url=local_record.thumb_image_url,
            format_type=local_record.format_type,
        )]

    # Dump-индекс по barcode_norm (btree) — закрывает скан без Discogs API.
    # Нормализация та же, что при ingest: только цифры.
    barcode_norm = re.sub(r"\D+", "", barcode)
    if barcode_norm:
        try:
            dump_rows = (await db.execute(
                text(
                    "SELECT discogs_id::text AS discogs_id, artist, title, year, "
                    "country, format_type, label, cover_image_url "
                    "FROM discogs_releases_index "
                    "WHERE barcode_norm = :bc LIMIT 10"
                ),
                {"bc": barcode_norm},
            )).mappings().all()
        except Exception:
            logger.warning("dump barcode lookup failed", exc_info=True)
            dump_rows = []
        if dump_rows:
            from app.services.cover_warm import schedule_warm_dump_covers
            schedule_warm_dump_covers(
                [r["discogs_id"] for r in dump_rows if not r["cover_image_url"]]
            )
            return [
                RecordSearchResult(
                    discogs_id=row["discogs_id"],
                    title=row["title"],
                    artist=row["artist"],
                    label=row["label"],
                    year=row["year"],
                    country=row["country"],
                    cover_image_url=row["cover_image_url"],
                    thumb_image_url=None,
                    format_type=row["format_type"],
                )
                for row in dump_rows
            ]

    # Поиск в Discogs — последний resort. Короткий watchdog 7с (не дефолтные
    # 30с лимитера): юзер в магазине не должен ждать полминуты и ловить 503.
    # При таймауте/ошибке/пусто → возвращаем [] («не найдено, добавьте вручную»),
    # а НЕ 503: клиент показывает пустой результат, а не «ошибку». Graceful
    # деградация — критично для скана в оффлайн-полях при перегрузе Discogs.
    discogs = DiscogsService()
    try:
        results = await asyncio.wait_for(discogs.search_by_barcode(barcode), timeout=7)
        return results or []
    except Exception:
        logger.info("scan_barcode: Discogs fallback miss/slow for %s", barcode)
        return []


# Порог визуальной уверенности (косинус CLIP). Ниже — клиенту показать
# "выбери вручную" вместо подсовывания одного результата как точного.
_COVER_MATCH_THRESHOLD = 0.75
# Сколько верхних кандидатов прогонять через CLIP (downloads + inference).
_COVER_RERANK_TOPN = 12


async def _visual_rerank(image_base64: str, candidates: list) -> list:
    """Переранжирует кандидатов по визуальной близости их обложек к фото юзера.

    Для каждого кандидата качает обложку (cover_image_url, fallback thumb),
    эмбеддит через CLIP, считает косинус с эмбеддингом фото, проставляет
    match_score и сортирует по убыванию. Кандидаты без скачанной/валидной
    обложки уходят в конец с match_score=None.
    """
    import base64 as _b64

    from app.services.cover_matcher import CoverMatcher

    try:
        query_bytes = _b64.b64decode(image_base64)
    except Exception:
        return candidates

    matcher = await CoverMatcher.get()
    query_vec = await matcher.embed(query_bytes)
    if query_vec is None:
        return candidates

    subset = candidates[:_COVER_RERANK_TOPN]

    def _cover_url(c) -> str | None:
        return getattr(c, "cover_image_url", None) or getattr(c, "thumb_image_url", None)

    async def _fetch(url: str | None) -> bytes | None:
        if not url:
            return None
        try:
            async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
                resp = await client.get(url, headers={"User-Agent": "Vertushka/1.0"})
                resp.raise_for_status()
                return resp.content
        except Exception:
            return None

    images = await asyncio.gather(*[_fetch(_cover_url(c)) for c in subset])
    vecs = await matcher.embed_many([img if img else b"" for img in images])

    for cand, img, vec in zip(subset, images, vecs):
        if img and vec is not None:
            cand.match_score = round(matcher.cosine(query_vec, vec), 4)
        else:
            cand.match_score = None

    scored = [c for c in subset if c.match_score is not None]
    unscored = [c for c in subset if c.match_score is None]
    scored.sort(key=lambda c: c.match_score, reverse=True)
    # хвост кандидатов за пределами top-N сохраняем как есть, после переранжированных
    tail = candidates[_COVER_RERANK_TOPN:]
    result = scored + unscored + tail

    # Вернуть ОС арены от скачанных/декодированных обложек-кандидатов: glibc не
    # отдаёт освобождённую память сама → RSS процесса пух после каждого скана
    # (инцидент 07-10). malloc_trim схлопывает транзиенты; резидентная CLIP-модель
    # остаётся (её держит singleton CoverMatcher).
    del images, vecs, query_vec
    try:
        import ctypes
        ctypes.CDLL("libc.so.6").malloc_trim(0)
    except Exception:
        pass
    return result


@router.post("/scan/cover/", response_model=CoverScanResponse)
async def scan_cover(
    request: CoverScanRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Распознавание обложки пластинки через AI Vision.
    Принимает base64-encoded JPEG, возвращает результаты поиска Discogs.
    Требует авторизации.
    """
    if len(request.image_base64) > 10_000_000:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="Изображение слишком большое (макс. ~7.5 МБ)"
        )

    vision = OpenAIVisionService()
    try:
        recognition = await vision.recognize_cover(request.image_base64)
    except CoverRecognitionError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Ошибка AI-сервиса: {str(e)}"
        )

    artist = recognition["artist"]
    album = recognition["album"]

    discogs = DiscogsService()

    async def _search_releases(query: str) -> list:
        """Поиск релизов без жёсткого artist-фильтра."""
        try:
            resp = await discogs.search(query=query, per_page=15, creds=user_creds(current_user))
            return resp.results
        except Exception:
            return []

    async def _search_masters(query: str) -> list:
        """Поиск мастер-релизов, конвертируем в RecordSearchResult."""
        try:
            resp = await discogs.search_masters(query=query, per_page=15)
            return [
                RecordSearchResult(
                    discogs_id=m.master_id,
                    title=m.title,
                    artist=m.artist,
                    year=m.year,
                    cover_image_url=m.cover_image_url,
                    thumb_image_url=m.thumb_image_url,
                )
                for m in resp.results
            ]
        except Exception:
            return []

    results: list = []

    # Стратегия 1: artist + album (самый точный запрос)
    if artist and album:
        results = await _search_releases(f"{artist} {album}")

    # Стратегия 2: только artist
    if not results and artist:
        results = await _search_releases(artist)

    # Стратегия 3: только album
    if not results and album:
        results = await _search_releases(album)

    # Стратегия 4: masters (artist + album или artist)
    if not results:
        master_query = f"{artist} {album}".strip() if artist or album else ""
        if master_query:
            results = await _search_masters(master_query)

    # Стратегия 5: masters только по artist
    if not results and artist:
        results = await _search_masters(artist)

    if not results:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Не удалось найти пластинку по распознанной обложке"
        )

    # ── Визуальный re-rank ─────────────────────────────────────────────
    # Текстовый поиск даёт ложные срабатывания (особенно обложки без текста).
    # Сравниваем фото юзера с обложками кандидатов в CLIP-пространстве и
    # переранжируем по реальной визуальной близости. Best-effort: при любой
    # ошибке возвращаем исходный текстовый порядок без score.
    confidence: float | None = None
    low_confidence = False
    try:
        results = await _visual_rerank(request.image_base64, results)
        if results and results[0].match_score is not None:
            confidence = results[0].match_score
            low_confidence = confidence < _COVER_MATCH_THRESHOLD
    except Exception:
        logger.exception("Visual re-rank failed, fallback to text order")

    # Обложки → наше зеркало /covers/{id}.jpg: RU-надёжно (не i.discogs.com
    # напрямую) + живой резолв (Deezer/CAA/Discogs) на промах вместо заглушки.
    # Rewrite ПОСЛЕ visual_rerank — ему нужны прямые image-URL для CLIP.
    from app.config import get_settings as _gs
    _cov_base = _gs().public_covers_base
    for _r in results:
        if _r.discogs_id and str(_r.discogs_id).isdigit():
            _r.cover_image_url = f"{_cov_base}/{_r.discogs_id}.jpg"
            _r.thumb_image_url = _r.cover_image_url

    return CoverScanResponse(
        recognized_artist=artist,
        recognized_album=album,
        results=results,
        confidence=confidence,
        low_confidence=low_confidence,
    )


async def _suggest_local(db: AsyncSession, q: str) -> dict | None:
    """Автодополнение по локальным данным, без Discogs API.

    masters — из dump-индекса (trgm-кандидаты, дедуп по master_id);
    artists — из records (там есть artist_id + thumb из discogs_data,
    дамп их не несёт). Возвращает None если masters не нашлись —
    caller уходит в Discogs API.
    """
    qs = q.strip()
    if len(qs) < 3:
        return None
    pat = f"%{qs}%"

    # Кандидаты из дампа: ILIKE активирует GIN trgm (как в _search_local_index),
    # similarity ранжирует малый набор. Берём с запасом — дедуп по master_id
    # ниже срежет переиздания одного альбома.
    master_rows = (await db.execute(
        text(
            """
            SELECT
                dri.master_id::text AS master_id,
                dri.artist, dri.title, dri.year,
                COALESCE(
                    CASE WHEN r.cover_local_path IS NOT NULL
                         THEN '/uploads/' || r.cover_local_path END,
                    r.cover_image_url,
                    dri.cover_image_url
                ) AS thumb,
                (
                  similarity(dri.artist, :q) * 2.0
                  + similarity(dri.title, :q)
                  + CASE WHEN dri.artist ILIKE :pat THEN 1.0 ELSE 0.0 END
                ) AS sim
            FROM discogs_releases_index dri
            LEFT JOIN records r
                ON r.discogs_id = dri.discogs_id::text
                AND r.merged_into_id IS NULL
            WHERE dri.master_id IS NOT NULL
              AND (dri.artist ILIKE :pat OR dri.title ILIKE :pat)
            ORDER BY sim DESC, dri.year ASC NULLS LAST
            LIMIT 40
            """
        ),
        {"q": qs, "pat": pat},
    )).mappings().all()

    masters: list[dict] = []
    seen: set[str] = set()
    for row in master_rows:
        mid = row["master_id"]
        if mid in seen:
            continue
        seen.add(mid)
        masters.append({
            "master_id": mid,
            "title": row["title"],
            "artist": row["artist"],
            "year": row["year"],
            "thumb": row["thumb"],
        })
        if len(masters) >= 5:
            break

    if not masters:
        return None

    # Артисты — из records: только там есть artist_id для навигации.
    # Покрытие растёт с использованием (каждый detail-view пишет artist_id).
    artist_rows = (await db.execute(
        text(
            """
            SELECT DISTINCT ON (lower(artist))
                discogs_data->>'artist_id' AS artist_id,
                artist AS name,
                discogs_data->>'artist_thumb_image_url' AS thumb
            FROM records
            WHERE artist ILIKE :pat
              AND discogs_data->>'artist_id' IS NOT NULL
              AND merged_into_id IS NULL
            ORDER BY lower(artist), created_at DESC
            LIMIT 3
            """
        ),
        {"pat": pat},
    )).mappings().all()

    artists = [
        {"artist_id": r["artist_id"], "name": r["name"], "thumb": r["thumb"]}
        for r in artist_rows
    ]
    return {"artists": artists, "masters": masters}


@router.get("/suggest")
async def suggest(
    q: str = Query(..., min_length=2, max_length=100),
    limit: int = Query(8, ge=1, le=15),
    current_user: User | None = Depends(get_current_user_optional),
    db: AsyncSession = Depends(get_db),
):
    """
    Автодополнение: local-first (dump-индекс + records), fallback на Discogs.

    Suggest — самый горячий путь к Discogs API (вызов на каждую паузу набора),
    локальный путь снимает его с rate-limit бюджета целиком.
    """
    try:
        local = await _suggest_local(db, q)
        if local is not None:
            return local
    except Exception:
        logger.warning("local suggest failed, fallback to API", exc_info=True)

    discogs = DiscogsService()
    try:
        return await discogs.suggest(query=q, per_page=limit, creds=user_creds(current_user))
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Ошибка автодополнения: {str(e)}"
        )


async def _schedule_store_native_discogs_match(record_id: UUID) -> None:
    """fire-and-forget: ищет Discogs match для store-native записи и сразу
    safe_merge'ит при удаче. После — следующий просмотр /records/{id} вернёт
    данные полноценной Discogs-записи (через follow merged_into_id).

    Стратегия:
      • запускается из get_record для source='store' без discogs_id_candidate;
      • открывает свою DB-session чтобы не зависеть от scope endpoint'а;
      • _try_discogs_fetch_by_text сам создаст Discogs Record при успехе;
      • safe_merge_store_native_into перепривяжет листинги, soft-delete'ит
        store-native через merged_into_id, пишет audit в record_merge_history;
      • при rate-limit/ошибке тихо выходит — повтор через сутки в
        daily_rematch_store_native (cron).
    Защита от повторов: проверяем discogs_id_candidate IS NULL прямо перед
    поиском (запрос мог отработать между моментом запуска и стартом задачи).
    """
    # Импорты внутри функции — listing_matcher импортирует из records.py
    # косвенно, выносим во избежание потенциальных circular imports.
    from app.services.listing_matcher import (
        _try_discogs_fetch_by_text,
        safe_merge_store_native_into,
    )

    try:
        async with async_session_maker() as db:
            res = await db.execute(select(Record).where(Record.id == record_id))
            rec = res.scalar_one_or_none()
            if rec is None or rec.source != "store":
                return
            if rec.merged_into_id is not None:
                return
            if rec.discogs_id_candidate:
                return  # уже искали в предыдущий раз

            found = await _try_discogs_fetch_by_text(
                db,
                artist=rec.artist,
                title=rec.title,
                year=rec.year,
            )
            if not (found and found.discogs_id and found.id != rec.id):
                # Записываем «искали — не нашли», чтобы не долбить Discogs
                # при каждом просмотре. discogs_id_candidate остаётся NULL,
                # но first_seen_at = now становится маркером попытки.
                rec.discogs_id_candidate_first_seen_at = datetime.utcnow()
                await db.commit()
                return

            rec.discogs_id_candidate = found.discogs_id
            rec.discogs_id_candidate_first_seen_at = datetime.utcnow()
            rec.discogs_id_candidate_confirmations = 1

            # On-demand merge: один confirmation достаточен, потому что юзер
            # уже смотрит карточку — задержки в 2 дня для cron'а здесь нет смысла.
            merge_res = await safe_merge_store_native_into(
                rec, found.discogs_id, db, merged_by="on_demand_detail",
            )
            await db.commit()
            if merge_res["target_found"]:
                logger.info(
                    "on-demand merge store-native %s → discogs_id=%s "
                    "(remapped %d listings, artist=%s title=%s)",
                    record_id, found.discogs_id,
                    merge_res["listings_remapped"], rec.artist, rec.title,
                )
    except Exception:
        logger.exception("on-demand store-native enrichment failed for %s", record_id)


# ── User-submitted records (source='user') ─────────────────────────────── #
# ВАЖНО: эти статичные роуты объявлены ДО `/{record_id}`, иначе path-param
# проглотит 'preflight'/'spotify-search'/'user' как record_id.


@router.post("/preflight/", response_model=PreflightResponse)
async def preflight(
    data: PreflightRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Дабл-чек перед ручным добавлением пластинки. Проверяет, нет ли её уже в
    Маркете/Discogs. См. USER_SUBMITTED_RECORDS.md §2.
    """
    from app.services.user_record import preflight_dedup

    res = await preflight_dedup(
        artist=data.artist,
        title=data.title,
        year=data.year,
        barcode=data.barcode,
        catalog=data.catalog,
        format_type=data.format_type,
        db=db,
    )
    return PreflightResponse(
        status=res.status,
        match=RecordResponse.model_validate(res.match) if res.match else None,
        discogs_id=res.discogs_id,
        score=res.score,
    )


@router.get("/spotify-search/", response_model=SpotifySearchResponse)
async def spotify_search(
    q: str = Query(..., min_length=2, max_length=200),
    current_user: User = Depends(get_current_user),
):
    """
    Автозаполнение из Spotify: артист/альбом → кандидаты с обложкой/годом/
    треклистом. Пустой результат, если Spotify-креды не настроены. §3.
    """
    from app.services.spotify import spotify_service

    albums = await spotify_service.search_album(artist="", title=q)
    candidates: list[SpotifyAlbumCandidate] = []
    for a in albums:
        tracks = await spotify_service.get_album_tracks(a["id"]) if a.get("id") else []
        candidates.append(SpotifyAlbumCandidate(**a, tracks=tracks))
    return SpotifySearchResponse(results=candidates)


@router.post("/user/", response_model=RecordResponse, status_code=status.HTTP_201_CREATED)
async def create_user_submitted_record(
    data: UserRecordCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Создать запись source='user' (пластинки нет ни в Discogs, ни в Маркете).
    Повторный preflight на бэке (фронт-чек не доверяем) → заливка фото →
    enrichment-merge Spotify → Record(approved, §6) → в коллекцию создателя. §4.
    """
    import base64
    from app.services.user_record import preflight_dedup, create_user_record, PreflightStatus
    from app.services.spotify import spotify_service
    from app.services.cover_storage import CoverStorageService
    from app.services.gifts import get_or_create_default_collection
    from app.models.collection import CollectionItem

    # 1) повторный дабл-чек на бэке
    pf = await preflight_dedup(
        artist=data.artist,
        title=data.title,
        year=data.year,
        barcode=data.barcode,
        catalog=data.catalog_number,
        format_type=data.format_type,
        db=db,
    )
    if pf.status in (PreflightStatus.DUPLICATE, PreflightStatus.FOUND_IN_DISCOGS):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "status": pf.status,
                "match_id": str(pf.match.id) if pf.match else None,
                "discogs_id": pf.discogs_id,
                "message": "Эта пластинка уже есть — добавьте её из найденного.",
            },
        )
    # LIKELY_DUPLICATE не блокируем жёстко — фронт уже показал юзеру кандидата
    # на этапе preflight, и раз дошли до создания — юзер настоял (human-in-loop).

    # 2) enrichment-merge: Spotify-данные (если есть album_id и треклист пуст)
    user_data: dict = {"manual": data.model_dump(exclude={"cover_photo_base64", "spine_photo_base64"})}
    tracklist = data.tracklist
    year = data.year
    if data.spotify_album_id:
        album = await spotify_service.get_album(data.spotify_album_id)
        if album:
            user_data["spotify"] = album
            if not tracklist:
                tracklist = await spotify_service.get_album_tracks(data.spotify_album_id)
            if not year:
                rel = album.get("release_date") or ""
                if rel[:4].isdigit():
                    year = int(rel[:4])

    # 3) создаём запись (pending)
    rec = await create_user_record(
        db=db,
        created_by_user_id=current_user.id,
        artist=data.artist,
        title=data.title,
        year=year,
        label=data.label,
        catalog_number=data.catalog_number,
        country=data.country,
        format_type=data.format_type,
        barcode=data.barcode,
        tracklist=tracklist,
        spotify_album_id=data.spotify_album_id,
        user_submitted_data=user_data,
    )

    # 3.5) Артист-линковка: пробуем найти Discogs-артиста по имени и привязать
    # artist_id (читается из discogs_data property) → карточка артиста оживает.
    # Уверенный матч = точное совпадение имени (case-insensitive). Не нашли —
    # оставляем артиста текстом.
    try:
        from app.services.discogs import DiscogsService

        ar = await DiscogsService().search_artists(data.artist, per_page=5)
        want = data.artist.strip().casefold()
        match = next(
            (a for a in ar.results if (a.name or "").strip().casefold() == want),
            None,
        )
        if match and match.artist_id:
            rec.discogs_data = {
                "artist_id": str(match.artist_id),
                "artist_thumb_image_url": match.thumb_image_url or match.cover_image_url,
            }
    except Exception:
        logger.warning("user-record artist link failed for %s", rec.id)

    # 4) заливка фото обложки (приоритет у юзерского фото над Spotify-обложкой)
    if data.cover_photo_base64:
        try:
            raw = base64.b64decode(data.cover_photo_base64)
            rel_path = CoverStorageService().store_user_cover(f"user_{rec.id}", raw)
            if rel_path:
                rec.cover_local_path = rel_path
                rec.cover_cached_at = datetime.utcnow()
        except Exception:
            logger.warning("user-record cover store failed for %s", rec.id)
    # Spotify-обложка как fallback (cover_image_url), если юзер фото не дал
    if not data.cover_photo_base64 and data.spotify_album_id:
        sp = user_data.get("spotify") or {}
        imgs = sp.get("images") or []
        if imgs:
            rec.cover_image_url = imgs[0].get("url")

    # 5) в коллекцию создателя
    collection = await get_or_create_default_collection(current_user, db)
    db.add(CollectionItem(collection_id=collection.id, record_id=rec.id))

    await db.commit()
    await db.refresh(rec)

    # Эмиссия ачивок: вклад (K8–K10) + добавление в коллекцию (B-серия,
    # пионер K17–K20 — ручной релиз почти всегда первый на платформе).
    from app.services.achievements import emit_event
    from app.services.achievements.events import (
        COLLECTION_ITEM_ADDED,
        USER_RECORD_CREATED,
    )
    await emit_event(db, current_user.id, USER_RECORD_CREATED, {"record_id": rec.id})
    await emit_event(
        db,
        current_user.id,
        COLLECTION_ITEM_ADDED,
        {"record_id": rec.id, "record": rec},
    )

    return RecordResponse.model_validate(rec)


@router.get("/user/mine", response_model=list[RecordResponse])
async def list_my_user_records(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Свои ручные релизы (source='user', created_by_user_id == me). §11.

    Для раздела «Мои релизы» в профиле и редактирования.
    """
    res = await db.execute(
        select(Record)
        .where(
            Record.source == "user",
            Record.created_by_user_id == current_user.id,
            Record.merged_into_id.is_(None),
        )
        .order_by(Record.created_at.desc())
    )
    records = res.scalars().all()
    return [RecordResponse.model_validate(r) for r in records]


@router.patch("/user/{record_id}", response_model=RecordResponse)
async def update_user_submitted_record(
    record_id: UUID,
    data: UserRecordUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Править свою user-record (§11). Только source='user' и только автор.

    Discogs/store записи не редактируются (403). Чужие user-records — 403.
    """
    import base64
    from app.services.user_record import update_user_record
    from app.services.cover_storage import CoverStorageService

    res = await db.execute(select(Record).where(Record.id == record_id))
    record = res.scalar_one_or_none()
    if record is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Пластинка не найдена")
    if record.source != "user" or record.created_by_user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Можно редактировать только свои добавленные релизы",
        )

    changes = data.model_dump(exclude_unset=True, exclude={"cover_photo_base64"})
    await update_user_record(db=db, record=record, changes=changes)

    # Новое фото обложки (приоритет у юзерского фото).
    if data.cover_photo_base64:
        try:
            raw = base64.b64decode(data.cover_photo_base64)
            rel_path = CoverStorageService().store_user_cover(f"user_{record.id}", raw)
            if rel_path:
                record.cover_local_path = rel_path
                record.cover_cached_at = datetime.utcnow()
        except Exception:
            logger.warning("user-record cover update failed for %s", record.id)

    await db.commit()
    await db.refresh(record)
    return RecordResponse.model_validate(record)


@router.get("/{record_id}/price-history")
async def get_record_price_history(
    record_id: UUID,
    days: int = Query(90, ge=7, le=365),
    db: AsyncSession = Depends(get_db),
):
    """Динамика цены пластинки: дневной минимум in_stock + историческая нижняя.

    Источник — listing_price_history (снапшоты при смене цены). Точки дают
    только дни, где были изменения; клиент интерполирует между ними.
    """
    from datetime import timedelta
    from app.models.listing_price_history import ListingPriceHistory
    from app.models.store_listing import ListingStatus

    since = datetime.utcnow() - timedelta(days=days)
    day = func.date_trunc("day", ListingPriceHistory.captured_at)

    rows = (
        await db.execute(
            select(
                day.label("day"),
                func.min(ListingPriceHistory.price_rub).label("min_price"),
                func.count(func.distinct(ListingPriceHistory.listing_id)).label("listings"),
            )
            .where(
                ListingPriceHistory.record_id == record_id,
                ListingPriceHistory.status == ListingStatus.IN_STOCK,
                ListingPriceHistory.price_rub.is_not(None),
                ListingPriceHistory.captured_at >= since,
            )
            .group_by(day)
            .order_by(day)
        )
    ).all()

    points = [
        {
            "date": d.date().isoformat(),
            "min_price_rub": float(mp) if mp is not None else None,
            "listings_count": int(cnt),
        }
        for d, mp, cnt in rows
    ]
    prices = [p["min_price_rub"] for p in points if p["min_price_rub"] is not None]
    return {
        "record_id": str(record_id),
        "days": days,
        "points": points,
        "historical_low_rub": min(prices) if prices else None,
    }


@router.get("/{record_id}", response_model=RecordResponse)
async def get_record(
    record_id: UUID,
    current_user: User | None = Depends(get_current_user_optional),
    db: AsyncSession = Depends(get_db)
):
    """Получение информации о пластинке"""
    result = await db.execute(select(Record).where(Record.id == record_id))
    record = result.scalar_one_or_none()

    if not record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Пластинка не найдена"
        )

    # §6 (revised 2026-06-17): модерация отменена — user-records сразу approved
    # и видны всем. Pending-гейт убран. Поле moderation_status оставлено для
    # 'merged' (rematch) и на будущее.

    # UGC takedown (Guideline 1.2): скрытая по жалобе запись ('rejected')
    # недоступна по прямой ссылке никому, кроме автора и staff.
    if (
        record.source == "user"
        and record.moderation_status == "rejected"
        and not (
            current_user is not None
            and (
                current_user.is_staff
                or record.created_by_user_id == current_user.id
            )
        )
    ):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Пластинка не найдена"
        )

    # Follow merged_into_id: если эту запись уже слили в Discogs-аналог,
    # отдаём данные целевой записи. Старые ссылки/push'и на исходный uuid
    # продолжают работать прозрачно для юзера.
    if record.merged_into_id is not None:
        target_res = await db.execute(
            select(Record).where(Record.id == record.merged_into_id)
        )
        target = target_res.scalar_one_or_none()
        if target is not None:
            record = target

    # Store-native без попытки матчинга — пускаем фоновый enrichment.
    # При удаче следующий просмотр (~секунды) уже вернёт полную Discogs-карточку.
    # asyncio.create_task — не блокируем ответ, юзер не ждёт Discogs API.
    if (
        record.source == "store"
        and record.merged_into_id is None
        and record.discogs_id_candidate is None
    ):
        asyncio.create_task(_schedule_store_native_discogs_match(record.id))

    # Порядок важен: payload ПЕРЕД artist_data.
    # _ensure_record_discogs_payload может догрузить полный Discogs release
    # с tracklist'ом — и положить туда же artist_id, что потом сэкономит
    # _ensure_record_artist_data один HTTP-запрос.
    # Price data — fire-and-forget: не блокирует ответ, подтягивается фоном.
    # Следующее открытие карточки уже покажет цены из БД.
    await _ensure_record_discogs_payload(record, db)
    await _ensure_record_artist_data(record, db)
    if not record.estimated_price_min and not record.estimated_price_median and record.discogs_id:
        asyncio.create_task(_ensure_record_price_data_bg(record.id, record.discogs_id))

    response = RecordResponse.model_validate(record)
    discogs_data = record.discogs_data or {}
    response.artist_id = discogs_data.get("artist_id")
    response.artist_thumb_image_url = discogs_data.get("artist_thumb_image_url")
    response.vinyl_color_raw = discogs_data.get("vinyl_color_raw")
    return await _enrich_response_with_rub(response, record, db)


@router.get("/discogs/{discogs_id}", response_model=RecordResponse)
async def get_record_by_discogs_id(
    discogs_id: str,
    response: Response,
    current_user: User | None = Depends(get_current_user_optional),
    db: AsyncSession = Depends(get_db)
):
    """
    Получение информации о пластинке по Discogs ID.
    Если пластинка не найдена в локальной БД, запрашивает Discogs и сохраняет.
    """
    # max-age 60 (раньше 3600) — после первой загрузки enrichment может
    # дополнить запись tracklist/artist_thumb/master_id. Если кэш на час,
    # юзер видит пустые поля до истечения. С 60 сек обновление через минуту.
    response.headers["Cache-Control"] = "public, max-age=60"
    # Проверяем локальную БД
    result = await db.execute(
        select(Record).where(Record.discogs_id == discogs_id)
    )
    record = result.scalar_one_or_none()

    if record:
        # Порядок: payload ПЕРЕД artist_data. Price — fire-and-forget.
        await _ensure_record_discogs_payload(record, db)
        await _ensure_record_artist_data(record, db)
        if not record.estimated_price_min and not record.estimated_price_median and record.discogs_id:
            asyncio.create_task(_ensure_record_price_data_bg(record.id, record.discogs_id))

        discogs_data = record.discogs_data or {}
        response = RecordResponse.model_validate(record)
        response.artist_id = discogs_data.get("artist_id")
        response.artist_thumb_image_url = discogs_data.get("artist_thumb_image_url")
        response.vinyl_color_raw = discogs_data.get("vinyl_color_raw")
        return await _enrich_response_with_rub(response, record, db)

    # Fallback local-first: создаём stub-запись из discogs_releases_index
    # без обращения к Discogs API. Юзер получает карточку за <100ms,
    # обогащение (tracklist, cover, artist) идёт фоном.
    # Это закрывает «вечную загрузку» когда юзер нажимает на версию релиза
    # которая ещё не в нашей БД — дамп покрывает ~13M релизов.
    try:
        dump_row = (await db.execute(
            text(
                "SELECT discogs_id, master_id, artist, title, year, country, "
                "format_type, label, catalog_norm, cover_image_url "
                "FROM discogs_releases_index WHERE discogs_id = :did LIMIT 1"
            ),
            {"did": discogs_id},
        )).mappings().first()
    except Exception:
        dump_row = None

    if dump_row:
        stub = Record(
            discogs_id=str(dump_row["discogs_id"]),
            discogs_master_id=str(dump_row["master_id"]) if dump_row["master_id"] else None,
            title=dump_row["title"] or "Unknown",
            artist=dump_row["artist"] or "Unknown",
            label=dump_row["label"],
            catalog_number=dump_row["catalog_norm"],
            year=dump_row["year"],
            country=dump_row["country"],
            format_type=dump_row["format_type"],
            cover_image_url=dump_row["cover_image_url"],
            source="discogs",
        )
        try:
            db.add(stub)
            await db.commit()
            await db.refresh(stub)
        except IntegrityError:
            await db.rollback()
            result = await db.execute(select(Record).where(Record.discogs_id == discogs_id))
            stub = result.scalar_one_or_none()
        if stub:
            # Обогащение payload/artist/price — fire-and-forget, собственные сессии
            if stub.discogs_id:
                asyncio.create_task(_enrich_stub_bg(stub.id, stub.discogs_id))
            response = RecordResponse.model_validate(stub)
            discogs_data = stub.discogs_data or {}
            response.artist_id = discogs_data.get("artist_id")
            response.artist_thumb_image_url = discogs_data.get("artist_thumb_image_url")
            response.vinyl_color_raw = discogs_data.get("vinyl_color_raw")
            return await _enrich_response_with_rub(response, stub, db)

    # Запрос в Discogs с watchdog: клиент не висит 60 сек.
    # asyncio.shield + create_task — на таймаут отдаём 503, но запрос
    # к Discogs продолжается в фоне и кладёт результат в Redis,
    # так что повторный запрос юзера отвечает мгновенно.
    discogs = DiscogsService()
    fetch_task = asyncio.create_task(discogs.get_release(discogs_id))
    fetch_task.add_done_callback(
        lambda t: t.exception() if not t.cancelled() else None
    )

    try:
        record_data = await asyncio.wait_for(asyncio.shield(fetch_task), timeout=20)
    except asyncio.TimeoutError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Discogs отвечает медленно. Попробуйте ещё раз через несколько секунд — данные подгружаются в фоне."
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Ошибка при получении данных из Discogs: {str(e)}"
        )

    try:
        record = Record(
            discogs_id=record_data.get("id"),
            discogs_master_id=record_data.get("master_id"),
            title=record_data.get("title", "Unknown"),
            artist=record_data.get("artist", "Unknown"),
            label=record_data.get("label"),
            catalog_number=record_data.get("catalog_number"),
            year=record_data.get("year"),
            country=record_data.get("country"),
            genre=record_data.get("genre"),
            style=record_data.get("style"),
            format_type=record_data.get("format"),
            barcode=record_data.get("barcode"),
            cover_image_url=record_data.get("cover_image"),
            thumb_image_url=record_data.get("thumb_image"),
            estimated_price_min=record_data.get("price_min"),
            estimated_price_max=record_data.get("price_max"),
            estimated_price_median=record_data.get("price_median"),
            is_first_press=bool(record_data.get("is_first_press")),
            is_canon=bool(record_data.get("is_canon")),
            is_collectible=bool(record_data.get("is_collectible")),
            is_limited=bool(record_data.get("is_limited")),
            is_hot=bool(record_data.get("is_hot")),
            discogs_data=record_data,
            tracklist=record_data.get("tracklist"),
        )

        db.add(record)
        await db.commit()
        await db.refresh(record)

        response = RecordResponse.model_validate(record)
        response.artist_id = record_data.get("artist_id")
        response.artist_thumb_image_url = record_data.get("artist_thumb_image_url")
        response.vinyl_color_raw = record_data.get("vinyl_color_raw")
        return await _enrich_response_with_rub(response, record, db)

    except IntegrityError:
        await db.rollback()
        result = await db.execute(
            select(Record).where(Record.discogs_id == discogs_id)
        )
        record = result.scalar_one_or_none()
        if record:
            response = RecordResponse.model_validate(record)
            response.artist_id = record_data.get("artist_id")
            response.artist_thumb_image_url = record_data.get("artist_thumb_image_url")
            response.vinyl_color_raw = record_data.get("vinyl_color_raw")
            return await _enrich_response_with_rub(response, record, db)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Не удалось сохранить запись",
        )


@router.post("/", response_model=RecordResponse, status_code=status.HTTP_201_CREATED)
async def create_record(
    record_data: RecordCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Создание пластинки вручную (без Discogs).
    Требует авторизации.
    """
    record = Record(**record_data.model_dump())
    db.add(record)
    await db.commit()
    await db.refresh(record)

    return record


@router.get("/masters/search", response_model=MasterSearchResponse)
async def search_masters(
    response: Response,
    q: str = Query(..., min_length=1, description="Поисковый запрос"),
    page: int = Query(1, ge=1, description="Номер страницы"),
    per_page: int = Query(20, ge=1, le=100, description="Записей на страницу"),
    current_user: User | None = Depends(get_current_user_optional),
):
    """
    Поиск мастер-релизов в Discogs.
    Не требует авторизации.
    """
    discogs = DiscogsService()

    try:
        results = await discogs.search_masters(
            query=q,
            page=page,
            per_page=per_page
        )
        # Кешируем на CDN только непустую выдачу — пустой ответ при деградации
        # Discogs не должен залипать в HTTP-кеше.
        if results.results:
            response.headers["Cache-Control"] = "public, max-age=300"
        return results
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Ошибка при поиске мастер-релизов: {str(e)}"
        )


@router.get("/releases/search", response_model=ReleaseSearchResponse)
async def search_releases(
    response: Response,
    q: str = Query(..., min_length=1, description="Поисковый запрос"),
    format: str | None = Query(None, description="Фильтр по формату (Vinyl, CD, Cassette)"),
    country: str | None = Query(None, description="Фильтр по стране"),
    year: int | None = Query(None, description="Фильтр по году (точный)"),
    year_min: int | None = Query(None, description="Минимальный год (включительно)"),
    year_max: int | None = Query(None, description="Максимальный год (включительно)"),
    page: int = Query(1, ge=1, description="Номер страницы"),
    per_page: int = Query(20, ge=1, le=100, description="Записей на страницу"),
    current_user: User | None = Depends(get_current_user_optional),
    db: AsyncSession = Depends(get_db),
):
    """
    Поиск конкретных релизов с фильтрами в Discogs.
    Не требует авторизации.
    """
    discogs = DiscogsService()

    try:
        results = await discogs.search_releases(
            query=q,
            format=format,
            country=country,
            year=year,
            year_min=year_min,
            year_max=year_max,
            page=page,
            per_page=per_page
        )
        await _enrich_search_results_with_rarity(
            results.results, db, id_attr="release_id", format_attr="format"
        )
        # Store-native (нет на Discogs, source='store') подмешиваем СВЕРХУ — это
        # «наши» свежие релизы из Маркета, которых Discogs API не отдаёт. Только
        # на первой странице: их единицы, пагинация дальше — чистый Discogs.
        # Дедуп не нужен: store-native release_id=UUID, Discogs release_id=int.
        if page == 1:
            try:
                native = await _search_store_native_releases(
                    db, q, format, year, year_min, year_max, limit=20
                )
            except Exception:
                logger.warning("store-native release search failed", exc_info=True)
                native = []
            if native:
                results.results = native + results.results
                results.total += len(native)
        # Кешируем на CDN только непустую выдачу (см. search_masters).
        if results.results:
            response.headers["Cache-Control"] = "public, max-age=300"
        return results
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Ошибка при поиске релизов: {str(e)}"
        )


def _release_only_id(master_id: str) -> str | None:
    """Возвращает discogs release id, если master_id — синтетический префикс
    release-only айтема (`r{release_id}`), иначе None. Такие id отдаёт
    get_artist_masters для релизов артиста без master-группировки на Discogs;
    префикс не коллизирует с реальными master_id (всегда чисто цифровыми)."""
    if len(master_id) > 1 and master_id[0] == "r" and master_id[1:].isdigit():
        return master_id[1:]
    return None


async def _synth_master_from_release(release_id: str) -> MasterRelease:
    """Синтез MasterRelease из обычного релиза. Release-only карточки артиста
    открываются через /master/r{release_id}; здесь отдаём релиз как мастер
    (одна версия — он сам). Watchdog 20с — клиент не висит в axios timeout;
    master-экран сам ретраит 503 дважды."""
    discogs = DiscogsService()
    fetch_task = asyncio.create_task(discogs.get_release(release_id))
    fetch_task.add_done_callback(
        lambda t: t.exception() if not t.cancelled() else None
    )
    try:
        d = await asyncio.wait_for(asyncio.shield(fetch_task), timeout=20)
    except asyncio.TimeoutError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Discogs отвечает медленно. Попробуйте ещё раз через несколько секунд.",
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Ошибка при получении релиза: {str(e)}",
        )
    genre = d.get("genre")
    style = d.get("style")
    return MasterRelease(
        master_id=f"r{release_id}",
        title=d.get("title") or "Unknown",
        artist=d.get("artist") or "Unknown",
        artist_id=str(d["artist_id"]) if d.get("artist_id") else None,
        artist_thumb_image_url=d.get("artist_thumb_image_url"),
        year=d.get("year"),
        main_release_id=release_id,
        genres=[g.strip() for g in genre.split(",")] if genre else [],
        styles=[s.strip() for s in style.split(",")] if style else [],
        cover_image_url=d.get("cover_image") or d.get("thumb_image"),
        tracklist=d.get("tracklist") or [],
    )


@router.get("/masters/{master_id}", response_model=MasterRelease)
async def get_master(
    master_id: str,
    response: Response,
    current_user: User | None = Depends(get_current_user_optional),
):
    """
    Получение информации о мастер-релизе.
    Не требует авторизации.
    """
    response.headers["Cache-Control"] = "public, max-age=3600"

    # Release-only айтем (r{release_id}) → синтез из релиза.
    release_id = _release_only_id(master_id)
    if release_id is not None:
        return await _synth_master_from_release(release_id)

    # Легаси-артефакт: у релизов без мастера Discogs отдаёт master_id=0,
    # старые строки БД хранят '0'. Живой запрос /masters/0 в Discogs всегда
    # падает → клиент видел 503 и «Повторить». Отвечаем 404 сразу.
    if not master_id.isdigit() or master_id == "0":
        raise HTTPException(status_code=404, detail="Master not found")

    discogs = DiscogsService()

    try:
        master = await discogs.get_master(master_id)
        # Замыкаем петлю обложек: live-master несёт cover почти всегда, а
        # сетка артиста (local-first) знает только cover_image_url индекса.
        # Персистим в discogs_master_covers — сетка подхватит через COALESCE.
        if master.cover_image_url and master_id.isdigit():
            _schedule_master_cover_persist(int(master_id), master.cover_image_url)
        return master
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Ошибка при получении мастер-релиза: {str(e)}"
        )


_master_cover_persist_tasks: set[asyncio.Task] = set()


def _schedule_master_cover_persist(master_id: int, cover_url: str) -> None:
    """Fire-and-forget upsert обложки мастера. Ошибки глотаются."""
    # Discogs отдаёт st.discogs.com/.../spacer.gif как no-image заглушку —
    # не персистим её как настоящую обложку (иначе мастер навсегда с пустышкой).
    if not cover_url or "spacer.gif" in cover_url or "st.discogs.com" in cover_url:
        return

    async def _persist() -> None:
        try:
            from app.database import async_session_maker
            async with async_session_maker() as session:
                await session.execute(
                    text(
                        "INSERT INTO discogs_master_covers (master_id, cover_image_url) "
                        "VALUES (:mid, :url) "
                        "ON CONFLICT (master_id) DO UPDATE "
                        "SET cover_image_url = EXCLUDED.cover_image_url, updated_at = now()"
                    ),
                    {"mid": master_id, "url": cover_url},
                )
                await session.commit()
        except Exception:
            logger.debug("master cover persist failed: %s", master_id, exc_info=True)

    task = asyncio.create_task(_persist())
    _master_cover_persist_tasks.add(task)
    task.add_done_callback(_master_cover_persist_tasks.discard)


@router.get("/masters/{master_id}/versions", response_model=MasterVersionsResponse)
async def get_master_versions(
    master_id: str,
    response: Response,
    background_tasks: BackgroundTasks,
    page: int = Query(1, ge=1, description="Номер страницы"),
    per_page: int = Query(50, ge=1, le=100, description="Записей на страницу"),
    current_user: User | None = Depends(get_current_user_optional),
    db: AsyncSession = Depends(get_db),
):
    """
    Получение всех версий (изданий) мастер-релиза.
    Не требует авторизации.

    Стратегия (fix axios 60s timeout, 2026-05):
    - Синхронная часть отдаёт is_canon/is_limited/is_hot — всё, что считается
      без N+1 к /releases/{id}. is_hot берём из stats.community мастер-versions
      response.
    - is_collectible требует price_stats + formats[].descriptions из
      /releases/{id} — отправляем в BackgroundTasks и пишем в
      master_versions_enriched. Следующий заход юзера получает enriched-ответ
      из Redis.
    - Single-flight через Redis-lock защищает от запуска параллельных
      enrichment-тасков на одну страницу.
    - Watchdog 25 сек на синхронной части — чтобы клиент не висел в axios
      timeout 60s, если Discogs отвечает медленно.
    """
    # Release-only айтем (r{release_id}) — мастер-группировки нет, версия одна
    # (сам релиз). Отдаём её, чтобы master-экран показал «Все версии (1)» и
    # versions-экран не падал в 503.
    release_id = _release_only_id(master_id)
    if release_id is None and (not master_id.isdigit() or master_id == "0"):
        # Легаси master_id='0' (Discogs отдаёт 0 для релизов без мастера).
        raise HTTPException(status_code=404, detail="Master not found")
    if release_id is not None:
        response.headers["Cache-Control"] = "public, max-age=3600"
        if page > 1:
            return MasterVersionsResponse(
                results=[], total=1, page=page, per_page=per_page,
            )
        # Тянем релиз (кэш прогрет соседним get_master) ради format → чип
        # Винил/CD на versions-экране работает (иначе major_formats пуст → 0).
        discogs = DiscogsService()
        fetch_task = asyncio.create_task(discogs.get_release(release_id))
        fetch_task.add_done_callback(
            lambda t: t.exception() if not t.cancelled() else None
        )
        try:
            d = await asyncio.wait_for(asyncio.shield(fetch_task), timeout=20)
        except asyncio.TimeoutError:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Discogs отвечает медленно. Попробуйте ещё раз через несколько секунд.",
            )
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=f"Ошибка при получении релиза: {str(e)}",
            )
        fmt = d.get("format")
        return MasterVersionsResponse(
            results=[
                MasterVersion(
                    release_id=release_id,
                    title=d.get("title") or "Unknown",
                    label=d.get("label"),
                    catalog_number=d.get("catalog_number"),
                    country=d.get("country"),
                    year=d.get("year"),
                    format=fmt,
                    major_formats=[fmt] if fmt else [],
                    cover_image_url=d.get("cover_image") or d.get("thumb_image"),
                    is_canon=True,
                )
            ],
            total=1,
            page=page,
            per_page=per_page,
        )

    # Кэш ENRICHED-ответа отдельный — get_master_versions кэширует только сырые
    # данные от Discogs (теперь с is_hot), здесь храним полностью обогащённую
    # версию (с is_collectible), чтобы не делать N×get_release на каждый запрос.
    enriched_ck = f"{master_id}:p{page}:pp{per_page}"
    cached_enriched = await cache.get("master_versions_enriched", enriched_ck)
    if cached_enriched:
        resp_obj = MasterVersionsResponse(**cached_enriched)
        # Если в кэше остались версии без обложки (master/versions thumb пуст) —
        # один раз в 6ч добираем их через get_release фоном и переписываем кэш
        # (durable-персист в дамп). no-store на этот ответ, чтобы следующий заход
        # дошёл до уже залеченного кэша, а не до часового nginx-кэша пустого.
        has_uncovered = any(
            not (v.cover_image_url or v.thumb_image_url) for v in resp_obj.results
        )
        if has_uncovered:
            # КРИТИЧНО: пока в ответе есть версии без обложки — НИКОГДА не отдаём
            # max-age, иначе nginx закэширует частичный (с закрывашками) ответ на
            # час, и телефон будет ловить x-cache-status:HIT со старыми пустотами,
            # даже после того как Redis-enriched долечился. no-store → запрос
            # всегда доходит до бэка и берёт свежий (долеченный) Redis-кэш.
            response.headers["Cache-Control"] = "no-store"
            # Заодно раз в 6ч пинаем фоновую дозагрузку обложек (get_release).
            if await cache.set_nx(
                "master_versions_straggler", enriched_ck, "1", ttl=21600
            ):
                background_tasks.add_task(
                    _enrich_covers_from_api,
                    master_id=master_id,
                    page=page,
                    per_page=per_page,
                    versions_dump=cached_enriched,
                    enriched_ck=enriched_ck,
                )
            # Response-time master-fallback для дыр: мутируем только resp_obj
            # (Redis-кэш нетронут → straggler-лечение точных обложек живо).
            mc_url = await _master_cover_url(db, master_id)
            if mc_url:
                for v in resp_obj.results:
                    if not (v.cover_image_url or v.thumb_image_url):
                        v.cover_image_url = mc_url
        else:
            response.headers["Cache-Control"] = "public, max-age=3600"
        return resp_obj

    # Local-first: discogs_releases_index содержит все 13M releases с master_id.
    # Полный SELECT покрывает большинство мастер-релизов без обращения к Discogs
    # API → убирает 503 от rate-limit и timeout'ов. Главное отличие от API-ответа:
    # cover_image_url в локальном индексе = NULL (дампы Discogs не несут image URLs),
    # main_release_id неизвестен → is_canon будет проставлен только из Record.is_canon.
    local_versions = await _fetch_versions_from_local_index(db, master_id, page, per_page)
    if local_versions is not None and local_versions.total > 0:
        versions = local_versions
        main_release_id = None

        # Master-обложка (Deezer-backfill 110k+, store, discogs) — закрывает
        # дыры на response-time и позволяет пропустить inline-watchdog Discogs.
        master_cover_url = await _master_cover_url(db, master_id)

        # P3: inline short-watchdog. Если у большинства версий нет обложки —
        # пробуем 1 вызов Discogs прямо сейчас (≤4с) и мёржим thumbs в ответ.
        # get_master_versions Redis-кэшируется → фоновый таск ниже добьёт остаток
        # из кэша без второго токена. На таймаут/ошибку — тихий fallback на retry.
        covered = sum(
            1 for v in versions.results if v.cover_image_url or v.thumb_image_url
        )
        # covered считается ТОЛЬКО по per-release источникам (records/index) —
        # master-fallback не учитываем, иначе фоновый enrich точных обложек
        # перестанет триггериться. Но при наличии master-обложки inline-вызов
        # Discogs (до 4с ожидания юзером) пропускаем: дыры закроет fallback
        # ниже, а точные обложки дольёт background _enrich_covers_from_api.
        if covered < len(versions.results) / 2 and not master_cover_url:
            try:
                api_resp = await asyncio.wait_for(
                    DiscogsService().get_master_versions(
                        master_id=master_id, page=page, per_page=per_page,
                        creds=user_creds(current_user),
                    ),
                    timeout=4,
                )
                cover_by_id = {
                    v.release_id: (v.cover_image_url or v.thumb_image_url)
                    for v in api_resp.results
                    if v.cover_image_url or v.thumb_image_url
                }
                for v in versions.results:
                    if not v.cover_image_url and not v.thumb_image_url:
                        c = cover_by_id.get(v.release_id)
                        if c:
                            v.cover_image_url = c
            except Exception:
                pass

        # Фоновый таск: персист обложек в PG (durable, мимо Redis-TTL), мёрж
        # версий, отсутствующих в дампе, и запись enriched-кэша. Вызов
        # get_master_versions попадёт в Redis-кэш после inline-фетча → без токена.
        background_tasks.add_task(
            _enrich_covers_from_api,
            master_id=master_id,
            page=page,
            per_page=per_page,
            versions_dump=versions.model_dump(),
            enriched_ck=enriched_ck,
        )

        # P2: бесплатный прогрев обложек через CAA (по barcode, мимо Discogs
        # rate-limit) для версий всё ещё без cover. Пишет в
        # discogs_releases_index.cover_image_url → следующий заход берёт из PG.
        from app.services.cover_warm import schedule_warm_dump_covers
        schedule_warm_dump_covers(
            [
                v.release_id
                for v in versions.results
                if v.release_id and not (v.cover_image_url or v.thumb_image_url)
            ]
        )
    else:
        master_cover_url = None  # API-ветка несёт обложки сама
        discogs = DiscogsService()
        try:
            versions, main_release_id = await asyncio.wait_for(
                _fetch_master_versions_and_main_release(discogs, master_id, page, per_page),
                timeout=25,
            )
        except asyncio.TimeoutError:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Discogs API отвечает медленно — попробуйте ещё раз через минуту",
            )
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=f"Ошибка при получении версий мастер-релиза: {str(e)}"
            )

    # Дешёвые «on-the-fly» флаги для всех версий:
    # - is_canon = release_id == master.main_release_id
    # - is_limited = парсинг строки format на токены
    # - is_hot уже выставлен в discogs.get_master_versions из stats.community
    for v in versions.results:
        if main_release_id and v.release_id == main_release_id:
            v.is_canon = True
        fmt_lower = (v.format or "").lower()
        if any(tok in fmt_lower for tok in DiscogsService.LIMITED_TOKENS):
            v.is_limited = True

    # Локальная БД дополняет всеми флагами для виденных
    release_ids = [v.release_id for v in versions.results if v.release_id]
    seen_ids: set[str] = set()
    if release_ids:
        rows = await db.execute(
            select(
                Record.discogs_id,
                Record.is_canon,
                Record.is_collectible,
                Record.is_limited,
                Record.is_hot,
            ).where(Record.discogs_id.in_(release_ids))
        )
        flags_by_id = {
            row.discogs_id: (row.is_canon, row.is_collectible, row.is_limited, row.is_hot)
            for row in rows
        }
        seen_ids = set(flags_by_id.keys())
        for v in versions.results:
            f = flags_by_id.get(v.release_id)
            if f:
                v.is_canon = v.is_canon or f[0]
                v.is_collectible = v.is_collectible or f[1]
                v.is_limited = v.is_limited or f[2]
                v.is_hot = v.is_hot or f[3]

    # Для невиденных в БД — is_collectible считаем фоном через get_release.
    # Юзер получает ответ за ~1–3 сек на холоде; enriched-кэш заполнится
    # к следующему заходу или pull-to-refresh.
    unseen_ids = [v.release_id for v in versions.results if v.release_id and v.release_id not in seen_ids]
    if unseen_ids:
        background_tasks.add_task(
            _enrich_collectible_async,
            master_id=master_id,
            page=page,
            per_page=per_page,
            versions_dump=versions.model_dump(),
            unseen_ids=unseen_ids,
            enriched_ck=enriched_ck,
        )
    else:
        # Все виденные — можно сразу записать enriched-кэш
        await cache.set("master_versions_enriched", enriched_ck, versions.model_dump(), TTL_MASTER_VERSIONS)

    # local-first ответ может быть неполным: обложки и версии, отсутствующие в
    # дампе, дотягиваются фоном в master_versions_enriched. Если разрешить nginx
    # кэшировать этот ответ (max-age=3600), он час отдаёт версию без обложек, а
    # клиентский retry попадает в nginx-кэш и не доходит до enriched в Redis.
    # no-store → retry проходит до бэка и получает обогащённый ответ.
    response.headers["Cache-Control"] = "no-store"

    # Response-time fallback: оставшиеся дыры закрываем master-обложкой.
    # ВАЖНО: строго после всех model_dump() выше — bg-таски и enriched-кэш
    # снимаются БЕЗ fallback'а, per-release лечение не подавляется.
    if master_cover_url:
        for v in versions.results:
            if not v.cover_image_url and not v.thumb_image_url:
                v.cover_image_url = master_cover_url

    return versions


async def _master_cover_url(db: AsyncSession, master_id: str) -> str | None:
    """Обложка мастера из discogs_master_covers (Deezer-backfill, store, discogs).

    Дешёвый PK-lookup. Используется как response-time fallback для версий без
    per-release обложки: НЕ персистится в кэши/дампы, чтобы фоновый enrich
    продолжал лечить точные per-release обложки.
    """
    try:
        mid = int(master_id)
    except (TypeError, ValueError):
        return None
    row = await db.execute(
        text("SELECT cover_image_url FROM discogs_master_covers WHERE master_id = :m"),
        {"m": mid},
    )
    return row.scalar()


async def _fetch_versions_from_local_index(
    db: AsyncSession,
    master_id: str,
    page: int,
    per_page: int,
) -> MasterVersionsResponse | None:
    """Возвращает MasterVersionsResponse из discogs_releases_index или None
    если master_id не парсится в bigint. Делает 2 запроса: count + paged list.
    """
    try:
        master_id_int = int(master_id)
    except (TypeError, ValueError):
        return None

    total_row = await db.execute(
        text("SELECT count(*) AS n FROM discogs_releases_index WHERE master_id = :m"),
        {"m": master_id_int},
    )
    total = int(total_row.scalar() or 0)
    if total == 0:
        return None

    offset = (page - 1) * per_page
    # LEFT JOIN records: подтягиваем обложки из локального кэша.
    # Дамп Discogs не несёт image URLs, но records.cover_local_path /
    # records.cover_image_url заполнены для релизов которые уже видели.
    rows = (
        await db.execute(
            text(
                """
                SELECT
                    dri.discogs_id::text AS release_id,
                    dri.artist, dri.title, dri.year, dri.country,
                    dri.format_type, dri.label, dri.catalog_norm,
                    COALESCE(
                        CASE WHEN r.cover_local_path IS NOT NULL
                             THEN '/uploads/' || r.cover_local_path END,
                        r.cover_image_url,
                        dri.cover_image_url
                    ) AS cover_image_url
                FROM discogs_releases_index dri
                LEFT JOIN records r
                    ON r.discogs_id = dri.discogs_id::text
                    AND r.merged_into_id IS NULL
                WHERE dri.master_id = :m
                ORDER BY dri.year ASC NULLS LAST, dri.discogs_id ASC
                LIMIT :limit OFFSET :offset
                """
            ),
            {"m": master_id_int, "limit": per_page, "offset": offset},
        )
    ).mappings().all()

    results = [
        MasterVersion(
            release_id=row["release_id"],
            title=row["title"],
            label=row["label"],
            catalog_number=row["catalog_norm"],
            country=row["country"],
            year=row["year"],
            format=row["format_type"],
            major_formats=[row["format_type"]] if row["format_type"] else [],
            thumb_image_url=None,
            cover_image_url=row["cover_image_url"],
        )
        for row in rows
    ]
    return MasterVersionsResponse(
        results=results, total=total, page=page, per_page=per_page,
    )


async def _fetch_master_versions_and_main_release(
    discogs: DiscogsService,
    master_id: str,
    page: int,
    per_page: int,
) -> tuple[MasterVersionsResponse, str | None]:
    """Параллельно тянем versions + master.main_release_id под общим watchdog."""
    versions_task = asyncio.create_task(
        discogs.get_master_versions(master_id=master_id, page=page, per_page=per_page)
    )
    master_task = asyncio.create_task(discogs.get_master(master_id))

    versions = await versions_task
    try:
        master = await master_task
        main_release_id = str(master.main_release_id) if master.main_release_id else None
    except Exception:
        main_release_id = None
    return versions, main_release_id


async def _enrich_covers_from_api(
    *,
    master_id: str,
    page: int,
    per_page: int,
    versions_dump: dict,
    enriched_ck: str,
) -> None:
    """Подтягивает обложки И версии, отсутствующие в локальном дампе, одним
    вызовом Discogs API.

    get_master_versions возвращает `thumb` по каждой версии — это намного
    эффективнее N×get_release. Дополнительно: дамп Discogs — месячный снапшот
    и не содержит релизы, добавленные/изменённые позже снапшота либо бывшие в
    Draft. Поэтому мёржим версии из живого API, которых нет в локальном списке
    (дедуп по release_id), и обновляем total. Результат сохраняется в
    master_versions_enriched — следующий заход юзера получит полный список.

    NB: не делаем early-return при наличии enriched-кэша. Этот таск —
    единственный, кто тянет live-API и добавляет версии, отсутствующие в дампе.
    _enrich_collectible_async может записать enriched (local-only) раньше нас;
    тогда берём его как базу и всё равно домёрживаем недостающие API-версии.
    """
    lock_key = f"covers:{master_id}:p{page}:pp{per_page}"
    if not await cache.set_nx("master_versions_lock", lock_key, "1", ttl=120):
        return

    try:
        discogs = DiscogsService()
        api_resp = await discogs.get_master_versions(
            master_id=master_id, page=page, per_page=per_page
        )

        # База для мёржа: уже записанный enriched (от collectible-таска), иначе
        # локальный dump. Так не теряем флаги/обложки, проставленные ранее.
        existing = await cache.get("master_versions_enriched", enriched_ck)
        versions = MasterVersionsResponse(**(existing or versions_dump))
        changed = False

        # 1) Обложки для версий, уже присутствующих в локальном списке.
        # Берём полную cover (600px), не thumb — её же персистим в PG.
        cover_by_id = {
            v.release_id: (v.cover_image_url or v.thumb_image_url)
            for v in api_resp.results
            if v.cover_image_url or v.thumb_image_url
        }
        for v in versions.results:
            if not v.cover_image_url and not v.thumb_image_url:
                c = cover_by_id.get(v.release_id)
                if c:
                    v.cover_image_url = c
                    changed = True

        # 1b) Для версий всё ещё без cover добираем обложку из get_release.
        # master/versions отдаёт thumb=null для части переизданий (винил-репрессы),
        # но у самого релиза images есть (это и видно при тапе в деталь). Bounded
        # cap+watchdog — чтобы не повторить 60s-фан-аут экрана артиста.
        # cap 30: одна heal-волна закрывает и крупные мастера; 10s-watchdog ниже
        # всё равно держит время, sem 5 ограничивает параллельность к Discogs.
        still = [
            v for v in versions.results
            if not v.cover_image_url and not v.thumb_image_url
        ][:30]

        # 1a-bis) Сначала CAA по офлайн-маппингу mb_discogs_map: has_front
        # известен из дампа CAA-индекса → URL строится БЕЗ единого сетевого
        # вызова. Схлопывает большинство страглеров до нуля Discogs-запросов.
        if still:
            from app.database import async_session_maker
            ids = [int(v.release_id) for v in still if v.release_id and v.release_id.isdigit()]
            if ids:
                async with async_session_maker() as _s:
                    caa_rows = (await _s.execute(
                        text(
                            "SELECT discogs_id::text AS did, mbid::text AS mbid "
                            "FROM mb_discogs_map "
                            "WHERE discogs_id = ANY(:ids) AND has_front"
                        ),
                        {"ids": ids},
                    )).mappings().all()
                caa_by_id = {
                    r["did"]: f"https://coverartarchive.org/release/{r['mbid']}/front-1200"
                    for r in caa_rows
                }
                if caa_by_id:
                    for v in versions.results:
                        if (
                            not v.cover_image_url and not v.thumb_image_url
                            and v.release_id in caa_by_id
                        ):
                            v.cover_image_url = caa_by_id[v.release_id]
                            changed = True
                    cover_by_id.update(caa_by_id)
                    still = [
                        v for v in still
                        if not v.cover_image_url and not v.thumb_image_url
                    ]

        if still:
            sem = asyncio.Semaphore(5)

            async def _one_cover(v):
                async with sem:
                    try:
                        # get_release_cover, НЕ get_release: полный get_release
                        # параллельно тянет marketplace/stats — для обложки это
                        # 2× расход окна Discogs впустую (цены тут не нужны).
                        return v.release_id, await discogs.get_release_cover(v.release_id)
                    except Exception:
                        return v.release_id, None

            tasks = [asyncio.create_task(_one_cover(v)) for v in still]
            done, pending = await asyncio.wait(tasks, timeout=10)
            for t in pending:
                t.cancel()
            release_covers: dict[str, str] = {}
            for t in done:
                try:
                    rid, cov = t.result()
                    if cov:
                        release_covers[rid] = cov
                except Exception:
                    pass
            if release_covers:
                for v in versions.results:
                    if (
                        not v.cover_image_url and not v.thumb_image_url
                        and v.release_id in release_covers
                    ):
                        v.cover_image_url = release_covers[v.release_id]
                        changed = True
                cover_by_id.update(release_covers)

        # P1: персистим обложки в discogs_releases_index.cover_image_url —
        # переживает Redis-TTL, виден всем юзерам и detail-stub'у через COALESCE.
        # Пишем только в NULL-строки, чтобы не затереть уже прогретое (CAA/cover_warm).
        if cover_by_id:
            from app.database import async_session_maker
            async with async_session_maker() as session:
                for rid, url in cover_by_id.items():
                    if rid and rid.isdigit():
                        await session.execute(
                            text(
                                "UPDATE discogs_releases_index "
                                "SET cover_image_url = :url "
                                "WHERE discogs_id = :did "
                                "AND cover_image_url IS NULL"
                            ),
                            {"url": url, "did": int(rid)},
                        )
                await session.commit()

        # 2) Версии из API, которых нет в дампе (дедуп по release_id).
        local_ids = {v.release_id for v in versions.results}
        for av in api_resp.results:
            if av.release_id and av.release_id not in local_ids:
                fmt_lower = (av.format or "").lower()
                if any(tok in fmt_lower for tok in DiscogsService.LIMITED_TOKENS):
                    av.is_limited = True
                versions.results.append(av)
                local_ids.add(av.release_id)
                changed = True

        # total отражает истинное число версий на мастере (pagination.items API),
        # если оно больше локального — дамп отстал.
        if api_resp.total > versions.total:
            versions.total = api_resp.total
            changed = True

        if changed:
            # Сортировка как в локальном индексе: год ASC, NULL в конец.
            versions.results.sort(
                key=lambda v: (v.year is None, v.year or 0, v.release_id or "")
            )
            await cache.set(
                "master_versions_enriched", enriched_ck,
                versions.model_dump(), TTL_MASTER_VERSIONS,
            )
    except Exception:
        logger.exception("_enrich_covers_from_api failed master_id=%s", master_id)
    finally:
        await cache.delete("master_versions_lock", lock_key)


async def _enrich_collectible_async(
    *,
    master_id: str,
    page: int,
    per_page: int,
    versions_dump: dict,
    unseen_ids: list[str],
    enriched_ck: str,
) -> None:
    """Фоновое обогащение is_collectible через discogs.get_release.

    Single-flight: Redis-lock не даёт двум воркерам обогащать одну страницу
    параллельно. Watchdog 120 сек защищает от вечного зависания.
    По завершении пишет master_versions_enriched, чтобы следующий заход
    юзера попал в кэш.
    """
    lock_key = f"enriching:{master_id}:p{page}:pp{per_page}"
    if not await cache.set_nx("master_versions_lock", lock_key, "1", ttl=180):
        # Другой воркер уже обогащает эту страницу
        return

    try:
        versions = MasterVersionsResponse(**versions_dump)
        unseen_set = set(unseen_ids)
        unseen_versions = [v for v in versions.results if v.release_id in unseen_set]

        discogs = DiscogsService()
        sem = asyncio.Semaphore(5)

        async def fetch_flags(v):
            async with sem:
                try:
                    # Priority.ENRICHMENT — не дренит token-bucket UI-запросов.
                    data = await discogs.get_release(v.release_id, priority=Priority.ENRICHMENT)
                    v.is_canon = v.is_canon or bool(data.get("is_canon"))
                    v.is_collectible = v.is_collectible or bool(data.get("is_collectible"))
                    v.is_limited = v.is_limited or bool(data.get("is_limited"))
                    v.is_hot = v.is_hot or bool(data.get("is_hot"))
                    # Обложка: берём из get_release если версия ещё без cover
                    if not v.cover_image_url and not v.thumb_image_url:
                        cover = data.get("cover_image") or data.get("cover_image_url")
                        thumb = data.get("thumb_image") or data.get("thumb_image_url")
                        if cover:
                            v.cover_image_url = cover
                        elif thumb:
                            v.thumb_image_url = thumb
                except Exception:
                    pass

        try:
            await asyncio.wait_for(
                asyncio.gather(*[fetch_flags(v) for v in unseen_versions]),
                timeout=120,
            )
        except asyncio.TimeoutError:
            logger.warning(
                "master_versions enrichment timeout master_id=%s page=%s",
                master_id, page,
            )

        # Мёрджим с уже имеющимся кэшем: если _enrich_covers_from_api успел
        # записать thumb'ы — не затираем их нулями из нашего versions объекта.
        # Также подбираем версии, дозалитые из API (отсутствуют в дампе), и
        # больший total — иначе перезатёрли бы их local-only списком.
        existing = await cache.get("master_versions_enriched", enriched_ck)
        if existing:
            existing_resp = MasterVersionsResponse(**existing)
            cover_by_id = {
                v.release_id: (v.cover_image_url or v.thumb_image_url)
                for v in existing_resp.results
                if v.cover_image_url or v.thumb_image_url
            }
            for v in versions.results:
                if not v.cover_image_url and not v.thumb_image_url:
                    c = cover_by_id.get(v.release_id)
                    if c:
                        v.thumb_image_url = c
            local_ids = {v.release_id for v in versions.results}
            for ev in existing_resp.results:
                if ev.release_id and ev.release_id not in local_ids:
                    versions.results.append(ev)
                    local_ids.add(ev.release_id)
            if existing_resp.total > versions.total:
                versions.total = existing_resp.total
            versions.results.sort(
                key=lambda v: (v.year is None, v.year or 0, v.release_id or "")
            )
        await cache.set("master_versions_enriched", enriched_ck, versions.model_dump(), TTL_MASTER_VERSIONS)
    finally:
        await cache.delete("master_versions_lock", lock_key)


@router.get("/artists/search", response_model=ArtistSearchResponse)
async def search_artists(
    response: Response,
    q: str = Query(..., min_length=1, description="Поисковый запрос"),
    page: int = Query(1, ge=1, description="Номер страницы"),
    per_page: int = Query(20, ge=1, le=100, description="Записей на страницу"),
    current_user: User | None = Depends(get_current_user_optional),
    db: AsyncSession = Depends(get_db),
):
    """
    Поиск артистов в Discogs.
    Не требует авторизации.
    """
    discogs = DiscogsService()

    try:
        results = await discogs.search_artists(
            query=q,
            page=page,
            per_page=per_page
        )
        for artist in results.results:
            artist.name = clean_artist_name(artist.name) or artist.name

        # Жёсткий фильтр: оставляем только артистов, чьё имя есть в локальном
        # дамп-индексе (= у них есть релизы). Убирает мусорных тёзок/фан-аккаунты
        # Discogs с 0 релизов. Один index-scan по discogs_artist_names, без
        # вызовов Discogs API. Fail-open на ошибке БД (вернёт все имена → дропа
        # нет). Применяется и на cache-hit, т.к. фильтр живёт в endpoint.
        if results.results:
            from app.services.discogs_index import filter_artist_names_with_releases
            with_releases = await filter_artist_names_with_releases(
                db, [a.name for a in results.results]
            )
            results.results = [
                a for a in results.results
                if a.name.strip().lower() in with_releases
            ]

        # Кешируем на CDN только когда Discogs реально что-то вернул (total>0).
        # results может быть пуст после фильтра псевдонимов при total>0 — это
        # валидно кешировать; пустой total — деградация, не кешируем.
        if results.total:
            response.headers["Cache-Control"] = "public, max-age=300"
        return results
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Ошибка при поиске артистов: {str(e)}"
        )


@router.get("/artists/{artist_id}", response_model=Artist)
async def get_artist(
    artist_id: str,
    response: Response,
    current_user: User | None = Depends(get_current_user_optional),
):
    """
    Получение информации об артисте.
    Не требует авторизации.
    """
    response.headers["Cache-Control"] = "public, max-age=1800"
    discogs = DiscogsService()

    try:
        artist = await discogs.get_artist(artist_id)
        return artist
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Ошибка при получении данных артиста: {str(e)}"
        )


@router.get("/artists/{artist_id}/releases", response_model=ReleaseSearchResponse)
async def get_artist_releases(
    artist_id: str,
    response: Response,
    page: int = Query(1, ge=1, description="Номер страницы"),
    per_page: int = Query(50, ge=1, le=100, description="Записей на страницу"),
    current_user: User | None = Depends(get_current_user_optional),
    db: AsyncSession = Depends(get_db),
):
    """
    Получение релизов артиста.
    Не требует авторизации.
    """
    response.headers["Cache-Control"] = "public, max-age=300"
    discogs = DiscogsService()

    # Local-first: все издания артиста из дамп-индекса (artist_ids GIN) — ноль
    # вызовов Discogs, sub-100ms. None = артиста нет в индексе → live-путь ниже.
    try:
        from app.services.discogs_index import get_artist_releases_local

        local = await get_artist_releases_local(
            db, artist_id, page=page, per_page=per_page,
        )
        if local is not None:
            await _enrich_search_results_with_rarity(
                local.results, db, id_attr="release_id", format_attr="format"
            )
            # Заглушки на странице → no-store, чтобы cover-retry дошёл до бэка,
            # а nginx не запинил неполный ответ (урок versions-экрана).
            if any(not r.cover_image_url for r in local.results):
                response.headers["Cache-Control"] = "no-store"
            return local
    except Exception:
        logger.exception("local artist releases failed, live fallback: %s", artist_id)

    try:
        releases = await discogs.get_artist_releases(
            artist_id=artist_id,
            page=page,
            per_page=per_page
        )
        await _enrich_search_results_with_rarity(
            releases.results, db, id_attr="release_id", format_attr="format"
        )
        return releases
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Ошибка при получении релизов артиста: {str(e)}"
        )


@router.get("/artists/{artist_id}/masters", response_model=MasterSearchResponse)
async def get_artist_masters(
    artist_id: str,
    response: Response,
    page: int = Query(1, ge=1, description="Номер страницы"),
    per_page: int = Query(100, ge=1, le=100, description="Записей на страницу"),
    load_all: bool = Query(False, description="Загрузить все страницы сразу"),
    sort_order: str = Query("desc", regex="^(asc|desc)$", description="Порядок по году"),
    current_user: User | None = Depends(get_current_user_optional),
    db: AsyncSession = Depends(get_db),
):
    """
    Получение только master releases артиста (альбомы, синглы, EP).
    Возвращает только основные релизы без всех версий/изданий.
    При load_all=true загружает все страницы за один вызов.
    Не требует авторизации.
    """
    # Короткий edge-кэш: обложки части мастеров могут догружаться фоном
    # (watchdog в get_artist_masters), max-age=300 даёт им зажить за пару заходов.
    response.headers["Cache-Control"] = "public, max-age=300"
    discogs = DiscogsService()

    # Local-first: дискография из дамп-индекса (artist_ids GIN) — ноль вызовов
    # Discogs, sub-100ms. None = артиста нет в индексе или backfill ещё не
    # прогнан → live-путь ниже как раньше.
    try:
        from app.services.discogs_index import get_artist_masters_local

        local = await get_artist_masters_local(
            db, artist_id, page=page, per_page=per_page, sort_order=sort_order,
        )
        if local is not None:
            # Заглушки на странице → no-store: batch-прогрев уже запущен,
            # клиентский cover-retry через секунды должен дойти до бэкенда,
            # а nginx не должен запинить неполный ответ (урок versions-экрана).
            if any(not r.cover_image_url for r in local.results):
                response.headers["Cache-Control"] = "no-store"
            return local
    except Exception:
        logger.exception("local artist masters failed, live fallback: %s", artist_id)

    try:
        # Watchdog 25с — backstop, чтобы клиент не висел в axios timeout 60с,
        # если Discogs деградирует. Внутренний bound на cover-fallback уже
        # держит ответ в ~10с; creds юзера уводят вызовы на его личный bucket.
        masters = await asyncio.wait_for(
            discogs.get_artist_masters(
                artist_id=artist_id,
                page=page,
                per_page=per_page,
                load_all=load_all,
                sort_order=sort_order,
                creds=user_creds(current_user),
            ),
            timeout=25,
        )
        return masters
    except asyncio.TimeoutError:
        response.headers["Cache-Control"] = "no-store"
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Discogs API отвечает медленно — попробуйте ещё раз через минуту",
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Ошибка при получении master releases артиста: {str(e)}"
        )

