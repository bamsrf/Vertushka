"""Одноразовый пересчёт CollectionItem.estimated_price_rub по актуальной pricing-формуле.

Не обращается в Discogs — использует уже сохранённый record.estimated_price_min.
Пересчитывает ВСЕ записи во всех коллекциях за один прогон.

Запуск:
    docker compose -f docker-compose.prod.yml exec api python scripts/recalc_collection_rub.py
"""
import asyncio
import logging

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.config import get_settings
from app.database import async_session_maker
from app.models.collection import CollectionItem
from app.services.exchange import get_usd_rub_rate
from app.services.pricing import PricingParams, estimate_rub

logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger("recalc")


async def main() -> None:
    usd_rub = await get_usd_rub_rate()
    params = PricingParams.from_settings(get_settings())
    log.info("rate=%.4f params=%s", usd_rub, params)

    async with async_session_maker() as session:
        result = await session.execute(
            select(CollectionItem).options(selectinload(CollectionItem.record))
        )
        items = result.scalars().all()

        updated = 0
        cleared = 0
        for item in items:
            rec = item.record
            if rec and rec.estimated_price_min:
                new_rub = estimate_rub(
                    float(rec.estimated_price_min),
                    rec.country,
                    usd_rub,
                    params,
                    format_type=rec.format_type,
                    format_description=rec.format_description,
                    discogs_data=rec.discogs_data,
                )
                if item.estimated_price_rub != new_rub:
                    item.estimated_price_rub = new_rub
                    updated += 1
            elif item.estimated_price_rub is not None:
                item.estimated_price_rub = None
                cleared += 1

        await session.commit()
        log.info("done: total=%d updated=%d cleared=%d", len(items), updated, cleared)


if __name__ == "__main__":
    asyncio.run(main())
