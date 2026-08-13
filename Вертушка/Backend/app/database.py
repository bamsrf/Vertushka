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
    """Инициализация базы данных (создание таблиц и миграция колонок)"""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

        # Миграция: добавляем новые колонки в существующие таблицы
        # (create_all не добавляет колонки к уже существующим таблицам)
        migrations = [
            "ALTER TABLE gift_bookings ADD COLUMN IF NOT EXISTS expires_at TIMESTAMP",
            "ALTER TABLE gift_bookings ADD COLUMN IF NOT EXISTS reminder_sent_at TIMESTAMP",
            "ALTER TABLE gift_bookings ADD COLUMN IF NOT EXISTS match_dismissed_at TIMESTAMP",
            "ALTER TABLE gift_bookings ADD COLUMN IF NOT EXISTS record_id UUID REFERENCES records(id) ON DELETE SET NULL",
            "CREATE INDEX IF NOT EXISTS ix_gift_bookings_record_id ON gift_bookings (record_id)",
            # Бэкфилл для живых броней: у них связь с пунктом вишлиста ещё цела.
            # У завершённых её нет — там колонка останется пустой, и такие
            # подарки в «Я дарю» не покажутся (данных для них просто не сохранилось).
            """
            UPDATE gift_bookings b
               SET record_id = wi.record_id
              FROM wishlist_items wi
             WHERE b.wishlist_item_id = wi.id
               AND b.record_id IS NULL
            """,
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS notify_follow_request BOOLEAN NOT NULL DEFAULT TRUE",
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS notify_wishlist_in_stock BOOLEAN NOT NULL DEFAULT TRUE",
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS notify_achievement BOOLEAN NOT NULL DEFAULT TRUE",
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS notify_gift_confirmed BOOLEAN NOT NULL DEFAULT TRUE",
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS notify_milestone BOOLEAN NOT NULL DEFAULT TRUE",
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS quiet_hours_enabled BOOLEAN NOT NULL DEFAULT FALSE",
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS quiet_hours_start TIME",
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS quiet_hours_end TIME",
        ]
        for sql in migrations:
            await conn.execute(text(sql))


async def close_db():
    """Закрытие подключения к базе данных"""
    await engine.dispose()

