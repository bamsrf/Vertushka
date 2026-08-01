"""Smoke-тесты модерации UGC (api/reports.py).

App Store Guideline 1.2 требует работающий тейкдаун, а не его видимость.
Самый опасный класс дефекта здесь — тихий no-op: staff нажал «скрыть»,
жалоба закрылась, а контент остался на месте. Эти тесты фиксируют, что
каждое действие либо реально применяется, либо явно отказывает.

БД не поднимаем: `action_report` ходит в неё только через `db.get`.
"""
import uuid
from datetime import datetime

import pytest
from fastapi import HTTPException

from app.api import reports as reports_api
from app.models.conversation import Conversation, Message
from app.models.record import Record
from app.models.report import Report
from app.models.user import User
from app.schemas.report import ReportActionRequest


class FakeDB:
    """Подмена AsyncSession: get по (модель, id), commit/refresh — no-op."""

    def __init__(self, objects: list = None):
        self.store: dict[tuple[type, uuid.UUID], object] = {}
        for obj in objects or []:
            self.store[(type(obj), obj.id)] = obj
        self.committed = False

    async def get(self, model, obj_id):
        return self.store.get((model, obj_id))

    async def commit(self):
        self.committed = True

    async def refresh(self, _obj):
        pass


@pytest.fixture(autouse=True)
def silence_side_effects(monkeypatch):
    """Алармы и WS-рассылка в тестах не нужны — перехватываем."""
    sent_alerts: list[str] = []
    ws_events: list[tuple] = []

    monkeypatch.setattr(
        reports_api.alerts, "fire_and_forget",
        lambda key, title, body="": sent_alerts.append(key),
    )

    async def fake_push(user_id, event):
        ws_events.append((user_id, event))

    monkeypatch.setattr(reports_api.messages_ws_hub, "push_event", fake_push)
    return {"alerts": sent_alerts, "ws": ws_events}


def make_report(target_type: str, target_id: uuid.UUID) -> Report:
    return Report(
        id=uuid.uuid4(),
        reporter_id=uuid.uuid4(),
        target_type=target_type,
        target_id=target_id,
        reason="оскорбление",
        status="open",
        created_at=datetime.utcnow(),
    )


def make_user_record() -> Record:
    return Record(
        id=uuid.uuid4(), title="Самиздат", artist="Аноним",
        source="user", moderation_status="approved",
    )


def make_catalog_record() -> Record:
    return Record(
        id=uuid.uuid4(), title="Kind of Blue", artist="Miles Davis",
        source="discogs", moderation_status=None,
    )


def make_message(body: str | None = "текст", deleted: bool = False) -> Message:
    return Message(
        id=uuid.uuid4(),
        conversation_id=uuid.uuid4(),
        sender_id=uuid.uuid4(),
        body=body,
        created_at=datetime.utcnow(),
        deleted_at=datetime.utcnow() if deleted else None,
    )


async def act(report: Report, action: str, db: FakeDB):
    return await reports_api.action_report(
        report_id=report.id, data=ReportActionRequest(action=action),
        _staff=User(id=uuid.uuid4()), db=db,
    )


class TestHideRecord:
    async def test_user_record_is_hidden(self):
        record = make_user_record()
        report = make_report("record", record.id)
        db = FakeDB([record, report])

        await act(report, "hide_record", db)

        assert record.moderation_status == "rejected"
        assert report.status == "actioned"

    async def test_catalog_record_refused_not_silently_ignored(self):
        """Гейт скрытия в records.py срабатывает только для source='user'.

        Раньше статус проставился бы и жалоба закрылась, а каталожная запись
        осталась бы видимой — модератор считал бы проблему решённой.
        """
        record = make_catalog_record()
        report = make_report("record", record.id)
        db = FakeDB([record, report])

        with pytest.raises(HTTPException) as exc:
            await act(report, "hide_record", db)

        assert exc.value.status_code == 400
        assert report.status == "open", "жалоба не должна закрываться при отказе"

    async def test_wrong_target_type_refused(self):
        report = make_report("user", uuid.uuid4())
        db = FakeDB([report])

        with pytest.raises(HTTPException) as exc:
            await act(report, "hide_record", db)

        assert exc.value.status_code == 400


class TestHideMessage:
    async def test_message_is_tombstoned(self):
        message = make_message("оскорбление")
        report = make_report("message", message.id)
        db = FakeDB([message, report])

        await act(report, "hide_message", db)

        assert message.body is None, "текст должен исчезнуть, а не просто пометиться"
        assert message.deleted_at is not None
        assert report.status == "actioned"

    async def test_participants_notified(self, silence_side_effects):
        conversation = Conversation(
            id=uuid.uuid4(), user_a_id=uuid.uuid4(), user_b_id=uuid.uuid4(),
        )
        message = make_message()
        message.conversation_id = conversation.id
        report = make_report("message", message.id)
        db = FakeDB([message, report, conversation])

        await act(report, "hide_message", db)

        events = silence_side_effects["ws"]
        assert len(events) == 2, "оба участника должны увидеть удаление сразу"
        assert all(e[1]["type"] == "message.deleted" for e in events)

    async def test_already_deleted_message_is_idempotent(self):
        message = make_message(body=None, deleted=True)
        original_deleted_at = message.deleted_at
        report = make_report("message", message.id)
        db = FakeDB([message, report])

        await act(report, "hide_message", db)

        assert message.deleted_at == original_deleted_at
        assert report.status == "actioned"

    async def test_missing_conversation_does_not_block_takedown(self):
        """Контент важнее рассылки: не нашли диалог — всё равно скрываем."""
        message = make_message()
        report = make_report("message", message.id)
        db = FakeDB([message, report])  # Conversation отсутствует

        await act(report, "hide_message", db)

        assert message.body is None

    async def test_wrong_target_type_refused(self):
        report = make_report("record", uuid.uuid4())
        db = FakeDB([report])

        with pytest.raises(HTTPException) as exc:
            await act(report, "hide_message", db)

        assert exc.value.status_code == 400


class TestBanUser:
    async def test_user_deactivated(self):
        user = User(id=uuid.uuid4(), is_active=True)
        report = make_report("user", user.id)
        db = FakeDB([user, report])

        await act(report, "ban_user", db)

        assert user.is_active is False
        assert report.status == "actioned"


class TestTargetPreview:
    """Без превью разобрать жалобу за 24ч можно только через доступ к БД."""

    async def test_record_preview(self):
        record = make_user_record()
        report = make_report("record", record.id)
        db = FakeDB([record, report])

        preview = await reports_api._build_target_preview(db, report)

        assert "Аноним" in preview and "Самиздат" in preview

    async def test_message_preview_shows_text(self):
        message = make_message("оскорбительный текст")
        report = make_report("message", message.id)
        db = FakeDB([message, report])

        assert await reports_api._build_target_preview(db, report) == "оскорбительный текст"

    async def test_deleted_message_preview_is_explicit(self):
        message = make_message(body=None, deleted=True)
        report = make_report("message", message.id)
        db = FakeDB([message, report])

        assert "удалено" in await reports_api._build_target_preview(db, report)

    async def test_preview_is_truncated(self):
        message = make_message("а" * 500)
        report = make_report("message", message.id)
        db = FakeDB([message, report])

        preview = await reports_api._build_target_preview(db, report)

        assert len(preview) == reports_api._PREVIEW_MAX_CHARS

    async def test_missing_target_gives_none(self):
        report = make_report("record", uuid.uuid4())
        db = FakeDB([report])

        assert await reports_api._build_target_preview(db, report) is None
