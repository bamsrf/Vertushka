"""
Главный файл приложения Вертушка API
"""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.config import get_settings
from app.database import init_db, close_db

logger = logging.getLogger(__name__)

# API роутеры
from app.api import auth, records, collections, wishlists, users, gifts, profile

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

# CORS настройки - разрешаем все origins для мобильного приложения
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Expo Go и мобильные приложения
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
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
    """Проверка здоровья API"""
    return {"status": "healthy"}

