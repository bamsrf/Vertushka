"""Завершение подарка: бронь закрывается, пластинка не двоится.

Два входа в один и тот же сервис:
  - «отметить полученным» из раздела подарков — пластинку в коллекцию создаём мы;
  - подтверждение поп-апа после скана — пластинка уже там, второй раз не нужна.

Отдельно фиксируем то, из-за чего всё чинилось: пункт вишлиста должен уйти,
статус стать COMPLETED, а recipient_user_id проставиться ДО обнуления связи —
иначе после wishlist_item_id=None получателя уже не достать, и серия ачивок
«Дарящая рука» останется без данных.
"""
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.models.collection import CollectionItem
from app.models.gift_booking import GiftStatus
from app.services.gifts import complete_gift_booking


class FakeSession:
    """Стаб AsyncSession: записывает add/delete, отдаёт готовую коллекцию."""

    def __init__(self, collection=None):
        self.added = []
        self.deleted = []
        self._collection = collection

    def add(self, obj):
        self.added.append(obj)

    async def delete(self, obj):
        self.deleted.append(obj)

    async def flush(self):
        pass

    async def execute(self, *_args, **_kwargs):
        collection = self._collection
        return SimpleNamespace(
            scalar_one_or_none=lambda: collection,
            scalars=lambda: SimpleNamespace(first=lambda: collection),
        )


def make_booking(*, item):
    return SimpleNamespace(
        id=uuid4(),
        wishlist_item=item,
        wishlist_item_id=item.id,
        status=GiftStatus.BOOKED,
        completed_at=None,
        recipient_user_id=None,
        booked_by_user_id=uuid4(),
        gifter_email="gifter@example.com",
        gifter_name="Даритель",
    )


def make_item():
    record = SimpleNamespace(id=uuid4(), title="Omnium Gatherum", artist="King Gizzard")
    return SimpleNamespace(id=uuid4(), record=record, record_id=record.id)


OWNER = SimpleNamespace(id=uuid4(), display_name="Владелец", username="owner")
COLLECTION = SimpleNamespace(id=uuid4())


@pytest.mark.asyncio
async def test_manual_complete_creates_collection_item():
    """Путь «отметить полученным»: пластинки в коллекции ещё нет — создаём."""
    item = make_item()
    booking = make_booking(item=item)
    db = FakeSession(collection=COLLECTION)

    result = await complete_gift_booking(booking=booking, owner=OWNER, db=db)

    assert isinstance(result, CollectionItem)
    assert result in db.added
    assert result.record_id == item.record_id


@pytest.mark.asyncio
async def test_scan_complete_does_not_duplicate_the_record():
    """Путь поп-апа: пластинку уже добавил скан — второй раз её быть не должно."""
    item = make_item()
    booking = make_booking(item=item)
    scanned = CollectionItem(collection_id=COLLECTION.id, record_id=uuid4())
    db = FakeSession(collection=COLLECTION)

    result = await complete_gift_booking(
        booking=booking, owner=OWNER, db=db, existing_collection_item=scanned
    )

    assert result is scanned
    assert db.added == [], "коллекция уже содержит подаренную пластинку — дубль не нужен"


@pytest.mark.asyncio
async def test_completion_closes_booking_and_frees_wishlist_item():
    """То, что раньше терялось при скане: бронь закрыта, пункт вишлиста удалён."""
    item = make_item()
    booking = make_booking(item=item)
    db = FakeSession(collection=COLLECTION)

    await complete_gift_booking(booking=booking, owner=OWNER, db=db)

    assert booking.status == GiftStatus.COMPLETED
    assert booking.completed_at is not None
    assert booking.wishlist_item_id is None
    assert item in db.deleted


@pytest.mark.asyncio
async def test_recipient_is_stamped_before_link_is_dropped():
    """Без recipient_user_id серия «Дарящая рука» останется без получателя."""
    item = make_item()
    booking = make_booking(item=item)
    db = FakeSession(collection=COLLECTION)

    await complete_gift_booking(booking=booking, owner=OWNER, db=db)

    assert booking.recipient_user_id == OWNER.id


@pytest.mark.asyncio
async def test_gifter_email_payload_is_prepared():
    """Письмо «подарок получен» уходит после commit — данные готовим здесь."""
    item = make_item()
    booking = make_booking(item=item)
    db = FakeSession(collection=COLLECTION)

    result = await complete_gift_booking(booking=booking, owner=OWNER, db=db)

    payload = getattr(result, "_pending_gift_email", None)
    assert payload is not None
    assert payload["gifter_email"] == "gifter@example.com"
    assert payload["record_title"] == "Omnium Gatherum"
    assert payload["owner_name"] == "Владелец"


@pytest.mark.asyncio
async def test_second_completion_raises_instead_of_silently_passing():
    """Повторное завершение — уже без пункта вишлиста; тихо проглотить его нельзя."""
    booking = SimpleNamespace(wishlist_item=None)
    db = FakeSession(collection=COLLECTION)

    with pytest.raises(ValueError):
        await complete_gift_booking(booking=booking, owner=OWNER, db=db)
