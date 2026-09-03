"""
Конфигурация Alembic для асинхронных миграций
"""
import asyncio
import os
from logging.config import fileConfig

from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from alembic import context

# Импортируем модели и настройки
from app.config import get_settings
from app.database import Base
from app.models import *  # noqa: F401, F403

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
# This line sets up loggers basically.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# add your model's MetaData object here
# for 'autogenerate' support
target_metadata = Base.metadata

# other values from the config, defined by the needs of env.py,
# can be acquired:
# my_important_option = config.get_main_option("my_important_option")
# ... etc.

settings = get_settings()


def get_url():
    return settings.database_url


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well.  By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.

    """
    url = get_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


#: Сколько миграция ждёт блокировку, прежде чем сдаться. Переопределяется
#: переменной окружения ALEMBIC_LOCK_TIMEOUT (например "30s" для окна работ).
LOCK_TIMEOUT = os.getenv("ALEMBIC_LOCK_TIMEOUT", "5s")


def do_run_migrations(connection: Connection) -> None:
    # ПРЕДОХРАНИТЕЛЬ. Деплой применяет миграции, пока старый контейнер держит
    # боевой трафик (см. scripts/deploy.sh: alembic upgrade head идёт ДО
    # поднятия нового цвета). Без lock_timeout ALTER, не получивший блокировку
    # сразу, встаёт в очередь — и, что хуже, ВСЕ последующие запросы к той же
    # таблице выстраиваются за ним. На discogs_releases_index (13M строк, 6 ГБ,
    # горячий путь поиска) это означает лежащий поиск у всех живых юзеров.
    #
    # С таймаутом сценарий другой: миграция падает, deploy.sh обрывается с
    # ненулевым кодом, трафик остаётся на старом цвете. Упавший деплой чинится
    # спокойно, лежащий прод — нет.
    connection.exec_driver_sql(f"SET lock_timeout = '{LOCK_TIMEOUT}'")
    # Зависшая транзакция миграции не должна держать блокировки вечно.
    connection.exec_driver_sql("SET idle_in_transaction_session_timeout = '60s'")

    context.configure(connection=connection, target_metadata=target_metadata)

    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """In this scenario we need to create an Engine
    and associate a connection with the context.

    """
    configuration = config.get_section(config.config_ini_section, {})
    configuration["sqlalchemy.url"] = get_url()
    connectable = async_engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()

