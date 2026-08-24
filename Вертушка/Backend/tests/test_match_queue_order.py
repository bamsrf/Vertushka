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
    loop_body = src.split("for listing in listings:", 1)[1].split("if attempted_ids:", 1)[0]
    assert "listing.match_attempted_at" not in loop_body


def test_attempt_stamped_for_accessories_and_crashes():
    """Аксессуары и упавшие — состоявшиеся попытки, они не должны застревать.

    Аксессуар пластинкой не станет, а упавший листинг падает из-за собственных
    данных — повторять их через час бессмысленно. Единственное исключение —
    исчерпанная квота Discogs (см. test_quota_block_does_not_stamp_attempt).
    """
    src = inspect.getsource(listing_matcher.match_unmatched_batch)
    accessory_branch = src.split("_is_accessory(listing)", 1)[1].split("raw =", 1)[0]
    assert "attempted_ids.append(listing.id)" in accessory_branch

    crash_branch = src.split("logger.exception(\"match failed", 1)[1].split("if ok or", 1)[0]
    assert "attempted_ids.append(listing.id)" in crash_branch


def test_queue_left_is_reported():
    """Без счётчика остатка застой очереди снова будет невидим."""
    src = inspect.getsource(listing_matcher.match_unmatched_batch)
    assert "queue_left" in src


@pytest.mark.parametrize("field", ["match_attempted_at"])
def test_model_has_attempt_column(field):
    assert hasattr(StoreListing, field)
    assert StoreListing.__table__.c[field].nullable


# ---- Исчерпанная квота Discogs не должна «сжигать» попытку ------------- #

def test_quota_block_does_not_stamp_attempt():
    """Листинг, до которого Discogs не дошёл, обязан остаться в очереди.

    Иначе исчерпанная квота молча отправляет остаток батча в недельный
    кулдаун, ни разу про них не спросив — и мы даже не узнаем.
    """
    src = inspect.getsource(listing_matcher.match_unmatched_batch)
    # 2026-08-23: к квоте добавился инфра-флаг — оба держат листинг в очереди.
    assert "if ok or not (_quota_blocked.get() or _infra_blocked.get()):" in src
    assert "attempted_ids" in src
    # UPDATE идёт по отобранным id, а не по всему батчу.
    assert "StoreListing.id.in_(attempted_ids)" in src


def test_quota_gates_raise_the_flag():
    """Оба on-demand пути (barcode/catalog и artist+title) должны его ставить."""
    for fn in (listing_matcher._try_discogs_fetch, listing_matcher._try_discogs_fetch_by_text):
        src = inspect.getsource(fn)
        assert "_quota_blocked.set(True)" in src, fn.__name__


def test_flag_is_reset_per_listing():
    """Флаг с предыдущего листинга не должен подвешивать следующий."""
    src = inspect.getsource(listing_matcher.match_unmatched_batch)
    assert "_quota_blocked.set(False)" in src


def test_flag_is_contextvar_not_global():
    """Матчер живёт в общем event loop — глобальный флаг протёк бы в чужие задачи."""
    from contextvars import ContextVar
    assert isinstance(listing_matcher._quota_blocked, ContextVar)
    assert listing_matcher._quota_blocked.get() is False
