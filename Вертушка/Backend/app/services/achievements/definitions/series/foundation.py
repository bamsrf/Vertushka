"""Серия «Первые шаги» (A* + META_foundation).

Phase 1: A1–A4 + META_foundation.
- A1: первая пластинка в коллекции
- A2: первая запись в вишлисте
- A3: установлен аватар
- A4: ссылкой на публичный профиль поделились
- META_foundation: все 4 открыты
"""
from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import select, exists
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.collection import Collection, CollectionItem
from app.models.profile_share import ProfileShare
from app.models.user import User
from app.models.user_achievement import UserAchievement
from app.models.wishlist import Wishlist, WishlistItem
from app.services.achievements.events import (
    AVATAR_SET,
    COLLECTION_ITEM_ADDED,
    PROFILE_SHARED_ENABLED,
    WISHLIST_ITEM_ADDED,
)
from app.services.achievements.registry import (
    AchievementDefinition,
    AchievementTier,
    EvalResult,
)


A1_CODE = "A1_first_record"
A2_CODE = "A2_first_wishlist"
A3_CODE = "A3_avatar_set"
A4_CODE = "A4_public_profile"
META_CODE = "META_foundation"
FOUNDATION_CODES = {A1_CODE, A2_CODE, A3_CODE, A4_CODE}


async def _evaluate_a1(
    db: AsyncSession,
    user_id: UUID,
    payload: dict[str, Any],
    unlocked_now: set[str],
) -> EvalResult:
    has_item = await db.scalar(
        select(
            exists().where(
                CollectionItem.collection_id == Collection.id,
                Collection.user_id == user_id,
            )
        )
    )
    return EvalResult(unlocked=bool(has_item))


async def _evaluate_a2(
    db: AsyncSession,
    user_id: UUID,
    payload: dict[str, Any],
    unlocked_now: set[str],
) -> EvalResult:
    has_item = await db.scalar(
        select(
            exists().where(
                WishlistItem.wishlist_id == Wishlist.id,
                Wishlist.user_id == user_id,
            )
        )
    )
    return EvalResult(unlocked=bool(has_item))


async def _evaluate_a3(
    db: AsyncSession,
    user_id: UUID,
    payload: dict[str, Any],
    unlocked_now: set[str],
) -> EvalResult:
    user = await db.scalar(select(User).where(User.id == user_id))
    return EvalResult(unlocked=bool(user and user.avatar_url))


async def _evaluate_a4(
    db: AsyncSession,
    user_id: UUID,
    payload: dict[str, Any],
    unlocked_now: set[str],
) -> EvalResult:
    """Открывается по факту отправки ссылки, а не по is_active.

    Публичность включена у всех с регистрации (server_default="true"), так
    что is_active истинен всегда и ачивка на нём была бы бесплатной. Ловим
    осознанное действие: shared_at ставит POST /profile/share из кнопок
    «Поделиться» и «Копировать ссылку».
    """
    share = await db.scalar(
        select(ProfileShare).where(ProfileShare.user_id == user_id)
    )
    return EvalResult(unlocked=bool(share and share.shared_at))


async def _evaluate_meta_foundation(
    db: AsyncSession,
    user_id: UUID,
    payload: dict[str, Any],
    unlocked_now: set[str],
) -> EvalResult:
    """Открывается, когда все A1–A4 уже unlocked.

    Учитывает ачивки, открытые ровно в этом же emit_event (unlocked_now),
    плюс уже сохранённые в БД.
    """
    persisted = await db.execute(
        select(UserAchievement.code).where(
            UserAchievement.user_id == user_id,
            UserAchievement.code.in_(FOUNDATION_CODES),
            UserAchievement.is_unlocked.is_(True),
        )
    )
    persisted_codes = set(persisted.scalars().all())
    all_unlocked = persisted_codes | (unlocked_now & FOUNDATION_CODES)
    progress = len(all_unlocked)
    target = len(FOUNDATION_CODES)
    if progress >= target:
        return EvalResult(unlocked=True, progress=progress, progress_target=target)
    return EvalResult(progress=progress, progress_target=target)


# META должна перепроверяться на любое событие из A-серии
_ALL_FOUNDATION_TRIGGERS = (
    COLLECTION_ITEM_ADDED,
    WISHLIST_ITEM_ADDED,
    AVATAR_SET,
    PROFILE_SHARED_ENABLED,
)


DEFINITIONS: list[AchievementDefinition] = [
    AchievementDefinition(
        code=A1_CODE,
        title_ru="Поехали",
        description_ru="Добавь первую пластинку в коллекцию.",
        description_done_ru="Первая пластинка в коллекции.",
        series="foundation",
        tier=AchievementTier.SIMPLE,
        is_hidden=False,
        triggers=(COLLECTION_ITEM_ADDED,),
        evaluator=_evaluate_a1,
        flavor_ru="Первая дорожка проиграна. С неё начинается всё.",
        icon_slug="a1_first_record",
    ),
    AchievementDefinition(
        code=A2_CODE,
        title_ru="Хотелка",
        description_ru="Добавь первую запись в вишлист.",
        description_done_ru="Первая запись в вишлисте.",
        series="foundation",
        tier=AchievementTier.SIMPLE,
        is_hidden=False,
        triggers=(WISHLIST_ITEM_ADDED,),
        evaluator=_evaluate_a2,
        icon_slug="a2_first_wishlist",
    ),
    AchievementDefinition(
        code=A3_CODE,
        title_ru="Аватар",
        description_ru="Поставь аватар.",
        description_done_ru="Аватар поставлен.",
        series="foundation",
        tier=AchievementTier.SIMPLE,
        is_hidden=False,
        triggers=(AVATAR_SET,),
        evaluator=_evaluate_a3,
        icon_slug="a3_avatar",
    ),
    AchievementDefinition(
        code=A4_CODE,
        title_ru="Распахнул",
        description_ru="Поделись ссылкой на свой профиль.",
        description_done_ru="Ссылкой на профиль поделились.",
        series="foundation",
        tier=AchievementTier.SIMPLE,
        is_hidden=False,
        triggers=(PROFILE_SHARED_ENABLED,),
        evaluator=_evaluate_a4,
        icon_slug="a4_public_profile",
    ),
    # META — всегда последний, на все события серии
    AchievementDefinition(
        code=META_CODE,
        title_ru="На борту",
        description_ru="Открой все ачивки серии «Первые шаги».",
        description_done_ru="Все ачивки «Первых шагов» открыты.",
        series="foundation",
        tier=AchievementTier.NOTABLE,
        is_hidden=False,
        triggers=_ALL_FOUNDATION_TRIGGERS,
        evaluator=_evaluate_meta_foundation,
        is_meta=True,
        flavor_ru="Канавки услышали тебя.",
        icon_slug="meta_foundation",
    ),
]
