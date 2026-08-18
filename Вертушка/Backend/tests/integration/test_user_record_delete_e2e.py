"""Мягкое удаление ручного релиза — живая БД, ходим по HTTP.

Юнит-тесты (tests/test_user_record_delete.py) закрывают ветвления на моках.
Здесь проверяем то, что моки соврать не могут: что запись реально пропадает
из «Моих релизов» и из выдачи по прямой ссылке, что чужая коллекция её
удерживает, и что собственные ссылки автора отцепляются без каскадных сюрпризов.
"""
from uuid import uuid4

import pytest
import pytest_asyncio

from app.models.collection import Collection, CollectionItem
from app.models.record import Record
from app.models.user import User
from app.models.wishlist import Wishlist, WishlistItem


@pytest_asyncio.fixture
async def my_record(db, owner):
    """Ручной релиз владельца, лежащий у него же в коллекции."""

    async def _make(title="Тестовый релиз"):
        record = Record(
            source="user",
            moderation_status="approved",
            created_by_user_id=owner.id,
            artist="Тестовый артист",
            title=title,
        )
        db.add(record)
        await db.flush()

        collection = (
            await db.execute(
                Collection.__table__.select().where(Collection.user_id == owner.id)
            )
        ).first()
        db.add(CollectionItem(collection_id=collection.id, record_id=record.id))
        await db.commit()
        await db.refresh(record)
        return record

    return _make


@pytest_asyncio.fixture
async def stranger(db):
    """Посторонний пользователь со своей коллекцией."""
    user = User(
        email=f"stranger-{uuid4().hex[:8]}@example.com",
        username=f"stranger{uuid4().hex[:8]}",
        password_hash="x",
        display_name="Посторонний",
    )
    db.add(user)
    await db.flush()
    db.add(Collection(user_id=user.id, name="Коллекция"))
    db.add(Wishlist(user_id=user.id, is_public=True))
    await db.commit()
    await db.refresh(user)
    return user


@pytest.mark.asyncio
async def test_delete_removes_record_everywhere(client, db, my_record):
    record = await my_record("Мусорный тест")

    listed = (await client.get("/records/user/mine")).json()
    assert [r["title"] for r in listed] == ["Мусорный тест"]

    resp = await client.delete(f"/records/user/{record.id}")
    assert resp.status_code == 204

    assert (await client.get("/records/user/mine")).json() == []
    assert (await client.get(f"/records/{record.id}")).status_code == 404

    # Запись жива в БД (на неё могли ссылаться подарки/клики), но помечена.
    await db.refresh(record)
    assert record.moderation_status == "deleted"

    # Своя ссылка из коллекции отцеплена — иначе карточка вела бы на 404.
    left = (
        await db.execute(
            CollectionItem.__table__.select().where(
                CollectionItem.record_id == record.id
            )
        )
    ).all()
    assert left == []


@pytest.mark.asyncio
async def test_record_in_stranger_collection_survives(client, db, my_record, stranger):
    record = await my_record("Кому-то пригодился")

    collection = (
        await db.execute(
            Collection.__table__.select().where(Collection.user_id == stranger.id)
        )
    ).first()
    db.add(CollectionItem(collection_id=collection.id, record_id=record.id))
    await db.commit()

    resp = await client.delete(f"/records/user/{record.id}")
    assert resp.status_code == 409
    detail = resp.json()["detail"]
    assert detail["code"] == "record_in_use"
    assert detail["holders"] == 1
    assert "1 человек" in detail["message"]

    # Остаётся и в «Моих релизах», и по прямой ссылке.
    assert [r["title"] for r in (await client.get("/records/user/mine")).json()] == [
        "Кому-то пригодился"
    ]
    assert (await client.get(f"/records/{record.id}")).status_code == 200
    await db.refresh(record)
    assert record.moderation_status == "approved"


@pytest.mark.asyncio
async def test_stranger_wishlist_also_holds(client, db, my_record, stranger):
    """Вишлист чужого человека держит запись так же, как коллекция."""
    record = await my_record("В чужом вишлисте")

    wishlist = (
        await db.execute(
            Wishlist.__table__.select().where(Wishlist.user_id == stranger.id)
        )
    ).first()
    db.add(WishlistItem(wishlist_id=wishlist.id, record_id=record.id))
    await db.commit()

    resp = await client.delete(f"/records/user/{record.id}")
    assert resp.status_code == 409
    assert resp.json()["detail"]["holders"] == 1


@pytest.mark.asyncio
async def test_own_wishlist_does_not_block(client, db, my_record, owner):
    """Своя же запись в собственном вишлисте удалению не мешает."""
    record = await my_record("Свой вишлист")

    wishlist = (
        await db.execute(
            Wishlist.__table__.select().where(Wishlist.user_id == owner.id)
        )
    ).first()
    db.add(WishlistItem(wishlist_id=wishlist.id, record_id=record.id))
    await db.commit()

    assert (await client.delete(f"/records/user/{record.id}")).status_code == 204

    left = (
        await db.execute(
            WishlistItem.__table__.select().where(WishlistItem.record_id == record.id)
        )
    ).all()
    assert left == []


@pytest.mark.asyncio
async def test_cannot_delete_foreign_record(client, db, stranger):
    """Чужой ручной релиз удалить нельзя — 403."""
    record = Record(
        source="user",
        moderation_status="approved",
        created_by_user_id=stranger.id,
        artist="Чужой",
        title="Чужой релиз",
    )
    db.add(record)
    await db.commit()

    assert (await client.delete(f"/records/user/{record.id}")).status_code == 403


@pytest.mark.asyncio
async def test_cannot_delete_discogs_record(client, db):
    """Каноничную запись Discogs трогать нельзя даже своим ключом — 403."""
    record = Record(source="discogs", artist="Radiohead", title="Kid A")
    db.add(record)
    await db.commit()

    assert (await client.delete(f"/records/user/{record.id}")).status_code == 403


@pytest.mark.asyncio
async def test_delete_is_idempotent_enough(client, my_record):
    """Повторное удаление идемпотентно: снова 204, без 500 и без дублей чистки."""
    record = await my_record()
    assert (await client.delete(f"/records/user/{record.id}")).status_code == 204
    assert (await client.delete(f"/records/user/{record.id}")).status_code == 204
