"""Мягкое удаление своего ручного релиза (§11).

Правило владельца: пока запись никому больше не понадобилась — её можно
убрать; как только она попала в чужую коллекцию или вишлист, она перестаёт
быть личным черновиком и остаётся в «Моих релизах» навсегда.

Физического DELETE нет: на record_id висят коллекции, вишлисты, подарки,
клики по офферам и ачивки.
"""
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.api.records import delete_user_submitted_record, get_record
from app.services.user_record import DELETED_STATUS


class FakeResult:
    def __init__(self, obj):
        self._obj = obj

    def scalar_one_or_none(self):
        return self._obj


class FakeSession:
    """Минимальная сессия: отдаёт запись на select, считает холдеров, пишет."""

    def __init__(self, record, foreign_holders=(0, 0)):
        self._record = record
        self._scalars = list(foreign_holders)
        self.deletes = []
        self.committed = False
        self.flushed = False

    async def execute(self, query, *_a, **_kw):
        # Два вида стейтментов: select(Record) на входе в ручку и DELETE-ы
        # чистки собственных ссылок автора. Различаем по тексту.
        text = str(query).lstrip()
        if text.upper().startswith("DELETE"):
            self.deletes.append(text)
            return None
        return FakeResult(self._record)

    async def scalar(self, *_a, **_kw):
        return self._scalars.pop(0) if self._scalars else 0

    async def flush(self):
        self.flushed = True

    async def commit(self):
        self.committed = True


def make_user_record(owner_id, *, source="user", statusv="approved"):
    return SimpleNamespace(
        id=uuid4(),
        source=source,
        created_by_user_id=owner_id,
        moderation_status=statusv,
        merged_into_id=None,
    )


def make_user(uid, *, staff=False):
    return SimpleNamespace(id=uid, is_staff=staff)


@pytest.mark.asyncio
async def test_owner_can_delete_unused_record():
    owner = uuid4()
    rec = make_user_record(owner)
    db = FakeSession(rec, foreign_holders=(0, 0))

    await delete_user_submitted_record(rec.id, current_user=make_user(owner), db=db)

    assert rec.moderation_status == DELETED_STATUS
    assert db.committed, "удаление должно коммититься"
    # Свои ссылки отцепляем: иначе в коллекции осталась бы карточка на 404.
    assert len(db.deletes) == 2, "чистим и коллекцию, и вишлист автора"


@pytest.mark.asyncio
async def test_record_held_by_others_survives():
    """Кто-то уже добавил себе — 409, запись остаётся в «Моих релизах»."""
    owner = uuid4()
    rec = make_user_record(owner)
    db = FakeSession(rec, foreign_holders=(2, 1))

    with pytest.raises(HTTPException) as exc:
        await delete_user_submitted_record(rec.id, current_user=make_user(owner), db=db)

    assert exc.value.status_code == 409
    assert exc.value.detail["code"] == "record_in_use"
    assert exc.value.detail["holders"] == 3
    assert rec.moderation_status == "approved", "статус не должен меняться"
    assert not db.committed
    assert not db.deletes


@pytest.mark.asyncio
async def test_holders_message_declines_correctly():
    owner = uuid4()
    for holders, expected in ((1, "1 человек"), (3, "3 человека"), (5, "5 человек")):
        rec = make_user_record(owner)
        db = FakeSession(rec, foreign_holders=(holders, 0))
        with pytest.raises(HTTPException) as exc:
            await delete_user_submitted_record(rec.id, current_user=make_user(owner), db=db)
        assert expected in exc.value.detail["message"]


@pytest.mark.asyncio
async def test_foreign_record_forbidden():
    rec = make_user_record(uuid4())
    db = FakeSession(rec)

    with pytest.raises(HTTPException) as exc:
        await delete_user_submitted_record(rec.id, current_user=make_user(uuid4()), db=db)

    assert exc.value.status_code == 403
    assert rec.moderation_status == "approved"


@pytest.mark.asyncio
async def test_discogs_record_not_deletable():
    """Каноничную запись Discogs автор ручного релиза удалить не может."""
    owner = uuid4()
    rec = make_user_record(owner, source="discogs")
    db = FakeSession(rec)

    with pytest.raises(HTTPException) as exc:
        await delete_user_submitted_record(rec.id, current_user=make_user(owner), db=db)

    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_missing_record_404():
    db = FakeSession(None)
    with pytest.raises(HTTPException) as exc:
        await delete_user_submitted_record(uuid4(), current_user=make_user(uuid4()), db=db)
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_deleted_record_is_gone_by_direct_link():
    """404 всем, включая автора и staff: это решение владельца, не модерация."""
    owner = uuid4()
    rec = make_user_record(owner, statusv=DELETED_STATUS)

    for viewer in (None, make_user(owner), make_user(uuid4(), staff=True)):
        db = FakeSession(rec)
        with pytest.raises(HTTPException) as exc:
            await get_record(rec.id, current_user=viewer, db=db)
        assert exc.value.status_code == 404


def test_my_records_list_hides_deleted():
    """Запрос «Моих релизов» обязан отсекать 'deleted' — иначе удаление немое."""
    import inspect

    from app.api.records import list_my_user_records

    src = inspect.getsource(list_my_user_records)
    assert 'Record.moderation_status != "deleted"' in src
