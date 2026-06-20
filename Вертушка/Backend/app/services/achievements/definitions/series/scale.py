"""Серия «Размер коллекции» (B*).

Phase 1: B1 (10) → B2 (50) → B3 (100) → B4 (250) → B5 (500) → B6 (1000) + META_scale.

Анти-фарм: считаем COUNT(DISTINCT record_id) ТОЛЬКО для записей старше 24 часов.
Это защищает от паттерна «накачал 50 пластинок и удалил часть ради ачивки».
Если юзер реально набрал N уникальных и подождал сутки — ачивка дойдёт через
ближайший daily_tick или при следующем добавлении.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.collection import Collection, CollectionItem
from app.models.user_achievement import UserAchievement
from app.services.achievements.events import COLLECTION_ITEM_ADDED, DAILY_TICK
from app.services.achievements.registry import (
    AchievementDefinition,
    AchievementTier,
    EvalResult,
)


B1_CODE = "B1_starter"
B2_CODE = "B2_collector"
B3_CODE = "B3_archivist"
B4_CODE = "B4_curator"
B5_CODE = "B5_keeper"
B6_CODE = "B6_warden"
META_CODE = "META_scale"
SCALE_CODES = {B1_CODE, B2_CODE, B3_CODE, B4_CODE, B5_CODE, B6_CODE}

ANTIFARM_COOLDOWN = timedelta(hours=24)


async def _count_aged_unique_records(db: AsyncSession, user_id: UUID) -> int:
    """COUNT(DISTINCT record_id) в ОСНОВНОЙ коллекции юзера старше 24 часов.

    Папки — это отдельные Collection с большим sort_order; пластинки в них
    копируются из основной коллекции. Считаем только основную коллекцию
    (минимальный sort_order), иначе папки накручивают размер коллекции.
    """
    cutoff = datetime.utcnow() - ANTIFARM_COOLDOWN
    default_collection_id = (
        select(Collection.id)
        .where(Collection.user_id == user_id)
        .order_by(Collection.sort_order, Collection.created_at)
        .limit(1)
        .scalar_subquery()
    )
    count = await db.scalar(
        select(func.count(func.distinct(CollectionItem.record_id)))
        .where(
            CollectionItem.collection_id == default_collection_id,
            CollectionItem.added_at <= cutoff,
        )
    )
    return int(count or 0)


def _make_threshold_evaluator(threshold: int):
    async def evaluator(
        db: AsyncSession,
        user_id: UUID,
        payload: dict[str, Any],
        unlocked_now: set[str],
    ) -> EvalResult:
        count = await _count_aged_unique_records(db, user_id)
        if count >= threshold:
            return EvalResult(unlocked=True, progress=count, progress_target=threshold)
        return EvalResult(progress=count, progress_target=threshold)
    return evaluator


async def _evaluate_meta_scale(
    db: AsyncSession,
    user_id: UUID,
    payload: dict[str, Any],
    unlocked_now: set[str],
) -> EvalResult:
    """Мета закрывается когда все B1–B6 разблокированы."""
    persisted = await db.execute(
        select(UserAchievement.code).where(
            UserAchievement.user_id == user_id,
            UserAchievement.code.in_(SCALE_CODES),
            UserAchievement.is_unlocked.is_(True),
        )
    )
    persisted_codes = set(persisted.scalars().all())
    all_unlocked = persisted_codes | (unlocked_now & SCALE_CODES)
    progress = len(all_unlocked)
    target = len(SCALE_CODES)
    if progress >= target:
        return EvalResult(unlocked=True, progress=progress, progress_target=target)
    return EvalResult(progress=progress, progress_target=target)


_SCALE_TRIGGERS = (COLLECTION_ITEM_ADDED, DAILY_TICK)


DEFINITIONS: list[AchievementDefinition] = [
    AchievementDefinition(
        code=B1_CODE,
        title_ru="Десятка",
        description_ru="Собери 10 уникальных пластинок в коллекции.",
        description_done_ru="10 уникальных пластинок собрано.",
        series="scale",
        tier=AchievementTier.SIMPLE,
        is_hidden=False,
        triggers=_SCALE_TRIGGERS,
        evaluator=_make_threshold_evaluator(10),
        icon_slug="b1_starter",
    ),
    AchievementDefinition(
        code=B2_CODE,
        title_ru="Полтинник",
        description_ru="Собери 50 уникальных пластинок.",
        description_done_ru="50 уникальных пластинок собрано.",
        series="scale",
        tier=AchievementTier.SIMPLE,
        is_hidden=False,
        triggers=_SCALE_TRIGGERS,
        evaluator=_make_threshold_evaluator(50),
        icon_slug="b2_collector",
    ),
    AchievementDefinition(
        code=B3_CODE,
        title_ru="Сотня",
        description_ru="100 уникальных пластинок.",
        description_done_ru="100 уникальных пластинок собрано.",
        series="scale",
        tier=AchievementTier.NOTABLE,
        is_hidden=False,
        triggers=_SCALE_TRIGGERS,
        evaluator=_make_threshold_evaluator(100),
        icon_slug="b3_archivist",
    ),
    AchievementDefinition(
        code=B4_CODE,
        title_ru="Куратор",
        description_ru="250 уникальных пластинок.",
        description_done_ru="250 уникальных пластинок собрано.",
        series="scale",
        tier=AchievementTier.RARE,
        is_hidden=False,
        triggers=_SCALE_TRIGGERS,
        evaluator=_make_threshold_evaluator(250),
        icon_slug="b4_curator",
    ),
    AchievementDefinition(
        code=B5_CODE,
        title_ru="Хранитель",
        description_ru="500 уникальных пластинок.",
        description_done_ru="500 уникальных пластинок собрано.",
        series="scale",
        tier=AchievementTier.EPIC,
        is_hidden=False,
        triggers=_SCALE_TRIGGERS,
        evaluator=_make_threshold_evaluator(500),
        icon_slug="b5_keeper",
    ),
    AchievementDefinition(
        code=B6_CODE,
        title_ru="Смотритель",
        description_ru="1 000 уникальных пластинок.",
        description_done_ru="1 000 уникальных пластинок собрано.",
        series="scale",
        tier=AchievementTier.LEGEND,
        is_hidden=False,
        triggers=_SCALE_TRIGGERS,
        evaluator=_make_threshold_evaluator(1000),
        flavor_ru="Целая фонотека.",
        icon_slug="b6_warden",
    ),
    AchievementDefinition(
        code=META_CODE,
        title_ru="Фонотека",
        description_ru="Закрой всю серию «Размер коллекции».",
        description_done_ru="Серия «Размер коллекции» закрыта.",
        series="scale",
        tier=AchievementTier.LEGEND,
        is_hidden=False,
        triggers=_SCALE_TRIGGERS,
        evaluator=_evaluate_meta_scale,
        is_meta=True,
        icon_slug="meta_scale",
    ),
]
