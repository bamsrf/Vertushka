"""Очередь матчера должна двигаться, а не перемалывать одну и ту же голову.

Диагноз 2026-08-12: сортировка шла по `first_seen_at`, а неудачная попытка не
оставляла следа. Каждый час матчер брал те же 2 000 старых безнадёжных позиций
и заново спрашивал про них Discogs — ~1 500 запросов на ~20 совпадений. Новый
магазин rotaryrecords (1 804 позиции) стоял за 12 535 чужими и не получил
ни одного запроса.

Лечение — `match_attempted_at`: сначала ни разу не пробованные, потом самые
давно пробованные, повтор не чаще раза в неделю.
"""
import inspect
from datetime import datetime, timedelta

import pytest

from app.models.store_listing import StoreListing
from app.services import listing_matcher


def _queue_sql() -> str:
    """SQL запроса очереди — собираем ту же конструкцию, что и в проде."""
    from sqlalchemy import or_, select

    retry_before = datetime.utcnow() - timedelta(days=listing_matcher._MATCH_RETRY_DAYS)
    stmt = (
        select(StoreListing)
        .where(StoreListing.matched_record_id.is_(None))
        .where(StoreListing.status.in_(("in_stock", "preorder")))
        .where(
            or_(
                StoreListing.match_attempted_at.is_(None),
                StoreListing.match_attempted_at < retry_before,
            )
        )
        .order_by(
            StoreListing.match_attempted_at.asc().nullsfirst(),
            StoreListing.first_seen_at.asc(),
        )
    )
    return str(stmt.compile(compile_kwargs={"literal_binds": True}))


def test_never_attempted_go_first():
    """NULLS FIRST — иначе новый магазин встаёт в хвост за чужими 12 тысячами."""
    sql = _queue_sql().lower()
    order = sql.split("order by", 1)[1]
    assert "nulls first" in order
    # Ключ сортировки — именно попытка, а не дата появления.
    assert order.index("match_attempted_at") < order.index("first_seen_at")


def test_cooldown_filters_recent_attempts():
    sql = _queue_sql().lower()
    assert "match_attempted_at is null" in sql
    assert "match_attempted_at <" in sql


def test_retry_window_is_sane():
    """Слишком часто — снова жжём квоту; слишком редко — новинки Discogs не догоним."""
    assert 3 <= listing_matcher._MATCH_RETRY_DAYS <= 30


def test_attempt_stamped_outside_savepoint():
    """Отметка обязана переживать откат савпоинта упавшего листинга.

    Если ставить её ORM-атрибутом до `begin_nested()`, `sp.rollback()` может
    её потерять — и листинг навсегда останется в голове очереди.
    """
    src = inspect.getsource(listing_matcher.match_unmatched_batch)
    # Отметка идёт одним UPDATE после цикла, а не присваиванием внутри него.
    assert "update(StoreListing)" in src
    assert "match_attempted_at=attempted_at" in src
    loop_body = src.split("for listing in listings:", 1)[1].split("if listings:", 1)[0]
    assert "listing.match_attempted_at" not in loop_body


def test_attempt_stamped_for_every_processed_listing():
    """Включая аксессуары и упавшие — иначе они и останутся головой очереди."""
    src = inspect.getsource(listing_matcher.match_unmatched_batch)
    stamp = src.split("if listings:", 1)[1]
    # UPDATE берёт весь батч целиком, без фильтра по исходу.
    assert "StoreListing.id.in_([lst.id for lst in listings])" in stamp


def test_queue_left_is_reported():
    """Без счётчика остатка застой очереди снова будет невидим."""
    src = inspect.getsource(listing_matcher.match_unmatched_batch)
    assert "queue_left" in src


@pytest.mark.parametrize("field", ["match_attempted_at"])
def test_model_has_attempt_column(field):
    assert hasattr(StoreListing, field)
    assert StoreListing.__table__.c[field].nullable
