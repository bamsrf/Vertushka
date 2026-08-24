"""emit_wishlist_in_stock_notifications: порядок коммита, savepoint'ы, array-бинды.

Прод-инцидент (ревью 23.08.2026): задача падала дважды в сутки после обхода
краулера. Три завязанные друг на друга поломки:

1. Запрос alt-версий разворачивал in_/not_in по спискам почти всего маркета
   в 48 961 bind-параметр при лимите asyncpg 32 767 → InterfaceError.
2. `db.commit()` стоял ПОСЛЕ `_emit_alt_versions`: падение alt-шага откатывало
   upsert'ы основного цикла, при этом push уже ушёл ДО коммита — уведомление,
   на которое ссылается push, не существовало.
3. Per-item try/except без savepoint: первая же не-IntegrityError ошибка БД
   оставляла сессию в failed-состоянии, и умирал весь прогон.

Тесты ниже ходят в живой Postgres (make test-db-up) и фиксируют каждый пункт.
"""
import uuid
from decimal import Decimal

import pytest
from sqlalchemy import select, text

from app.models.notification import Notification
from app.models.store import Store
from app.models.store_listing import ListingStatus, StoreListing
from app.models.wishlist import WishlistItem
from app.tasks import notification_tasks

pytestmark = pytest.mark.asyncio


@pytest.fixture
def make_store(db):
    """Магазин-партнёр для листингов."""

    async def _make(slug: str | None = None) -> Store:
        slug = slug or f"shop{uuid.uuid4().hex[:8]}"
        store = Store(
            slug=slug,
            name=f"Магазин {slug}",
            domain=f"{slug}.example.com",
            base_url=f"https://{slug}.example.com",
            parser_class="TestParser",
        )
        db.add(store)
        await db.commit()
        await db.refresh(store)
        return store

    return _make


@pytest.fixture
def make_listing(db):
    """In-stock листинг, привязанный к записи; updated_at попадает в окно recent."""

    async def _make(store: Store, record, *, price: str = "3500") -> StoreListing:
        listing = StoreListing(
            store_id=store.id,
            external_id=f"ext-{uuid.uuid4().hex[:8]}",
            url=f"{store.base_url}/item/{uuid.uuid4().hex[:8]}",
            title_raw=record.title,
            status=ListingStatus.IN_STOCK,
            matched_record_id=record.id,
            price_rub=Decimal(price),
        )
        db.add(listing)
        await db.commit()
        await db.refresh(listing)
        return listing

    return _make


async def _notifications(db, user_id, ntype: str) -> list[Notification]:
    return (
        (
            await db.execute(
                select(Notification).where(
                    Notification.user_id == user_id,
                    Notification.type == ntype,
                )
            )
        )
        .scalars()
        .all()
    )


async def test_alt_step_failure_does_not_rollback_main_notifications(
    db, owner, make_record, wishlist_item, make_store, make_listing, monkeypatch
):
    """P0: основной цикл коммитится ДО alt-шага.

    Push уходит внутри upsert_notification ещё до коммита; если падение
    alt-шага откатывает основной цикл (как было), push ссылается на
    несуществующее уведомление, а прогон теряется целиком.
    """
    record = await make_record(artist="Miles Davis", title="Kind of Blue")
    await wishlist_item(record)
    store = await make_store()
    await make_listing(store, record)

    async def boom(*_args, **_kwargs):
        raise RuntimeError("alt-шаг упал (например, на лимите биндов)")

    monkeypatch.setattr(notification_tasks, "_emit_alt_versions", boom)

    await notification_tasks.emit_wishlist_in_stock_notifications()

    rows = await _notifications(db, owner.id, "wishlist_in_stock")
    assert len(rows) == 1, (
        "падение alt-шага не должно откатывать уведомления основного цикла"
    )
    assert rows[0].data["record_id"] == str(record.id)


async def test_db_error_on_one_item_does_not_kill_the_run(
    db, owner, make_record, wishlist_item, make_store, make_listing, monkeypatch
):
    """P1: не-IntegrityError ошибка БД по одному айтему гасится savepoint'ом.

    Без savepoint сессия остаётся в failed-состоянии (InFailedSQLTransaction),
    остальные айтемы и финальный commit умирают — уведомлений ноль.
    """
    bad = await make_record(title="Битый айтем", artist="A")
    good = await make_record(title="Здоровый айтем", artist="B")
    await wishlist_item(bad)
    await wishlist_item(good)
    store = await make_store()
    await make_listing(store, bad)
    await make_listing(store, good)

    real_upsert = notification_tasks.upsert_notification

    async def flaky_upsert(db_, **kwargs):
        if kwargs.get("data", {}).get("record_title") == "Битый айтем":
            # Настоящая ошибка БД: без savepoint она абортит транзакцию.
            await db_.execute(text("SELECT no_such_column FROM records"))
        return await real_upsert(db_, **kwargs)

    monkeypatch.setattr(notification_tasks, "upsert_notification", flaky_upsert)

    await notification_tasks.emit_wishlist_in_stock_notifications()

    rows = await _notifications(db, owner.id, "wishlist_in_stock")
    titles = {r.data["record_title"] for r in rows}
    assert titles == {"Здоровый айтем"}, (
        "ошибка по одному айтему не должна убивать уведомления остальных"
    )


async def test_alt_pressing_emitted_through_array_binds(
    db, owner, make_record, wishlist_item, make_store, make_listing
):
    """Alt-запрос (= ANY / != ALL на живом asyncpg) находит другой прессинг.

    Владелец желает оба прессинга: точное совпадение по alt держит основной
    цикл живым (без единого exact-матча _run выходит до alt-шага), а по
    wanted, которого нет в наличии, должен прийти именно alt-алерт.
    """
    wanted = await make_record(title="OK Computer", artist="Radiohead", master="791202")
    alt = await make_record(
        title="OK Computer (2016 reissue)", artist="Radiohead", master="791202"
    )
    await wishlist_item(wanted)
    await wishlist_item(alt)
    store = await make_store()
    await make_listing(store, alt, price="4200")

    await notification_tasks.emit_wishlist_in_stock_notifications()

    exact = await _notifications(db, owner.id, "wishlist_in_stock")
    assert [r.data["record_id"] for r in exact] == [str(alt.id)]

    rows = await _notifications(db, owner.id, "wishlist_in_stock_alt")
    assert len(rows) == 1
    assert rows[0].data["record_id"] == str(wanted.id)
    assert rows[0].data["alt_record_id"] == str(alt.id)


async def test_id_filter_survives_asyncpg_bind_limit(db):
    """Регресс инцидента: >32 767 id в фильтре — один array-бинд, запрос живёт.

    Старый `WishlistItem.record_id.in_(ids)` на этом объёме валил asyncpg
    задолго до исполнения запроса.
    """
    # Импорт локальный: на старом коде хелпера нет, и модульный импорт валил бы
    # сбор всего файла — маскируя настоящие падения соседних тестов.
    from app.tasks.notification_tasks import _id_filter

    ids = [uuid.uuid4() for _ in range(33_000)]

    result = await db.execute(
        select(WishlistItem.id).where(
            _id_filter(WishlistItem.record_id, ids, dialect="postgresql")
        )
    )
    assert result.scalars().all() == []

    negated = await db.execute(
        select(WishlistItem.id).where(
            _id_filter(WishlistItem.record_id, ids, dialect="postgresql", negate=True)
        )
    )
    assert negated.scalars().all() == []
