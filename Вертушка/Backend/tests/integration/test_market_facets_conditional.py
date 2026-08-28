"""Счётчики чипов Маркета считаются с учётом уже выбранного.

Жалоба звучала как «жанр + цветной винил выдаёт около 12 штук, не более» —
похоже на потолок выдачи. Потолка нет: бэкенд отдаёт до 100 за страницу, Mobile
листает по 30. Врали чипы. Цвет винила парсят фактически два маленьких магазина
из девяти, весь «цветной» пул — около 800 карточек, и на пересечении с регги
честно остаётся 14. А чип обещал «Регги 342» и «Цветной винил 832».

Тесты фиксируют правило «фасет не видит собственное измерение» и стабильность
порядка чипов — иначе они переставлялись бы под пальцем на каждый тап.
"""
import uuid
from datetime import datetime

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.database import async_session_maker
from app.main import app
from app.models.record import Record
from app.models.store import Store
from app.models.store_listing import StoreListing

pytestmark = pytest.mark.asyncio


async def _seed(store_id, *, genre: str, color: str | None, fmt: str = "LP",
                record_fmt: str = "Vinyl, LP") -> None:
    async with async_session_maker() as db:
        rec = Record(
            title=f"T{uuid.uuid4().hex[:6]}", artist="A", source="discogs",
            discogs_id=str(uuid.uuid4().int)[:9], genre=genre,
            format_type=record_fmt, cover_image_url="http://x/c.jpg",
        )
        db.add(rec)
        await db.flush()
        db.add(StoreListing(
            store_id=store_id, external_id=uuid.uuid4().hex, url="http://x",
            title_raw="T", format_raw=fmt, status="in_stock", price_rub=1000,
            vinyl_color_raw=color, matched_record_id=rec.id, match_method="fuzzy",
            matched_at=datetime.utcnow(), last_seen_at=datetime.utcnow(),
            first_seen_at=datetime.utcnow(),
        ))
        await db.commit()


@pytest_asyncio.fixture
async def market():
    """Склад: 3 рока (1 цветной), 2 регги (1 цветной), 1 джаз (чёрный)."""
    async with async_session_maker() as db:
        suffix = uuid.uuid4().hex[:8]
        st = Store(name="S", slug=f"s-{suffix}", domain=f"{suffix}.example",
                   base_url=f"https://{suffix}.example", parser_class="P", is_active=True)
        db.add(st)
        await db.commit()
        store_id = st.id

    await _seed(store_id, genre="Rock", color="Orange")
    await _seed(store_id, genre="Rock", color=None)
    await _seed(store_id, genre="Rock", color="Black")
    await _seed(store_id, genre="Reggae", color="Green")
    await _seed(store_id, genre="Reggae", color=None)
    await _seed(store_id, genre="Jazz", color="Black")
    return store_id


async def _facets(**params):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/market/facets", params=params)
    assert resp.status_code == 200, resp.text
    data = resp.json()
    return (
        {g["key"]: g["count"] for g in data["genres"]},
        {f["key"]: f["count"] for f in data["features"]},
        [g["key"] for g in data["genres"]],
    )


async def test_unfiltered_counts_are_totals(market):
    genres, features, _order = await _facets()

    assert genres == {"rock": 3, "reggae": 2, "jazz": 1}
    assert features["colored"] == 2  # оранжевый рок + зелёное регги


async def test_genre_counts_respect_active_feature(market):
    """С включённым «Цветным» жанры показывают пересечение, а не свой объём."""
    genres, _features, _order = await _facets(colored="true")

    assert genres == {"rock": 1, "reggae": 1}  # джаз только чёрный — чипа нет


async def test_feature_counts_respect_active_genre(market):
    """И симметрично: с выбранным регги «Цветной» показывает 1, а не 2."""
    _genres, features, _order = await _facets(genre="reggae")

    assert features["colored"] == 1


async def test_facet_does_not_filter_itself(market):
    """Жанровый чип не сужается собственным измерением.

    Иначе с выбранным регги все остальные жанры показали бы ноль и исчезли —
    добавить второй жанр в мультивыборе стало бы невозможно.
    """
    genres, _features, _order = await _facets(genre="reggae")

    assert genres == {"rock": 3, "reggae": 2, "jazz": 1}


async def test_chip_order_does_not_move_when_filters_change(market):
    """Порядок — по объёму склада, не по текущему числу.

    Рок остаётся первым даже когда с «Цветным» у него 1, а у регги тоже 1:
    иначе ряд перестраивался бы прямо под пальцем.
    """
    _g1, _f1, order_plain = await _facets()
    _g2, _f2, order_colored = await _facets(colored="true")

    assert order_plain[:2] == ["rock", "reggae"]
    assert order_colored == ["rock", "reggae"]


async def test_zero_intersection_chips_disappear(market):
    """Чип, который с текущим выбором даст пустой экран, не показываем."""
    genres, _features, _order = await _facets(colored="true")

    assert "jazz" not in genres
