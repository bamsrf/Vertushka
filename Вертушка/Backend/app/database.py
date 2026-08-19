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
    # Прод = ОДИН uvicorn-воркер (CLIP живёт в том же процессе) + отдельный
    # scheduler-контейнер на тех же настройках: 2 × (10+20) = 60 макс — в
    # рамках max_connections=100. Старый комментарий «× 4 воркера» врал:
    # воркер один, и 5+10 на процесс упирались в потолок при наплыве.
    pool_size=10,
    max_overflow=20,
    # statement_timeout: ни один запрос не висит вечно, воркер не залипает
    # (инцидент 07-10: лок-вейт морозил корутины на часы → тотальный аут).
    # 30с с запасом покрывает любой user-запрос (замеры <1с). Только для
    # app-коннектов — alembic поднимает свой engine (alembic/env.py:81), так
    # что миграции НЕ задеты. Тяжёлые фоновые агрегации (backfill worklist)
    # локально поднимают лимит через `SET statement_timeout` в своей сессии.
    connect_args={"server_settings": {"statement_timeout": "30000"}},
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
    """Проверка доступности БД на старте.

    Схемой управляет ТОЛЬКО alembic (деплой гоняет `alembic upgrade head`
    до подъёма контейнера). Раньше здесь на каждом старте шли create_all,
    пачка ALTER TABLE и UPDATE-бэкфилл gift_bookings — всё под
    statement_timeout=30s: бэкфилл по выросшей таблице однажды упёрся бы в
    таймаут и уронил старт. Эти DDL/UPDATE переехали в миграцию
    20260819_legacy_startup_ddl (alembic/versions/), а create_all не нужен и
    тестам — интеграционный conftest создаёт схему сам.

    SELECT 1 оставлен сознательно: старт с недоступной БД должен падать
    сразу и громко, как падал бы на create_all, а не на первом запросе.
    """
    async with engine.begin() as conn:
        await conn.execute(text("SELECT 1"))


async def close_db():
    """Закрытие подключения к базе данных"""
    await engine.dispose()

