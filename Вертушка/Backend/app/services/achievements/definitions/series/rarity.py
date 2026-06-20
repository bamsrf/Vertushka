"""Серия «Охота за редкостями» (C* + META_rarity).

Phase 3 (реализовано): считает по флагам редкости на `Record`
(`is_limited`, `is_collectible`, `is_hot`), которые проставляет
`DiscogsService._compute_rarity_flags` при создании/обогащении релиза.

Анти-фарм для коллекционных порогов — тот же 24h-cooldown и только основная
коллекция, что в B-серии. Вишлист (C6) считается «как сейчас», без cooldown.

Состав (см. PLAN_ACHIEVEMENTS_V2.md §4.3):
- C1 «Тираж ограничен» (5 лимиток)
- C2 «По счёту»       (25 лимиток)
- C3 «Сокровище»      (1 коллекционка)
- C4 «Шкаф редкостей» (5 коллекционок)
- C5 «Кладовая»       (15 коллекционок)
- C6 «Хочу горячего»  (5 hot одновременно в вишлисте)
- C7 «Тренд на полке» (10 hot в коллекции)
- META_rarity «Грааль» (C2 + C5 + C7)
"""
from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.collection import Collection, CollectionItem
from app.models.record import Record
from app.models.user_achievement import UserAchievement
from app.models.wishlist import Wishlist, WishlistItem
from app.services.achievements.events import (
    COLLECTION_ITEM_ADDED,
    DAILY_TICK,
    WISHLIST_ITEM_ADDED,
)
from app.services.achievements.registry import (
    AchievementDefinition,
    AchievementTier,
    EvalResult,
)


C1_CODE = "C1_limited_x5"
C2_CODE = "C2_limited_x25"
C3_CODE = "C3_collectible_x1"
C4_CODE = "C4_collectible_x5"
C5_CODE = "C5_collectible_x15"
C6_CODE = "C6_hot_in_wishlist"
C7_CODE = "C7_hot_in_collection"
META_CODE = "META_rarity"
RARITY_CODES = {C1_CODE, C2_CODE, C3_CODE, C4_CODE, C5_CODE, C6_CODE, C7_CODE}


def _default_collection_id(user_id: UUID):
    return (
        select(Collection.id)
        .where(Collection.user_id == user_id)
        .order_by(Collection.sort_order, Collection.created_at)
        .limit(1)
        .scalar_subquery()
    )


async def _count_flagged_in_collection(
    db: AsyncSession, user_id: UUID, flag_col
) -> int:
    """COUNT(DISTINCT record_id) в основной коллекции, у которых данный флаг
    редкости = True.

    Без 24ч-cooldown (в отличие от B-серии): редкость — внутренний флаг релиза,
    его не накрутишь массовым добавлением, поэтому отклик мгновенный."""
    count = await db.scalar(
        select(func.count(func.distinct(CollectionItem.record_id)))
        .join(Record, Record.id == CollectionItem.record_id)
        .where(
            CollectionItem.collection_id == _default_collection_id(user_id),
            flag_col.is_(True),
        )
    )
    return int(count or 0)


async def _count_hot_in_wishlist(db: AsyncSession, user_id: UUID) -> int:
    """Сколько hot-пластинок одновременно в вишлисте юзера (без cooldown —
    это снимок текущего состояния)."""
    count = await db.scalar(
        select(func.count(func.distinct(WishlistItem.record_id)))
        .join(Wishlist, Wishlist.id == WishlistItem.wishlist_id)
        .join(Record, Record.id == WishlistItem.record_id)
        .where(Wishlist.user_id == user_id, Record.is_hot.is_(True))
    )
    return int(count or 0)


def _make_collection_flag_evaluator(flag_col, threshold: int):
    async def evaluator(
        db: AsyncSession,
        user_id: UUID,
        payload: dict[str, Any],
        unlocked_now: set[str],
    ) -> EvalResult:
        count = await _count_flagged_in_collection(db, user_id, flag_col)
        if count >= threshold:
            return EvalResult(unlocked=True, progress=count, progress_target=threshold)
        return EvalResult(progress=count, progress_target=threshold)
    return evaluator


async def _evaluate_c6_hot_wishlist(
    db: AsyncSession,
    user_id: UUID,
    payload: dict[str, Any],
    unlocked_now: set[str],
) -> EvalResult:
    count = await _count_hot_in_wishlist(db, user_id)
    if count >= 5:
        return EvalResult(unlocked=True, progress=count, progress_target=5)
    return EvalResult(progress=count, progress_target=5)


async def _evaluate_meta_rarity(
    db: AsyncSession,
    user_id: UUID,
    payload: dict[str, Any],
    unlocked_now: set[str],
) -> EvalResult:
    """C2 + C5 + C7."""
    needed = {C2_CODE, C5_CODE, C7_CODE}
    persisted = await db.execute(
        select(UserAchievement.code).where(
            UserAchievement.user_id == user_id,
            UserAchievement.code.in_(needed),
            UserAchievement.is_unlocked.is_(True),
        )
    )
    have = set(persisted.scalars().all()) | (unlocked_now & needed)
    progress = len(have)
    target = len(needed)
    if progress >= target:
        return EvalResult(unlocked=True, progress=progress, progress_target=target)
    return EvalResult(progress=progress, progress_target=target)


_COLLECTION_TRIGGERS = (COLLECTION_ITEM_ADDED, DAILY_TICK)
_WISHLIST_TRIGGERS = (WISHLIST_ITEM_ADDED, DAILY_TICK)


DEFINITIONS: list[AchievementDefinition] = [
    AchievementDefinition(
        code=C1_CODE,
        title_ru="Тираж ограничен",
        description_ru="Добавь 5 лимиток в коллекцию.",
        description_done_ru="5 лимиток в коллекции.",
        series="rarity",
        tier=AchievementTier.SIMPLE,
        is_hidden=False,
        triggers=_COLLECTION_TRIGGERS,
        evaluator=_make_collection_flag_evaluator(Record.is_limited, 5),
        icon_slug="c1_limited_x5",
    ),
    AchievementDefinition(
        code=C2_CODE,
        title_ru="По счёту",
        description_ru="Добери 25 лимиток.",
        description_done_ru="25 лимиток собрано.",
        series="rarity",
        tier=AchievementTier.RARE,
        is_hidden=False,
        triggers=_COLLECTION_TRIGGERS,
        evaluator=_make_collection_flag_evaluator(Record.is_limited, 25),
        icon_slug="c2_limited_x25",
    ),
    AchievementDefinition(
        code=C3_CODE,
        title_ru="Сокровище",
        description_ru="Найди первую коллекционку.",
        description_done_ru="Первая коллекционка найдена.",
        series="rarity",
        tier=AchievementTier.NOTABLE,
        is_hidden=False,
        triggers=_COLLECTION_TRIGGERS,
        evaluator=_make_collection_flag_evaluator(Record.is_collectible, 1),
        icon_slug="c3_collectible_x1",
    ),
    AchievementDefinition(
        code=C4_CODE,
        title_ru="Шкаф редкостей",
        description_ru="5 коллекционок на полке.",
        description_done_ru="5 коллекционок на полке.",
        series="rarity",
        tier=AchievementTier.RARE,
        is_hidden=False,
        triggers=_COLLECTION_TRIGGERS,
        evaluator=_make_collection_flag_evaluator(Record.is_collectible, 5),
        icon_slug="c4_collectible_x5",
    ),
    AchievementDefinition(
        code=C5_CODE,
        title_ru="Кладовая",
        description_ru="15 коллекционок.",
        description_done_ru="15 коллекционок собрано.",
        series="rarity",
        tier=AchievementTier.EPIC,
        is_hidden=False,
        triggers=_COLLECTION_TRIGGERS,
        evaluator=_make_collection_flag_evaluator(Record.is_collectible, 15),
        icon_slug="c5_collectible_x15",
    ),
    AchievementDefinition(
        code=C6_CODE,
        title_ru="Хочу горячего",
        description_ru="5 горячих пластинок одновременно в вишлисте.",
        description_done_ru="5 горячих пластинок в вишлисте.",
        series="rarity",
        tier=AchievementTier.NOTABLE,
        is_hidden=False,
        triggers=_WISHLIST_TRIGGERS,
        evaluator=_evaluate_c6_hot_wishlist,
        icon_slug="c6_hot_in_wishlist",
    ),
    AchievementDefinition(
        code=C7_CODE,
        title_ru="Тренд на полке",
        description_ru="10 горячих пластинок в коллекции.",
        description_done_ru="10 горячих пластинок в коллекции.",
        series="rarity",
        tier=AchievementTier.RARE,
        is_hidden=False,
        triggers=_COLLECTION_TRIGGERS,
        evaluator=_make_collection_flag_evaluator(Record.is_hot, 10),
        icon_slug="c7_hot_in_collection",
    ),
    AchievementDefinition(
        code=META_CODE,
        title_ru="Грааль",
        description_ru="Открой C2 + C5 + C7.",
        description_done_ru="C2, C5 и C7 открыты.",
        series="rarity",
        tier=AchievementTier.EPIC,
        is_hidden=False,
        triggers=(COLLECTION_ITEM_ADDED, WISHLIST_ITEM_ADDED, DAILY_TICK),
        evaluator=_evaluate_meta_rarity,
        is_meta=True,
        flavor_ru="Не каждая полка дотянет.",
        icon_slug="meta_rarity",
    ),
]
