"""База радара «дешевле обычного» считает дни, когда пластинка продавалась.

Журнал listing_price_history пишет точку только при СМЕНЕ цены или статуса.
Раньше база бралась лишь по дням, в которые была точка, — то есть по дням
изменений. У пластинки, которая месяц стоит 4 990 и не двигается, такой день
один, «меньше пяти дней» → базы нет → относительный порог молча падал на
абсолютный, а у кого рубли не заданы — на «слать всегда». Замер 19.09 по
проду: база была у 32 пластинок из 320 в выборке по восьми магазинам.

Теперь цена — ступенька: точка держит цену до следующей точки листинга,
последняя — до его последнего наблюдения. Гоняем живой Postgres: вся логика —
окна, LEAD и generate_series в SQL.
"""
import uuid
from datetime import datetime, timedelta
from decimal import Decimal

import pytest

import app.services.radar_threshold as radar
from app.models.listing_price_history import ListingPriceHistory
from app.models.record import Record
from app.models.store import Store
from app.models.store_listing import StoreListing
from app.services.radar_threshold import baseline_prices, daily_min_prices

pytestmark = pytest.mark.asyncio

NOW = datetime.utcnow()


def _ago(days: float) -> datetime:
    return NOW - timedelta(days=days)


async def _record(db) -> uuid.UUID:
    rec = Record(
        title="Black Sands", artist="Bonobo", source="discogs",
        discogs_id=str(uuid.uuid4().int)[:9],
    )
    db.add(rec)
    await db.commit()
    return rec.id


async def _store(db) -> uuid.UUID:
    suffix = uuid.uuid4().hex[:8]
    st = Store(
        name=suffix, slug=f"s-{suffix}", domain=f"{suffix}.example",
        base_url=f"https://{suffix}.example", parser_class="P", is_active=True,
    )
    db.add(st)
    await db.commit()
    return st.id


async def _listing(
    db, store_id, record_id, *, price: int, status: str = "in_stock",
    first_seen: datetime, last_seen: datetime | None = None,
    points: list[tuple[datetime, int | None, str]] = (),
) -> uuid.UUID:
    """Листинг плюс его журнал: points = [(когда, цена, статус), ...]."""
    li = StoreListing(
        store_id=store_id, external_id=uuid.uuid4().hex, url="http://x",
        title_raw="T", status=status, price_rub=Decimal(price),
        matched_record_id=record_id, first_seen_at=first_seen,
        last_seen_at=last_seen or NOW,
    )
    db.add(li)
    await db.flush()
    for when, p, st in points:
        db.add(ListingPriceHistory(
            listing_id=li.id, record_id=None,  # денорм пуст: привязка — джойном
            price_rub=Decimal(p) if p is not None else None,
            status=st, captured_at=when,
        ))
    await db.commit()
    return li.id


async def test_stable_price_gives_baseline(db):
    """Главный случай: одна точка 60 дней назад, цена с тех пор не менялась.

    По старой формуле это 1 день → базы нет. Теперь 60+ дней по 4 990."""
    rec, st = await _record(db), await _store(db)
    await _listing(db, st, rec, price=4990, first_seen=_ago(60),
                   points=[(_ago(60), 4990, "in_stock")])

    days = await daily_min_prices(db, [rec], 90)
    assert len(days) >= 60
    assert {float(d[2]) for d in days} == {4990.0}
    assert (await baseline_prices(db, [rec]))[rec] == 4990.0


async def test_listing_older_than_journal_counts_from_epoch(db, monkeypatch):
    """Листинг появился до журнала и ни разу не менялся — точек нет вовсе.

    Раз с HISTORY_EPOCH ни одной смены не записано, цена и наличие всё это
    время были текущими: ступенька от эпохи до последнего наблюдения."""
    monkeypatch.setattr(radar, "HISTORY_EPOCH", _ago(40))
    rec, st = await _record(db), await _store(db)
    await _listing(db, st, rec, price=3990, first_seen=_ago(120))

    days = await daily_min_prices(db, [rec], 90)
    assert 40 <= len(days) <= 42
    assert (await baseline_prices(db, [rec]))[rec] == 3990.0


async def test_price_step_is_held_until_next_point(db):
    """4 990 тридцать дней, затем 3 990 десять: минимум дня следует ступеньке."""
    rec, st = await _record(db), await _store(db)
    await _listing(db, st, rec, price=3990, first_seen=_ago(40), points=[
        (_ago(40), 4990, "in_stock"),
        (_ago(10), 3990, "in_stock"),
    ])

    by_day = {d[1].date(): float(d[2]) for d in await daily_min_prices(db, [rec], 90)}
    assert by_day[_ago(20).date()] == 4990.0
    assert by_day[_ago(5).date()] == 3990.0
    # Медиана по дням, а не по точкам: 4 990 держалась втрое дольше.
    assert (await baseline_prices(db, [rec]))[rec] == 4990.0


async def test_out_of_stock_gap_is_not_counted(db):
    """Пока позиции не было в наличии, «обычной цены» у неё не было."""
    rec, st = await _record(db), await _store(db)
    await _listing(db, st, rec, price=4990, first_seen=_ago(50), points=[
        (_ago(50), 4990, "in_stock"),
        (_ago(40), 4990, "out_of_stock"),
        (_ago(10), 4990, "in_stock"),
    ])

    days = {d[1].date() for d in await daily_min_prices(db, [rec], 90)}
    assert _ago(45).date() in days
    assert _ago(25).date() not in days
    assert _ago(5).date() in days


async def test_vanished_listing_stops_at_last_sighting(db):
    """Обход перестал видеть позицию 20 дней назад (retire ставит REMOVED
    без точки в журнале) — ступенька обрывается на последнем наблюдении."""
    rec, st = await _record(db), await _store(db)
    await _listing(db, st, rec, price=4990, first_seen=_ago(60),
                   last_seen=_ago(20), status="removed",
                   points=[(_ago(60), 4990, "in_stock")])

    days = {d[1].date() for d in await daily_min_prices(db, [rec], 90)}
    assert _ago(30).date() in days
    assert _ago(10).date() not in days


async def test_daily_minimum_across_stores(db):
    """Два магазина: день берёт самый дешёвый из тех, что были в наличии."""
    rec = await _record(db)
    await _listing(db, await _store(db), rec, price=5990, first_seen=_ago(30),
                   points=[(_ago(30), 5990, "in_stock")])
    await _listing(db, await _store(db), rec, price=4490, first_seen=_ago(10),
                   points=[(_ago(10), 4490, "in_stock")])

    rows = {d[1].date(): d for d in await daily_min_prices(db, [rec], 90)}
    assert float(rows[_ago(20).date()][2]) == 5990.0
    assert float(rows[_ago(5).date()][2]) == 4490.0
    assert rows[_ago(5).date()][3] == 2  # листингов в наличии в этот день


async def test_fresh_listing_still_has_no_baseline(db):
    """Гейт MIN_BASELINE_DAYS на месте: два дня продаж — не «обычная цена»."""
    rec, st = await _record(db), await _store(db)
    await _listing(db, st, rec, price=4990, first_seen=_ago(2),
                   points=[(_ago(2), 4990, "in_stock")])

    assert rec not in await baseline_prices(db, [rec])


async def test_window_clips_old_history(db):
    """Ступенька, начатая за окном, считается только внутри окна."""
    rec, st = await _record(db), await _store(db)
    await _listing(db, st, rec, price=4990, first_seen=_ago(200),
                   points=[(_ago(200), 4990, "in_stock")])

    days = await daily_min_prices(db, [rec], 30)
    assert 30 <= len(days) <= 31
