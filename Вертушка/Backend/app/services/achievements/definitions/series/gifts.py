"""Серия «Дарящая рука» (J* + META_gifts).

Phase 0: J1 (реализован).
Phase 2: J2–J6 + META_gifts — ⚠️ КАРКАС / SCAFFOLDING, evaluator-ы возвращают
`unlocked=False` пока не утверждены финальные дизайны и события `gift_completed`
/ `gift_received` не подключены в `Backend/app/api/gifts.py`.

См. PLAN_ACHIEVEMENTS_V2.md §4.7.

Анти-фарм для J3/J4: разные `recipient_user_id`. META открывается на J4 + J6.
"""
from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import select, exists
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.gift_booking import GiftBooking, GiftStatus
from app.services.achievements.events import (
    GIFT_BOOKED,
    GIFT_COMPLETED,
    GIFT_RECEIVED,
)
from app.services.achievements.registry import (
    AchievementDefinition,
    AchievementTier,
    EvalResult,
)


J1_CODE = "J1_first_gift"
J2_CODE = "J2_gift_done"
J3_CODE = "J3_three_recipients"
J4_CODE = "J4_ten_recipients"
J5_CODE = "J5_first_received"
J6_CODE = "J6_perfect_match"
META_CODE = "META_gifts"
GIFTS_CODES = {J1_CODE, J2_CODE, J3_CODE, J4_CODE, J5_CODE, J6_CODE}


async def _evaluate_j1(
    db: AsyncSession,
    user_id: UUID,
    payload: dict[str, Any],
    unlocked_now: set[str],
) -> EvalResult:
    """J1 (Phase 0, реальная логика): юзер забронировал хотя бы один подарок."""
    has_booking = await db.scalar(
        select(
            exists().where(
                GiftBooking.booked_by_user_id == user_id,
                GiftBooking.status.in_(
                    [GiftStatus.PENDING, GiftStatus.BOOKED, GiftStatus.COMPLETED]
                ),
            )
        )
    )
    return EvalResult(unlocked=bool(has_booking))


async def _stub(
    db: AsyncSession,
    user_id: UUID,
    payload: dict[str, Any] | None,
    unlocked_now: set[str],
) -> EvalResult:
    """Заглушка для J2–J6/META — финальная логика в Phase 2."""
    return EvalResult(unlocked=False)


DEFINITIONS: list[AchievementDefinition] = [
    AchievementDefinition(
        code=J1_CODE,
        title_ru="Подарил",
        description_ru="Забронируй первый подарок другу.",
        description_done_ru="Первый подарок забронирован.",
        series="gifts",
        tier=AchievementTier.SIMPLE,
        is_hidden=False,
        triggers=(GIFT_BOOKED,),
        evaluator=_evaluate_j1,
        icon_slug="j1_first_gift",
    ),
    # --- Phase 2 stubs ---
    AchievementDefinition(
        code=J2_CODE,
        title_ru="Долетело",
        description_ru="Первый подарок дошёл до адресата.",
        description_done_ru="Первый подарок доставлен.",
        series="gifts",
        tier=AchievementTier.SIMPLE,
        is_hidden=False,
        triggers=(GIFT_COMPLETED,),
        evaluator=_stub,
        icon_slug="j2_gift_done",
    ),
    AchievementDefinition(
        code=J3_CODE,
        title_ru="Дарящая рука",
        description_ru="Завершил подарки 3 разным получателям.",
        description_done_ru="Подарки 3 получателям завершены.",
        series="gifts",
        tier=AchievementTier.NOTABLE,
        is_hidden=False,
        triggers=(GIFT_COMPLETED,),
        evaluator=_stub,
        icon_slug="j3_three_recipients",
    ),
    AchievementDefinition(
        code=J4_CODE,
        title_ru="Праздник",
        description_ru="10 разных получателей.",
        description_done_ru="10 разных получателей одарено.",
        series="gifts",
        tier=AchievementTier.RARE,
        is_hidden=False,
        triggers=(GIFT_COMPLETED,),
        evaluator=_stub,
        icon_slug="j4_ten_recipients",
    ),
    AchievementDefinition(
        code=J5_CODE,
        title_ru="С теплом",
        description_ru="Получил первый подарок.",
        description_done_ru="Первый подарок получен.",
        series="gifts",
        tier=AchievementTier.SIMPLE,
        is_hidden=False,
        triggers=(GIFT_RECEIVED,),
        evaluator=_stub,
        icon_slug="j5_first_received",
    ),
    AchievementDefinition(
        code=J6_CODE,
        title_ru="В точку",
        description_ru="Подаренный релиз был с priority=high в вишлисте.",
        description_done_ru="Подарен релиз из топа вишлиста.",
        series="gifts",
        tier=AchievementTier.RARE,
        is_hidden=False,
        triggers=(GIFT_COMPLETED,),
        evaluator=_stub,
        icon_slug="j6_perfect_match",
    ),
    AchievementDefinition(
        code=META_CODE,
        title_ru="Щедрость",
        description_ru="J4 + J6.",
        description_done_ru="J4 и J6 закрыты.",
        series="gifts",
        tier=AchievementTier.EPIC,
        is_hidden=False,
        triggers=(GIFT_BOOKED, GIFT_COMPLETED, GIFT_RECEIVED),
        evaluator=_stub,
        is_meta=True,
        flavor_ru="Конверт уходит сам.",
        icon_slug="meta_gifts",
    ),
]
