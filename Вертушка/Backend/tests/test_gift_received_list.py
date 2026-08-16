"""Раздел «Мне дарят» не должен терять брони после вручения.

Регрессия: /gifts/me/received строился join'ом по WishlistItem, а при
вручении (и при отмене/удалении пункта) wishlist_item_id обнуляется —
подарок пропадал из списка, и тап по уведомлению «кто-то забронировал…»
приводил на экран «Подарок не найден».
"""
from datetime import datetime
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.api.gifts import get_received_bookings
from app.models.gift_booking import GiftStatus


class FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def scalars(self):
        rows = self._rows
        return SimpleNamespace(all=lambda: rows, unique=lambda: SimpleNamespace(all=lambda: rows))


class FakeSession:
    """Отдаёт заранее заготовленные результаты по порядку вызовов execute."""

    def __init__(self, *results):
        self._results = list(results)
        self.queries = []

    async def execute(self, query, *_args, **_kwargs):
        self.queries.append(query)
        return FakeResult(self._results.pop(0))


def make_record(title="Tim Maia"):
    return SimpleNamespace(
        id=uuid4(),
        source="discogs",
        discogs_id="123",
        title=title,
        artist="Tim Maia",
        year=1978,
        cover_image_url=None,
        thumb_image_url=None,
        cover_local_path=None,
        estimated_price_median=None,
        price_currency="RUB",
        cover_cached_at=None,
    )


def make_booking(*, record, wishlist_item, status, recipient_id):
    return SimpleNamespace(
        id=uuid4(),
        record=record,
        wishlist_item=wishlist_item,
        wishlist_item_id=wishlist_item.id if wishlist_item else None,
        recipient_user_id=recipient_id,
        status=status,
        gifter_name="Даритель",
        gifter_email="gifter@example.com",
        gifter_phone=None,
        gifter_message=None,
        booked_at=datetime(2026, 8, 15, 12, 0),
        completed_at=None,
        cancelled_at=None,
    )


OWNER = SimpleNamespace(id=uuid4(), username="owner")
WISHLIST = SimpleNamespace(id=uuid4(), reveal_gifter_to_owner=False)


@pytest.mark.asyncio
async def test_completed_gift_survives_broken_wishlist_link():
    """Вручённая бронь: пункта вишлиста уже нет, релиз берём с самой брони."""
    record = make_record()
    booking = make_booking(
        record=record,
        wishlist_item=None,
        status=GiftStatus.COMPLETED,
        recipient_id=OWNER.id,
    )
    db = FakeSession([WISHLIST], [booking])

    result = await get_received_bookings(current_user=OWNER, db=db)

    assert len(result) == 1
    assert result[0].id == booking.id
    assert result[0].wishlist_item_id is None
    assert result[0].record.title == "Tim Maia"


@pytest.mark.asyncio
async def test_active_booking_still_returned_with_item():
    """Обычный путь: активная бронь с живым пунктом вишлиста."""
    record = make_record("Hello Nasty")
    item = SimpleNamespace(id=uuid4(), record=record)
    booking = make_booking(
        record=None,  # legacy-строка без record_id — падаем на пункт вишлиста
        wishlist_item=item,
        status=GiftStatus.BOOKED,
        recipient_id=OWNER.id,
    )
    db = FakeSession([WISHLIST], [booking])

    result = await get_received_bookings(current_user=OWNER, db=db)

    assert len(result) == 1
    assert result[0].wishlist_item_id == item.id
    assert result[0].record.title == "Hello Nasty"


@pytest.mark.asyncio
async def test_gifter_stays_anonymous_without_reveal_flag():
    """Дефолт — тайный даритель: имя и почта не утекают владельцу."""
    booking = make_booking(
        record=make_record(),
        wishlist_item=None,
        status=GiftStatus.BOOKED,
        recipient_id=OWNER.id,
    )
    db = FakeSession([WISHLIST], [booking])

    result = await get_received_bookings(current_user=OWNER, db=db)

    assert result[0].gifter_name == ""
    assert result[0].gifter_email == ""


@pytest.mark.asyncio
async def test_no_wishlist_does_not_hide_received_gifts():
    """Вишлист удалили — подарки, где ты получатель, всё равно видны."""
    booking = make_booking(
        record=make_record(),
        wishlist_item=None,
        status=GiftStatus.COMPLETED,
        recipient_id=OWNER.id,
    )
    db = FakeSession([], [booking])

    result = await get_received_bookings(current_user=OWNER, db=db)

    assert len(result) == 1
