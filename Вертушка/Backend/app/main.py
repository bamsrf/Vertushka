"""
Главный файл приложения Вертушка API
"""
import asyncio
import logging
import sys
import uuid
from contextvars import ContextVar
from contextlib import asynccontextmanager

import sentry_sdk
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pythonjsonlogger import jsonlogger
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from app.utils.request_ip import get_client_ip
from sqlalchemy import text

from app.config import get_settings
from app.database import init_db, close_db, async_session_maker
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
from app.api import auth, records, collections, wishlists, users, gifts, profile, export, covers, user_photos, waitlist, achievements, offers, market, messages, notifications, discogs_oauth, admin

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
            from app.tasks.discogs_tasks import cleanup_search_cache, enrich_records_artist_data, update_prices_batch, enrich_market_covers, refresh_market_store_stats, refresh_new_releases
            from app.tasks.valuation_tasks import record_daily_snapshots
            from app.tasks.achievements_tasks import daily_tick_achievements
            from app.tasks.notification_tasks import emit_wishlist_in_stock_notifications, emit_weekly_wishlist_digest
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
            scheduler.add_job(update_prices_batch, 'cron', hour=4, minute=0, id='update_prices_batch')
            scheduler.add_job(record_daily_snapshots, 'cron', hour=5, minute=0, id='value_snapshots')
            scheduler.add_job(cleanup_covers, 'cron', hour=3, minute=0, id='covers_lru_cleanup')
            scheduler.add_job(enrich_market_covers, 'interval', hours=2, id='enrich_market_covers')
            scheduler.add_job(refresh_market_store_stats, 'interval', minutes=15, id='refresh_market_store_stats')
            scheduler.add_job(refresh_new_releases, 'cron', day=1, hour=4, minute=45, id='refresh_new_releases')
            scheduler.add_job(daily_tick_achievements, 'cron', hour=6, minute=0, id='achievements_daily_tick')
            scheduler.add_job(emit_wishlist_in_stock_notifications, 'interval', minutes=15, id='wishlist_in_stock_notifications')
            scheduler.add_job(emit_weekly_wishlist_digest, 'cron', day_of_week='mon', hour=10, minute=0, id='weekly_wishlist_digest')

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
                scheduler.add_job(invalidate_offers_for_recently_updated, 'interval', minutes=15, id='scrape_invalidate_offers')
                scheduler.add_job(daily_rematch_store_native, 'cron', hour=3, minute=30, id='scrape_rematch_store_native')
                scheduler.add_job(daily_rematch_format_conflicts, 'cron', hour=3, minute=45, id='scrape_rematch_format_conflicts')
                scheduler.add_job(daily_rematch_album_with_barcode, 'cron', hour=4, minute=15, id='scrape_rematch_album_barcode')
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

# Rate limiter
limiter = Limiter(key_func=get_client_ip)
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


# Глобальный exception handler — не возвращаем стектрейсы клиенту
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.exception("Unhandled exception on %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error"},
    )

# Статические файлы и шаблоны
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
app.include_router(offers.router, prefix="/api", tags=["Магазины"])
app.include_router(market.router, prefix="/api", tags=["Маркет"])
app.include_router(messages.router, prefix="/api/messages", tags=["Сообщения"])
app.include_router(notifications.router, prefix="/api/notifications", tags=["Уведомления"])

app.include_router(admin.router, prefix="/api/admin", tags=["Модерация"])

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


@app.get("/health", tags=["Health"])
async def health_check():
    """Проверка здоровья API с проверкой БД и Redis"""
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

    redis_health = await cache.health()

    return {
        "status": "healthy",
        "db": db_status,
        "redis": redis_health,
    }

