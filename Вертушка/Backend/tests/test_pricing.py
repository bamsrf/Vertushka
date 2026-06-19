"""Smoke-тесты компонентной RUB-формулы (services/pricing.py).

Контракт цены — то, что видит каждый юзер на каждой карточке. Регрессия
здесь молча искажает оценку всей коллекции, поэтому фиксируем поведение.
"""
from app.services.pricing import (
    PricingParams,
    estimate_rub,
    effective_markup,
    format_weight_factor,
    is_local_country,
)

PARAMS = PricingParams()  # дефолты: shipping $20, overhead 20%, customs 15% > $220


class TestIsLocalCountry:
    def test_russia_variants_are_local(self):
        assert is_local_country("Russia")
        assert is_local_country("СССР")
        assert is_local_country("USSR")

    def test_foreign_and_empty_are_not_local(self):
        assert not is_local_country("US")
        assert not is_local_country(None)
        assert not is_local_country("")


class TestFormatWeightFactor:
    def test_format_multipliers(self):
        assert format_weight_factor(format_description="Box Set") == 1.6
        assert format_weight_factor(format_description='7"') == 0.6
        assert format_weight_factor(format_description='10"') == 0.8

    def test_default_single_lp(self):
        assert format_weight_factor(format_type="LP") == 1.0

    def test_multi_disc_from_qty(self):
        assert format_weight_factor(discogs_data={"formats": [{"qty": "2"}]}) == 1.2
        assert format_weight_factor(discogs_data={"formats": [{"qty": "3"}]}) == 1.4

    def test_qty_is_capped(self):
        # 1.0 + 0.2*qty, но не больше 2.5
        assert format_weight_factor(discogs_data={"formats": [{"qty": "99"}]}) == 2.5

    def test_garbage_qty_does_not_crash(self):
        assert format_weight_factor(discogs_data={"formats": [{"qty": "nope"}]}) == 1.0


class TestEstimateRub:
    def test_zero_or_invalid_inputs_return_zero(self):
        assert estimate_rub(None, "US", 90.0, PARAMS) == 0.0
        assert estimate_rub(0, "US", 90.0, PARAMS) == 0.0
        assert estimate_rub(100, "US", 0, PARAMS) == 0.0

    def test_local_is_bare_usd_times_rate(self):
        # Локальный путь — без shipping/overhead/customs.
        assert estimate_rub(100, "Russia", 90.0, PARAMS) == 9000.0

    def test_import_below_customs_threshold(self):
        # 100 + 20 ship = 120; +20% overhead = 144 (<220, без пошлины); ×90.
        assert estimate_rub(100, "US", 90.0, PARAMS) == 12960.0

    def test_import_above_customs_threshold_adds_duty(self):
        # 300 + 20 = 320; +20% = 384; пошлина (384-220)*15% = 24.6 → 408.6; ×90.
        assert estimate_rub(300, "US", 90.0, PARAMS) == 36774.0

    def test_box_set_raises_shipping(self):
        bare = estimate_rub(100, "US", 90.0, PARAMS)
        box = estimate_rub(100, "US", 90.0, PARAMS, format_description="Box Set")
        assert box > bare


class TestEffectiveMarkup:
    def test_local_markup_is_one(self):
        assert effective_markup(100, "Russia", 90.0, PARAMS) == 1.0

    def test_import_markup_above_one(self):
        assert effective_markup(100, "US", 90.0, PARAMS) > 1.0

    def test_invalid_returns_one(self):
        assert effective_markup(None, "US", 90.0, PARAMS) == 1.0
