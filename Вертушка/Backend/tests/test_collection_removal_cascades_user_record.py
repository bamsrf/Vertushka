"""Удаление ручного релиза свайпом из коллекции должно каскадить туда же, куда
и явное удаление через экран деталей (`DELETE /records/user/{id}`).

До фикса `remove_record_from_collection`/`remove_item_from_collection` рвали
только связь `CollectionItem`, а сама `Record` оставалась `approved` — релиз
пропадал из коллекции, но вечно висел в «Моих релизах» и продолжал
засчитываться в вклад (K8–K10), даже будучи фактически удалённым.
"""
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy.sql.dml import Delete

import app.services.achievements as ach_pkg
import app.services.achievements.evaluator as ach_eval
from app.api.collections import remove_item_from_collection, remove_record_from_collection
from app.services.achievements.events import COLLECTION_ITEM_REMOVED, USER_RECORD_DELETED
from app.services.user_record import DELETED_STATUS


class FakeResult:
    def __init__(self, obj):
        self._obj = obj

    def scalar_one_or_none(self):
        return self._obj

    def scalars(self):
        return self

    def first(self):
        return self._obj


class FakeSession:
    """Различает select(Collection)/select(CollectionItem)/select(Record) по
    выбранной сущности и отдельно считает Core-DELETE стейтменты по таблице —
    так же, как их пишет `soft_delete_user_record`."""

    def __init__(self, *, collection, item, record, foreign_holders=(0, 0)):
        self._collection = collection
        self._item = item
        self._record = record
        self._scalars = list(foreign_holders)
        self.deleted_items = []
        self.delete_tables = []
        self.commits = 0
        self.flushed = False

    async def execute(self, query, *_a, **_kw):
        if isinstance(query, Delete):
            self.delete_tables.append(query.table.name)
            return None
        entity = query.column_descriptions[0]["entity"]
        from app.models.collection import Collection, CollectionItem
        from app.models.record import Record

        if entity is Collection:
            return FakeResult(self._collection)
        if entity is CollectionItem:
            return FakeResult(self._item)
        if entity is Record:
            return FakeResult(self._record)
        raise AssertionError(f"unexpected query entity: {entity}")

    async def scalar(self, *_a, **_kw):
        return self._scalars.pop(0) if self._scalars else 0

    async def delete(self, obj):
        self.deleted_items.append(obj)

    async def flush(self):
        self.flushed = True

    async def commit(self):
        self.commits += 1


def make_record(owner_id, *, source="user", statusv="approved"):
    return SimpleNamespace(
        id=uuid4(), source=source, created_by_user_id=owner_id, moderation_status=statusv
    )


def make_user(uid):
    return SimpleNamespace(id=uid, is_staff=False)


def _patch_emit(monkeypatch):
    seen = []

    async def fake_emit(_db, user_id, event, payload=None):
        seen.append((user_id, event, payload))
        return []

    monkeypatch.setattr(ach_pkg, "emit_event", fake_emit)
    monkeypatch.setattr(ach_eval, "emit_event", fake_emit)
    return seen


@pytest.mark.asyncio
async def test_remove_item_cascades_when_last_holder(monkeypatch):
    seen = _patch_emit(monkeypatch)
    owner = uuid4()
    collection_id, item_id = uuid4(), uuid4()
    record = make_record(owner)
    collection = SimpleNamespace(id=collection_id, user_id=owner)
    item = SimpleNamespace(id=item_id, collection_id=collection_id, record_id=record.id)
    db = FakeSession(collection=collection, item=item, record=record, foreign_holders=(0, 0))

    await remove_item_from_collection(
        collection_id, item_id, current_user=make_user(owner), db=db
    )

    assert record.moderation_status == DELETED_STATUS
    assert item in db.deleted_items
    assert db.delete_tables == ["collection_items", "wishlist_items"]
    assert (owner, USER_RECORD_DELETED, {"record_id": record.id}) in seen
    assert (owner, COLLECTION_ITEM_REMOVED, {"record_id": str(record.id)}) in seen


@pytest.mark.asyncio
async def test_remove_item_survives_when_held_by_others(monkeypatch):
    seen = _patch_emit(monkeypatch)
    owner = uuid4()
    collection_id, item_id = uuid4(), uuid4()
    record = make_record(owner)
    collection = SimpleNamespace(id=collection_id, user_id=owner)
    item = SimpleNamespace(id=item_id, collection_id=collection_id, record_id=record.id)
    db = FakeSession(collection=collection, item=item, record=record, foreign_holders=(1, 0))

    await remove_item_from_collection(
        collection_id, item_id, current_user=make_user(owner), db=db
    )

    assert record.moderation_status == "approved", "запись жива у другого держателя"
    assert db.delete_tables == [], "soft-delete не должен звать чистку связей"
    assert all(event != USER_RECORD_DELETED for _u, event, _p in seen)
    assert (owner, COLLECTION_ITEM_REMOVED, {"record_id": str(record.id)}) in seen


@pytest.mark.asyncio
async def test_remove_item_ignores_discogs_record(monkeypatch):
    """Каноничная Discogs-запись не должна пытаться софт-делетиться."""
    seen = _patch_emit(monkeypatch)
    owner = uuid4()
    collection_id, item_id = uuid4(), uuid4()
    record = make_record(owner, source="discogs")
    collection = SimpleNamespace(id=collection_id, user_id=owner)
    item = SimpleNamespace(id=item_id, collection_id=collection_id, record_id=record.id)
    db = FakeSession(collection=collection, item=item, record=record, foreign_holders=(0, 0))

    await remove_item_from_collection(
        collection_id, item_id, current_user=make_user(owner), db=db
    )

    assert record.moderation_status == "approved"
    assert db.delete_tables == []
    assert all(event != USER_RECORD_DELETED for _u, event, _p in seen)


@pytest.mark.asyncio
async def test_remove_record_from_collection_cascades_too(monkeypatch):
    """Второй delete-эндпоинт (по record_id, не по item_id) — тот же баг."""
    seen = _patch_emit(monkeypatch)
    owner = uuid4()
    collection_id = uuid4()
    record = make_record(owner)
    collection = SimpleNamespace(id=collection_id, user_id=owner)
    item = SimpleNamespace(id=uuid4(), collection_id=collection_id, record_id=record.id)
    db = FakeSession(collection=collection, item=item, record=record, foreign_holders=(0, 0))

    await remove_record_from_collection(
        collection_id, record.id, current_user=make_user(owner), db=db
    )

    assert record.moderation_status == DELETED_STATUS
    assert (owner, USER_RECORD_DELETED, {"record_id": record.id}) in seen
