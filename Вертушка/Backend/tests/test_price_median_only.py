"""Пластинка с одним лишь median не должна выпадать из оценки.

Discogs отдаёт `lowest_price` только при ЖИВЫХ лотах на маркетплейсе, а
`median_price` — при наличии истории продаж. Величины независимые: у пластинки,
которую сейчас никто не продаёт, но которая продавалась раньше, min пустой,
median заполнен.

Баг, от которого сторожат эти тесты: счётчик «оценено N из M» считал запись
оценённой по «median или min», а рубли считались строго от min. Median-only
пластинка попадала в счётчик, но рублёвой цены не получала — выпадала из списка
«По стоимости» и из суммы. На проде это выглядело как «оценено 6 из 26», список
из трёх строк, и заголовок ~34 300 ₽, в точности равный сумме этих трёх.

Инвариант, который надо держать: множество «записей с ценой» для счётчика и
множество, дающее ненулевые рубли, — одно и то же.
"""
import pytest

from app.services.pricing import PricingParams, estimate_rub, record_usd, stat_price_value


class _Record:
    """Минимальный дубль Record — record_usd читает только два поля."""

    def __init__(self, median=None, minimum=None, country=None):
        self.estimated_price_median = median
        self.estimated_price_min = minimum
        self.country = country
        self.format_type = "Vinyl"
        self.format_description = "LP, Album"
        self.discogs_data = None


def _counted_as_priced(record) -> bool:
    """Условие счётчика «оценено» из api/collections.py::get_collection_stats."""
    return bool(record.estimated_price_median or record.estimated_price_min)


class TestCounterMatchesValue:
    @pytest.mark.parametrize(
        "median,minimum",
        [
            (None, 12.5),     # живые лоты, продаж не было
            (30.0, None),     # продажи были, лотов сейчас нет  ← ломалось
            (30.0, 12.5),     # и то, и другое
        ],
    )
    def test_counted_records_always_get_a_price(self, median, minimum):
        """Всё, что счётчик назвал оценённым, обязано давать ненулевые рубли."""
        record = _Record(median=median, minimum=minimum)
        assert _counted_as_priced(record) is True

        usd = record_usd(record)
        assert usd is not None, "запись в счётчике, но без долларовой базы"

        rub = estimate_rub(usd, record.country, 84.54, PricingParams())
        assert rub > 0

    def test_unpriced_record_is_not_counted(self):
        record = _Record()
        assert _counted_as_priced(record) is False
        assert record_usd(record) is None


class TestMedianPreferred:
    def test_median_wins_over_min(self):
        """Медиана устойчивее одиночного минимального лота — та же формула,
        что в valuation.record_value_rub для карточки профиля."""
        assert record_usd(_Record(median=30.0, minimum=12.5)) == 30.0

    def test_falls_back_to_min(self):
        assert record_usd(_Record(median=None, minimum=12.5)) == 12.5

    def test_matches_profile_valuation_formula(self):
        """Экран коллекции и карточка профиля обязаны совпадать.

        Раньше расходились: профиль считал median-or-min, коллекция — min.
        """
        from app.services.valuation import record_value_rub

        record = _Record(median=30.0, minimum=12.5)
        params = PricingParams()
        rate = 84.54

        assert record_value_rub(record, rate, params) == estimate_rub(
            record_usd(record), record.country, rate, params,
            format_type=record.format_type,
            format_description=record.format_description,
            discogs_data=record.discogs_data,
        )


class TestBackfillQueueTerminates:
    def test_median_only_record_is_not_pending_forever(self):
        """Очередь дозагрузки не должна считать median-only запись «без цены».

        Иначе задача гоняла бы её по кругу: Discogs каждый раз отвечает без
        lowest_price, min остаётся NULL, remaining никогда не дойдёт до нуля.
        """
        from app.services.price_backfill import records_without_price_query

        sql = str(records_without_price_query(
            __import__("uuid").uuid4()
        ).compile(compile_kwargs={"literal_binds": False})).lower()

        assert "estimated_price_median is null" in sql, (
            "фильтр «без цены» не проверяет median — median-only записи "
            "застрянут в очереди навсегда"
        )
        assert "estimated_price_min is null" in sql


class TestStatValueSharedHelper:
    @pytest.mark.parametrize(
        "raw,expected",
        [
            ({"value": 12.5, "currency": "USD"}, 12.5),
            (12.5, 12.5),
            (0, 0.0),
            (None, None),
            ({}, None),
            ({"currency": "USD"}, None),
        ],
    )
    def test_handles_both_discogs_shapes(self, raw, expected):
        assert stat_price_value(raw) == expected
