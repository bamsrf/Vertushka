"""Серия «Дарящая рука» (J* + META_gifts).

Реализовано (Phase 2):
- J1  «Забронировал»  — забронировал первый подарок          (GIFT_BOOKED)
- J2  «Долетело»      — первый подарок дошёл до адресата       (GIFT_COMPLETED)
- J3  «Дарящая рука»  — завершил подарки 3 разным получателям  (GIFT_COMPLETED)
- J4  «Праздник»      — 10 разных получателей                  (GIFT_COMPLETED)
- J5  «С теплом»      — получил первый подарок                 (GIFT_RECEIVED)
- J7  «Бумеранг»      — подарил тому, кто раньше дарил тебе     (GIFT_COMPLETED)
- J8  «Любимчик»      — получил подарки от 3 разных дарителей   (GIFT_RECEIVED)
- J9  «Дед Мороз»     — подарок дошёл в окно 25.12–14.01        (GIFT_COMPLETED)
- META «Щедрость»     — закрыл ядро серии (J2+J3+J4+J5)

Анти-фарм: распределение считается по РАЗНЫМ `recipient_user_id` (J3/J4) и
РАЗНЫМ `booked_by_user_id` (J8). Подарок требует реальной брони + подтверждения
получения владельцем вишлиста, поэтому фарм дорогой.

J6 «В точку» (priority=high) удалён: в данных priority — int 0..10 без UI-понятия
«High», ачивка ссылалась на несуществующую сущность.

См. PLAN_ACHIEVEMENTS_V2.md §4.7.
"""
from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import and_, exists, extract, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.gift_booking import GiftBooking, GiftStatus
from app.models.user_achievement import UserAchievement
from app.services.achievements.definitions.eggs import MSK_UTC_OFFSET
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
J7_CODE = "J7_boomerang"
J8_CODE = "J8_loved"
J9_CODE = "J9_santa"
META_CODE = "META_gifts"
META_CORE = {J2_CODE, J3_CODE, J4_CODE, J5_CODE}
GIFTS_CODES = {J1_CODE, J2_CODE, J3_CODE, J4_CODE, J5_CODE, J7_CODE, J8_CODE, J9_CODE}

_ACTIVE_BOOKING_STATUSES = (
    GiftStatus.PENDING,
    GiftStatus.BOOKED,
    GiftStatus.COMPLETED,
)


# --- Счётчики ---------------------------------------------------------------

async def _count_distinct_recipients(db: AsyncSession, gifter_id: UUID) -> int:
    """Сколько РАЗНЫХ получателей у завершённых подарков дарителя."""
    count = await db.scalar(
        select(func.count(func.distinct(GiftBooking.recipient_user_id))).where(
            GiftBooking.booked_by_user_id == gifter_id,
            GiftBooking.status == GiftStatus.COMPLETED,
            GiftBooking.recipient_user_id.isnot(None),
        )
    )
    return int(count or 0)


async def _count_distinct_gifters(db: AsyncSession, recipient_id: UUID) -> int:
    """От скольких РАЗНЫХ дарителей получил завершённые подарки."""
    count = await db.scalar(
        select(func.count(func.distinct(GiftBooking.booked_by_user_id))).where(
            GiftBooking.recipient_user_id == recipient_id,
            GiftBooking.status == GiftStatus.COMPLETED,
            GiftBooking.booked_by_user_id.isnot(None),
        )
    )
    return int(count or 0)


# --- Evaluator-ы ------------------------------------------------------------

async def _evaluate_j1(
    db: AsyncSession,
    user_id: UUID,
    payload: dict[str, Any],
    unlocked_now: set[str],
) -> EvalResult:
    """Юзер забронировал хотя бы один подарок (любой активный статус)."""
    has_booking = await db.scalar(
        select(
            exists().where(
                GiftBooking.booked_by_user_id == user_id,
                GiftBooking.status.in_(_ACTIVE_BOOKING_STATUSES),
            )
        )
    )
    return EvalResult(unlocked=bool(has_booking))


async def _evaluate_j2(
    db: AsyncSession,
    user_id: UUID,
    payload: dict[str, Any],
    unlocked_now: set[str],
) -> EvalResult:
    """Хотя бы один подарок дарителя дошёл до адресата (COMPLETED)."""
    has_done = await db.scalar(
        select(
            exists().where(
                GiftBooking.booked_by_user_id == user_id,
                GiftBooking.status == GiftStatus.COMPLETED,
            )
        )
    )
    return EvalResult(unlocked=bool(has_done))


def _make_recipients_evaluator(threshold: int):
    async def evaluator(
        db: AsyncSession,
        user_id: UUID,
        payload: dict[str, Any],
        unlocked_now: set[str],
    ) -> EvalResult:
        count = await _count_distinct_recipients(db, user_id)
        unlocked = count >= threshold
        return EvalResult(
            unlocked=unlocked, progress=count, progress_target=threshold
        )

    return evaluator


async def _evaluate_j5(
    db: AsyncSession,
    user_id: UUID,
    payload: dict[str, Any],
    unlocked_now: set[str],
) -> EvalResult:
    """Юзер получил хотя бы один завершённый подарок."""
    has_received = await db.scalar(
        select(
            exists().where(
                GiftBooking.recipient_user_id == user_id,
                GiftBooking.status == GiftStatus.COMPLETED,
            )
        )
    )
    return EvalResult(unlocked=bool(has_received))


async def _evaluate_j7_boomerang(
    db: AsyncSession,
    user_id: UUID,
    payload: dict[str, Any],
    unlocked_now: set[str],
) -> EvalResult:
    """Подарил тому, кто РАНЬШЕ дарил тебе.

    Триггер GIFT_COMPLETED у дарителя (user_id). Проверяем: существует ли среди
    получателей завершённых подарков user_id такой R, который сам когда-либо
    завершил подарок в адрес user_id.
    """
    # Получатели завершённых подарков текущего юзера
    my_recipients = (
        select(GiftBooking.recipient_user_id)
        .where(
            GiftBooking.booked_by_user_id == user_id,
            GiftBooking.status == GiftStatus.COMPLETED,
            GiftBooking.recipient_user_id.isnot(None),
        )
        .scalar_subquery()
    )
    has_boomerang = await db.scalar(
        select(
            exists().where(
                GiftBooking.status == GiftStatus.COMPLETED,
                GiftBooking.recipient_user_id == user_id,
                GiftBooking.booked_by_user_id.in_(my_recipients),
            )
        )
    )
    return EvalResult(unlocked=bool(has_boomerang))


async def _evaluate_j8_loved(
    db: AsyncSession,
    user_id: UUID,
    payload: dict[str, Any],
    unlocked_now: set[str],
) -> EvalResult:
    """Получил завершённые подарки от 3 разных дарителей."""
    count = await _count_distinct_gifters(db, user_id)
    return EvalResult(unlocked=count >= 3, progress=count, progress_target=3)


async def _evaluate_j9_santa(
    db: AsyncSession,
    user_id: UUID,
    payload: dict[str, Any],
    unlocked_now: set[str],
) -> EvalResult:
    """Подарок дошёл до адресата в новогоднее окно (25.12–14.01) по completed_at.

    Границы окна считаем по МСК (completed_at в БД — naive UTC): та же логика
    «настенного» времени, что и у временных пасхалок в eggs.py.
    """
    completed_msk = GiftBooking.completed_at + MSK_UTC_OFFSET
    m = extract("month", completed_msk)
    d = extract("day", completed_msk)
    winter = or_(and_(m == 12, d >= 25), and_(m == 1, d <= 14))
    has = await db.scalar(
        select(
            exists().where(
                GiftBooking.booked_by_user_id == user_id,
                GiftBooking.status == GiftStatus.COMPLETED,
                GiftBooking.completed_at.isnot(None),
                winter,
            )
        )
    )
    return EvalResult(unlocked=bool(has))


async def _evaluate_meta_gifts(
    db: AsyncSession,
    user_id: UUID,
    payload: dict[str, Any],
    unlocked_now: set[str],
) -> EvalResult:
    """Открывается, когда ядро серии (J2+J3+J4+J5) закрыто."""
    persisted = await db.execute(
        select(UserAchievement.code).where(
            UserAchievement.user_id == user_id,
            UserAchievement.code.in_(META_CORE),
            UserAchievement.is_unlocked.is_(True),
        )
    )
    unlocked = set(persisted.scalars().all()) | (unlocked_now & META_CORE)
    progress = len(unlocked)
    target = len(META_CORE)
    return EvalResult(
        unlocked=progress >= target, progress=progress, progress_target=target
    )


# META должна перепроверяться на любое событие серии.
_ALL_GIFT_TRIGGERS = (GIFT_BOOKED, GIFT_COMPLETED, GIFT_RECEIVED)


DEFINITIONS: list[AchievementDefinition] = [
    AchievementDefinition(
        code=J1_CODE,
        title_ru="Забронировал",
        description_ru="Забронируй первый подарок другу.",
        description_done_ru="Первый подарок забронирован.",
        series="gifts",
        tier=AchievementTier.SIMPLE,
        is_hidden=False,
        triggers=(GIFT_BOOKED,),
        evaluator=_evaluate_j1,
        icon_slug="j1_first_gift",
    ),
    AchievementDefinition(
        code=J2_CODE,
        title_ru="Долетело",
        description_ru="Первый подарок дошёл до адресата.",
        description_done_ru="Первый подарок доставлен.",
        series="gifts",
        tier=AchievementTier.SIMPLE,
        is_hidden=False,
        triggers=(GIFT_COMPLETED,),
        evaluator=_evaluate_j2,
        icon_slug="j2_gift_done",
    ),
    AchievementDefinition(
        code=J3_CODE,
        title_ru="Дарящая рука",
        description_ru="Заверши подарки 3 разным получателям.",
        description_done_ru="Подарки 3 получателям завершены.",
        series="gifts",
        tier=AchievementTier.NOTABLE,
        is_hidden=False,
        triggers=(GIFT_COMPLETED,),
        evaluator=_make_recipients_evaluator(3),
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
        evaluator=_make_recipients_evaluator(10),
        icon_slug="j4_ten_recipients",
    ),
    AchievementDefinition(
        code=J5_CODE,
        title_ru="С теплом",
        description_ru="Получи первый подарок.",
        description_done_ru="Первый подарок получен.",
        series="gifts",
        tier=AchievementTier.SIMPLE,
        is_hidden=False,
        triggers=(GIFT_RECEIVED,),
        evaluator=_evaluate_j5,
        icon_slug="j5_first_received",
    ),
    AchievementDefinition(
        code=J7_CODE,
        title_ru="Бумеранг",
        description_ru="Подари тому, кто раньше дарил тебе.",
        description_done_ru="Подарок ушёл тому, кто раньше дарил тебе.",
        series="gifts",
        tier=AchievementTier.RARE,
        is_hidden=False,
        triggers=(GIFT_COMPLETED,),
        evaluator=_evaluate_j7_boomerang,
        flavor_ru="Что отдал — то и вернулось.",
        icon_slug="j7_boomerang",
    ),
    AchievementDefinition(
        code=J8_CODE,
        title_ru="Любимчик",
        description_ru="Получи подарки от 3 разных дарителей.",
        description_done_ru="Подарки от 3 дарителей получены.",
        series="gifts",
        tier=AchievementTier.NOTABLE,
        is_hidden=False,
        triggers=(GIFT_RECEIVED,),
        evaluator=_evaluate_j8_loved,
        icon_slug="j8_loved",
    ),
    AchievementDefinition(
        code=J9_CODE,
        title_ru="Дед Мороз",
        description_ru="Подари в новогодние праздники (25.12–14.01).",
        description_done_ru="Новогодний подарок доставлен.",
        series="gifts",
        tier=AchievementTier.NOTABLE,
        is_hidden=False,
        triggers=(GIFT_COMPLETED,),
        evaluator=_evaluate_j9_santa,
        flavor_ru="Подарок под ёлку успел.",
        icon_slug="j9_santa",
    ),
    # META — последней в серии (порядок регистрации важен).
    AchievementDefinition(
        code=META_CODE,
        title_ru="Щедрость",
        description_ru="Закрой ядро серии «Дарящая рука».",
        description_done_ru="Ядро серии закрыто: подарок забронирован, доставлен, получен и роздан трём людям.",
        series="gifts",
        tier=AchievementTier.EPIC,
        is_hidden=False,
        triggers=_ALL_GIFT_TRIGGERS,
        evaluator=_evaluate_meta_gifts,
        is_meta=True,
        flavor_ru="Конверт уходит сам.",
        icon_slug="meta_gifts",
    ),
]
