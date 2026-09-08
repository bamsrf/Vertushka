"""Даты сообщений/уведомлений уходят в API с офсетом (BUGS A14).

Модели пишут в БД naive `datetime.utcnow()`. Без явного офсета клиент
(Hermes) парсит `2026-09-08T12:00:00` как локальное время, и «минуту назад»
в Москве превращается в «3 ч назад». Схемы сообщений и уведомлений обязаны
отдавать `Z`/`+00:00`, а хранение (naive) при этом не меняется.
"""
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from app.schemas.message import ConversationRead, MessageRead, PresenceResponse
from app.schemas.notification import NotificationResponse
from app.schemas.utc import as_utc, utc_isoformat

NAIVE = datetime(2026, 9, 8, 12, 0, 5)


def _message(**overrides) -> MessageRead:
    base = dict(
        id=uuid4(),
        conversation_id=uuid4(),
        sender_id=uuid4(),
        body="hi",
        created_at=NAIVE,
    )
    base.update(overrides)
    return MessageRead(**base)


def test_message_created_at_json_has_utc_marker():
    payload = _message().model_dump(mode="json")
    assert payload["created_at"] == "2026-09-08T12:00:05Z"
    assert payload["edited_at"] is None


def test_json_roundtrip_is_same_utc_instant():
    payload = _message().model_dump(mode="json")
    parsed = datetime.fromisoformat(payload["created_at"].replace("Z", "+00:00"))
    assert parsed == NAIVE.replace(tzinfo=timezone.utc)


def test_aware_datetime_is_not_shifted():
    msk = timezone(timedelta(hours=3))
    aware = datetime(2026, 9, 8, 15, 0, 5, tzinfo=msk)
    payload = _message(created_at=aware).model_dump(mode="json")
    parsed = datetime.fromisoformat(payload["created_at"])
    assert parsed == aware
    assert parsed.utcoffset() is not None


def test_python_mode_keeps_datetime_but_aware():
    dumped = _message().model_dump()
    assert isinstance(dumped["created_at"], datetime)
    assert dumped["created_at"].tzinfo is timezone.utc


def test_conversation_and_presence_optional_fields():
    conv = ConversationRead(
        id=uuid4(),
        partner={"id": uuid4(), "username": "u"},
        last_message_at=NAIVE,
        partner_last_read_at=None,
    ).model_dump(mode="json")
    assert conv["last_message_at"].endswith("Z")
    assert conv["partner_last_read_at"] is None
    assert conv["muted_until"] is None

    presence = PresenceResponse(online=False, last_seen_at=NAIVE).model_dump(mode="json")
    assert presence["last_seen_at"].endswith("Z")


def test_notification_dates_have_utc_marker():
    payload = NotificationResponse(
        id=uuid4(),
        type="achievement_unlocked",
        created_at=NAIVE,
        bumped_at=NAIVE,
        read_at=NAIVE + timedelta(minutes=1),
    ).model_dump(mode="json")
    for key in ("created_at", "bumped_at", "read_at"):
        assert payload[key].endswith("Z"), key
    assert payload["snoozed_until"] is None


def test_utc_isoformat_for_manual_ws_events():
    assert utc_isoformat(None) is None
    out = utc_isoformat(NAIVE)
    assert out == "2026-09-08T12:00:05+00:00"
    assert datetime.fromisoformat(out) == NAIVE.replace(tzinfo=timezone.utc)


def test_as_utc_keeps_storage_semantics():
    # Значение по стрелкам не меняется — только помечается как UTC.
    assert as_utc(NAIVE).replace(tzinfo=None) == NAIVE
