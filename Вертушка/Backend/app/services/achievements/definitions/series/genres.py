"""Серия «Жанры» (F* + META_genres).

Phase 3 (реализовано): считает по `Record.genre` (Discogs-жанры, склеены через
", "). Анти-фарм — тот же 24h-cooldown и только основная коллекция, что в B-серии.

Состав:
- F1 «Разносторонний» — 5 разных жанров
- F2 «Всеядный»       — 10 разных жанров
- F3 «Селектор»       — 25 Jazz
- F4 «Рейв»           — 25 Electronic
- F5 «Классик»        — 15 Classical
- F6 «Громко»         — 25 Rock
- META_genres «Эрудит» — F2 + любые 3 из F3–F6.
"""
from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.collection import Collection, CollectionItem
from app.models.record import Record
from app.models.user_achievement import UserAchievement
from app.services.genre_vocab import split_genres
from app.services.achievements.events import COLLECTION_ITEM_ADDED, DAILY_TICK
from app.services.achievements.registry import (
    AchievementDefinition,
    AchievementTier,
    EvalResult,
)


F1_CODE = "F1_diversity_5"
F2_CODE = "F2_diversity_10"
F3_CODE = "F3_jazz_x25"
F4_CODE = "F4_electronic_x25"
F5_CODE = "F5_classical_x15"
F6_CODE = "F6_rock_x25"
META_CODE = "META_genres"
GENRE_CODES = {F1_CODE, F2_CODE, F3_CODE, F4_CODE, F5_CODE, F6_CODE}


def _default_collection_id(user_id: UUID):
    """Основная коллекция (минимальный sort_order) — папки не накручивают."""
    return (
        select(Collection.id)
        .where(Collection.user_id == user_id)
        .order_by(Collection.sort_order, Collection.created_at)
        .limit(1)
        .scalar_subquery()
    )


async def _count_genre_substr(db: AsyncSession, user_id: UUID, token: str) -> int:
    """COUNT(DISTINCT record_id) в основной коллекции, у которых `genre`
    содержит token (case-insensitive). Без cooldown — мгновенный отклик."""
    count = await db.scalar(
        select(func.count(func.distinct(CollectionItem.record_id)))
        .join(Record, Record.id == CollectionItem.record_id)
        .where(
            CollectionItem.collection_id == _default_collection_id(user_id),
            Record.genre.is_not(None),
            Record.genre.ilike(f"%{token}%"),
        )
    )
    return int(count or 0)


async def _count_distinct_genres(db: AsyncSession, user_id: UUID) -> int:
    """Число РАЗНЫХ жанров в основной коллекции. Без cooldown.

    `Record.genre` — это склейка Discogs-жанров через ", ", поэтому распуляем
    их в Python (коллекции ограничены, дешевле, чем SQL-split). Сплит — через
    `split_genres`, а не `.split(",")`: «Folk, World, & Country» сам содержит
    запятые и наивным сплитом давал три жанра вместо одного, втрое удешевляя
    F1/F2."""
    rows = await db.execute(
        select(func.distinct(Record.genre))
        .join(CollectionItem, CollectionItem.record_id == Record.id)
        .where(
            CollectionItem.collection_id == _default_collection_id(user_id),
            Record.genre.is_not(None),
        )
    )
    seen: set[str] = set()
    for (genre_str,) in rows.all():
        for g in split_genres(genre_str):
            seen.add(g.casefold())
    return len(seen)


def _make_diversity_evaluator(threshold: int):
    async def evaluator(
        db: AsyncSession,
        user_id: UUID,
        payload: dict[str, Any],
        unlocked_now: set[str],
    ) -> EvalResult:
        count = await _count_distinct_genres(db, user_id)
        if count >= threshold:
            return EvalResult(unlocked=True, progress=count, progress_target=threshold)
        return EvalResult(progress=count, progress_target=threshold)
    return evaluator


def _make_genre_evaluator(token: str, threshold: int):
    async def evaluator(
        db: AsyncSession,
        user_id: UUID,
        payload: dict[str, Any],
        unlocked_now: set[str],
    ) -> EvalResult:
        count = await _count_genre_substr(db, user_id, token)
        if count >= threshold:
            return EvalResult(unlocked=True, progress=count, progress_target=threshold)
        return EvalResult(progress=count, progress_target=threshold)
    return evaluator


async def _evaluate_meta_genres(
    db: AsyncSession,
    user_id: UUID,
    payload: dict[str, Any],
    unlocked_now: set[str],
) -> EvalResult:
    """F2 + любые 3 из F3–F6."""
    persisted = await db.execute(
        select(UserAchievement.code).where(
            UserAchievement.user_id == user_id,
            UserAchievement.code.in_(GENRE_CODES),
            UserAchievement.is_unlocked.is_(True),
        )
    )
    have = set(persisted.scalars().all()) | (unlocked_now & GENRE_CODES)
    deep = {F3_CODE, F4_CODE, F5_CODE, F6_CODE}
    ok = (F2_CODE in have) and len(have & deep) >= 3
    # Прогресс: 0..4 (F2 + до 3 глубоких), таргет 4.
    progress = (1 if F2_CODE in have else 0) + min(len(have & deep), 3)
    if ok:
        return EvalResult(unlocked=True, progress=4, progress_target=4)
    return EvalResult(progress=progress, progress_target=4)


_GENRE_TRIGGERS = (COLLECTION_ITEM_ADDED, DAILY_TICK)


DEFINITIONS: list[AchievementDefinition] = [
    AchievementDefinition(
        code=F1_CODE,
        title_ru="Разносторонний",
        description_ru="5 разных жанров.",
        description_done_ru="5 жанров в коллекции.",
        series="genres",
        tier=AchievementTier.SIMPLE,
        is_hidden=False,
        triggers=_GENRE_TRIGGERS,
        evaluator=_make_diversity_evaluator(5),
        icon_slug="f1_diversity_5",
    ),
    AchievementDefinition(
        code=F2_CODE,
        title_ru="Всеядный",
        description_ru="10 разных жанров.",
        description_done_ru="10 жанров собрано.",
        series="genres",
        tier=AchievementTier.NOTABLE,
        is_hidden=False,
        triggers=_GENRE_TRIGGERS,
        evaluator=_make_diversity_evaluator(10),
        icon_slug="f2_diversity_10",
    ),
    AchievementDefinition(
        code=F3_CODE,
        title_ru="Эй, Арнольд",
        description_ru="25 пластинок Jazz.",
        description_done_ru="25 джазовых пластинок собрано.",
        series="genres",
        tier=AchievementTier.RARE,
        is_hidden=False,
        triggers=_GENRE_TRIGGERS,
        evaluator=_make_genre_evaluator("jazz", 25),
        icon_slug="f3_jazz_x25",
    ),
    AchievementDefinition(
        code=F4_CODE,
        title_ru="Рейв",
        description_ru="25 пластинок Electronic.",
        description_done_ru="25 электронных пластинок собрано.",
        series="genres",
        tier=AchievementTier.RARE,
        is_hidden=False,
        triggers=_GENRE_TRIGGERS,
        evaluator=_make_genre_evaluator("electronic", 25),
        icon_slug="f4_electronic_x25",
    ),
    AchievementDefinition(
        code=F5_CODE,
        title_ru="Классик",
        description_ru="15 пластинок Classical.",
        description_done_ru="15 классических пластинок собрано.",
        series="genres",
        tier=AchievementTier.RARE,
        is_hidden=False,
        triggers=_GENRE_TRIGGERS,
        evaluator=_make_genre_evaluator("classical", 15),
        icon_slug="f5_classical_x15",
    ),
    AchievementDefinition(
        code=F6_CODE,
        title_ru="Громко",
        description_ru="25 пластинок Rock.",
        description_done_ru="25 рок-пластинок собрано.",
        series="genres",
        tier=AchievementTier.RARE,
        is_hidden=False,
        triggers=_GENRE_TRIGGERS,
        evaluator=_make_genre_evaluator("rock", 25),
        icon_slug="f6_rock_x25",
    ),
    AchievementDefinition(
        code=META_CODE,
        title_ru="Эрудит",
        description_ru="Открой «Всеядного» и любые три жанровые ачивки серии.",
        description_done_ru="«Всеядный» и три жанровые ветки закрыты.",
        series="genres",
        tier=AchievementTier.EPIC,
        is_hidden=False,
        triggers=(COLLECTION_ITEM_ADDED, DAILY_TICK),
        evaluator=_evaluate_meta_genres,
        is_meta=True,
        flavor_ru="Шире, чем фон в кафе.",
        icon_slug="meta_genres",
    ),
]
