"""Интеграционные тесты: живой Postgres + приложение целиком.

Остальной сюит намеренно без базы — он быстрый и бьёт по чистым функциям.
Здесь наоборот: поднимаем настоящую схему, ходим по HTTP через ASGI и проверяем
эндпоинты вместе с транзакциями, каскадами и уникальными индексами. Именно на
этом уровне живут баги вроде «пункт вишлиста удалили мимо брони» — юнит-тест
такого не видит, потому что удаление происходит в эндпоинте.

Запуск:
    make test-db-up && make test-integration

Без поднятой тестовой базы модуль целиком пропускается, чтобы обычный
`pytest tests` оставался зелёным и быстрым на любой машине.
"""
import os
from uuid import uuid4

import pytest
import pytest_asyncio

# База выбирается до импорта app.*: иначе engine и async_session_maker
# соберутся на dummy-URL из корневого conftest, и фоновые сервисы (ачивки,
# уведомления) пойдут мимо тестовой базы — они ходят через async_session_maker,
# а не через переопределённую зависимость get_db.
TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql+asyncpg://postgres:postgres@127.0.0.1:55432/vertushka_test",
)
os.environ["DATABASE_URL"] = TEST_DATABASE_URL

from httpx import ASGITransport, AsyncClient  # noqa: E402

from app.database import Base, engine, async_session_maker  # noqa: E402
from app.api.auth import get_current_user  # noqa: E402
from app.main import app  # noqa: E402
from app.models.collection import Collection  # noqa: E402
from app.models.record import Record  # noqa: E402
from app.models.user import User  # noqa: E402
from app.models.wishlist import Wishlist, WishlistItem  # noqa: E402


@pytest_asyncio.fixture(scope="session", autouse=True)
async def _schema():
    """Создаёт схему один раз на прогон; пропускает всё, если базы нет.

    DDL гоняем на отдельном движке, который тут же закрываем: сессионная
    фикстура и тесты у pytest-asyncio живут в разных циклах событий, и
    соединение из общего пула, открытое здесь, в тестах было бы «чужим».

    Схему сносим целиком, а не Base.metadata.drop_all: между conversations и
    messages круговой внешний ключ (pinned_message_id ↔ conversation_id), и
    отсортировать таблицы для DROP невозможно. DROP SCHEMA CASCADE этого не знает.
    """
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import create_async_engine

    # Движок собирается при первом импорте app.database, а этот conftest
    # выставляет DATABASE_URL до него — но только если импорт не случился
    # раньше (другой тест, плагин, порядок сборки). Молча уехать в чужую базу
    # хуже, чем упасть: так тесты «зеленели» бы, ничего не проверяя.
    if engine.url.render_as_string(hide_password=False) != TEST_DATABASE_URL:
        raise RuntimeError(
            "app.database.engine собран на другой URL "
            f"({engine.url.render_as_string()}), а не на {TEST_DATABASE_URL}. "
            "Значит app.* импортировали до этого conftest — интеграционные "
            "тесты ходили бы не в ту базу."
        )

    ddl_engine = create_async_engine(TEST_DATABASE_URL)
    try:
        async with ddl_engine.begin() as conn:
            # asyncpg не принимает две команды в одном statement — отсюда две строки
            await conn.execute(text("DROP SCHEMA public CASCADE"))
            await conn.execute(text("CREATE SCHEMA public"))
            await conn.run_sync(Base.metadata.create_all)
    except Exception as exc:  # noqa: BLE001 — причина не важна, важен внятный вердикт
        await ddl_engine.dispose()
        message = (
            f"нет тестовой БД ({TEST_DATABASE_URL}): {type(exc).__name__}. "
            "Подними её: make test-db-up"
        )
        # В CI пропуск недопустим: отвалившийся Postgres не должен выглядеть
        # как зелёный прогон. Локально — просто skip, чтобы `pytest tests`
        # работал без докера.
        if os.environ.get("REQUIRE_TEST_DB") == "1":
            raise RuntimeError(message) from exc
        pytest.skip(message, allow_module_level=True)
    await ddl_engine.dispose()
    yield


@pytest_asyncio.fixture(autouse=True)
async def _clean_tables():
    """Чистит данные после каждого теста и закрывает соединения общего движка.

    dispose() обязателен: у каждого теста свой цикл событий, а живое соединение
    из пула, открытое в предыдущем, ломается с «attached to a different loop».
    Список таблиц берём из базы — metadata.sorted_tables на цикле FK падает.
    """
    yield
    from sqlalchemy import text

    async with engine.begin() as conn:
        rows = await conn.execute(
            text("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")
        )
        names = [f'public."{r[0]}"' for r in rows]
        if names:
            await conn.execute(
                text(f"TRUNCATE {', '.join(names)} RESTART IDENTITY CASCADE")
            )
    await engine.dispose()


@pytest.fixture(autouse=True)
def _no_outbound_calls(monkeypatch):
    """
    Глушим почту и пуши: тесты про данные, а не про SMTP.

    В коде они и так под try/except, но живая попытка достучаться наружу делает
    прогон медленным и флаки-зависимым от сети.
    """
    import app.services.notifications as notifications
    import app.services.push as push

    async def _noop(*_args, **_kwargs):
        return None

    for name in dir(notifications):
        if name.startswith("send_"):
            monkeypatch.setattr(notifications, name, _noop, raising=False)
    monkeypatch.setattr(push, "send_push_to_user", _noop, raising=False)


@pytest_asyncio.fixture
async def db():
    async with async_session_maker() as session:
        yield session


@pytest_asyncio.fixture
async def owner(db) -> User:
    """Получатель подарка: пользователь с вишлистом и коллекцией."""
    user = User(
        email=f"owner-{uuid4().hex[:8]}@example.com",
        username=f"owner{uuid4().hex[:8]}",
        password_hash="x",
        display_name="Владелец",
    )
    db.add(user)
    await db.flush()

    db.add(Collection(user_id=user.id, name="Моя коллекция"))
    db.add(Wishlist(user_id=user.id, is_public=True))
    await db.commit()
    await db.refresh(user)
    return user


@pytest_asyncio.fixture
async def client(owner):
    """HTTP-клиент, авторизованный как owner."""
    app.dependency_overrides[get_current_user] = lambda: owner
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test/api") as ac:
        yield ac
    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def make_record(db):
    """Фабрика пластинок. estimated_price_min не ставим — иначе эндпоинт полезет за курсом ЦБ."""

    async def _make(*, artist="King Gizzard", title="Omnium Gatherum", master=None, year=None):
        record = Record(
            source="user",
            title=title,
            artist=artist,
            discogs_master_id=master,
            year=year,
        )
        db.add(record)
        await db.commit()
        await db.refresh(record)
        return record

    return _make


@pytest_asyncio.fixture
async def wishlist_item(db, owner):
    """Кладёт пластинку в вишлист владельца."""

    async def _add(record) -> WishlistItem:
        wishlist = (
            await db.execute(
                Wishlist.__table__.select().where(Wishlist.user_id == owner.id)
            )
        ).first()
        item = WishlistItem(wishlist_id=wishlist.id, record_id=record.id)
        db.add(item)
        await db.commit()
        await db.refresh(item)
        return item

    return _add


@pytest_asyncio.fixture
async def collection_id(db, owner) -> str:
    result = await db.execute(
        Collection.__table__.select().where(Collection.user_id == owner.id)
    )
    return str(result.first().id)
