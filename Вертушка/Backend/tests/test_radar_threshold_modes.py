"""Эффективный порог радара: абсолютный режим и «дешевле обычного».

effective_threshold — чистая функция, проверяем без БД. Запрос базы
(baseline_prices) покрыт интеграционно на уровне API.
"""
from decimal import Decimal

import pytest

from app.services.radar_threshold import effective_threshold


def test_absolute_mode_returns_stored_sum():
    """pct не задан — работает старое поведение, копейка в копейку."""
    assert effective_threshold(Decimal("5000.00"), None, None) == 5000.0
    assert effective_threshold(Decimal("5000.00"), None, 9000.0) == 5000.0


def test_absolute_mode_without_sum_means_always_notify():
    assert effective_threshold(None, None, None) is None


def test_relative_mode_discounts_baseline():
    """База 10 000, «на 20% дешевле» → 8 000."""
    assert effective_threshold(None, 20, 10000.0) == 8000.0


def test_relative_mode_wins_over_stored_sum():
    """Оба поля заполнены (переключали режим туда-обратно) — решает pct."""
    assert effective_threshold(Decimal("5000.00"), 20, 10000.0) == 8000.0


def test_relative_mode_without_baseline_falls_back_to_absolute():
    """Нет истории по записи — следим по старой сумме, а не молчим."""
    assert effective_threshold(Decimal("4200.00"), 20, None) == 4200.0
    assert effective_threshold(None, 20, None) is None


@pytest.mark.parametrize("pct", [0, -5, 100, 150])
def test_degenerate_percentages_disable_threshold(pct):
    """0% — не скидка, ≥100% — отрицательная цена. Не выдумываем число."""
    assert effective_threshold(Decimal("5000.00"), pct, 10000.0) is None


def test_baseline_tracks_market_growth():
    """Смысл режима: база выросла — порог вырос сам, без ручного пересмотра."""
    before = effective_threshold(None, 20, 10000.0)
    after = effective_threshold(None, 20, 14000.0)
    assert before == 8000.0
    assert after == 11200.0
