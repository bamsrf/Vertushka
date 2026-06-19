"""
Фоновые задачи: ежедневный снапшот стоимости коллекций
"""
import logging
from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.config import get_settings
from app.database import async_session_maker
from app.models.collection import Collection, CollectionItem
from app.models.collection_value_snapshot import CollectionValueSnapshot
from app.models.record import Record
from app.services.exchange import get_usd_rub_rate
from app.services.pricing import PricingParams
from app.services.valuation import record_value_rub

logger = logging.getLogger(__name__)


async def record_daily_snapshots():
    """
    Записывает дневной снапшот стоимости коллекции для каждого пользователя.
    UPSERT на (user_id, snapshot_date) — повторный запуск перетирает значение.

    Стоимость считается той же формулой `record_value_rub` (estimate_rub с
    fallback median→min + поправки страны/формата), что и карточка профиля —
    иначе SUM(median) даёт 0 у пластинок без median и обнуляет дельту за месяц.
    """
    today = date.today()
    rate = await get_usd_rub_rate()
    params = PricingParams.from_settings(get_settings())

    async with async_session_maker() as db:
        try:
            rows = (
                await db.execute(
                    select(Collection.user_id, Record)
                    .select_from(Collection)
                    .join(CollectionItem, CollectionItem.collection_id == Collection.id)
                    .join(Record, Record.id == CollectionItem.record_id)
                )
            ).all()

            # Дедуп по (user_id, record_id): пластинка может лежать в общей
            # коллекции и в папках одновременно — считаем один раз.
            value_by_user: dict = {}
            seen: set = set()
            for user_id, record in rows:
                key = (user_id, record.id)
                if key in seen:
                    continue
                seen.add(key)
                agg = value_by_user.setdefault(user_id, {"value": 0.0, "count": 0})
                agg["value"] += record_value_rub(record, rate, params)
                agg["count"] += 1

            for user_id, agg in value_by_user.items():
                value_rub = Decimal(str(agg["value"])).quantize(Decimal("0.01"))
                stmt_upsert = pg_insert(CollectionValueSnapshot).values(
                    user_id=user_id,
                    snapshot_date=today,
                    total_value_rub=value_rub,
                    items_count=agg["count"],
                ).on_conflict_do_update(
                    index_elements=["user_id", "snapshot_date"],
                    set_={
                        "total_value_rub": value_rub,
                        "items_count": agg["count"],
                    },
                )
                await db.execute(stmt_upsert)

            await db.commit()
            logger.info(
                f"Снапшоты стоимости записаны: {len(value_by_user)} пользователей, дата={today}"
            )
        except Exception as e:
            await db.rollback()
            logger.error(f"Ошибка в record_daily_snapshots: {e}")
