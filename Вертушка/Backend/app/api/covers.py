"""
API endpoints для обложек виниловых пластинок.

GET /covers/{discogs_id}  — вызывается ТОЛЬКО через nginx @covers_fallback
                            когда файл на диске не найден.
POST /covers/{discogs_id}/refresh — принудительное обновление обложки.
                                    Требует X-Internal-Token.
"""
import asyncio
import logging
from pathlib import Path

from fastapi import APIRouter, Depends, Header, HTTPException
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database import async_session_maker, get_db
from app.models.record import Record
from app.services.cache import cache
from app.services.cover_demand import (
    OUTCOME_BUDGET,
    OUTCOME_BUSY,
    OUTCOME_LIVE_HIT,
    OUTCOME_LIVE_MISS,
    OUTCOME_NEG_CACHE,
    OUTCOME_NOT_FOUND,
    OUTCOME_REDIRECT,
    record_cold_outcome,
    record_cold_request,
)
from app.services.cover_storage import (
    CoverStorageService,
    _download_cover_background,
    discogs_img_budget_exhausted,
    is_discogs_image_url,
    schedule_store_native_cover_cache,
)
from app.utils.url_guard import is_safe_redirect_target

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Обложки"])

# Сильные ссылки на фоновые задачи зеркалирования. asyncio держит на задачи
# только weak reference — bare create_task в обработчике, который сразу
# возвращает 302, GC-шится ДО запуска скачивания → файл m{gid}.jpg не пишется,
# и каждый заход снова падает в 302 на Discogs (баг «обложки грузятся заново»).
_mirror_tasks: set[asyncio.Task] = set()

# ── Гейты живого резолва ────────────────────────────────────────────────────
# Живой резолв — единственное место, где запрос юзера ходит по внешним API.
# Без гейтов он был бомбой: каждый повторный промах того же id заново гонял
# лестницу на 6с, параллельные запросы дублировали её, а каждый висящий
# запрос держал соединение пула БД (их 15 на один uvicorn-воркер).
_RESOLVE_NEG_NS = "cover_resolve_neg"
# 12ч (внутри вилки 6-24ч): достаточно, чтобы шквал ретраев одного экрана не
# гонял лестницу, и достаточно коротко, чтобы обложка, появившаяся у
# источников, приехала на следующий день.
_RESOLVE_NEG_TTL = 12 * 3600
_RESOLVE_LOCK_NS = "cover_resolve_lock"
# Резолв капнут 6с; TTL с запасом страхует от смерти процесса с висящим локом.
_RESOLVE_LOCK_TTL = 30
_RESOLVE_TIMEOUT = 6
# ~4 одновременных резолва на процесс: больше — значит лестница стала главным
# потребителем и пула БД, и троттлов источников. Остальные получают мгновенный
# 404 + фоновый прогрев.
_resolve_semaphore = asyncio.Semaphore(4)


def _spawn_mirror(discogs_id: str, url: str) -> None:
    """Fire-and-forget зеркалирование с удержанием ссылки до завершения."""
    task = asyncio.create_task(_download_cover_background(discogs_id, url))
    _mirror_tasks.add(task)
    task.add_done_callback(_mirror_tasks.discard)


def _safe(url: str | None) -> str | None:
    """Guard для всех 302 ручки /covers/{id}.

    Три разные причины не редиректить:
    1. собственное зеркало — петля;
    2. no-image заглушка Discogs (st.discogs.com/.../spacer.gif);
    3. небезопасная цель — иначе api-домен работает открытым редиректором.
       URL едет из dump-индекса и из живого резолва, то есть в конечном
       счёте из внешних данных. См. SECURITY_AUDIT_PRERELEASE.md §S2.
    """
    if not url:
        return None
    if url.startswith(get_settings().public_covers_base):
        return None
    if "spacer.gif" in url or "st.discogs.com" in url:
        return None
    if not is_safe_redirect_target(url):
        logger.warning("covers: небезопасная цель редиректа отброшена: %s", url)
        return None
    return url


async def _deny_discogs_by_budget(url: str | None) -> bool:
    """True — это discogs-URL при исчерпанном дневном бюджете скачиваний.

    302 на подписанный Discogs-URL при выеденном бюджете — почти наверняка
    битая картинка после 403 (клиентская заглушка честнее), а зеркалирование
    всё равно будет скипнуто бюджет-гейтом в download_and_store.
    """
    return bool(url) and is_discogs_image_url(url) and await discogs_img_budget_exhausted()


async def _resolve_cover_live(
    discogs_id: str, artist: str | None, title: str | None,
    year: int | None, barcode: str | None,
) -> str | None:
    """Синхронный резолв обложки для release без URL в индексе — показать
    реальную обложку вместо заглушки (первый заход). Порядок по цене:
    CAA-оффлайн (бесплатно, mb_discogs_map) → Deezer → iTunes → Yandex (все
    бесплатные) → Discogs (последним, под лимитером 60/мин + interactive-reserve).
    Yandex перед Discogs добирает русский/советский слой. Найденное пишем в
    индекс → следующий заход отдаёт 302 из БД без повторного резолва.

    Сессию БД сюда НЕ передаём: лестница ходит только во внешние API, и держать
    соединение пула (15 на воркер) до 6с ради неё непозволительно. Оба похода в
    БД — lookup офлайн-маппинга и запись результата — своими короткими сессиями,
    которые закрываются ДО/ПОСЛЕ сетевых вызовов.
    """
    url = None
    try:
        from app.services.cover_fallback import caa_cover_url_by_mbid
        from sqlalchemy import text as _t

        mbid = None
        if str(discogs_id).isdigit():
            # Короткая сессия только на lookup — сетевой HEAD к CAA идёт уже
            # без соединения БД на руках.
            async with async_session_maker() as s:
                mbid = (await s.execute(
                    _t("SELECT mbid::text FROM mb_discogs_map WHERE discogs_id = :did"),
                    {"did": int(discogs_id)},
                )).scalar()
        if mbid:
            url = await caa_cover_url_by_mbid(mbid)
    except Exception:
        pass
    if not url and artist and title:
        try:
            from app.services.deezer import cover_by_meta
            dz = await cover_by_meta(artist, title, year=year)
            if dz:
                url = dz.url
        except Exception:
            pass
    if not url and artist and title:
        try:
            from app.services.cover_fallback import cover_url_by_artist_title
            url = await cover_url_by_artist_title(artist, title)
        except Exception:
            pass
    if not url and artist and title:
        try:
            from app.services.yandex_music import cover_by_meta as yandex_cover_by_meta
            yc = await yandex_cover_by_meta(artist, title, year=year)
            if yc:
                url = yc.url
        except Exception:
            pass
    if not url:
        try:
            from app.services.discogs import DiscogsService
            url = await DiscogsService().get_release_cover(discogs_id)
        except Exception:
            pass

    if url and str(discogs_id).isdigit():
        from sqlalchemy import text as _t
        try:
            async with async_session_maker() as s:
                await s.execute(
                    _t("UPDATE discogs_releases_index SET cover_image_url = :u, "
                       "cover_checked_at = now() WHERE discogs_id = :d "
                       "AND cover_image_url IS NULL"),
                    {"u": url, "d": int(discogs_id)},
                )
                await s.commit()
        except Exception:
            pass
    return url


async def _live_resolve_guarded(db: AsyncSession, discogs_id: str, row) -> str | None:
    """Обёртка живого резолва: negative-cache → семафор → дедуп → лестница.

    Все «нет» здесь мгновенные — клиент получает 404 и ретраит позже
    (MarketCarouselCard уже умеет), обложка доезжает фоном. Ни один запрос
    юзера не висит на лестнице толпой и не держит сессию БД на 6с.
    """
    # Неудача уже известна — не гоняем лестницу повторно весь TTL.
    if await cache.exists(_RESOLVE_NEG_NS, discogs_id):
        await record_cold_outcome(OUTCOME_NEG_CACHE)
        return None

    # Семафор полон — не ждём: мгновенный 404 + fire-and-forget прогрев, чтобы
    # обложка приехала к следующему просмотру. discogs_budget=1: точечный
    # прогрев одного id не должен выедать батчевый бюджет warm'а.
    if _resolve_semaphore.locked():
        from app.services.cover_warm import schedule_warm_dump_covers
        schedule_warm_dump_covers([discogs_id], discogs_budget=1)
        await record_cold_outcome(OUTCOME_BUSY)
        return None

    # Дедуп одновременных резолвов одного id (SET NX, как lock в cover_storage):
    # второй запрос не ждёт первого — тот сам запишет результат в индекс.
    if not await cache.set_nx(_RESOLVE_LOCK_NS, discogs_id, 1, ttl=_RESOLVE_LOCK_TTL):
        await record_cold_outcome(OUTCOME_BUSY)
        return None

    resolved = None
    try:
        # Отпускаем сессию запроса ДО лестницы: commit возвращает соединение в
        # пул, дальше лестница живёт только на внешних API и коротких сессиях
        # внутри _resolve_cover_live.
        await db.commit()
        async with _resolve_semaphore:
            resolved = _safe(await asyncio.wait_for(
                _resolve_cover_live(
                    discogs_id, row["artist"], row["title"],
                    row["year"], row["barcode_norm"],
                ),
                timeout=_RESOLVE_TIMEOUT,
            ))
    except Exception:
        resolved = None
    finally:
        await cache.delete(_RESOLVE_LOCK_NS, discogs_id)

    if resolved:
        await record_cold_outcome(OUTCOME_LIVE_HIT)
        return resolved

    # Помечаем промах: повторные запросы того же id получают мгновенный 404
    # без лестницы, пока TTL не даст источникам шанс обновиться.
    await cache.set(_RESOLVE_NEG_NS, discogs_id, 1, ttl=_RESOLVE_NEG_TTL)
    await record_cold_outcome(OUTCOME_LIVE_MISS)
    return None


@router.get("/store/{record_id}")
async def get_store_cover(
    record_id: str,
    db: AsyncSession = Depends(get_db),
) -> RedirectResponse:
    """
    nginx @covers_fallback для store-native обложек (covers/store/{uuid}.jpg).

    Файл зеркала отсутствует на диске (эвикция / ещё не скачан) — пускаем
    фоновое скачивание из cover_image_url и 302-редиректим на store CDN.
    """
    rid = record_id.removesuffix(".jpg")
    result = await db.execute(
        select(Record.id, Record.cover_image_url, Record.cover_local_path)
        .where(Record.id == rid)
    )
    record = result.first()

    if record is None:
        raise HTTPException(status_code=404, detail="Record not found")

    if not record.cover_local_path and record.cover_image_url:
        schedule_store_native_cover_cache(record.id, record.cover_image_url)

    if not record.cover_image_url:
        raise HTTPException(status_code=404, detail="Cover image not available")

    # 302 на URL из БД, а тот пришёл из парсера чужой витрины. Без проверки
    # наш api-домен работает открытым редиректором — ровно то, чего избегает
    # /go/{click_id} в web/routes.py. Отдаём 404 вместо редиректа: для nginx
    # @covers_fallback это штатный исход (обложки просто не будет).
    if not is_safe_redirect_target(record.cover_image_url):
        logger.warning(
            "covers: небезопасный cover_image_url у записи %s — редирект не отдаём", rid,
        )
        raise HTTPException(status_code=404, detail="Cover image not available")

    return RedirectResponse(url=record.cover_image_url, status_code=302)


@router.get("/{discogs_id}")
async def get_cover(
    discogs_id: str,
    db: AsyncSession = Depends(get_db),
) -> RedirectResponse:
    """
    Вызывается nginx @covers_fallback когда файл не найден на диске.

    Если запись есть в БД — запускаем фоновое скачивание и возвращаем
    302 redirect на оригинальный Discogs URL (signed URL из БД).
    """
    # nginx проксирует полный путь `/covers/{discogs_id}.jpg` — снимаем суффикс.
    discogs_id = discogs_id.removesuffix(".jpg")

    # Точка учёта холодного спроса. Сюда nginx попадает ТОЛЬКО когда мастера нет
    # на диске, значит каждый вызов — холодный просмотр живого пользователя.
    # Именно этого числа не хватало для планирования ёмкости: рост
    # records.cover_cached_at считает и фоновые джобы, и людей вперемешку.
    await record_cold_request(discogs_id)

    # m{master_id} — обложка МАСТЕРА (сетка артиста): discogs_master_covers,
    # иначе лучшая обложка любой версии группы из dump-индекса.
    if discogs_id.startswith("m") and discogs_id[1:].isdigit():
        from sqlalchemy import text as _text

        mid = int(discogs_id[1:])
        url = _safe((await db.execute(
            _text("SELECT cover_image_url FROM discogs_master_covers WHERE master_id = :mid"),
            {"mid": mid},
        )).scalar())
        if not url:
            url = _safe((await db.execute(
                _text(
                    "SELECT cover_image_url FROM discogs_releases_index "
                    "WHERE master_id = :mid AND cover_image_url IS NOT NULL "
                    "ORDER BY year ASC NULLS LAST, discogs_id LIMIT 1"
                ),
                {"mid": mid},
            )).scalar())
        if not url:
            await record_cold_outcome(OUTCOME_NOT_FOUND)
            raise HTTPException(status_code=404, detail="Cover image not available")
        if await _deny_discogs_by_budget(url):
            await record_cold_outcome(OUTCOME_BUDGET)
            raise HTTPException(status_code=404, detail="Cover image not available")
        _spawn_mirror(discogs_id, url)
        await record_cold_outcome(OUTCOME_REDIRECT)
        return RedirectResponse(url=url, status_code=302)

    result = await db.execute(
        select(Record.discogs_id, Record.cover_image_url, Record.cover_local_path)
        .where(Record.discogs_id == discogs_id)
    )
    record = result.first()

    record_url = _safe(record.cover_image_url) if record is not None else None
    if record_url:
        if await _deny_discogs_by_budget(record_url):
            await record_cold_outcome(OUTCOME_BUDGET)
            raise HTTPException(status_code=404, detail="Cover image not available")
        # Запускаем фоновое скачивание если обложки нет локально
        if not record.cover_local_path:
            _spawn_mirror(discogs_id, record_url)
        # 302 redirect — клиент получит обложку немедленно через внешний URL
        await record_cold_outcome(OUTCOME_REDIRECT)
        return RedirectResponse(url=record_url, status_code=302)

    # Записи нет (или без обложки) — dump-индекс: сетка артиста, поиск,
    # версии отдают /covers/{discogs_id}.jpg для любых строк индекса.
    if discogs_id.isdigit():
        from sqlalchemy import text as _text

        row = (await db.execute(
            _text(
                "SELECT cover_image_url, artist, title, year, barcode_norm "
                "FROM discogs_releases_index WHERE discogs_id = :did"
            ),
            {"did": int(discogs_id)},
        )).mappings().first()
        if row:
            url = _safe(row["cover_image_url"])
            if url:
                if await _deny_discogs_by_budget(url):
                    await record_cold_outcome(OUTCOME_BUDGET)
                    raise HTTPException(status_code=404, detail="Cover image not available")
                _spawn_mirror(discogs_id, url)
                await record_cold_outcome(OUTCOME_REDIRECT)
                return RedirectResponse(url=url, status_code=302)

            # Нет URL в индексе → живой резолв (мин заглушек), под гейтами:
            # negative-cache / дедуп / семафор — см. _live_resolve_guarded.
            resolved = await _live_resolve_guarded(db, discogs_id, row)
            if resolved:
                _spawn_mirror(discogs_id, resolved)
                return RedirectResponse(url=resolved, status_code=302)
            raise HTTPException(status_code=404, detail="Cover image not available")

    await record_cold_outcome(OUTCOME_NOT_FOUND)
    raise HTTPException(status_code=404, detail="Cover image not available")


@router.post("/{discogs_id}/refresh", status_code=200)
async def refresh_cover(
    discogs_id: str,
    x_internal_token: str = Header(alias="X-Internal-Token"),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    Принудительно перекачивает обложку из Discogs.
    Требует заголовок X-Internal-Token.
    """
    settings = get_settings()
    if not settings.internal_api_token or x_internal_token != settings.internal_api_token:
        raise HTTPException(status_code=403, detail="Invalid token")

    result = await db.execute(
        select(Record).where(Record.discogs_id == discogs_id)
    )
    record = result.scalar_one_or_none()

    if record is None:
        raise HTTPException(status_code=404, detail="Record not found")

    if not record.cover_image_url:
        raise HTTPException(status_code=422, detail="No source cover URL in DB")

    service = CoverStorageService()

    # Удалить старый файл если есть
    if record.cover_local_path:
        old_path = Path("uploads") / record.cover_local_path
        if old_path.exists():
            old_path.unlink(missing_ok=True)

    # Скачать заново (cover_cached_at обновится внутри)
    rel_path = await service.download_and_store(discogs_id, record.cover_image_url, db)

    return {
        "discogs_id": discogs_id,
        "cover_local_path": rel_path,
        "refreshed": rel_path is not None,
    }
