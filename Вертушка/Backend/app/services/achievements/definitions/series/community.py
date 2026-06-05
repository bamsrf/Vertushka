"""Серия «Сообщество» (K*).

Phase 1: K1-K7 + META_community.

Анти-фарм для K3/K4/K7:
- Фолловер должен иметь ≥10 пластинок в коллекции.
- Аккаунт фолловера старше 30 дней.
K2 (первый фолловер) — без анти-фарма, ачивка слабая и one-off.
K5/K6 (просмотры публичного профиля) — view_count из ProfileShare. Сам себе
view не инкрементится в API, фарм сложен.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import func, select, exists, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.collection import Collection, CollectionItem
from app.models.follow import Follow
from app.models.profile_share import ProfileShare
from app.models.user import User
from app.models.user_achievement import UserAchievement
from app.services.achievements.events import (
    DAILY_TICK,
    FOLLOW_CREATED,
    FOLLOW_RECEIVED,
    PROFILE_VIEW,
)
from app.services.achievements.registry import (
    AchievementDefinition,
    AchievementTier,
    EvalResult,
)


K1_CODE = "K1_following_x5"
K2_CODE = "K2_first_follower"
K3_CODE = "K3_followers_x5"
K4_CODE = "K4_followers_x50"
K5_CODE = "K5_views_x100"
K6_CODE = "K6_views_x1000"
K7_CODE = "K7_mutual_x10"
META_CODE = "META_community"
COMMUNITY_CODES = {K1_CODE, K2_CODE, K3_CODE, K4_CODE, K5_CODE, K6_CODE, K7_CODE}

ANTIFARM_MIN_RECORDS = 10
ANTIFARM_MIN_AGE = timedelta(days=30)


def _quality_follower_subquery(direction: str):
    """SELECT user_id для качественных фолловеров.

    direction='follower'  → return User table joined with anti-farm filters.
    Использовать .where(Follow.<col>.in_(qualified_subq)).
    """
    cutoff = datetime.utcnow() - ANTIFARM_MIN_AGE
    records_per_user = (
        select(
            Collection.user_id.label("u"),
            func.count(func.distinct(CollectionItem.record_id)).label("c"),
        )
        .join(CollectionItem, CollectionItem.collection_id == Collection.id)
        .group_by(Collection.user_id)
        .subquery()
    )
    qualified = (
        select(User.id)
        .join(records_per_user, records_per_user.c.u == User.id, isouter=False)
        .where(
            User.is_active.is_(True),
            User.created_at <= cutoff,
            records_per_user.c.c >= ANTIFARM_MIN_RECORDS,
        )
    )
    return qualified


async def _evaluate_k1(
    db: AsyncSession,
    user_id: UUID,
    payload: dict[str, Any],
    unlocked_now: set[str],
) -> EvalResult:
    """Подписан на 5 разных коллекций. Без анти-фарма — это активность самого
    юзера."""
    count = await db.scalar(
        select(func.count(func.distinct(Follow.following_id)))
        .where(Follow.follower_id == user_id)
    )
    count = int(count or 0)
    if count >= 5:
        return EvalResult(unlocked=True, progress=count, progress_target=5)
    return EvalResult(progress=count, progress_target=5)


async def _evaluate_k2(
    db: AsyncSession,
    user_id: UUID,
    payload: dict[str, Any],
    unlocked_now: set[str],
) -> EvalResult:
    """Первый подписчик — без анти-фарма (1 шт всё равно слабо фармить)."""
    has = await db.scalar(
        select(exists().where(Follow.following_id == user_id))
    )
    return EvalResult(unlocked=bool(has))


async def _count_quality_followers(db: AsyncSession, user_id: UUID) -> int:
    qualified = _quality_follower_subquery("follower")
    count = await db.scalar(
        select(func.count(func.distinct(Follow.follower_id)))
        .where(
            Follow.following_id == user_id,
            Follow.follower_id.in_(qualified),
        )
    )
    return int(count or 0)


def _make_followers_evaluator(threshold: int):
    async def evaluator(
        db: AsyncSession,
        user_id: UUID,
        payload: dict[str, Any],
        unlocked_now: set[str],
    ) -> EvalResult:
        count = await _count_quality_followers(db, user_id)
        if count >= threshold:
            return EvalResult(unlocked=True, progress=count, progress_target=threshold)
        return EvalResult(progress=count, progress_target=threshold)
    return evaluator


def _make_views_evaluator(threshold: int):
    async def evaluator(
        db: AsyncSession,
        user_id: UUID,
        payload: dict[str, Any],
        unlocked_now: set[str],
    ) -> EvalResult:
        share = await db.scalar(
            select(ProfileShare).where(ProfileShare.user_id == user_id)
        )
        count = int(share.view_count) if share else 0
        if count >= threshold:
            return EvalResult(unlocked=True, progress=count, progress_target=threshold)
        return EvalResult(progress=count, progress_target=threshold)
    return evaluator


async def _evaluate_k7_mutual(
    db: AsyncSession,
    user_id: UUID,
    payload: dict[str, Any],
    unlocked_now: set[str],
) -> EvalResult:
    """Взаимные подписки: A→B И B→A, оба учитываются 1 раз.

    Анти-фарм: B должен пройти качество (≥10 пластинок, аккаунт ≥30 дней).
    """
    qualified = _quality_follower_subquery("follower")
    # Подписки текущего юзера на качественных
    out_subq = (
        select(Follow.following_id)
        .where(
            Follow.follower_id == user_id,
            Follow.following_id.in_(qualified),
        )
        .subquery()
    )
    # Из них — те, кто подписан на нас
    count = await db.scalar(
        select(func.count(func.distinct(Follow.follower_id)))
        .where(
            Follow.following_id == user_id,
            Follow.follower_id.in_(select(out_subq.c.following_id)),
        )
    )
    count = int(count or 0)
    if count >= 10:
        return EvalResult(unlocked=True, progress=count, progress_target=10)
    return EvalResult(progress=count, progress_target=10)


async def _evaluate_meta_community(
    db: AsyncSession,
    user_id: UUID,
    payload: dict[str, Any],
    unlocked_now: set[str],
) -> EvalResult:
    """Закрывается, когда открыты K4 + K6 + K7 (топовые в трёх ветках:
    подписчики, просмотры, взаимность). Остальные K — бонус."""
    needed = {K4_CODE, K6_CODE, K7_CODE}
    persisted = await db.execute(
        select(UserAchievement.code).where(
            UserAchievement.user_id == user_id,
            UserAchievement.code.in_(needed),
            UserAchievement.is_unlocked.is_(True),
        )
    )
    persisted_codes = set(persisted.scalars().all())
    all_unlocked = persisted_codes | (unlocked_now & needed)
    progress = len(all_unlocked)
    target = len(needed)
    if progress >= target:
        return EvalResult(unlocked=True, progress=progress, progress_target=target)
    return EvalResult(progress=progress, progress_target=target)


_COMMUNITY_TRIGGERS = (
    FOLLOW_CREATED,
    FOLLOW_RECEIVED,
    PROFILE_VIEW,
    DAILY_TICK,
)


DEFINITIONS: list[AchievementDefinition] = [
    AchievementDefinition(
        code=K1_CODE,
        title_ru="Любопытный",
        description_ru="Подпишись на 5 коллекций.",
        description_done_ru="5 коллекций в подписках.",
        series="community",
        tier=AchievementTier.SIMPLE,
        is_hidden=False,
        triggers=(FOLLOW_CREATED, DAILY_TICK),
        evaluator=_evaluate_k1,
        icon_slug="k1_following_x5",
    ),
    AchievementDefinition(
        code=K2_CODE,
        title_ru="Услышали",
        description_ru="На тебя подписался первый пользователь.",
        description_done_ru="Первый подписчик появился.",
        series="community",
        tier=AchievementTier.SIMPLE,
        is_hidden=False,
        triggers=(FOLLOW_RECEIVED,),
        evaluator=_evaluate_k2,
        icon_slug="k2_first_follower",
    ),
    AchievementDefinition(
        code=K3_CODE,
        title_ru="Услышан",
        description_ru="5 подписчиков с реальными коллекциями.",
        description_done_ru="5 подписчиков с коллекциями набрано.",
        series="community",
        tier=AchievementTier.SIMPLE,
        is_hidden=False,
        triggers=(FOLLOW_RECEIVED, DAILY_TICK),
        evaluator=_make_followers_evaluator(5),
        icon_slug="k3_followers_x5",
    ),
    AchievementDefinition(
        code=K4_CODE,
        title_ru="Голос сцены",
        description_ru="50 подписчиков с реальными коллекциями.",
        description_done_ru="50 подписчиков с коллекциями набрано.",
        series="community",
        tier=AchievementTier.RARE,
        is_hidden=False,
        triggers=(FOLLOW_RECEIVED, DAILY_TICK),
        evaluator=_make_followers_evaluator(50),
        icon_slug="k4_followers_x50",
    ),
    AchievementDefinition(
        code=K5_CODE,
        title_ru="Витрина",
        description_ru="Публичный профиль просмотрели 100 раз.",
        description_done_ru="100 просмотров профиля набрано.",
        series="community",
        tier=AchievementTier.NOTABLE,
        is_hidden=False,
        triggers=(PROFILE_VIEW, DAILY_TICK),
        evaluator=_make_views_evaluator(100),
        icon_slug="k5_views_x100",
    ),
    AchievementDefinition(
        code=K6_CODE,
        title_ru="На главной",
        description_ru="1 000 просмотров публичного профиля.",
        description_done_ru="1 000 просмотров профиля набрано.",
        series="community",
        tier=AchievementTier.RARE,
        is_hidden=False,
        triggers=(PROFILE_VIEW, DAILY_TICK),
        evaluator=_make_views_evaluator(1000),
        icon_slug="k6_views_x1000",
    ),
    AchievementDefinition(
        code=K7_CODE,
        title_ru="Взаимность",
        description_ru="10 взаимных подписок с реальными юзерами.",
        description_done_ru="10 взаимных подписок набрано.",
        series="community",
        tier=AchievementTier.NOTABLE,
        is_hidden=False,
        triggers=(FOLLOW_CREATED, FOLLOW_RECEIVED, DAILY_TICK),
        evaluator=_evaluate_k7_mutual,
        icon_slug="k7_mutual_x10",
    ),
    AchievementDefinition(
        code=META_CODE,
        title_ru="Резидент",
        description_ru="Закрой K4, K6 и K7 — главные ветки сообщества.",
        description_done_ru="K4, K6 и K7 закрыты.",
        series="community",
        tier=AchievementTier.EPIC,
        is_hidden=False,
        triggers=_COMMUNITY_TRIGGERS,
        evaluator=_evaluate_meta_community,
        is_meta=True,
        icon_slug="meta_community",
    ),
]
