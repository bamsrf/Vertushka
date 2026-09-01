"""
Главный файл приложения Вертушка API
"""
import asyncio
import logging
import secrets
import sys
import time
import uuid
from contextvars import ContextVar
from contextlib import asynccontextmanager
from pathlib import Path

import sentry_sdk
from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pythonjsonlogger import jsonlogger
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from app.utils.rate_limit import limiter
from sqlalchemy import text

from app.config import assert_secrets_ok, get_settings
from app.database import init_db, close_db, async_session_maker
from app.services import alerts, health_metrics
from app.services.cache import cache
from app.services.rate_limiter import discogs_limiter

# --- Request ID context var ---
_request_id_ctx: ContextVar[str] = ContextVar("request_id", default="-")


class _RequestIdFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = _request_id_ctx.get()  # type: ignore[attr-defined]
        return True


# --- Structured logging (JSON) ---
_log_handler = logging.StreamHandler(sys.stdout)
_log_handler.setFormatter(
    jsonlogger.JsonFormatter(
        fmt="%(asctime)s %(levelname)s %(name)s %(message)s %(request_id)s",
        rename_fields={"asctime": "timestamp", "levelname": "level"},
    )
)
_log_handler.addFilter(_RequestIdFilter())
logging.root.handlers = [_log_handler]
logging.root.setLevel(logging.INFO)

logger = logging.getLogger(__name__)

# --- Гейт конфигурации ---
# ДО Sentry и до создания приложения: если секреты дефолтные, поднимать процесс
# нельзя вообще, а не «поднять и заодно отрапортовать». См. config.py и
# docs/plans/appstore/SECURITY_AUDIT_PRERELEASE.md §S5.
assert_secrets_ok()

# --- Sentry ---
_settings_early = get_settings()
if _settings_early.sentry_dsn:
    sentry_sdk.init(
        dsn=_settings_early.sentry_dsn,
        traces_sample_rate=0.2,
        environment="production" if not _settings_early.debug else "development",
        send_default_pii=False,
    )
    logger.info("Sentry initialised")

# API роутеры
from app.api import auth, records, collections, wishlists, users, gifts, profile, export, covers, user_photos, waitlist, achievements, offers, market, messages, notifications, discogs_oauth, admin, reports, app_config

# Web роутеры (HTML страницы)
from app.web import routes as web_routes

settings = get_settings()


scheduler = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifecycle события приложения"""
    global scheduler

    # Startup
    print("🚀 Запуск Вертушка API...")
    await init_db()
    print("✅ База данных инициализирована")

    await cache.connect()
    print(f"{'✅' if cache.available else '⚠️'} Redis {'подключён' if cache.available else 'недоступен — работаем без кэша'}")

    discogs_limiter.start()
    print("✅ Discogs rate limiter запущен")

    # APScheduler — запускается только в scheduler-контейнере (IS_SCHEDULER=true)
    import os
    if os.environ.get("IS_SCHEDULER", "false").lower() == "true":
        try:
            from apscheduler.schedulers.asyncio import AsyncIOScheduler
        except ImportError:
            logger.warning("APScheduler не установлен, фоновые задачи отключены")
            AsyncIOScheduler = None

        if AsyncIOScheduler is not None:
          try:
            from app.tasks.booking_tasks import send_booking_reminders, auto_release_expired_bookings, auto_cancel_unverified_bookings
            from app.tasks.discogs_tasks import cleanup_search_cache, enrich_records_artist_data, update_prices_batch, enrich_market_covers, refresh_market_store_stats, refresh_new_releases, run_price_backfill_jobs, enrich_collection_records
            from app.tasks.valuation_tasks import record_daily_snapshots
            from app.tasks.achievements_tasks import daily_tick_achievements, cooldown_tick_achievements
            from app.tasks.notification_tasks import (
                emit_wishlist_in_stock_notifications,
                emit_weekly_wishlist_digest,
                emit_wishlist_price_drop_notifications,
                emit_wishlist_absent_notifications,
                cleanup_price_history,
                check_push_receipts,
            )
            from app.tasks.cover_drip_tasks import drip_covers_batch
            from app.tasks.cover_drip_tasks import hourly_backfill_store_covers
            from app.tasks.cover_coverage_tasks import report_cover_coverage
            from app.tasks.cover_upgrade_tasks import upgrade_low_res_covers
            from app.services.cover_storage import CoverStorageService

            async def cleanup_covers():
                async with async_session_maker() as db:
                    service = CoverStorageService()
                    deleted = await service.cleanup_lru(settings.covers_max_cache_mb, db)
                    if deleted:
                        logger.info("LRU cleanup: deleted %d covers", deleted)

            scheduler = AsyncIOScheduler()
            scheduler.add_job(send_booking_reminders, 'cron', hour=10, minute=0, id='booking_reminders')
            scheduler.add_job(auto_release_expired_bookings, 'interval', hours=1, id='booking_auto_release')
            scheduler.add_job(auto_cancel_unverified_bookings, 'interval', minutes=5, id='booking_auto_cancel_unverified')
            scheduler.add_job(cleanup_search_cache, 'interval', hours=1, id='search_cache_cleanup')
            scheduler.add_job(enrich_records_artist_data, 'cron', hour=5, minute=0, id='enrich_artist_data')
            # Полный payload (rarity-флаги, формат) для записей коллекций,
            # добавленных без открытия карточки. До daily_tick ачивок (6:00),
            # чтобы довыдача случилась тем же утром.
            scheduler.add_job(enrich_collection_records, 'cron', hour=4, minute=30, id='enrich_collection_records', max_instances=1, coalesce=True)
            # Каждые 30 минут, а не раз в ночь: пачка в 50 записей в сутки на
            # всю базу означала, что импортированная коллекция заполняется
            # ценами неделями. 200 × 48 прогонов даёт ~9600/сутки при лимите
            # app-токена 86 400/сутки. max_instances=1 — прогон на 200 записей
            # идёт минуты, наложение запрещено.
            scheduler.add_job(update_prices_batch, 'interval', minutes=30, id='update_prices_batch', max_instances=1, coalesce=True)
            # Дозагрузка цен свежеимпортированных коллекций под личным токеном
            # юзера. Раз в минуту: задача живёт в БД и разбирается батчами, так
            # что частый лёгкий прогон и есть механика «долгой» работы.
            scheduler.add_job(run_price_backfill_jobs, 'interval', minutes=1, id='price_backfill_jobs', max_instances=1, coalesce=True)
            scheduler.add_job(record_daily_snapshots, 'cron', hour=5, minute=0, id='value_snapshots')
            scheduler.add_job(cleanup_covers, 'cron', hour=3, minute=0, id='covers_lru_cleanup')
            # Перегрев мелких мастеров — ПОСЛЕ LRU-очистки: та освобождает место,
            # которое апгрейд тут же займёт (мелкий файл ~10 КБ → нормальный ~84 КБ).
            # max_instances=1: прогон может идти до 30 минут, наложение запрещено.
            scheduler.add_job(upgrade_low_res_covers, 'cron', hour=3, minute=40, id='cover_upgrade_sweep', max_instances=1, coalesce=True)
            # Сторож диска. Алертов было много, а за местом не следил никто —
            # при этом кончившийся диск роняет Postgres, то есть всё приложение.
            # Каждые 30 минут: авария развивается часами, чаще незачем.
            from app.tasks.disk_tasks import check_disk_space
            scheduler.add_job(check_disk_space, 'interval', minutes=30,
                              id='disk_space_guard', max_instances=1, coalesce=True)
            # Heartbeat: disk guard и все ночные джобы живут в этом процессе —
            # если он умер или в крэш-лупе, снаружи не видно (autoheal при
            # постоянных рестартах молчит, алёрты слать некому). Ключ с TTL
            # 5 мин; api-процесс показывает возраст в /health/covers.
            async def _scheduler_heartbeat():
                await cache.set("health", "scheduler_heartbeat", int(time.time()), ttl=300)
            scheduler.add_job(_scheduler_heartbeat, 'interval', minutes=1,
                              id='scheduler_heartbeat', max_instances=1, coalesce=True)
            # Метрика покрытия обложек (§4.2): 6:15, после ночного прогрева/enrichment.
            scheduler.add_job(report_cover_coverage, 'cron', hour=6, minute=15, id='cover_coverage_report', max_instances=1, coalesce=True)
            scheduler.add_job(enrich_market_covers, 'interval', hours=2, id='enrich_market_covers')
            scheduler.add_job(refresh_market_store_stats, 'interval', minutes=15, id='refresh_market_store_stats')
            # Понедельник 4:45. max_instances=1: глубокий прогон идёт минуты, наложение запрещено.
            scheduler.add_job(refresh_new_releases, 'cron', day_of_week='mon', hour=4, minute=45, id='refresh_new_releases', max_instances=1, coalesce=True)
            scheduler.add_job(daily_tick_achievements, 'cron', hour=6, minute=0, id='achievements_daily_tick')
            # Пасхалки «ровно N пластинок и сутки тишины» ловятся только тиком:
            # добавление само обнуляет кулдаун. С одним суточным прогоном ждать
            # приходилось до 48 часов вместо заявленных 24 — отсюда ежечасный
            # тик по узкой выборке кандидатов (один запрос, обычно пустой).
            scheduler.add_job(cooldown_tick_achievements, 'interval', hours=1, id='achievements_cooldown_tick', max_instances=1, coalesce=True)
            scheduler.add_job(emit_wishlist_in_stock_notifications, 'interval', minutes=15, id='wishlist_in_stock_notifications')
            scheduler.add_job(emit_wishlist_price_drop_notifications, 'interval', minutes=15, id='wishlist_price_drop_notifications')
            scheduler.add_job(emit_wishlist_absent_notifications, 'interval', minutes=15, id='wishlist_absent_notifications')
            scheduler.add_job(emit_weekly_wishlist_digest, 'cron', day_of_week='mon', hour=10, minute=0, id='weekly_wishlist_digest')
            scheduler.add_job(cleanup_price_history, 'cron', hour=3, minute=30, id='price_history_cleanup')
            # Окончательное удаление аккаунтов, у которых истекло 30-дневное окно
            # отмены. Джоба существовала давно, но нигде не была запущена — то
            # есть данные удалённых аккаунтов не вычищались вообще, вопреки
            # обещанию в UI и в политике (Guideline 5.1.1(v), 152-ФЗ).
            # 04:30 — после ночных обходов, до утренних отчётов.
            from app.scripts.purge_deleted_users import purge as purge_deleted_users
            scheduler.add_job(purge_deleted_users, 'cron', hour=4, minute=30,
                              id='purge_deleted_users', max_instances=1, coalesce=True)
            # Drip-прогрев обложек: каждую минуту, тратит только простой app-bucket'а
            scheduler.add_job(drip_covers_batch, 'interval', minutes=1, id='cover_drip', max_instances=1, coalesce=True)

            # Bulk-backfill обложек (Deezer) — in-process интервальная джоба вместо
            # хрупкого detached `docker exec -d` (не переживал деплой, детект
            # самоматчился → «RUNNING» врал, реально не крутилось сутки). Гейт
            # внутри = маркер /app/uploads/.backfill_enabled. Resumable, ест только
            # свободный Deezer-throttle. max_instances=1 → без перекрытий.
            from app.scripts.backfill_covers_deezer import run_scheduled_batch
            scheduler.add_job(run_scheduled_batch, 'interval', minutes=2,
                              id='cover_backfill_deezer', max_instances=1, coalesce=True)

            # Обложки по ШТРИХКОДУ через Deezer — точный канал вместо угадывания
            # по названию. Замер на проде: 15.3% попаданий против 10.7% у iTunes,
            # но темп 0.13с против 3.1с, то есть в 39 раз больше обложек за сутки
            # обхода. Очередь 2.3 млн уникальных UPC ≈ 3.5 дня. Гейт — маркер
            # /app/uploads/.backfill_upc_enabled.
            from app.scripts.backfill_covers_upc import (
                run_scheduled_batch as run_backfill_upc,
            )
            scheduler.add_job(run_backfill_upc, 'interval', minutes=2,
                              id='cover_backfill_upc', max_instances=1, coalesce=True)

            # Обложки по UPC через Apple Music (MusicKit): добор промахов всех
            # предыдущих каналов, артворк до 1200px. Спит, пока нет ключа
            # (APPLE_MUSIC_*) и маркера /app/uploads/.backfill_apple_enabled.
            from app.scripts.backfill_covers_apple import (
                run_scheduled_batch as run_backfill_apple,
            )
            scheduler.add_job(run_backfill_apple, 'interval', minutes=2,
                              id='cover_backfill_apple', max_instances=1, coalesce=True)

            # Обратный поток обложек из маркета в дамп: магазины фотографируют
            # свой товар, но ссылка дальше витрины не шла. Данные уже в нашей
            # базе — ноль внешних запросов на поиск, только замер картинки.
            # Раз в 6 часов: маркет растёт медленно, очередь мала (8.2 тыс).
            from app.scripts.backfill_covers_from_market import (
                run_scheduled_batch as run_backfill_market,
            )
            scheduler.add_job(run_backfill_market, 'interval', hours=6,
                              id='cover_backfill_market', max_instances=1, coalesce=True)

            # Постсоветский винил: Deezer → Yandex, ПО РЕЛИЗАМ. 45% этой
            # популяции не имеет master_id и потому не попадала ни в одну
            # master-очередь. Гейт — /app/uploads/.backfill_ru_enabled.
            from app.scripts.backfill_covers_ru import (
                run_scheduled_batch as run_backfill_ru,
            )
            scheduler.add_job(run_backfill_ru, 'interval', minutes=2,
                              id='cover_backfill_ru', max_instances=1, coalesce=True)

            # Доп. источники обложек для хвоста, не покрытого Deezer: iTunes
            # (западный латинский остаток) и Yandex (русский/советский + транслит
            # слой, которого нет в Discogs/Deezer). Каждый — своя worklist-таблица
            # (анти-джойн к discogs_master_covers → только ещё не закрытые мастера)
            # + свой gate-маркер /app/uploads/.backfill_{itunes,yandex}_enabled.
            from app.scripts.backfill_covers import run_scheduled_batch as run_backfill_source
            scheduler.add_job(run_backfill_source, 'interval', minutes=3,
                              args=['itunes'], id='cover_backfill_itunes',
                              max_instances=1, coalesce=True)
            scheduler.add_job(run_backfill_source, 'interval', minutes=2,
                              args=['yandex'], id='cover_backfill_yandex',
                              max_instances=1, coalesce=True)

            # Yandex-обогащение существующих записей вне Discogs (source='store'):
            # добор обложки/года/треклиста. Гейт — флаг YANDEX_MATCH_ENABLED.
            from app.tasks.yandex_enrich_tasks import enrich_store_native_yandex
            scheduler.add_job(enrich_store_native_yandex, 'interval', minutes=10,
                              id='yandex_enrich_store_native', max_instances=1, coalesce=True)
            scheduler.add_job(check_push_receipts, 'interval', minutes=20, id='push_receipts_check')

            # ---- Парсеры магазинов винила (под env SCRAPERS_ENABLED) ----
            if os.environ.get("SCRAPERS_ENABLED", "false").lower() == "true":
                from app.tasks.scraper_tasks import (
                    daily_market_sync,
                    incremental_market_sync,
                    weekly_full_crawl_browser,
                    daily_incremental_crawl_browser,
                    stock_refresh_active,
                    hourly_match_unmatched,
                    weekly_cleanup_stale,
                    invalidate_offers_for_recently_updated,
                    daily_rematch_store_native,
                    daily_rematch_format_conflicts,
                    daily_rematch_album_with_barcode,
                    daily_market_health_report,
                    daily_retire_vanished_listings,
                    hourly_enrich_artist_thumbs,
                )
                # Цепочки crawl→match→offers→covers: новинки в маркете сразу после обхода
                scheduler.add_job(daily_market_sync, 'cron', hour=2, minute=0, id='scrape_full_http')
                scheduler.add_job(weekly_full_crawl_browser, 'cron', day_of_week='sat', hour=2, minute=0, id='scrape_full_browser')
                scheduler.add_job(daily_incremental_crawl_browser, 'cron', hour=5, minute=30, id='scrape_incremental_browser')
                scheduler.add_job(incremental_market_sync, 'cron', hour=14, minute=0, id='scrape_incremental')
                scheduler.add_job(stock_refresh_active, 'interval', hours=6, id='scrape_stock_refresh')
                scheduler.add_job(hourly_match_unmatched, 'interval', minutes=60, id='scrape_match_unmatched')
                scheduler.add_job(weekly_cleanup_stale, 'cron', day_of_week='sun', hour=4, minute=0, id='scrape_cleanup_stale')
                # Сразу после ночного обхода: снимаем с витрины то, чего больше нет
                # в каталоге. Обход к 02:30 заканчивается с запасом (23 мин).
                scheduler.add_job(daily_retire_vanished_listings, 'cron', hour=3, minute=0, id='retire_vanished')
                scheduler.add_job(invalidate_offers_for_recently_updated, 'interval', minutes=15, id='scrape_invalidate_offers')
                scheduler.add_job(daily_rematch_store_native, 'cron', hour=3, minute=30, id='scrape_rematch_store_native')
                scheduler.add_job(daily_rematch_format_conflicts, 'cron', hour=3, minute=45, id='scrape_rematch_format_conflicts')
                scheduler.add_job(daily_rematch_album_with_barcode, 'cron', hour=4, minute=15, id='scrape_rematch_album_barcode')
                # 04:00 UTC = 07:00 MSK: обход (02:00) и основные rematch'и (03:30,
                # 03:45) позади, сводка ждёт человека к началу дня. Догоняющий
                # rematch в 04:15 в неё не попадёт — он правит привязки, а не
                # свежесть обхода, ради которой сводку и читают.
                scheduler.add_job(daily_market_health_report, 'cron', hour=4, minute=0, id='market_health_report')
                scheduler.add_job(hourly_backfill_store_covers, 'interval', minutes=60, id='store_cover_backfill', max_instances=1, coalesce=True)
                scheduler.add_job(hourly_enrich_artist_thumbs, 'interval', minutes=60, id='enrich_artist_thumbs')
                logger.info("✅ Scraper jobs зарегистрированы (SCRAPERS_ENABLED=true)")

            scheduler.start()
            print("✅ Планировщик задач запущен")
          except Exception:
            logger.exception("Ошибка запуска планировщика")
    else:
        print("ℹ️ Планировщик задач отключён на этом воркере (IS_SCHEDULER != true)")

    yield

    # Shutdown
    if scheduler:
        scheduler.shutdown()
        print("✅ Планировщик задач остановлен")
    await cache.close()
    print("✅ Redis отключён")
    print("👋 Остановка Вертушка API...")
    await close_db()
    print("✅ Подключение к БД закрыто")


# Создание приложения
app = FastAPI(
    title=settings.app_name,
    description="API для приложения сканирования и управления коллекцией виниловых пластинок",
    version=settings.app_version,
    lifespan=lifespan,
    docs_url="/api/docs" if settings.debug else None,
    redoc_url="/api/redoc" if settings.debug else None,
)

# Rate limiter — один общий инстанс на приложение (app/utils/rate_limit.py).
# Раньше их было два с разными хранилищами, и лимиты не сходились.
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# CORS настройки
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://vinyl-vertushka.ru"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Request timeout middleware
# Discogs enrichment (artist/masters, per_page=20) может занять до 60с на холодном кэше
REQUEST_TIMEOUT_SECONDS = 90

@app.middleware("http")
async def timeout_middleware(request: Request, call_next):
    try:
        return await asyncio.wait_for(call_next(request), timeout=REQUEST_TIMEOUT_SECONDS)
    except asyncio.TimeoutError:
        logger.warning("Request timeout: %s %s", request.method, request.url.path)
        return JSONResponse(status_code=504, content={"detail": "Request timeout"})


# X-Request-ID middleware — трассировка запросов в логах
@app.middleware("http")
async def request_id_middleware(request: Request, call_next):
    request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
    _request_id_ctx.set(request_id)
    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    return response


# Метрики здоровья: доля 5xx, p99, шторм 429.
# Добавлен ПОСЛЕДНИМ намеренно — в Starlette это делает его самым внешним,
# поэтому он видит и 504, который timeout_middleware отдаёт напрямую в обход
# обработчика исключений. Именно эта дыра оставляла волну таймаутов без единого
# аларма. См. services/health_metrics.py
@app.middleware("http")
async def health_metrics_middleware(request: Request, call_next):
    started = time.monotonic()
    try:
        response = await call_next(request)
    except Exception:
        # Исключение долетит до обработчика ниже, который отдаст 500 и свой
        # аларм. Нам важно не потерять его из статистики.
        health_metrics.observe(500, (time.monotonic() - started) * 1000)
        raise

    health_metrics.observe(response.status_code, (time.monotonic() - started) * 1000)
    return response


# Переполнение интерактивной очереди к Discogs (семафор/лимитер в
# services/discogs.py). Это штатная защита пула БД, а не авария: отдаём 503 c
# Retry-After, клиент повторит. Отдельный handler, чтобы такие случаи не
# падали в глобальный 500-обработчик с алармом в Telegram.
from app.services.discogs import DiscogsOverloadedError  # noqa: E402


@app.exception_handler(DiscogsOverloadedError)
async def discogs_overloaded_handler(request: Request, exc: DiscogsOverloadedError):
    return JSONResponse(
        status_code=503,
        content={"detail": "Discogs сейчас перегружен, попробуйте через пару секунд"},
        headers={"Retry-After": "5"},
    )


# Глобальный exception handler — не возвращаем стектрейсы клиенту
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.exception("Unhandled exception on %s %s", request.method, request.url.path)
    # Аларм в Telegram: троттлится по пути, не блокирует ответ клиенту.
    #
    # В тело идут ТОЛЬКО тип исключения и request_id. Раньше уходил `str(exc)`,
    # а текст исключения регулярно содержит пользовательские данные:
    # IntegrityError печатает конфликтующие значения (email, username),
    # ValidationError — сам ввод. Telegram-чат для этого не место, тем более
    # что рядом стоит send_default_pii=False.
    #
    # На диагностике это не сказывается: по request_id полный трейс находится
    # в логах и в Sentry за пару секунд, а раньше его в аларме и не было.
    alerts.fire_and_forget(
        key=f"http_500:{request.url.path}",
        title=f"500 на {request.method} {request.url.path}",
        body=f"{type(exc).__name__} · request_id={_request_id_ctx.get()}",
    )
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error"},
    )

# Статические файлы и шаблоны
#
# uploads/ лежит в .gitignore, а на проде это docker-волюм — в свежем чекауте
# каталога нет. StaticFiles проверяет существование каталога в конструкторе, то
# есть падает прямо на импорте app.main: не поднимается ни приложение, ни сбор
# тестов. Создаём сами; на проде волюм уже примонтирован, exist_ok делает вызов
# пустым. Путь относительный, как и у соседних mount — рабочий каталог Backend/.
Path("uploads").mkdir(exist_ok=True)
app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")
app.mount("/static", StaticFiles(directory="app/web/static"), name="static")
templates = Jinja2Templates(directory="app/web/templates")

# Подключение API роутеров
app.include_router(auth.router, prefix="/api/auth", tags=["Аутентификация"])
app.include_router(discogs_oauth.router, prefix="/api/auth/discogs", tags=["Discogs OAuth"])
app.include_router(records.router, prefix="/api/records", tags=["Пластинки"])
app.include_router(collections.router, prefix="/api/collections", tags=["Коллекции"])
app.include_router(wishlists.router, prefix="/api/wishlists", tags=["Вишлисты"])
app.include_router(users.router, prefix="/api/users", tags=["Пользователи"])
app.include_router(gifts.router, prefix="/api/gifts", tags=["Подарки"])
app.include_router(profile.router, prefix="/api/profile", tags=["Профиль"])
app.include_router(export.router, prefix="/api/export", tags=["Экспорт"])
app.include_router(covers.router, prefix="/covers", tags=["Обложки"])  # НЕ /api/covers — nginx location /covers/
app.include_router(user_photos.router, prefix="/api/collections", tags=["Фото пластинок"])
app.include_router(waitlist.router, prefix="/api/waitlist", tags=["Waitlist"])
app.include_router(achievements.router, prefix="/api/achievements", tags=["Ачивки"])
# Маркет и офферы магазинов — целиком под kill-switch `market`:
# при претензии по ToS магазина раздел гасится за секунды, без деплоя.
_market_gate = [Depends(app_config.require_flag("market"))]
app.include_router(offers.router, prefix="/api", tags=["Магазины"], dependencies=_market_gate)
app.include_router(market.router, prefix="/api", tags=["Маркет"], dependencies=_market_gate)
app.include_router(messages.router, prefix="/api/messages", tags=["Сообщения"])
app.include_router(notifications.router, prefix="/api/notifications", tags=["Уведомления"])

app.include_router(admin.router, prefix="/api/admin", tags=["Модерация"])
app.include_router(reports.router, prefix="/api/reports", tags=["Жалобы"])

# Remote config: публичный конфиг для клиента + staff-флип без деплоя
app.include_router(app_config.router, prefix="/api/config", tags=["Конфиг"])
app.include_router(app_config.admin_router, prefix="/api/admin/config", tags=["Конфиг"])

# Web страницы (публичный профиль, OG-изображения)
app.include_router(web_routes.router, tags=["Web"])


@app.get("/", tags=["Health"])
async def root():
    """Главная страница API"""
    return {
        "app": settings.app_name,
        "version": settings.app_version,
        "status": "running",
        "docs": "/api/docs" if settings.debug else "disabled"
    }


def _require_internal_token(x_internal_token: str | None) -> None:
    """Гейт для служебных ручек. Тот же токен, что у /covers/{id}/refresh."""
    expected = settings.internal_api_token
    if not expected or not x_internal_token or not secrets.compare_digest(
        x_internal_token, expected
    ):
        raise HTTPException(status_code=403, detail="Invalid token")


@app.get("/health", tags=["Health"])
async def health_check():
    """Живость для деплой-гейта и docker healthcheck.

    Наружу отдаём ТОЛЬКО код ответа и `status`. Раньше здесь публично лежало
    состояние БД и Redis — не секрет, но бесплатная разведка для того, кто
    решает, стоит ли ковырять дальше (§S17). Подробности переехали в
    /health/detailed под internal-токен.

    Тело не урезаем до пустого: docker healthcheck и `curl -fsS` в deploy.sh
    смотрят статус-код, но человеку, открывшему URL руками, полезно увидеть
    осмысленный ответ.
    """
    try:
        async with async_session_maker() as session:
            await session.execute(text("SELECT 1"))
    except Exception:
        logger.exception("Health check: DB unreachable")
        return JSONResponse(status_code=503, content={"status": "unhealthy"})

    return {"status": "healthy"}


@app.get("/health/detailed", tags=["Health"])
async def health_check_detailed(
    x_internal_token: str | None = Header(default=None, alias="X-Internal-Token"),
):
    """Состояние зависимостей. Под internal-токеном.

        curl -H "X-Internal-Token: $INTERNAL_API_TOKEN" https://api.../health/detailed
    """
    _require_internal_token(x_internal_token)

    try:
        async with async_session_maker() as session:
            await session.execute(text("SELECT 1"))
        db_status = "connected"
    except Exception:
        logger.exception("Health check: DB unreachable")
        return JSONResponse(
            status_code=503,
            content={"status": "unhealthy", "db": "disconnected"},
        )

    return {
        "status": "healthy",
        "db": db_status,
        "redis": await cache.health(),
    }


@app.get("/health/covers", tags=["Health"])
async def cover_coverage_snapshot(
    x_internal_token: str | None = Header(default=None, alias="X-Internal-Token"),
):
    """Последний снапшот покрытия обложек. Под internal-токеном (§S17).

    Считается задачей cover_coverage_tasks (ежедневно 6:15). Сами цифры не
    сенситивны, но публично отдавать внутреннюю метрику незачем — из браузера
    ручка всё равно открывалась редко, а из терминала это один curl с
    заголовком. status=no_data до первого прогона.
    """
    _require_internal_token(x_internal_token)

    snapshot = await cache.get("metrics", "cover_coverage")
    if snapshot is None:
        snapshot = {"status": "no_data", "hint": "cover_coverage job ещё не отработала"}

    # Живой счётчик, а не из снапшота: снапшот суточный (6:15), а бюджет
    # скачиваний Discogs-картинок интересен именно «сколько уже сегодня».
    # used=None — Redis недоступен, учёт не ведётся.
    from app.services.cover_storage import discogs_img_used_today
    snapshot["discogs_img_today"] = {
        "used": await discogs_img_used_today(),
        "budget": settings.discogs_img_daily_budget,
    }

    # Живость шедулера — только в теле ответа. На статус-код НЕ влияет:
    # /health смотрят docker healthcheck и autoheal, и мёртвый scheduler
    # не повод рестартить api-контейнер.
    hb = await cache.get("health", "scheduler_heartbeat")
    snapshot["scheduler"] = {
        "alive": hb is not None,
        "heartbeat_age_seconds": (int(time.time()) - int(hb)) if hb is not None else None,
    }
    return snapshot

