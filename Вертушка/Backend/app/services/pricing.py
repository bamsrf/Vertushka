"""Расчёт рублёвой цены пластинки из USD-цены Discogs.

Компонентная формула: фиксированная доставка с поправкой на формат/вес,
накладные расходы (процессинг + спред + маржа), таможенная пошлина при
превышении порога. Для локальных (РФ/СССР) релизов импортная формула
не применяется — возвращается чистая USD × курс ЦБ как fallback, когда
маркетплейсная цена недоступна. Основной путь для локальных — данные
из `store_listings`, см. `services/marketplace_pricing.py`.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

LOCAL_COUNTRIES = {"Russia", "USSR", "Россия", "СССР"}


@dataclass(frozen=True)
class PricingParams:
    base_shipping_usd: float = 20.0
    import_overhead_pct: float = 0.20
    local_overhead_pct: float = 0.30
    customs_threshold_usd: float = 220.0
    customs_rate: float = 0.15

    @classmethod
    def from_settings(cls, settings) -> "PricingParams":
        return cls(
            base_shipping_usd=settings.pricing_base_shipping_usd,
            import_overhead_pct=settings.pricing_import_overhead_pct,
            local_overhead_pct=settings.pricing_local_overhead_pct,
            customs_threshold_usd=settings.pricing_customs_threshold_usd,
            customs_rate=settings.pricing_customs_rate,
        )


def is_local_country(country: Optional[str]) -> bool:
    return bool(country) and country in LOCAL_COUNTRIES


def format_weight_factor(
    format_type: Optional[str] = None,
    format_description: Optional[str] = None,
    discogs_data: Optional[dict] = None,
) -> float:
    """Множитель к базовой доставке по формату/количеству дисков."""
    qty: Optional[int] = None
    if discogs_data:
        formats = discogs_data.get("formats") or []
        if formats:
            try:
                qty_raw = formats[0].get("qty")
                qty = int(qty_raw) if qty_raw else None
            except (TypeError, ValueError):
                qty = None

    desc = (format_description or "").lower()
    ftype = (format_type or "").lower()

    if "box" in desc or "box" in ftype:
        return 1.6
    if '7"' in desc or '7"' in ftype:
        return 0.6
    if '10"' in desc or '10"' in ftype:
        return 0.8

    if qty and qty >= 2:
        if qty == 2:
            return 1.2
        if qty == 3:
            return 1.4
        return min(1.0 + 0.2 * qty, 2.5)

    return 1.0


def estimate_rub(
    usd_price: Optional[float],
    country: Optional[str],
    rate: float,
    params: PricingParams,
    *,
    format_type: Optional[str] = None,
    format_description: Optional[str] = None,
    discogs_data: Optional[dict] = None,
) -> float:
    """Рассчитывает рублёвую цену из USD-цены Discogs."""
    if not usd_price or usd_price <= 0 or rate <= 0:
        return 0.0

    if is_local_country(country):
        return round(usd_price * rate, 0)

    weight = format_weight_factor(format_type, format_description, discogs_data)
    shipping = params.base_shipping_usd * weight
    subtotal = usd_price + shipping
    overhead = subtotal * params.import_overhead_pct
    total_usd = subtotal + overhead

    if total_usd > params.customs_threshold_usd:
        total_usd += (total_usd - params.customs_threshold_usd) * params.customs_rate

    return round(total_usd * rate, 0)


def effective_markup(
    usd_price: Optional[float],
    country: Optional[str],
    rate: float,
    params: PricingParams,
    *,
    format_type: Optional[str] = None,
    format_description: Optional[str] = None,
    discogs_data: Optional[dict] = None,
) -> float:
    """Эффективный множитель rub/(usd × rate) — для отображения в UI."""
    if not usd_price or usd_price <= 0 or rate <= 0:
        return 1.0
    rub = estimate_rub(
        usd_price,
        country,
        rate,
        params,
        format_type=format_type,
        format_description=format_description,
        discogs_data=discogs_data,
    )
    return round(rub / (usd_price * rate), 2)


def record_usd(record) -> float | None:
    """Долларовая база для рублёвой оценки записи: median, иначе min.

    ЕДИНСТВЕННЫЙ источник правды. Все три пути — карточка коллекции
    (`api/collections.py`), стоимость профиля (`services/valuation.py`) и
    фоновые задачи (`tasks/discogs_tasks.py`) — обязаны звать эту функцию.

    Discogs отдаёт `lowest_price` только при ЖИВЫХ лотах на маркетплейсе, а
    `median_price` — при наличии истории продаж. Это независимые величины: у
    пластинки, которую сейчас никто не продаёт, но которая продавалась раньше,
    min пустой, а median заполнен. И наоборот, у редкого релиза с одним лотом и
    без продаж median пустой, а min есть.

    Правило уже было выведено в valuation.py для карточки профиля, но не
    протянуто в коллекцию: там рубли считались строго от min, а счётчик
    «оценено N из M» — от «median или min». Пластинка с одним лишь median
    попадала в счётчик, но рублёвой цены не получала и выпадала из списка «По
    стоимости» и из суммы. Снаружи это выглядело как «пишет 6, показывает 3».

    Median первым, а не min: медиана устойчивее одиночного минимального лота.
    """
    usd = record.estimated_price_median or record.estimated_price_min
    return float(usd) if usd else None


def stat_price_value(raw) -> float | None:
    """Достаёт число из ценового поля marketplace-статистики Discogs.

    Discogs отдаёт цену то объектом `{"value": 12.5, "currency": "USD"}`, то
    голым числом — форма зависит от эндпоинта и наличия лотов. Разбор был
    продублирован в трёх местах разными выражениями; здесь он один.
    """
    if isinstance(raw, dict):
        value = raw.get("value")
    else:
        value = raw
    return float(value) if isinstance(value, (int, float)) else None
