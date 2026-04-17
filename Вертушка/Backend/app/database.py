"""
Настройка подключения к базе данных
"""
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import declarative_base

from app.config import get_settings

settings = get_settings()

# Создание асинхронного движка SQLAlchemy
engine = create_async_engine(
    settings.database_url,
    echo=settings.debug,  # Логирование SQL запросов в режиме отладки
    future=True,
    pool_pre_ping=True,
    pool_size=5,   # × 4 воркера = 20 базовых соединений
    max_overflow=10,  # × 4 воркера = 60 макс (в рамках max_connections=100)
)

# Фабрика сессий
async_session_maker = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)

# Базовый класс для моделей
Base = declarative_base()


async def get_db() -> AsyncSession:
    """
    Dependency для получения сессии базы данных.
    Используется в FastAPI endpoints.
    """
    async with async_session_maker() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def init_db():
    """Инициализация базы данных (создание таблиц и миграция колонок)"""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

        # Миграция: добавляем новые колонки в существующие таблицы
        # (create_all не добавляет колонки к уже существующим таблицам)
        migrations = [
            "ALTER TABLE gift_bookings ADD COLUMN IF NOT EXISTS expires_at TIMESTAMP",
            "ALTER TABLE gift_bookings ADD COLUMN IF NOT EXISTS reminder_sent_at TIMESTAMP",
        ]
        for sql in migrations:
            await conn.execute(text(sql))


async def close_db():
    """Закрытие подключения к базе данных"""
    await engine.dispose()

