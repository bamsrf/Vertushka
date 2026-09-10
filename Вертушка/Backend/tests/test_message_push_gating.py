"""Гейты пушей о личных сообщениях.

Две дыры, закрытые здесь (срез уведомлений 10.09.2026):

1. Колонка `notify_messages` жила в базе с дефолтом true, но не была ни в
   схеме API, ни в `PUSH_PREFERENCE_FIELD` — то есть чат-пуши не выключались
   изнутри приложения вообще, только мьютом каждого диалога или системными
   настройками iOS.
2. Мьют треда в «Запросах» снимал с пуша аватар, но не сам пуш: гейт стоял
   в ветке принятых диалогов, а ветка pending его не проверяла.
"""
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.api.messages import _push_for_request
from app.schemas.user import NotificationSettingsResponse, NotificationSettingsUpdate
from app.services import push as push_service


class _FakeDB:
    """Минимальная сессия: send_push читает юзера и, возможно, коммитит токен."""

    def __init__(self, user):
        self._user = user
        self.commits = 0

    async def scalar(self, *_args, **_kwargs):
        return self._user

    async def commit(self):
        self.commits += 1


def _user(**overrides):
    base = dict(
        id=uuid4(),
        is_active=True,
        deleted_at=None,
        push_token="ExponentPushToken[xxxxxxxxxxxxxxxxxxxxxx]",
        notify_messages=True,
        quiet_hours_enabled=False,
        quiet_hours_start=None,
        quiet_hours_end=None,
    )
    base.update(overrides)
    return SimpleNamespace(**base)


# --- Настройки: флаг доезжает до API и до гейта -----------------------------


@pytest.mark.parametrize("notification_type", ["message", "message_request"])
def test_chat_types_are_mapped_to_notify_messages(notification_type):
    """Без маппинга push уходит мимо настроек — выключить его нечем."""
    assert push_service.PUSH_PREFERENCE_FIELD[notification_type] == "notify_messages"


def test_notification_settings_schema_exposes_the_flag():
    """Флаг в базе без поля в схеме — ровно тот случай, что и был."""
    assert "notify_messages" in NotificationSettingsResponse.model_fields
    assert "notify_messages" in NotificationSettingsUpdate.model_fields
    assert NotificationSettingsResponse().notify_messages is True


# --- send_push уважает флаг -------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize("notification_type", ["message", "message_request"])
async def test_push_is_skipped_when_messages_disabled(monkeypatch, notification_type):
    posted: list = []

    async def _fail(messages):
        posted.append(messages)
        return [{"status": "ok", "id": "receipt"}]

    monkeypatch.setattr(push_service, "_post_with_retry", _fail)

    db = _FakeDB(_user(notify_messages=False))
    sent = await push_service.send_push(
        db,
        db._user.id,
        notification_type=notification_type,
        title="Ксения",
        body="Привет!",
        bypass_cap=True,
    )

    assert sent is False
    assert posted == [], "push ушёл в Expo при выключенном тумблере сообщений"


@pytest.mark.asyncio
async def test_push_goes_through_when_messages_enabled(monkeypatch):
    posted: list = []

    async def _ok(messages):
        posted.append(messages)
        return [{"status": "ok", "id": "receipt"}]

    monkeypatch.setattr(push_service, "_post_with_retry", _ok)

    db = _FakeDB(_user(notify_messages=True))
    sent = await push_service.send_push(
        db,
        db._user.id,
        notification_type="message",
        title="Ксения",
        body="Привет!",
        bypass_cap=True,
    )

    assert sent is True
    assert posted and posted[0][0]["title"] == "Ксения"


# --- Мьют треда в «Запросах» ------------------------------------------------


def test_muted_request_thread_sends_no_push():
    assert _push_for_request("Ксения", "Привет!", muted=True) == (None, None)


def test_unmuted_request_thread_keeps_sender_and_preview():
    title, body = _push_for_request("Ксения", "Привет!", muted=False)
    assert (title, body) == ("Ксения", "Привет!")


def test_empty_preview_falls_back_to_generic_body():
    _, body = _push_for_request("Ксения", "", muted=False)
    assert body == "Новое сообщение"
