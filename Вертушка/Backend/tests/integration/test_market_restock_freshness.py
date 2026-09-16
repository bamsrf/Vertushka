"""Перезавоз читается витриной как «появилось», а не как позиция от онбординга.

«Новинки» и сортировка «сначала свежие» считались по first_seen_at — дате
ПЕРВОГО показа листинга. Магазин со стабильным ассортиментом перезавозит те же
наименования под тем же external_id: новой строки не появляется, first_seen
остаётся датой онбординга, и позиция не попадает в новинки никогда. Замер
15.09 на проде: у Коробки Винила самый свежий видимый листинг — 23 мая, при
живом перезавозе ~700 позиций.

Гоняем живой Postgres: вся логика — это выражение GREATEST в SQL, и ломается
оно молча (выдача остаётся правдоподобной, просто в неверном порядке).
"""
import uuid
from datetime import datetime, timedelta

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.database import async_session_maker
from app.main import app
from app.models.record import Record
from app.models.store import Store
from app.models.store_listing import StoreListing

pytestmark = pytest.mark.asyncio

NOW = datetime.utcnow()
LONG_AGO = NOW - timedelta(days=120)  # «онбординг магазина»
RECENTLY = NOW - timedelta(days=2)


async def _store() -> tuple[uuid.UUID, str]:
    async with async_session_maker() as db:
        suffix = uuid.uuid4().hex[:8]
        st = Store(
            name=f"shop-{suffix}", slug=f"shop-{suffix}",
            domain=f"{suffix}.example", base_url=f"https://{suffix}.example",
            parser_class="P", is_active=True,
        )
        db.add(st)
        await db.commit()
        return st.id, st.slug


async def _record(title: str) -> uuid.UUID:
    async with async_session_maker() as db:
        rec = Record(
            title=title, artist="Bonobo", source="discogs",
            discogs_id=str(uuid.uuid4().int)[:9],
            # master=None → дедуп-ключ это r.id, каждая запись своя группа.
            discogs_master_id=None,
            format_type="Vinyl", format_description="LP, Album",
            cover_image_url="http://x/c.jpg",
            year=datetime.utcnow().year,  # чтобы проходить чип «Новинки»
        )
        db.add(rec)
        await db.commit()
        return rec.id


async def _listing(
    store_id: uuid.UUID,
    record_id: uuid.UUID,
    *,
    price: int,
    first_seen: datetime,
    restocked: datetime | None = None,
) -> None:
    async with async_session_maker() as db:
        db.add(StoreListing(
            store_id=store_id, external_id=uuid.uuid4().hex, url="http://x",
            title_raw="T", format_raw="LP", status="in_stock", price_rub=price,
            matched_record_id=record_id, match_method="fuzzy", matched_at=NOW,
            # last_seen_at свежий: обход магазин видит, витрина его не отсеивает.
            last_seen_at=NOW, first_seen_at=first_seen, restocked_at=restocked,
        ))
        await db.commit()


@pytest_asyncio.fixture
async def shelf():
    """Две позиции одного магазина:

    `restocked` — заведена при онбординге 120 дней назад, вернулась в наличие
    два дня назад. `plain` — заведена вчера, никуда не уходила. По честной
    свежести «вчерашняя» новее, но перезавоз обязан стоять рядом с ней, а не
    в хвосте витрины вместе с майским старьём.
    """
    store_id, slug = await _store()
    restocked = await _record("Black Sands")
    plain = await _record("Migration")
    stale = await _record("Dial M For Monkey")

    await _listing(store_id, restocked, price=4990,
                   first_seen=LONG_AGO, restocked=RECENTLY)
    await _listing(store_id, plain, price=5990,
                   first_seen=NOW - timedelta(days=1))
    await _listing(store_id, stale, price=3990, first_seen=LONG_AGO)
    return {
        "slug": slug,
        "restocked": str(restocked),
        "plain": str(plain),
        "stale": str(stale),
    }


async def _get(path: str, **params) -> list[dict]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.get(path, params=params)
    assert res.status_code == 200, res.text
    return res.json()


async def test_store_carousel_puts_restock_above_old_listing(shelf):
    items = await _get(
        f"/api/market/stores/{shelf['slug']}/listings", sort="newest", limit=10
    )
    order = [it["record_id"] for it in items]
    assert shelf["restocked"] in order and shelf["stale"] in order
    assert order.index(shelf["restocked"]) < order.index(shelf["stale"])
    # Вчерашняя позиция всё равно свежее двухдневного перезавоза — свежесть
    # это дата, а не приоритет «перезавоз всегда наверх».
    assert order.index(shelf["plain"]) < order.index(shelf["restocked"])


async def test_store_grid_orders_by_freshness(shelf):
    items = await _get(
        f"/api/market/stores/{shelf['slug']}/all", sort="newest", limit=50
    )
    order = [it["record_id"] for it in items]
    assert order.index(shelf["restocked"]) < order.index(shelf["stale"])


async def test_first_seen_at_still_reports_first_sighting(shelf):
    """Порядок считаем по свежести, но поле наружу не переопределяем: оно
    означает «впервые увидели в продаже», и на нём висит смысл в схеме."""
    items = await _get(
        f"/api/market/stores/{shelf['slug']}/listings", sort="newest", limit=10
    )
    by_id = {it["record_id"]: it for it in items}
    first_seen = datetime.fromisoformat(
        by_id[shelf["restocked"]]["first_seen_at"].replace("Z", "")
    )
    assert first_seen < NOW - timedelta(days=100)


async def test_new_chip_includes_restocked_position(shelf):
    """Чип «Новинки» (свежесть ≤ 30 дней + свежий релиз) обязан видеть
    перезавоз — иначе магазин с постоянным ассортиментом в нём пуст всегда."""
    items = await _get("/api/market/search", new=True, limit=100, sort="newest")
    ids = {it["record_id"] for it in items}
    assert shelf["restocked"] in ids
    assert shelf["stale"] not in ids
