"""Эффективный порог радара: абсолютный или «дешевле обычного».

Порог читается в трёх местах (GET /wishlists/radar и оба продюсера уведомлений —
in_stock и price_drop). Пока он был одним числом, дублирование было безобидным;
с появлением относительного режима разъехавшиеся формулы означали бы, что экран
показывает «подходит», а пуш не приходит. Поэтому расчёт живёт здесь один раз.

Режимы:
    threshold_pct задан  → порог = база × (1 − pct/100), база пересчитывается;
    иначе                → порог = price_threshold_rub (как было).

База — медиана дневных минимумов за BASELINE_DAYS. Медиана, а не среднее:
единственный демпинговый лот не должен обрушивать «обычную» цену. Дневной
минимум, а не все снапшоты: это ровно та величина, которую рисует график в
шторке цены, и обещание «дешевле обычного» должно совпадать с картинкой.
"""
from __future__ import annotations

from decimal import Decimal
from datetime import datetime, timedelta
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.listing_price_history import ListingPriceHistory
from app.models.store_listing import ListingStatus

# Окно базы. Совпадает с дефолтом графика в шторке цены (days=90).
BASELINE_DAYS = 90

# Минимум дней с данными, иначе базе нельзя верить: на двух точках «обычная
# цена» — это просто последняя цена, и относительный порог сработает мусорно.
MIN_BASELINE_DAYS = 5


async def baseline_prices(
    db: AsyncSession, record_ids: list[UUID]
) -> dict[UUID, float]:
    """{record_id: медиана дневных минимумов за 90 дней} для записей с данными.

    Записи, у которых меньше MIN_BASELINE_DAYS дней истории, в ответ не попадают.
    """
    if not record_ids:
        return {}

    since = datetime.utcnow() - timedelta(days=BASELINE_DAYS)
    day = func.date_trunc("day", ListingPriceHistory.captured_at)

    daily = (
        select(
            ListingPriceHistory.record_id.label("record_id"),
            day.label("day"),
            func.min(ListingPriceHistory.price_rub).label("min_price"),
        )
        .where(
            ListingPriceHistory.record_id.in_(record_ids),
            ListingPriceHistory.status == ListingStatus.IN_STOCK,
            ListingPriceHistory.price_rub.is_not(None),
            ListingPriceHistory.captured_at >= since,
        )
        .group_by(ListingPriceHistory.record_id, day)
        .subquery()
    )

    rows = (
        await db.execute(
            select(
                daily.c.record_id,
                func.percentile_cont(0.5)
                .within_group(daily.c.min_price)
                .label("median_price"),
                func.count().label("days"),
            ).group_by(daily.c.record_id)
        )
    ).all()

    return {
        record_id: float(median)
        for record_id, median, days in rows
        if median is not None and days >= MIN_BASELINE_DAYS
    }


def effective_threshold(
    price_threshold_rub: Decimal | float | None,
    threshold_pct: int | None,
    baseline: float | None,
) -> float | None:
    """Порог в рублях для сравнения с ценой лота. None = «уведомлять всегда».

    Относительный режим без базы (нет истории по записи) осознанно падает на
    абсолютный порог, а не молчит: пользователь подписался на пластинку, и
    отсутствие статистики не повод переставать за ней следить.
    """
    if threshold_pct is not None and baseline is not None:
        if threshold_pct <= 0 or threshold_pct >= 100:
            return None
        return round(baseline * (1 - threshold_pct / 100), 2)
    if price_threshold_rub is None:
        return None
    return float(price_threshold_rub)
