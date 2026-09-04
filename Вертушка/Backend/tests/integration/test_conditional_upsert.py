"""WS7 2.1 — условный upsert листингов (живой Postgres, make test-db-up).

До фикса ON CONFLICT DO UPDATE безусловно переписывал все ~66k строк за
обход (и второй раз днём): WAL, автовакуум, а окна уведомлений и
инвалидации по updated_at «вбирали весь маркет». Теперь:

- содержимое не изменилось и last_seen_at свежий → строка НЕ переписывается
  (RETURNING пуст, обход считает skipped);
- содержимое изменилось → полноценный апдейт, updated_at бампается,
  история цен пишется как раньше;
- содержимое то же, но last_seen_at старше 20 ч → «суточный пульс»: бампается
  только last_seen_at (для retire), updated_at НЕ трогается, истории нет.
"""
import uuid
from datetime import datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import func, select, update

from app.models.listing_price_history import ListingPriceHistory
from app.models.store import Store
from app.models.store_listing import StoreListing
from app.services.scrapers.base import ListingDTO
from app.services.scrapers.runner import _upsert_listing

pytestmark = pytest.mark.asyncio


@pytest.fixture
def store(db):
    async def _make() -> Store:
        slug = f"shop{uuid.uuid4().hex[:8]}"
        s = Store(
            slug=slug, name=slug, domain=f"{slug}.example.com",
            base_url=f"https://{slug}.example.com", parser_class="TestParser",
        )
        db.add(s)
        await db.commit()
        await db.refresh(s)
        return s

    return _make


def _dto(ext: str, *, price: str = "3990", status: str = "in_stock") -> ListingDTO:
    return ListingDTO(
        external_id=ext,
        url=f"https://x.example.com/{ext}/",
        title_raw="Abbey Road",
        artist_raw="The Beatles",
        year_raw=1969,
        price_rub=Decimal(price),
        status=status,
    )


async def _row(db, store_id, ext):
    """Голые колонки (не ORM-объект) — чтобы не ловить lazy-load после commit."""
    return (await db.execute(
        select(
            StoreListing.id, StoreListing.price_rub, StoreListing.status,
            StoreListing.updated_at, StoreListing.last_seen_at,
        ).where(
            StoreListing.store_id == store_id, StoreListing.external_id == ext
        )
    )).one()


async def _history_count(db, listing_id) -> int:
    return await db.scalar(
        select(func.count()).select_from(ListingPriceHistory)
        .where(ListingPriceHistory.listing_id == listing_id)
    )


async def test_unchanged_listing_is_skipped(db, store):
    s = await store()
    ext = uuid.uuid4().hex[:10]
    assert await _upsert_listing(db, s.id, _dto(ext)) is True
    await db.commit()
    before = await _row(db, s.id, ext)
    updated_at_before = before.updated_at
    hist_before = await _history_count(db, before.id)

    # Тот же DTO сразу же — строка не должна переписываться
    assert await _upsert_listing(db, s.id, _dto(ext)) is False
    await db.commit()
    after = await _row(db, s.id, ext)
    assert after.updated_at == updated_at_before
    assert await _history_count(db, after.id) == hist_before


async def test_price_change_updates_and_writes_history(db, store):
    s = await store()
    ext = uuid.uuid4().hex[:10]
    await _upsert_listing(db, s.id, _dto(ext, price="3990"))
    await db.commit()
    before = await _row(db, s.id, ext)
    updated_at_before = before.updated_at

    assert await _upsert_listing(db, s.id, _dto(ext, price="4490")) is True
    await db.commit()
    after = await _row(db, s.id, ext)
    assert after.price_rub == Decimal("4490")
    assert after.updated_at > updated_at_before
    # Первая смена цены дописывает точку со старой ценой (backfill) + новую
    prices = {
        h.price_rub for h in (await db.execute(
            select(ListingPriceHistory).where(ListingPriceHistory.listing_id == after.id)
        )).scalars().all()
    }
    assert Decimal("3990") in prices and Decimal("4490") in prices


async def test_stale_seen_gets_pulse_without_updated_at(db, store):
    s = await store()
    ext = uuid.uuid4().hex[:10]
    await _upsert_listing(db, s.id, _dto(ext))
    await db.commit()
    lid = (await _row(db, s.id, ext)).id

    # Состариваем отметку наблюдения за порог пульса (20 ч). У колонки
    # updated_at есть onupdate=utcnow, поэтому эта ручная правка сама бампнет
    # updated_at — снимаем эталон ПОСЛЕ неё, чтобы мерить эффект самого пульса.
    old = datetime.utcnow() - timedelta(hours=26)
    await db.execute(
        update(StoreListing).where(StoreListing.id == lid).values(last_seen_at=old)
    )
    await db.commit()
    baseline = await _row(db, s.id, ext)
    updated_at_before = baseline.updated_at
    hist_before = await _history_count(db, lid)

    # Содержимое то же → пульс: last_seen_at бампнут, updated_at нетронут
    assert await _upsert_listing(db, s.id, _dto(ext)) is True
    await db.commit()
    after = await _row(db, s.id, ext)
    assert after.last_seen_at > old + timedelta(hours=1)
    assert after.updated_at == updated_at_before
    assert await _history_count(db, lid) == hist_before


async def test_status_change_updates(db, store):
    s = await store()
    ext = uuid.uuid4().hex[:10]
    await _upsert_listing(db, s.id, _dto(ext, status="in_stock"))
    await db.commit()

    assert await _upsert_listing(db, s.id, _dto(ext, status="out_of_stock")) is True
    await db.commit()
    after = await _row(db, s.id, ext)
    assert after.status == "out_of_stock"
