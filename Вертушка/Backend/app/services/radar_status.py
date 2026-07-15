"""
Радар: общие хелперы состояния и запись хронологии статусов.

Используется продюсерами уведомлений (subscribed-айтемы) — фильтр по «Состоянию
релиза» и запись переходов в radar_status_events для «Истории» в шторке цены.
"""
from __future__ import annotations

from decimal import Decimal

from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.radar_status_event import RadarStatusEvent
from app.models.wishlist import WishlistItem


def grade_of(condition_raw: str | None) -> str | None:
    """Сырой condition → канон-грейд ('sealed'|'mint'|'vg_plus'|'vg'). Неизвестное → None."""
    if not condition_raw:
        return None
    c = condition_raw.strip().lower()
    if any(k in c for k in ("seal", "запечат", "ss", "new", "новая")):
        return "sealed"
    if "vg+" in c or "vg plus" in c or "very good plus" in c:
        return "vg_plus"
    if any(k in c for k in ("mint", "nm", "m-", "m/", "идеальн")):
        return "mint"
    if "vg" in c or "very good" in c or "хорош" in c:
        return "vg"
    return None


def condition_ok(condition_raw: str | None, accepted: list | None) -> bool:
    """Проходит ли листинг по выбранным грейдам. accepted пусто/None → любое."""
    if not accepted:
        return True
    grade = grade_of(condition_raw)
    if grade is None:
        return True  # нераспознанное не отсеиваем
    return grade in accepted


async def record_radar_event(
    db: AsyncSession,
    wi: WishlistItem,
    status: str,
    price: Decimal | float | None = None,
    store_name: str | None = None,
) -> None:
    """Записать смену статуса радара. Дедуп: пропускаем, если последний
    event по айтему такой же статус И та же цена (без изменений)."""
    if wi.notify_mode != "subscribed":
        return
    last = (
        await db.execute(
            select(RadarStatusEvent)
            .where(RadarStatusEvent.wishlist_item_id == wi.id)
            .order_by(desc(RadarStatusEvent.created_at))
            .limit(1)
        )
    ).scalar_one_or_none()
    price_dec = Decimal(str(price)) if price is not None else None
    if last is not None and last.status == status and last.price_rub == price_dec:
        return
    db.add(
        RadarStatusEvent(
            wishlist_item_id=wi.id,
            record_id=wi.record_id,
            status=status,
            price_rub=price_dec,
            store_name=(store_name[:120] if store_name else None),
        )
    )
