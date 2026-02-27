"""
Главный файл приложения Вертушка API
"""
import logging
import sys
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
from slowapi.util import get_remote_address
from sqlalchemy import text

from app.config import get_settings
from app.database import init_db, close_db, async_session_maker

# --- Structured logging (JSON) ---
_log_handler = logging.StreamHandler(sys.stdout)
_log_handler.setFormatter(
    jsonlogger.JsonFormatter(
        fmt="%(asctime)s %(levelname)s %(name)s %(message)s",
        rename_fields={"asctime": "timestamp", "levelname": "level"},
    )
)
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
from app.api import auth, records, collections, wishlists, users, gifts, profile, export

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

    # APScheduler
    try:
        from apscheduler.schedulers.asyncio import AsyncIOScheduler
        from app.tasks.booking_tasks import send_booking_reminders, auto_extend_expired_bookings

        scheduler = AsyncIOScheduler()
        scheduler.add_job(send_booking_reminders, 'cron', hour=10, minute=0, id='booking_reminders')
        scheduler.add_job(auto_extend_expired_bookings, 'interval', hours=1, id='booking_auto_extend')
        scheduler.start()
        print("✅ Планировщик задач запущен")
    except ImportError:
        logger.warning("APScheduler не установлен, фоновые задачи отключены")
    except Exception as e:
        logger.error(f"Ошибка запуска планировщика: {e}")

    yield

    # Shutdown
    if scheduler:
        scheduler.shutdown()
        print("✅ Планировщик задач остановлен")
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
limiter = Limiter(key_func=get_remote_address)
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


# Глобальный exception handler — не возвращаем стектрейсы клиенту
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.exception("Unhandled exception on %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error"},
    )

# Статические файлы и шаблоны
app.mount("/static", StaticFiles(directory="app/web/static"), name="static")
templates = Jinja2Templates(directory="app/web/templates")

# Подключение API роутеров
app.include_router(auth.router, prefix="/api/auth", tags=["Аутентификация"])
app.include_router(records.router, prefix="/api/records", tags=["Пластинки"])
app.include_router(collections.router, prefix="/api/collections", tags=["Коллекции"])
app.include_router(wishlists.router, prefix="/api/wishlists", tags=["Вишлисты"])
app.include_router(users.router, prefix="/api/users", tags=["Пользователи"])
app.include_router(gifts.router, prefix="/api/gifts", tags=["Подарки"])
app.include_router(profile.router, prefix="/api/profile", tags=["Профиль"])
app.include_router(export.router, prefix="/api/export", tags=["Экспорт"])

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
    """Проверка здоровья API с проверкой БД"""
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
    return {"status": "healthy", "db": db_status}

