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
import asyncio
from uuid import UUID

import pytest
from sqlalchemy import func, select

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


async def verify_email(client, db, booking_id: str) -> None:
    """Подтверждает владение email через реальный PUT /confirm.

    Флаг gift_booking_require_email_verification в тестах выключен, поэтому
    бронь создаётся сразу BOOKED без verify_token. Эмулируем включённую
    верификацию: возвращаем бронь в PENDING с токеном и подтверждаем через
    эндпоинт — именно он проставляет verified_at, по которому «Я дарю»
    матчит анонимные брони к аккаунту по gifter_email.
    """
    booking = await db.scalar(
        select(GiftBooking).where(GiftBooking.id == UUID(booking_id))
    )
    token = f"tok-{booking_id[:8]}"
    booking.status = GiftStatus.PENDING
    booking.verify_token = token
    await db.commit()

    response = await client.put(
        f"/gifts/{booking_id}/confirm", params={"token": token}
    )
    assert response.status_code == 200, response.text


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


async def test_concurrent_booking_only_one_wins(
    client, db, make_record, wishlist_item
):
    """Гонка: два дарителя ПАРАЛЛЕЛЬНО бронируют один пункт вишлиста.

    Последовательный случай ловит Python-проверка `if item.gift_booking`
    (см. test_double_booking_is_rejected). Параллельный она пропускает: оба
    запроса успевают прочитать «брони ещё нет» до любого commit'а. Единственный
    барьер тогда — UNIQUE-индекс ix_gift_bookings_wishlist_item_id: у второго
    commit падает с IntegrityError, и эндпоинт отдаёт 409. Именно ради этого
    индекса и заведена baseline-миграция 20260820_wishlist_gift_baseline —
    раньше он держался только на давно отключённом create_all и ничем не был
    гарантирован.

    У дарителей разные email — чтобы отсечь помеху per-email rate-limit и
    оставить в игре ровно защиту от двойной брони.
    """
    record = await make_record()
    item = await wishlist_item(record)

    async def attempt(email: str):
        return await client.post(
            "/gifts/book",
            json={
                "wishlist_item_id": str(item.id),
                "gifter_name": email,
                "gifter_email": email,
            },
        )

    first, second = await asyncio.gather(
        attempt("racer-a@example.com"),
        attempt("racer-b@example.com"),
    )

    statuses = [first.status_code, second.status_code]
    # Ровно один 201; проигравший — 409 (гонка на commit'е) либо 400 (его SELECT
    # успел уже после чужого commit'а). И то и другое — корректный отказ.
    assert statuses.count(201) == 1, (statuses, first.text, second.text)
    loser = second if first.status_code == 201 else first
    assert loser.status_code in (400, 409), loser.text

    # В базе — ровно одна бронь на этот пункт: проигравший откатился, дубля нет.
    count = await db.scalar(
        select(func.count(GiftBooking.id)).where(
            GiftBooking.wishlist_item_id == item.id
        )
    )
    assert count == 1
    survivor = await db.scalar(
        select(GiftBooking).where(GiftBooking.wishlist_item_id == item.id)
    )
    assert survivor.status in (GiftStatus.BOOKED, GiftStatus.PENDING)


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


async def test_given_list_survives_completion(
    client, db, collection_id, make_record, wishlist_item, owner, gifter, as_user
):
    """Вручённый подарок остаётся в «Я дарю» — раньше он оттуда пропадал.

    Список строился через пункт вишлиста, а при завершении связь обнуляется,
    поэтому фильтр wishlist_item_id IS NOT NULL выбрасывал ровно те подарки,
    которые дошли до адресата. Теперь релиз и получатель лежат на самой броне.
    """
    wished = await make_record(master="m1", year=2023)
    item = await wishlist_item(wished)
    booked = await book(client, item.id)
    # Анонимная бронь попадает в «Я дарю» по email только после подтверждения.
    await verify_email(client, db, booked["id"])

    # Пока бронь активна, даритель видит забронированную версию.
    as_user(gifter)
    active = await client.get("/gifts/me/given")
    assert active.status_code == 200, active.text
    assert [g["id"] for g in active.json()] == [booked["id"]]
    assert active.json()[0]["record"]["year"] == 2023

    # Отмечает получение владелец вишлиста, а не даритель.
    as_user(owner)
    gifted = await make_record(master="m1", year=2026)
    added = await add_to_collection(client, collection_id, gifted)
    await client.put(
        f"/gifts/me/received/{added['gift_match']['booking_id']}/complete-with-record",
        params={"collection_item_id": added["id"]},
    )

    as_user(gifter)
    given = await client.get("/gifts/me/given")
    assert given.status_code == 200, given.text
    rows = given.json()
    assert len(rows) == 1, "вручённый подарок не должен исчезать из списка"
    assert rows[0]["status"] == "completed"
    assert rows[0]["completed_at"] is not None
    # Показываем подаренную версию, а не ту, что лежала в вишлисте.
    assert rows[0]["record"]["year"] == 2026
    assert rows[0]["for_user"]["username"] == owner.username

    booking = await db.scalar(select(GiftBooking))
    assert booking.record_id == gifted.id


async def test_manual_completion_also_keeps_the_record(
    client, db, make_record, wishlist_item, gifter, as_user
):
    """Тот же результат для обычного «отметить полученным», без скана."""
    record = await make_record()
    item = await wishlist_item(record)
    booked = await book(client, item.id)
    await verify_email(client, db, booked["id"])

    done = await client.put(f"/gifts/me/received/{booked['id']}/complete")
    assert done.status_code == 200, done.text

    as_user(gifter)
    rows = (await client.get("/gifts/me/given")).json()
    assert len(rows) == 1
    assert rows[0]["status"] == "completed"
    assert rows[0]["record"]["id"] == str(record.id)


async def test_spoofed_email_does_not_leak_booking_to_victim(
    client, make_record, wishlist_item, gifter, as_user
):
    """Спуф чужого email в форме брони не подсовывает жертве фантомный подарок.

    Атакующий бронирует анонимно, указав gifter_email жертвы. Раньше «Я дарю»
    матчил по одной строке email — жертва видела чужую бронь целиком: личность
    получателя и cancel_token (могла отменить бронь, а спуфер — засорять её
    раздел). Непроверенный email-матч теперь скрыт полностью.
    """
    record = await make_record()
    # book() шлёт gifter_email=gifter@example.com — это email «жертвы» gifter,
    # владение которым никто не подтверждал.
    await book(client, (await wishlist_item(record)).id)

    as_user(gifter)
    response = await client.get("/gifts/me/given")
    assert response.status_code == 200, response.text
    assert response.json() == [], "непроверенный email-матч не должен отдаваться"


async def test_confirmed_email_booking_appears_in_given(
    client, db, make_record, wishlist_item, owner, gifter, as_user
):
    """Цель email-ветки жива: подтверждённая анонимная бронь видна целиком."""
    record = await make_record()
    booked = await book(client, (await wishlist_item(record)).id)
    await verify_email(client, db, booked["id"])

    as_user(gifter)
    rows = (await client.get("/gifts/me/given")).json()
    assert [g["id"] for g in rows] == [booked["id"]]
    assert rows[0]["cancel_token"] == booked["cancel_token"]
    assert rows[0]["for_user"]["username"] == owner.username


async def test_authenticated_booking_shows_fully_without_email_match(
    client, make_record, wishlist_item, owner, gifter, as_user
):
    """Своя бронь (booked_by_user_id) показывается полностью без email-ветки.

    Даритель залогинен и указал в форме сторонний адрес — бронь всё равно
    привязана к аккаунту и видна в «Я дарю» с cancel_token и получателем.
    """
    from app.api.auth import get_current_user_optional
    from app.main import app

    record = await make_record()
    item = await wishlist_item(record)

    app.dependency_overrides[get_current_user_optional] = lambda: gifter
    response = await client.post(
        "/gifts/book",
        json={
            "wishlist_item_id": str(item.id),
            "gifter_name": "Даритель",
            "gifter_email": "other-address@example.com",
        },
    )
    assert response.status_code == 201, response.text
    booked = response.json()

    as_user(gifter)
    rows = (await client.get("/gifts/me/given")).json()
    assert [g["id"] for g in rows] == [booked["id"]]
    assert rows[0]["cancel_token"] == booked["cancel_token"]
    assert rows[0]["for_user"]["username"] == owner.username
