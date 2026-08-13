"""Подарочный флоу целиком: бронь → сканирование → подтверждение.

Здесь проверяется то, что юнит-тесты увидеть не могут, потому что живёт в
эндпоинте и в транзакции:

  - POST /collections/{id}/items не должен удалять пункт вишлиста, пока на нём
    висит бронь (именно это молча теряло подарок: пункт удалялся, FK обнулял
    wishlist_item_id, бронь навсегда застревала в BOOKED);
  - совпадение отдаётся клиенту прямо в ответе, без второго запроса;
  - подтверждение закрывает бронь и убирает пункт, не создавая дубль пластинки;
  - отказ гасит вопрос навсегда;
  - когда брони нет, старое поведение сохраняется — пункт уезжает из вишлиста.
"""
import pytest
from sqlalchemy import select

from app.models.collection import CollectionItem
from app.models.gift_booking import GiftBooking, GiftStatus
from app.models.wishlist import WishlistItem

pytestmark = pytest.mark.asyncio


async def book(client, item_id) -> dict:
    """Бронирует подарок как посторонний человек по публичной ссылке."""
    response = await client.post(
        "/gifts/book",
        json={
            "wishlist_item_id": str(item_id),
            "gifter_name": "Даритель",
            "gifter_email": "gifter@example.com",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


async def add_to_collection(client, collection_id, record) -> dict:
    response = await client.post(
        f"/collections/{collection_id}/items",
        json={"record_id": str(record.id)},
    )
    assert response.status_code == 201, response.text
    return response.json()


async def test_scanning_the_same_version_does_not_lose_the_booking(
    client, db, collection_id, make_record, wishlist_item
):
    """Регрессия: раньше бронь тут терялась насовсем."""
    record = await make_record(master="m1")
    item = await wishlist_item(record)
    await book(client, item.id)

    added = await add_to_collection(client, collection_id, record)

    assert added["gift_match"] is not None
    assert added["gift_match"]["match_kind"] == "exact"

    # Пункт вишлиста на месте — иначе бронь осталась бы без связи.
    survived = await db.scalar(select(WishlistItem).where(WishlistItem.id == item.id))
    assert survived is not None

    booking = await db.scalar(select(GiftBooking))
    assert booking.status == GiftStatus.BOOKED
    assert booking.wishlist_item_id == item.id


async def test_scanning_another_pressing_offers_the_booking(
    client, collection_id, make_record, wishlist_item
):
    """Главный сценарий: забронировали одно издание, подарили другое."""
    wished = await make_record(master="m1", year=2023)
    await book(client, (await wishlist_item(wished)).id)

    gifted = await make_record(master="m1", year=2026)
    added = await add_to_collection(client, collection_id, gifted)

    match = added["gift_match"]
    assert match is not None
    assert match["match_kind"] == "master"
    # Клиенту нужна версия из вишлиста, чтобы показать её рядом в поп-апе.
    assert match["wished_record"]["year"] == 2023


async def test_confirming_completes_booking_without_duplicating_the_record(
    client, db, collection_id, make_record, wishlist_item
):
    """«Да, мне её подарили»: бронь закрыта, пункт ушёл, пластинка одна."""
    wished = await make_record(master="m1", year=2023)
    item = await wishlist_item(wished)
    await book(client, item.id)

    gifted = await make_record(master="m1", year=2026)
    added = await add_to_collection(client, collection_id, gifted)

    response = await client.put(
        f"/gifts/me/received/{added['gift_match']['booking_id']}/complete-with-record",
        params={"collection_item_id": added["id"]},
    )
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "completed"

    booking = await db.scalar(select(GiftBooking))
    assert booking.status == GiftStatus.COMPLETED
    assert booking.completed_at is not None
    assert booking.wishlist_item_id is None
    # Получателя фиксируем до обнуления связи — иначе ачивкам не с чем работать.
    assert booking.recipient_user_id is not None

    assert await db.scalar(select(WishlistItem).where(WishlistItem.id == item.id)) is None

    items = (await db.execute(select(CollectionItem))).scalars().all()
    assert len(items) == 1, "в коллекции должна остаться ровно подаренная пластинка"
    assert items[0].record_id == gifted.id


async def test_declining_stops_asking_on_the_next_scan(
    client, db, collection_id, make_record, wishlist_item
):
    """«Нет, купил сам»: бронь жива, но вопрос больше не всплывает."""
    wished = await make_record(master="m1", year=2023)
    item = await wishlist_item(wished)
    await book(client, item.id)

    gifted = await make_record(master="m1", year=2026)
    added = await add_to_collection(client, collection_id, gifted)

    response = await client.put(
        f"/gifts/me/received/{added['gift_match']['booking_id']}/dismiss-match"
    )
    assert response.status_code == 200, response.text

    another = await make_record(master="m1", year=2019)
    again = await add_to_collection(client, collection_id, another)
    assert again["gift_match"] is None

    # Бронь при отказе не трогаем: подарок всё ещё могут вручить.
    booking = await db.scalar(select(GiftBooking))
    assert booking.status == GiftStatus.BOOKED
    assert booking.wishlist_item_id == item.id


async def test_without_booking_item_still_leaves_the_wishlist(
    client, db, collection_id, make_record, wishlist_item
):
    """Старое поведение не сломано: без брони пункт по-прежнему уезжает сам."""
    record = await make_record()
    item = await wishlist_item(record)

    added = await add_to_collection(client, collection_id, record)

    assert added["gift_match"] is None
    assert await db.scalar(select(WishlistItem).where(WishlistItem.id == item.id)) is None


async def test_unrelated_album_does_not_touch_the_booking(
    client, db, collection_id, make_record, wishlist_item
):
    """Чужой альбом не должен ни давать поп-ап, ни задевать бронь."""
    wished = await make_record(master="m1")
    item = await wishlist_item(wished)
    await book(client, item.id)

    other = await make_record(artist="Radiohead", title="In Rainbows", master="m2")
    added = await add_to_collection(client, collection_id, other)

    assert added["gift_match"] is None
    booking = await db.scalar(select(GiftBooking))
    assert booking.wishlist_item_id == item.id


async def test_double_booking_is_rejected(client, make_record, wishlist_item):
    """Уникальный индекс на wishlist_item_id: второй даритель получает отказ."""
    record = await make_record()
    item = await wishlist_item(record)
    await book(client, item.id)

    response = await client.post(
        "/gifts/book",
        json={
            "wishlist_item_id": str(item.id),
            "gifter_name": "Второй",
            "gifter_email": "second@example.com",
        },
    )
    assert response.status_code in (400, 409), response.text


async def test_owner_does_not_see_who_booked_the_gift(
    client, make_record, wishlist_item
):
    """Анонимность: получатель видит факт брони, но не имя дарителя."""
    record = await make_record()
    await book(client, (await wishlist_item(record)).id)

    response = await client.get("/wishlists/")
    assert response.status_code == 200, response.text

    booked = [i for i in response.json()["items"] if i["is_booked"]]
    assert len(booked) == 1
    assert booked[0]["gift_booking"]["gifter_name"] == ""

    received = await client.get("/gifts/me/received")
    assert received.status_code == 200, received.text
    assert received.json()[0]["gifter_name"] == ""
