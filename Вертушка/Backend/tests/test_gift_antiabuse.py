"""Анти-абуз публичного бронирования подарков.

Три вектора закрываются здесь:
  1. per-email лимит теперь считает и PENDING (иначе при включённой
     email-верификации лимит обходился неподтверждёнными бронями);
  2. владелец вишлиста может отклонить подозрительную бронь и освободить пункт
     (раньше снять бронь мог только даритель или авто-экспирация);
  3. безопасный дефолт короткого holding-TTL для анонимной брони (0 = выключено,
     честный «подарил без регистрации» не ломается).
"""
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException

import app.api.gifts as gifts_mod
from app.api.gifts import _check_rate_limits, reject_booking
from app.models.gift_booking import GiftStatus


# ── Фейки ────────────────────────────────────────────────────────────────────

class ScalarSession:
    """Стаб под _check_rate_limits: отдаёт заготовленные scalar-значения по очереди."""

    def __init__(self, *scalars):
        self._scalars = list(scalars)
        self.queries = []

    async def scalar(self, query):
        self.queries.append(query)
        return self._scalars.pop(0)


class FakeResult:
    def __init__(self, obj):
        self._obj = obj

    def scalar_one_or_none(self):
        return self._obj


class ExecSession:
    """Стаб под reject_booking: execute отдаёт бронь, commit считается."""

    def __init__(self, booking):
        self._booking = booking
        self.committed = 0

    async def execute(self, *_a, **_k):
        return FakeResult(self._booking)

    async def commit(self):
        self.committed += 1


def _limits(ip_limit=5, email_limit=3):
    return SimpleNamespace(
        gift_booking_per_ip_limit=ip_limit,
        gift_booking_per_ip_window_minutes=60,
        gift_booking_per_email_active_limit=email_limit,
    )


def make_owner():
    return SimpleNamespace(id=uuid4(), display_name="Владелец", username="owner")


def make_booking(
    *,
    owner_id,
    status=GiftStatus.BOOKED,
    with_item=True,
    booked_by_user_id=None,
    record_title="Kind of Blue",
):
    record = SimpleNamespace(title=record_title, artist="Miles Davis")
    wl_item = None
    if with_item:
        wl_item = SimpleNamespace(
            id=uuid4(),
            record=record,
            wishlist=SimpleNamespace(user_id=owner_id),
        )
    return SimpleNamespace(
        id=uuid4(),
        record=record,
        wishlist_item=wl_item,
        wishlist_item_id=wl_item.id if wl_item else None,
        recipient_user_id=owner_id,
        booked_by_user_id=booked_by_user_id,
        gifter_email="gifter@example.com",
        gifter_name="Даритель",
        status=status,
        cancelled_at=None,
        cancellation_reason=None,
        verify_token="tok",
    )


# ── 1. per-email лимит учитывает PENDING ─────────────────────────────────────

@pytest.mark.asyncio
async def test_per_email_query_counts_pending_and_booked(monkeypatch):
    """SQL лимита per-email должен ловить оба статуса, а не только BOOKED."""
    monkeypatch.setattr(gifts_mod, "get_settings", lambda: _limits())
    db = ScalarSession(0)

    await _check_rate_limits(db, email="a@b.com", ip=None)

    sql = str(db.queries[0].compile(compile_kwargs={"literal_binds": True})).lower()
    assert "'pending'" in sql, "PENDING-брони должны считаться в per-email лимите"
    assert "'booked'" in sql


@pytest.mark.asyncio
async def test_per_email_limit_blocks_at_cap(monkeypatch):
    """Достигнут лимит активных (BOOKED+PENDING) — 429."""
    monkeypatch.setattr(gifts_mod, "get_settings", lambda: _limits(email_limit=3))
    db = ScalarSession(3)  # ip=None → работает только email-ветка

    with pytest.raises(HTTPException) as exc:
        await _check_rate_limits(db, email="a@b.com", ip=None)
    assert exc.value.status_code == 429


@pytest.mark.asyncio
async def test_per_email_limit_allows_below_cap(monkeypatch):
    """Ниже лимита — не бросаем."""
    monkeypatch.setattr(gifts_mod, "get_settings", lambda: _limits(email_limit=3))
    db = ScalarSession(2)

    await _check_rate_limits(db, email="a@b.com", ip=None)  # не должно бросить


# ── 2. reject владельцем ─────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_reject_frees_item_and_emails_gifter(monkeypatch):
    """Владелец отклоняет бронь: статус CANCELLED, пункт свободен, письмо ушло."""
    sent = {}

    async def fake_email(**kw):
        sent.update(kw)

    monkeypatch.setattr(
        "app.services.notifications.send_booking_rejected_to_gifter", fake_email
    )
    owner = make_owner()
    booking = make_booking(owner_id=owner.id)
    db = ExecSession(booking)

    res = await reject_booking(booking_id=booking.id, current_user=owner, db=db)

    assert res == {"status": "cancelled"}
    assert booking.status == GiftStatus.CANCELLED
    assert booking.cancellation_reason == "rejected_by_owner"
    assert booking.wishlist_item_id is None
    assert booking.verify_token is None
    assert sent["gifter_email"] == "gifter@example.com"
    assert sent["owner_name"] == "Владелец"


@pytest.mark.asyncio
async def test_reject_works_on_pending(monkeypatch):
    """Неподтверждённую (PENDING) бронь владелец тоже может снять."""
    async def fake_email(**_kw):
        return None

    monkeypatch.setattr(
        "app.services.notifications.send_booking_rejected_to_gifter", fake_email
    )
    owner = make_owner()
    booking = make_booking(owner_id=owner.id, status=GiftStatus.PENDING)
    db = ExecSession(booking)

    res = await reject_booking(booking_id=booking.id, current_user=owner, db=db)

    assert res == {"status": "cancelled"}
    assert booking.status == GiftStatus.CANCELLED


@pytest.mark.asyncio
async def test_reject_denied_for_non_owner():
    """Чужой пользователь не может отклонить бронь."""
    owner = make_owner()
    stranger = make_owner()
    booking = make_booking(owner_id=owner.id, with_item=False)
    db = ExecSession(booking)

    with pytest.raises(HTTPException) as exc:
        await reject_booking(booking_id=booking.id, current_user=stranger, db=db)
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_reject_denied_via_wishlist_ownership_only():
    """Доступ и без recipient_user_id — по владению пунктом вишлиста."""
    async def fake_email(**_kw):
        return None

    import app.services.notifications as notif
    notif.send_booking_rejected_to_gifter = fake_email  # type: ignore[assignment]

    owner = make_owner()
    booking = make_booking(owner_id=owner.id)
    booking.recipient_user_id = None  # денормализованного получателя нет
    db = ExecSession(booking)

    res = await reject_booking(booking_id=booking.id, current_user=owner, db=db)
    assert res == {"status": "cancelled"}


@pytest.mark.asyncio
async def test_reject_completed_is_400():
    """Вручённый подарок отклонить нельзя."""
    owner = make_owner()
    booking = make_booking(owner_id=owner.id, status=GiftStatus.COMPLETED)
    db = ExecSession(booking)

    with pytest.raises(HTTPException) as exc:
        await reject_booking(booking_id=booking.id, current_user=owner, db=db)
    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_reject_already_cancelled_is_idempotent():
    """Повторный reject на CANCELLED — тихо возвращаем cancelled, без письма/commit."""
    owner = make_owner()
    booking = make_booking(owner_id=owner.id, status=GiftStatus.CANCELLED)
    db = ExecSession(booking)

    res = await reject_booking(booking_id=booking.id, current_user=owner, db=db)

    assert res == {"status": "cancelled"}
    assert db.committed == 0


@pytest.mark.asyncio
async def test_reject_notifies_registered_gifter(monkeypatch):
    """Зарегистрированному дарителю летит in-app уведомление gift_rejected."""
    async def fake_email(**_kw):
        return None

    calls = []

    async def fake_notif(_db, **kw):
        calls.append(kw)

    monkeypatch.setattr(
        "app.services.notifications.send_booking_rejected_to_gifter", fake_email
    )
    monkeypatch.setattr(
        "app.services.notification_service.create_notification", fake_notif
    )
    owner = make_owner()
    booking = make_booking(owner_id=owner.id, booked_by_user_id=uuid4())
    db = ExecSession(booking)

    await reject_booking(booking_id=booking.id, current_user=owner, db=db)

    assert calls, "registered gifter must get an in-app notification"
    assert calls[0]["type"] == "gift_rejected"


# ── 3. безопасный дефолт holding-TTL ─────────────────────────────────────────

def test_anon_hold_days_defaults_to_disabled():
    """Дефолт 0 — анонимная бронь сохраняет прежние 60 дней, честный флоу цел."""
    from app.config import get_settings

    assert get_settings().gift_booking_anon_hold_days == 0
