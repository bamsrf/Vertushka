"""Динамика цены обязана брать привязку из store_listings, а не из денорма.

Что здесь ловится. `listing_price_history.record_id` заполняется в
`_upsert_listing` значением `matched_record_id` НА МОМЕНТ снятия снапшота.
Матчинг листингов — отдельная часовая задача (`hourly_match_unmatched`), и
`listing_matcher` историю не досыпает: в нём нет ни одного обращения к
ListingPriceHistory. Значит всё, что снято до матча, лежит с record_id=NULL.

Пока эндпоинт фильтровал по денорму, эти строки выпадали из выборки. На
«Song Machine Season One» это дало «минимум за 3 мес — 4 990 ₽» при цене
3 352 ₽, которая держалась третьи сутки, и «цена менялась слишком редко»
там, где точек хватало с запасом.

Живой БД у тестов нет — перехватываем сам statement и смотрим на скомпи-
лированный SQL: джойн есть, фильтр по денорму отсутствует.
"""
from datetime import datetime
from uuid import uuid4

import pytest
from sqlalchemy.dialects import postgresql

from app.api.records import get_record_price_history


class _FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


class CapturingSession:
    """Стаб AsyncSession, запоминающий выполненный statement."""

    def __init__(self, rows=()):
        self.statements = []
        self._rows = list(rows)

    async def execute(self, statement, *_args, **_kwargs):
        self.statements.append(statement)
        return _FakeResult(self._rows)


def _sql(session) -> str:
    assert session.statements, "эндпоинт не выполнил ни одного запроса"
    compiled = session.statements[0].compile(
        dialect=postgresql.dialect(),
        compile_kwargs={"literal_binds": False},
    )
    return str(compiled)


@pytest.mark.asyncio
async def test_price_history_joins_store_listings_for_current_match():
    db = CapturingSession()
    await get_record_price_history(record_id=uuid4(), days=90, db=db)
    sql = _sql(db)

    assert "store_listings" in sql, "привязка должна браться джойном"
    assert "matched_record_id" in sql, "источник истины — текущий матч листинга"


@pytest.mark.asyncio
async def test_price_history_does_not_filter_by_denormalized_record_id():
    """Регрессия: возврат к денорму снова спрячет до-матчевые снапшоты."""
    db = CapturingSession()
    await get_record_price_history(record_id=uuid4(), days=90, db=db)
    sql = _sql(db)

    assert "listing_price_history.record_id" not in sql, (
        "денорм заполняется на момент снапшота и отстаёт от матча — "
        "фильтровать по нему значит терять историю"
    )


@pytest.mark.asyncio
async def test_price_history_keeps_in_stock_and_window_filters():
    """Джойн не должен был растерять прежние условия выборки."""
    db = CapturingSession()
    await get_record_price_history(record_id=uuid4(), days=30, db=db)
    sql = _sql(db)

    assert "status" in sql, "берём только in_stock"
    assert "captured_at" in sql, "окно по времени на месте"
    assert "price_rub IS NOT NULL" in sql


@pytest.mark.asyncio
async def test_price_history_shapes_points_and_low():
    """Форма ответа: точки по дням + минимум по ним же."""
    rows = [
        (datetime(2026, 8, 24), 7590, 2),
        (datetime(2026, 8, 25), 3352, 3),
        (datetime(2026, 8, 26), 3352, 3),
    ]
    db = CapturingSession(rows)
    out = await get_record_price_history(record_id=uuid4(), days=90, db=db)

    assert [p["date"] for p in out["points"]] == ["2026-08-24", "2026-08-25", "2026-08-26"]
    assert out["points"][0]["min_price_rub"] == 7590.0
    assert out["points"][0]["listings_count"] == 2
    # Минимум считается по тем же точкам — на «Song Machine» он обязан стать
    # 3 352 ₽, а не 4 990 ₽ из невидимой половины истории.
    assert out["historical_low_rub"] == 3352.0
    assert out["days"] == 90
