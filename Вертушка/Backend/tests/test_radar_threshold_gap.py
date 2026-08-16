"""Зазор до порога радара — тихий сигнал «почти дошло».

Функция чистая, поэтому проверяем её напрямую, без БД и планировщика.
"""
import pytest

from app.tasks.notification_tasks import NEAR_THRESHOLD_RATIO, _threshold_gap


def test_price_below_threshold_has_no_gap():
    """Цена ≤ порога — это уже match, зазор бессмысленен."""
    assert _threshold_gap(4500.0, 5000.0) == (None, False)
    assert _threshold_gap(5000.0, 5000.0) == (None, False)


def test_near_threshold_within_ratio():
    """5 200 при пороге 5 000 — 200 ₽ до цели, это «почти»."""
    gap, near = _threshold_gap(5200.0, 5000.0)
    assert gap == 200.0
    assert near is True


def test_exactly_on_ratio_edge_is_near():
    """Граница включительно: ровно 10% сверху ещё считается близким."""
    edge = 5000.0 * (1 + NEAR_THRESHOLD_RATIO)
    gap, near = _threshold_gap(edge, 5000.0)
    assert gap == 500.0
    assert near is True


def test_far_above_threshold_is_not_near():
    """11 000 при пороге 5 000 — зазор считаем, но «почти» не заявляем."""
    gap, near = _threshold_gap(11000.0, 5000.0)
    assert gap == 6000.0
    assert near is False


@pytest.mark.parametrize(
    "price,threshold",
    [(None, 5000.0), (5200.0, None), (None, None), (5200.0, 0.0), (5200.0, -1.0)],
)
def test_missing_or_degenerate_inputs(price, threshold):
    """Нет цены/порога или порог ≤ 0 — молчим, а не делим на ноль."""
    assert _threshold_gap(price, threshold) == (None, False)
