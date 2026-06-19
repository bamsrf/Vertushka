"""
Расчёт стоимости коллекции и дельты за месяц
"""
from datetime import date, timedelta, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models.collection import Collection, CollectionItem
from app.models.collection_value_snapshot import CollectionValueSnapshot
from app.models.record import Record
from app.services.exchange import get_usd_rub_rate
from app.services.pricing import PricingParams, estimate_rub


def record_value_rub(record: Record, rate: float, params: PricingParams) -> float:
    """Рублёвая стоимость одной записи — единая формула с карточкой профиля.

    Discogs отдаёт median_price только при ≥2 продажах, у редких пластинок он
    NULL → берём fallback на estimated_price_min (как `_record_to_public`/
    `compute_rub` в публичном профиле). Голый SUM(median) обнулял оценку и ломал
    дельту за месяц.
    """
    usd = record.estimated_price_median or record.estimated_price_min
    if not usd:
        return 0.0
    return estimate_rub(
        float(usd),
        record.country,
        rate,
        params,
        format_type=record.format_type,
        format_description=record.format_description,
        discogs_data=record.discogs_data,
    )


async def get_current_collection_value_rub(user_id: UUID, db: AsyncSession) -> Decimal:
    """Текущая стоимость коллекции пользователя в рублях.

    DISTINCT по record_id: пластинка может лежать в общей коллекции и в папке
    одновременно — не дублируем её в стоимости.
    """
    records = (
        (
            await db.execute(
                select(Record)
                .join(CollectionItem, CollectionItem.record_id == Record.id)
                .join(Collection)
                .where(Collection.user_id == user_id)
            )
        )
        .scalars()
        .all()
    )
    # Дедуп по record.id в Python (DISTINCT по строке ломается на JSON discogs_data).
    by_id = {r.id: r for r in records}
    if not by_id:
        return Decimal("0")
    rate = await get_usd_rub_rate()
    params = PricingParams.from_settings(get_settings())
    total = sum(record_value_rub(r, rate, params) for r in by_id.values())
    return Decimal(str(total)).quantize(Decimal("0.01"))


async def get_monthly_delta(user_id: UUID, db: AsyncSession) -> Decimal | None:
    """
    Дельта стоимости коллекции за последние 30 дней (RUB).
    Возвращает None, если истории снапшотов < 30 дней.
    """
    today = date.today()
    target_date = today - timedelta(days=30)

    oldest_snap = await db.scalar(
        select(func.min(CollectionValueSnapshot.snapshot_date))
        .where(CollectionValueSnapshot.user_id == user_id)
    )
    if not oldest_snap or oldest_snap > target_date:
        return None

    past_value = await db.scalar(
        select(CollectionValueSnapshot.total_value_rub)
        .where(
            CollectionValueSnapshot.user_id == user_id,
            CollectionValueSnapshot.snapshot_date <= target_date,
        )
        .order_by(CollectionValueSnapshot.snapshot_date.desc())
        .limit(1)
    )
    # `not past_value` ловит и None, и 0. Снапшоты до фикса формулы писали 0 (SUM
    # пустого median) — такой baseline невалиден, дельту показываем None (pill
    # скрыт), пока не накопится реальный ненулевой снапшот 30-дневной давности.
    if not past_value:
        return None

    today_value = await get_current_collection_value_rub(user_id, db)
    return (Decimal(today_value) - Decimal(past_value)).quantize(Decimal("0.01"))
