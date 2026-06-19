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
from app.models.conversation import Message
from app.models.follow import Follow
from app.models.profile_share import ProfileShare
from app.models.record import Record
from app.models.user import User
from app.models.user_achievement import UserAchievement
from app.models.wishlist import Wishlist, WishlistItem
from app.services.achievements.events import (
    COLLECTION_ITEM_ADDED,
    DAILY_TICK,
    FOLLOW_CREATED,
    FOLLOW_RECEIVED,
    MESSAGE_SENT,
    PROFILE_VIEW,
    RECORD_WANTED,
    USER_RECORD_CREATED,
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
# Трек 2 — вклад (ручные релизы)
K8_CODE = "K8_contrib_x1"
K9_CODE = "K9_contrib_x5"
K10_CODE = "K10_contrib_x20"
# Трек 3 — сообщения
K11_CODE = "K11_msgs_x10"
K12_CODE = "K12_msgs_x50"
K13_CODE = "K13_msgs_x200"
# Трек 4 — твои записи хотят другие
K14_CODE = "K14_wanted_x1"
K15_CODE = "K15_wanted_x5"
K16_CODE = "K16_wanted_x10"
# Трек 5 — первым добавил релиз на платформу
K17_CODE = "K17_pioneer_x1"
K18_CODE = "K18_pioneer_x5"
K19_CODE = "K19_pioneer_x10"
K20_CODE = "K20_pioneer_x50"
META_CODE = "META_community"
COMMUNITY_CODES = {
    K1_CODE, K2_CODE, K3_CODE, K4_CODE, K5_CODE, K6_CODE, K7_CODE,
    K8_CODE, K9_CODE, K10_CODE, K11_CODE, K12_CODE, K13_CODE,
    K14_CODE, K15_CODE, K16_CODE, K17_CODE, K18_CODE, K19_CODE, K20_CODE,
}

# K14 — твоя пластинка должна быть в вишлисте у стольких РАЗНЫХ людей
WANTED_K14_MIN_WISHERS = 3

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


def _owned_records_subquery(user_id: UUID):
    """DISTINCT record_id во всех коллекциях юзера. Для треков 4/5."""
    return (
        select(func.distinct(CollectionItem.record_id))
        .join(Collection, Collection.id == CollectionItem.collection_id)
        .where(Collection.user_id == user_id)
    )


def _make_contrib_evaluator(threshold: int):
    """Трек 2 — одобренные ручные релизы (source='user'). Без анти-фарма:
    каждая запись проходит создание вручную, дубли по мастеру отсекаются на
    уровне UI/preflight."""
    async def evaluator(
        db: AsyncSession,
        user_id: UUID,
        payload: dict[str, Any],
        unlocked_now: set[str],
    ) -> EvalResult:
        count = await db.scalar(
            select(func.count(func.distinct(Record.id))).where(
                Record.source == "user",
                Record.created_by_user_id == user_id,
                Record.moderation_status == "approved",
            )
        )
        count = int(count or 0)
        if count >= threshold:
            return EvalResult(unlocked=True, progress=count, progress_target=threshold)
        return EvalResult(progress=count, progress_target=threshold)
    return evaluator


def _make_messages_evaluator(threshold: int):
    """Трек 3 — отправленные сообщения (живые, не soft-deleted)."""
    async def evaluator(
        db: AsyncSession,
        user_id: UUID,
        payload: dict[str, Any],
        unlocked_now: set[str],
    ) -> EvalResult:
        count = await db.scalar(
            select(func.count(Message.id)).where(
                Message.sender_id == user_id,
                Message.deleted_at.is_(None),
            )
        )
        count = int(count or 0)
        if count >= threshold:
            return EvalResult(unlocked=True, progress=count, progress_target=threshold)
        return EvalResult(progress=count, progress_target=threshold)
    return evaluator


async def _evaluate_k14_wanted(
    db: AsyncSession,
    user_id: UUID,
    payload: dict[str, Any],
    unlocked_now: set[str],
) -> EvalResult:
    """Хотя бы 1 пластинка из коллекции юзера лежит в вишлисте у ≥3 РАЗНЫХ
    других людей."""
    owned = _owned_records_subquery(user_id).subquery()
    wishers = await db.scalar(
        select(func.count())
        .select_from(
            select(WishlistItem.record_id)
            .join(Wishlist, Wishlist.id == WishlistItem.wishlist_id)
            .where(
                Wishlist.user_id != user_id,
                WishlistItem.record_id.in_(select(owned)),
            )
            .group_by(WishlistItem.record_id)
            .having(
                func.count(func.distinct(Wishlist.user_id)) >= WANTED_K14_MIN_WISHERS
            )
            .subquery()
        )
    )
    has = int(wishers or 0) > 0
    return EvalResult(unlocked=has, progress=1 if has else 0, progress_target=1)


def _make_wanted_count_evaluator(threshold: int):
    """Треки 4 (K15/K16) — сколько РАЗНЫХ пластинок юзера хотят другие
    (каждая ≥1 чужим вишлистом)."""
    async def evaluator(
        db: AsyncSession,
        user_id: UUID,
        payload: dict[str, Any],
        unlocked_now: set[str],
    ) -> EvalResult:
        owned = _owned_records_subquery(user_id).subquery()
        count = await db.scalar(
            select(func.count(func.distinct(WishlistItem.record_id)))
            .join(Wishlist, Wishlist.id == WishlistItem.wishlist_id)
            .where(
                Wishlist.user_id != user_id,
                WishlistItem.record_id.in_(select(owned)),
            )
        )
        count = int(count or 0)
        if count >= threshold:
            return EvalResult(unlocked=True, progress=count, progress_target=threshold)
        return EvalResult(progress=count, progress_target=threshold)
    return evaluator


def _make_pioneer_evaluator(threshold: int):
    """Трек 5 — сколько релизов юзер добавил в коллекцию ПЕРВЫМ на платформе.

    Юзер «первый», если его самое раннее добавление record_id не позже
    глобального самого раннего добавления того же record_id (ties → юзер
    засчитывается)."""
    async def evaluator(
        db: AsyncSession,
        user_id: UUID,
        payload: dict[str, Any],
        unlocked_now: set[str],
    ) -> EvalResult:
        user_first = (
            select(
                CollectionItem.record_id.label("rid"),
                func.min(CollectionItem.added_at).label("u_first"),
            )
            .join(Collection, Collection.id == CollectionItem.collection_id)
            .where(Collection.user_id == user_id)
            .group_by(CollectionItem.record_id)
            .subquery()
        )
        global_first = (
            select(
                CollectionItem.record_id.label("rid"),
                func.min(CollectionItem.added_at).label("g_first"),
            )
            .group_by(CollectionItem.record_id)
            .subquery()
        )
        count = await db.scalar(
            select(func.count())
            .select_from(user_first)
            .join(global_first, global_first.c.rid == user_first.c.rid)
            .where(user_first.c.u_first <= global_first.c.g_first)
        )
        count = int(count or 0)
        if count >= threshold:
            return EvalResult(unlocked=True, progress=count, progress_target=threshold)
        return EvalResult(progress=count, progress_target=threshold)
    return evaluator


async def _evaluate_meta_community(
    db: AsyncSession,
    user_id: UUID,
    payload: dict[str, Any],
    unlocked_now: set[str],
) -> EvalResult:
    """Закрывается, когда открыты K4 + K7 + K16 (топовые в трёх ветках:
    подписчики, взаимность, спрос на коллекцию). Остальные K — бонус.

    K6 (просмотры) выпилен из требований с v2.1 — просмотры скрыты."""
    needed = {K4_CODE, K7_CODE, K16_CODE}
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
    RECORD_WANTED,
    DAILY_TICK,
)


DEFINITIONS: list[AchievementDefinition] = [
    # ── Трек 1 — подписки/подписчики (сцена) ──────────────────────────── #
    AchievementDefinition(
        code=K1_CODE,
        title_ru="Зритель",
        description_ru="Подпишись на 5 пользователей.",
        description_done_ru="5 пользователей в подписках.",
        series="community",
        tier=AchievementTier.SIMPLE,
        is_hidden=False,
        triggers=(FOLLOW_CREATED, DAILY_TICK),
        evaluator=_evaluate_k1,
        icon_slug="k1_following_x5",
    ),
    AchievementDefinition(
        code=K2_CODE,
        title_ru="Первый ряд",
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
        title_ru="Квартирник",
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
        title_ru="Хедлайнер",
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
        code=K7_CODE,
        title_ru="Бэкстейдж",
        description_ru="10 взаимных подписок с реальными юзерами.",
        description_done_ru="10 взаимных подписок набрано.",
        series="community",
        tier=AchievementTier.NOTABLE,
        is_hidden=False,
        triggers=(FOLLOW_CREATED, FOLLOW_RECEIVED, DAILY_TICK),
        evaluator=_evaluate_k7_mutual,
        icon_slug="k7_mutual_x10",
    ),
    # ── СКРЫТЫ (v2.1): просмотры профиля. Подсчёт ненадёжен (боты, self-view).
    # Не удалены, чтобы не терять прогресс/историю — просто is_hidden=True.
    AchievementDefinition(
        code=K5_CODE,
        title_ru="Витрина",
        description_ru="Публичный профиль просмотрели 100 раз.",
        description_done_ru="100 просмотров профиля набрано.",
        series="community",
        tier=AchievementTier.NOTABLE,
        is_hidden=True,
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
        is_hidden=True,
        triggers=(PROFILE_VIEW, DAILY_TICK),
        evaluator=_make_views_evaluator(1000),
        icon_slug="k6_views_x1000",
    ),
    # ── Трек 2 — вклад (ручные релизы) ────────────────────────────────── #
    AchievementDefinition(
        code=K8_CODE,
        title_ru="Стажёр",
        description_ru="Добавь первый одобренный релиз вручную.",
        description_done_ru="Первый ручной релиз доставлен.",
        series="community",
        tier=AchievementTier.SIMPLE,
        is_hidden=False,
        triggers=(USER_RECORD_CREATED, DAILY_TICK),
        evaluator=_make_contrib_evaluator(1),
        icon_slug="k8_contrib_x1",
    ),
    AchievementDefinition(
        code=K9_CODE,
        title_ru="Поставщик",
        description_ru="5 одобренных ручных релизов.",
        description_done_ru="5 ручных релизов доставлено.",
        series="community",
        tier=AchievementTier.NOTABLE,
        is_hidden=False,
        triggers=(USER_RECORD_CREATED, DAILY_TICK),
        evaluator=_make_contrib_evaluator(5),
        icon_slug="k9_contrib_x5",
    ),
    AchievementDefinition(
        code=K10_CODE,
        title_ru="Да, шеф!",
        description_ru="20 одобренных ручных релизов.",
        description_done_ru="20 ручных релизов доставлено.",
        series="community",
        tier=AchievementTier.RARE,
        is_hidden=False,
        triggers=(USER_RECORD_CREATED, DAILY_TICK),
        evaluator=_make_contrib_evaluator(20),
        icon_slug="k10_contrib_x20",
    ),
    # ── Трек 3 — сообщения ────────────────────────────────────────────── #
    AchievementDefinition(
        code=K11_CODE,
        title_ru="Есть контакт",
        description_ru="Отправь 10 сообщений.",
        description_done_ru="10 сообщений отправлено.",
        series="community",
        tier=AchievementTier.SIMPLE,
        is_hidden=False,
        triggers=(MESSAGE_SENT, DAILY_TICK),
        evaluator=_make_messages_evaluator(10),
        icon_slug="k11_msgs_x10",
    ),
    AchievementDefinition(
        code=K12_CODE,
        title_ru="Продажник",
        description_ru="Отправь 50 сообщений.",
        description_done_ru="50 сообщений отправлено.",
        series="community",
        tier=AchievementTier.NOTABLE,
        is_hidden=False,
        triggers=(MESSAGE_SENT, DAILY_TICK),
        evaluator=_make_messages_evaluator(50),
        icon_slug="k12_msgs_x50",
    ),
    AchievementDefinition(
        code=K13_CODE,
        title_ru="Уолл-стрит",
        description_ru="Отправь 200 сообщений.",
        description_done_ru="200 сообщений отправлено.",
        series="community",
        tier=AchievementTier.RARE,
        is_hidden=False,
        triggers=(MESSAGE_SENT, DAILY_TICK),
        evaluator=_make_messages_evaluator(200),
        icon_slug="k13_msgs_x200",
    ),
    # ── Трек 4 — твои записи хотят другие ─────────────────────────────── #
    AchievementDefinition(
        code=K14_CODE,
        title_ru="За витриной",
        description_ru="Одна твоя пластинка попала в вишлист к 3 людям.",
        description_done_ru="Твою пластинку хотят сразу трое.",
        series="community",
        tier=AchievementTier.NOTABLE,
        is_hidden=False,
        triggers=(RECORD_WANTED, DAILY_TICK),
        evaluator=_evaluate_k14_wanted,
        icon_slug="k14_wanted_x1",
    ),
    AchievementDefinition(
        code=K15_CODE,
        title_ru="Шоурум",
        description_ru="5 твоих пластинок хотят другие.",
        description_done_ru="5 твоих пластинок в чужих вишлистах.",
        series="community",
        tier=AchievementTier.RARE,
        is_hidden=False,
        triggers=(RECORD_WANTED, DAILY_TICK),
        evaluator=_make_wanted_count_evaluator(5),
        icon_slug="k15_wanted_x5",
    ),
    AchievementDefinition(
        code=K16_CODE,
        title_ru="Личный Санта",
        description_ru="10 твоих пластинок хотят другие.",
        description_done_ru="10 твоих пластинок в чужих вишлистах.",
        series="community",
        tier=AchievementTier.RARE,
        is_hidden=False,
        triggers=(RECORD_WANTED, DAILY_TICK),
        evaluator=_make_wanted_count_evaluator(10),
        icon_slug="k16_wanted_x10",
    ),
    # ── Трек 5 — первым добавил релиз на платформу (космос) ───────────── #
    AchievementDefinition(
        code=K17_CODE,
        title_ru="Маленький шаг",
        description_ru="Первым на платформе добавь релиз в коллекцию.",
        description_done_ru="Один релиз ты добавил первым.",
        series="community",
        tier=AchievementTier.SIMPLE,
        is_hidden=False,
        triggers=(COLLECTION_ITEM_ADDED, DAILY_TICK),
        evaluator=_make_pioneer_evaluator(1),
        icon_slug="k17_pioneer_x1",
    ),
    AchievementDefinition(
        code=K18_CODE,
        title_ru="Высадка",
        description_ru="Первым на платформе добавь 5 релизов.",
        description_done_ru="5 релизов ты добавил первым.",
        series="community",
        tier=AchievementTier.NOTABLE,
        is_hidden=False,
        triggers=(COLLECTION_ITEM_ADDED, DAILY_TICK),
        evaluator=_make_pioneer_evaluator(5),
        icon_slug="k18_pioneer_x5",
    ),
    AchievementDefinition(
        code=K19_CODE,
        title_ru="На орбите",
        description_ru="Первым на платформе добавь 10 релизов.",
        description_done_ru="10 релизов ты добавил первым.",
        series="community",
        tier=AchievementTier.RARE,
        is_hidden=False,
        triggers=(COLLECTION_ITEM_ADDED, DAILY_TICK),
        evaluator=_make_pioneer_evaluator(10),
        icon_slug="k19_pioneer_x10",
    ),
    AchievementDefinition(
        code=K20_CODE,
        title_ru="Своё созвездие",
        description_ru="Первым на платформе добавь 50 релизов.",
        description_done_ru="50 релизов ты добавил первым.",
        series="community",
        tier=AchievementTier.EPIC,
        is_hidden=False,
        triggers=(COLLECTION_ITEM_ADDED, DAILY_TICK),
        evaluator=_make_pioneer_evaluator(50),
        icon_slug="k20_pioneer_x50",
    ),
    # ── META ──────────────────────────────────────────────────────────── #
    AchievementDefinition(
        code=META_CODE,
        title_ru="Резидент",
        description_ru="Закрой K4, K7 и K16 — главные ветки сообщества.",
        description_done_ru="K4, K7 и K16 закрыты.",
        series="community",
        tier=AchievementTier.EPIC,
        is_hidden=False,
        triggers=_COMMUNITY_TRIGGERS,
        evaluator=_evaluate_meta_community,
        is_meta=True,
        icon_slug="meta_community",
    ),
]
