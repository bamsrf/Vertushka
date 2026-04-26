"""
Расчёт стоимости коллекции и дельты за месяц
"""
from datetime import date, timedelta, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.collection import Collection, CollectionItem
from app.models.collection_value_snapshot import CollectionValueSnapshot
from app.models.record import Record
from app.services.exchange import get_usd_rub_rate


async def get_current_collection_value_rub(user_id: UUID, db: AsyncSession) -> Decimal:
    """Текущая стоимость коллекции пользователя в рублях."""
    value_usd = await db.scalar(
        select(func.sum(Record.estimated_price_median))
        .join(CollectionItem, CollectionItem.record_id == Record.id)
        .join(Collection)
        .where(Collection.user_id == user_id)
    )
    if not value_usd:
        return Decimal("0")
    rate = await get_usd_rub_rate()
    return Decimal(str(float(value_usd) * rate)).quantize(Decimal("0.01"))


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
    if past_value is None:
        return None

    today_value = await get_current_collection_value_rub(user_id, db)
    return (Decimal(today_value) - Decimal(past_value)).quantize(Decimal("0.01"))
