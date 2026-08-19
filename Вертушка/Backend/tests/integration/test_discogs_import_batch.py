"""Батч-запись импорта Discogs: _write_imported_releases.

Живой Postgres обязателен: проверяется именно SQL-механика, ради которой
импорт переписан, — записи резолвятся пачками (WHERE discogs_id IN (...)
вместо SELECT'а на каждый релиз), дедуп по discogs_id, идемпотентность
повторного прогона и видимый прогресс в state.
"""
from uuid import uuid4

import pytest
from sqlalchemy import func, select


def _basic(discogs_id: int, title: str = "Test LP") -> dict:
    """Минимальный basic_information, как его отдаёт Discogs collection API."""
    return {
        "id": discogs_id,
        "master_id": None,
        "title": title,
        "artists": [{"name": "Test Artist"}],
        "labels": [{"name": "Test Label", "catno": "TL-1"}],
        "formats": [{"name": "Vinyl", "descriptions": ["LP"]}],
        "year": 1985,
        "genres": ["Rock"],
        "styles": [],
        "cover_image": None,
        "thumb": None,
    }


def _state() -> dict:
    return {"status": "running", "imported": 0, "skipped": 0, "total": 0, "error": None}


@pytest.fixture(autouse=True)
def _no_outbound(monkeypatch):
    """Курс и дамп-обогащение — вне предмета теста, глушим сеть/дамп."""
    from app.api import collections as col

    async def _rate():
        return 100.0

    async def _no_enrich(db, ids):
        return 0

    monkeypatch.setattr(col, "get_usd_rub_rate", _rate)
    monkeypatch.setattr(col, "enrich_records_from_dump", _no_enrich)


@pytest.fixture
async def user(db):
    from app.models.user import User

    u = User(
        email=f"importer-{uuid4().hex[:8]}@example.com",
        username=f"importer{uuid4().hex[:8]}",
        password_hash="x",
        display_name="Импортёр",
    )
    db.add(u)
    await db.commit()
    return u


async def test_batch_import_creates_records_items_and_dedupes(db, user):
    from app.api.collections import _write_imported_releases
    from app.models.collection import Collection, CollectionItem
    from app.models.record import Record

    # 5 релизов, один из них — дважды (две копии одного прессинга в Discogs).
    releases = [_basic(i, title=f"LP {i}") for i in range(1001, 1006)]
    releases.append(_basic(1001))

    state = _state()
    await _write_imported_releases(db, user.id, releases, state)

    assert state["imported"] == 5
    assert state["skipped"] == 0

    items_count = await db.scalar(
        select(func.count(CollectionItem.id))
        .join(Collection, CollectionItem.collection_id == Collection.id)
        .where(Collection.user_id == user.id)
    )
    assert items_count == 5

    records_count = await db.scalar(
        select(func.count(Record.id)).where(
            Record.discogs_id.in_([str(i) for i in range(1001, 1006)])
        )
    )
    assert records_count == 5


async def test_existing_records_reused_not_duplicated(db, user):
    from app.api.collections import _write_imported_releases, _record_from_basic_information
    from app.models.record import Record

    # Запись уже существует (создана чужим импортом/поиском) — новый импорт
    # обязан привязаться к ней, а не вставить дубль discogs_id.
    existing = _record_from_basic_information(_basic(2001, title="Уже есть"))
    db.add(existing)
    await db.commit()

    state = _state()
    await _write_imported_releases(db, user.id, [_basic(2001), _basic(2002)], state)

    assert state["imported"] == 2
    count = await db.scalar(
        select(func.count(Record.id)).where(Record.discogs_id == "2001")
    )
    assert count == 1


async def test_second_run_is_idempotent(db, user):
    from app.api.collections import _write_imported_releases
    from app.models.collection import Collection, CollectionItem

    releases = [_basic(i) for i in range(3001, 3004)]

    first = _state()
    await _write_imported_releases(db, user.id, releases, first)
    assert first["imported"] == 3

    second = _state()
    await _write_imported_releases(db, user.id, releases, second)
    assert second["imported"] == 0
    assert second["skipped"] == 3

    items_count = await db.scalar(
        select(func.count(CollectionItem.id))
        .join(Collection, CollectionItem.collection_id == Collection.id)
        .where(Collection.user_id == user.id)
    )
    assert items_count == 3


async def test_garbage_ids_skipped(db, user):
    from app.api.collections import _write_imported_releases
    from app.models.collection import Collection, CollectionItem

    releases = [_basic(4001), {"id": None, "title": "мусор"}]
    state = _state()
    await _write_imported_releases(db, user.id, releases, state)

    assert state["imported"] == 1
    items_count = await db.scalar(
        select(func.count(CollectionItem.id))
        .join(Collection, CollectionItem.collection_id == Collection.id)
        .where(Collection.user_id == user.id)
    )
    assert items_count == 1
