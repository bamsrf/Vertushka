"""«Цена-огонь» (M4) — ачивка должна оставаться редкой.

Что здесь ловится. Раньше эвалюатор сравнивал цену магазина с
`record_value_rub` — стоимостью ВВОЗА, куда входят фиксированные ~$20
доставки, накладные и пошлина. Для дешёвой пластинки оценка раздувалась в
разы, любой российский листинг оказывался «дешевле», и ачивка редкого тира
падала вместе с «Первой вылазкой» на первом же переходе в магазин.

Живой БД у тестов нет: эвалюатор ходит в базу единственным `execute()` за
парами (цена листинга, запись) — его и подменяем стабом. Курс фиксируем,
чтобы арифметика была проверяемой.
"""
from decimal import Decimal

import pytest

from app.services.achievements.definitions.series import market as M


class _FakeResult:
    def __init__(self, pairs):
        self._pairs = pairs

    def all(self):
        return self._pairs


class FakeSession:
    """Минимальный стаб AsyncSession под `_evaluate_deal_finder`."""

    def __init__(self, pairs):
        self._pairs = pairs

    async def execute(self, *_args, **_kwargs):
        return _FakeResult(self._pairs)


class FakeRecord:
    def __init__(self, median=None, minimum=None, country="US"):
        self.estimated_price_median = median
        self.estimated_price_min = minimum
        self.country = country
        self.format_type = "Vinyl"
        self.format_description = 'LP, Album'
        self.discogs_data = None


USER = "11111111-1111-1111-1111-111111111111"
RATE = 90.0


@pytest.fixture(autouse=True)
def _fixed_rate(monkeypatch):
    async def _rate():
        return RATE

    monkeypatch.setattr("app.services.exchange.get_usd_rub_rate", _rate)


async def _evaluate(pairs):
    return await M._evaluate_deal_finder(FakeSession(pairs), USER, {}, set())


@pytest.mark.asyncio
async def test_no_clicks_keeps_locked():
    assert (await _evaluate([])).unlocked is False


@pytest.mark.asyncio
async def test_cheap_import_no_longer_unlocks_on_first_click():
    """Главный регресс: $5-пластинка за 1 500 ₽.

    Рыночная оценка — 450 ₽, магазин просит 1 500 ₽, то есть ВТРОЕ дороже.
    По старой формуле «оценка ввоза» была ≈2 700 ₽ и ачивка открывалась.
    """
    record = FakeRecord(median=Decimal("5"))
    assert (await _evaluate([(Decimal("1500"), record)])).unlocked is False


@pytest.mark.asyncio
async def test_single_min_price_without_median_is_not_an_estimate():
    """Ровно случай из отчёта: у релиза одна цена и никакой истории продаж."""
    record = FakeRecord(median=None, minimum=Decimal("100"))
    assert (await _evaluate([(Decimal("100"), record)])).unlocked is False


@pytest.mark.asyncio
async def test_marginally_cheaper_is_not_a_find():
    """Дешевле на процент — не находка: 8 900 ₽ против оценки 9 000 ₽."""
    record = FakeRecord(median=Decimal("100"))  # 9 000 ₽
    assert (await _evaluate([(Decimal("8900"), record)])).unlocked is False


@pytest.mark.asyncio
async def test_real_deal_unlocks():
    """Оценка 9 000 ₽, магазин просит 6 000 ₽ — вот это находка."""
    record = FakeRecord(median=Decimal("100"))
    assert (await _evaluate([(Decimal("6000"), record)])).unlocked is True


@pytest.mark.asyncio
async def test_exact_threshold_unlocks():
    """Ровно 80% оценки — граница включительно."""
    record = FakeRecord(median=Decimal("100"))  # 9 000 ₽ → порог 7 200 ₽
    assert (await _evaluate([(Decimal("7200"), record)])).unlocked is True


@pytest.mark.asyncio
async def test_any_one_of_many_clicks_counts():
    """Достаточно одной находки среди всех переходов пользователя."""
    pairs = [
        (Decimal("1500"), FakeRecord(median=Decimal("5"))),
        (Decimal("100"), FakeRecord(median=None, minimum=Decimal("100"))),
        (Decimal("6000"), FakeRecord(median=Decimal("100"))),
    ]
    assert (await _evaluate(pairs)).unlocked is True


@pytest.mark.asyncio
async def test_broken_rate_does_not_unlock():
    """Курс не получен — сравнивать не с чем, молча остаёмся закрытыми."""

    async def _zero():
        return 0.0

    import app.services.exchange as exchange

    original = exchange.get_usd_rub_rate
    exchange.get_usd_rub_rate = _zero
    try:
        record = FakeRecord(median=Decimal("100"))
        assert (await _evaluate([(Decimal("1"), record)])).unlocked is False
    finally:
        exchange.get_usd_rub_rate = original
