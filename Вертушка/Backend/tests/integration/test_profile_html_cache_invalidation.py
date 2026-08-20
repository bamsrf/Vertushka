"""Инвалидация кэша HTML публичного профиля при смене состояния брони.

Страница /@{username} кэшируется в Redis целиком (web_profile_html, TTL 120с),
и бейдж «Забронировано» вшит прямо в HTML. До фикса ни бронь, ни отмена, ни
авто-таски кэш не сбрасывали: гость до двух минут видел устаревшее
«свободно/занято» и кликал по пункту, который уже занят.

В обычном прогоне Redis недоступен и кэш — noop, поэтому здесь он подменяется
in-memory фейком: так проверяется не только «страница в итоге правильная»,
но и что ключ реально ЛЕЖАЛ в кэше и был выбит инвалидацией, а не дожил бы
до TTL.
"""
import time
from datetime import datetime, timedelta

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.models.gift_booking import GiftBooking, GiftStatus
from app.models.profile_share import ProfileShare
from app.services import cache as cache_module
from app.services.profile_cache import PROFILE_HTML_NS

pytestmark = pytest.mark.asyncio

# Слово «Забронировано» есть и в статичной справке модалки, поэтому маркер —
# полная разметка бейджа на карточке пункта: она рендерится только когда
# item.gift_booking is not none (public_profile.html, сетка вишлиста).
BOOKED_BADGE = '<span class="reserved-badge"><span class="reserved-dot"></span>Забронировано</span>'


class FakeCache:
    """In-memory замена RedisCache: ровно те методы, что зовёт страница."""

    def __init__(self):
        self.store = {}

    async def get(self, namespace, key):
        return self.store.get((namespace, key))

    async def set(self, namespace, key, value, ttl):
        self.store[(namespace, key)] = value

    async def delete(self, namespace, key):
        self.store.pop((namespace, key), None)

    async def incr(self, namespace, key, ttl):
        # None = «Redis недоступен» для счётчика просмотров — страница
        # уходит в прямую запись в БД, что для теста и нужно.
        return None


@pytest.fixture
def fake_cache(monkeypatch):
    """Подменяет методы singleton-кэша: web/routes и profile_cache держат
    ссылку на один и тот же объект, поэтому патчим его атрибуты."""
    fake = FakeCache()
    for name in ("get", "set", "delete", "incr"):
        monkeypatch.setattr(cache_module.cache, name, getattr(fake, name))
    # Курс ЦБ не должен ходить в сеть из теста.
    import app.services.exchange as exchange
    monkeypatch.setattr(exchange, "_cached_rate", 90.0)
    monkeypatch.setattr(exchange, "_cached_at", time.time())
    return fake


@pytest_asyncio.fixture
async def public_owner(db, owner):
    """Владелец с активированным публичным профилем."""
    db.add(ProfileShare(user_id=owner.id))
    await db.commit()
    return owner


@pytest_asyncio.fixture
async def web_client():
    """Клиент для web-маршрутов (они висят на корне, а не на /api)."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


def _wishlist_key(username: str) -> tuple:
    return (PROFILE_HTML_NS, f"{username}:wishlist")


async def _get_wishlist_page(web_client, username: str) -> str:
    response = await web_client.get(f"/@{username}", params={"tab": "wishlist"})
    assert response.status_code == 200, response.text
    return response.text


async def test_booking_shows_up_without_waiting_for_ttl(
    fake_cache, client, web_client, public_owner, make_record, wishlist_item
):
    """Бронь → страница отдаёт «Забронировано» сразу, из свежего рендера."""
    record = await make_record()
    item = await wishlist_item(record)

    # Прогреваем кэш: пункт свободен, HTML лёг в кэш.
    html = await _get_wishlist_page(web_client, public_owner.username)
    assert BOOKED_BADGE not in html
    assert _wishlist_key(public_owner.username) in fake_cache.store

    response = await client.post(
        "/gifts/book",
        json={
            "wishlist_item_id": str(item.id),
            "gifter_name": "Даритель",
            "gifter_email": "guest@example.com",
        },
    )
    assert response.status_code == 201, response.text

    # Ключ выбит бронью — страница не доживает свой TTL с устаревшим HTML.
    assert _wishlist_key(public_owner.username) not in fake_cache.store
    assert (PROFILE_HTML_NS, f"{public_owner.username}:collection") \
        not in fake_cache.store

    html = await _get_wishlist_page(web_client, public_owner.username)
    assert BOOKED_BADGE in html


async def test_cancel_frees_the_item_immediately(
    fake_cache, client, web_client, public_owner, make_record, wishlist_item
):
    """Отмена дарителем: бейдж пропадает без ожидания TTL."""
    record = await make_record()
    item = await wishlist_item(record)

    booked = await client.post(
        "/gifts/book",
        json={
            "wishlist_item_id": str(item.id),
            "gifter_name": "Даритель",
            "gifter_email": "guest@example.com",
        },
    )
    assert booked.status_code == 201, booked.text
    payload = booked.json()

    # Кэш прогрет состоянием «занято».
    html = await _get_wishlist_page(web_client, public_owner.username)
    assert BOOKED_BADGE in html
    assert _wishlist_key(public_owner.username) in fake_cache.store

    response = await client.put(
        f"/gifts/{payload['id']}/cancel",
        params={"cancel_token": payload["cancel_token"]},
    )
    assert response.status_code == 200, response.text

    assert _wishlist_key(public_owner.username) not in fake_cache.store
    html = await _get_wishlist_page(web_client, public_owner.username)
    assert BOOKED_BADGE not in html


async def test_owner_removing_item_evicts_cache(
    fake_cache, client, web_client, public_owner, make_record, wishlist_item
):
    """Удаление пункта владельцем сбрасывает кэш (даже с активной бронью)."""
    record = await make_record()
    item = await wishlist_item(record)

    booked = await client.post(
        "/gifts/book",
        json={
            "wishlist_item_id": str(item.id),
            "gifter_name": "Даритель",
            "gifter_email": "guest@example.com",
        },
    )
    assert booked.status_code == 201, booked.text

    html = await _get_wishlist_page(web_client, public_owner.username)
    assert BOOKED_BADGE in html

    response = await client.delete(f"/wishlists/records/{item.id}")
    assert response.status_code == 204, response.text

    assert _wishlist_key(public_owner.username) not in fake_cache.store
    html = await _get_wishlist_page(web_client, public_owner.username)
    assert BOOKED_BADGE not in html


async def test_auto_release_evicts_cache(
    fake_cache, db, web_client, public_owner, make_record, wishlist_item
):
    """Истёкшая бронь: фоновая таска освобождает пункт и выбивает кэш."""
    from app.tasks.booking_tasks import auto_release_expired_bookings

    record = await make_record()
    item = await wishlist_item(record)

    db.add(GiftBooking(
        wishlist_item_id=item.id,
        recipient_user_id=public_owner.id,
        record_id=record.id,
        gifter_name="Даритель",
        gifter_email="guest@example.com",
        status=GiftStatus.BOOKED,
        cancel_token="t" * 24,
        expires_at=datetime.utcnow() - timedelta(hours=1),
    ))
    await db.commit()

    html = await _get_wishlist_page(web_client, public_owner.username)
    assert BOOKED_BADGE in html
    assert _wishlist_key(public_owner.username) in fake_cache.store

    await auto_release_expired_bookings()

    assert _wishlist_key(public_owner.username) not in fake_cache.store
    html = await _get_wishlist_page(web_client, public_owner.username)
    assert BOOKED_BADGE not in html
