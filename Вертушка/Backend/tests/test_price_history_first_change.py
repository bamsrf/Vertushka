"""Первая смена цены не должна стирать память о прежней.

`listing_price_history` — журнал ПЕРЕХОДОВ, но читают её как полный ряд цен:
минимум за 90 дней считается именно по ней. Листинг, который месяцами стоял с
одной ценой, до первого изменения не имел в таблице ни одной точки — и когда
цена наконец менялась, единственной записью оказывалась НОВАЯ цена. Минимум
становился равен свежему максимуму.

Живой случай: Arctic Monkeys «AM» в «Коробке Винила». Листинг заведён 17.05,
держал 3 990 ₽ (радар трижды писал `match` по этой цене), 27.08 подорожал до
4 490 ₽ — и «минимум за 3 мес» стал 4 490 ₽.

Живой БД у тестов нет — подменяем сессию и смотрим, что именно ушло в db.add.
"""
from datetime import datetime, timedelta
from uuid import uuid4

import pytest

from app.models.listing_price_history import ListingPriceHistory
from app.services.scrapers.runner import _upsert_listing
from app.services.scrapers.base import ListingDTO


class _Row:
    def __init__(self, **kw):
        self.__dict__.update(kw)


class _Result:
    def __init__(self, row):
        self._row = row

    def one(self):
        return self._row


class _FakeDB:
    """Сессия-заглушка: отдаёт заранее заданную строку и копит db.add."""

    def __init__(self, row, has_history: bool):
        self._row = row
        self._has_history = has_history
        self.added: list = []

    async def execute(self, *a, **kw):
        return _Result(self._row)

    async def scalar(self, *a, **kw):
        return uuid4() if self._has_history else None

    def add(self, obj):
        self.added.append(obj)


def _dto(price):
    return ListingDTO(
        external_id="ext-1",
        url="https://example.test/x",
        title_raw="AM",
        price_rub=price,
        status="in_stock",
    )


def _row(old_price, new_price, old_seen):
    return _Row(
        id=uuid4(),
        matched_record_id=uuid4(),
        price_rub=new_price,
        status="in_stock",
        old_price=old_price,
        old_status="in_stock",
        old_seen=old_seen,
    )


@pytest.mark.asyncio
async def test_first_change_keeps_previous_price():
    """Истории не было → пишем и старую цену, и новую."""
    seen = datetime(2026, 8, 26, 12, 0, 0)
    db = _FakeDB(_row(3990, 4490, seen), has_history=False)

    await _upsert_listing(db, uuid4(), _dto(4490))

    prices = [h.price_rub for h in db.added if isinstance(h, ListingPriceHistory)]
    assert prices == [3990, 4490], prices
    # Старую цену датируем прошлым наблюдением — временем, когда её видели.
    old_row = next(h for h in db.added if h.price_rub == 3990)
    assert old_row.captured_at == seen


@pytest.mark.asyncio
async def test_change_with_existing_history_writes_only_new():
    """История уже есть — прошлое зафиксировано, дубль не нужен."""
    db = _FakeDB(_row(3990, 4490, datetime(2026, 8, 26)), has_history=True)

    await _upsert_listing(db, uuid4(), _dto(4490))

    prices = [h.price_rub for h in db.added if isinstance(h, ListingPriceHistory)]
    assert prices == [4490], prices


@pytest.mark.asyncio
async def test_brand_new_listing_writes_single_point():
    """Первый показ листинга: старой цены не существует, дописывать нечего."""
    row = _row(None, 4490, None)
    row.old_status = None
    db = _FakeDB(row, has_history=False)

    await _upsert_listing(db, uuid4(), _dto(4490))

    prices = [h.price_rub for h in db.added if isinstance(h, ListingPriceHistory)]
    assert prices == [4490], prices
