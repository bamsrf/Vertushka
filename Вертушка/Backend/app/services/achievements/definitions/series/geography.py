"""Серия «Кругосветка» (D* + META_geography).

Phase 3 (реализовано): считает по `Record.country` / `Record.label`
(Discogs-нормализованные). Без 24ч-cooldown — страна/лейбл релиза не
накрутишь массовым добавлением, отклик мгновенный (как в rarity/genres).

Состав:
- D1 «Космополит»       — 5 разных стран
- D2 «Глобус»           — 15 стран
- D3 «Кругосветка»      — 30 стран
- D4 «Из Токио»         — 10 японских прессов (country=Japan)
- D5 «Мелодия»          — 10 пластинок Melodiya (label ILIKE)
- D6 «Британский почерк» — 3 коллекционки country=UK
- D7 «Made in Germany»  — 10 пластинок Germany / West Germany / East Germany
- META_geography «Атлас» — D3 + любые 3 из D4–D7. Награда: тема «Globus».
"""
from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.collection import Collection, CollectionItem
from app.models.record import Record
from app.models.user_achievement import UserAchievement
from app.services.achievements.events import COLLECTION_ITEM_ADDED, DAILY_TICK
from app.services.achievements.registry import (
    AchievementDefinition,
    AchievementTier,
    EvalResult,
)


D1_CODE = "D1_country_x5"
D2_CODE = "D2_country_x15"
D3_CODE = "D3_country_x30"
D4_CODE = "D4_japanese_x10"
D5_CODE = "D5_melodiya_x10"
D6_CODE = "D6_uk_collectible_x3"
D7_CODE = "D7_german_x10"
META_CODE = "META_geography"
GEOGRAPHY_CODES = {D1_CODE, D2_CODE, D3_CODE, D4_CODE, D5_CODE, D6_CODE, D7_CODE}


def _default_collection_id(user_id: UUID):
    """Основная коллекция (минимальный sort_order) — папки не накручивают."""
    return (
        select(Collection.id)
        .where(Collection.user_id == user_id)
        .order_by(Collection.sort_order, Collection.created_at)
        .limit(1)
        .scalar_subquery()
    )


async def _count_distinct_countries(db: AsyncSession, user_id: UUID) -> int:
    """Число РАЗНЫХ стран (case-insensitive) в основной коллекции."""
    rows = await db.execute(
        select(func.distinct(func.lower(Record.country)))
        .join(CollectionItem, CollectionItem.record_id == Record.id)
        .where(
            CollectionItem.collection_id == _default_collection_id(user_id),
            Record.country.is_not(None),
            Record.country != "",
        )
    )
    return len([c for (c,) in rows.all() if c and c.strip()])


async def _count_country_ilike(db: AsyncSession, user_id: UUID, token: str) -> int:
    """COUNT(DISTINCT record_id) в основной коллекции, у которых `country`
    содержит token (case-insensitive)."""
    count = await db.scalar(
        select(func.count(func.distinct(CollectionItem.record_id)))
        .join(Record, Record.id == CollectionItem.record_id)
        .where(
            CollectionItem.collection_id == _default_collection_id(user_id),
            Record.country.is_not(None),
            Record.country.ilike(f"%{token}%"),
        )
    )
    return int(count or 0)


async def _count_label_ilike(db: AsyncSession, user_id: UUID, tokens: tuple[str, ...]) -> int:
    """COUNT(DISTINCT record_id) в основной коллекции, у которых `label`
    содержит любой из token (case-insensitive)."""
    from sqlalchemy import or_

    conditions = [Record.label.ilike(f"%{t}%") for t in tokens]
    count = await db.scalar(
        select(func.count(func.distinct(CollectionItem.record_id)))
        .join(Record, Record.id == CollectionItem.record_id)
        .where(
            CollectionItem.collection_id == _default_collection_id(user_id),
            Record.label.is_not(None),
            or_(*conditions),
        )
    )
    return int(count or 0)


async def _count_uk_collectible(db: AsyncSession, user_id: UUID) -> int:
    """COUNT(DISTINCT record_id) в основной коллекции: country=UK и is_collectible."""
    count = await db.scalar(
        select(func.count(func.distinct(CollectionItem.record_id)))
        .join(Record, Record.id == CollectionItem.record_id)
        .where(
            CollectionItem.collection_id == _default_collection_id(user_id),
            Record.is_collectible.is_(True),
            func.lower(Record.country).in_(("uk", "united kingdom")),
        )
    )
    return int(count or 0)


def _make_distinct_country_evaluator(threshold: int):
    async def evaluator(
        db: AsyncSession,
        user_id: UUID,
        payload: dict[str, Any],
        unlocked_now: set[str],
    ) -> EvalResult:
        count = await _count_distinct_countries(db, user_id)
        if count >= threshold:
            return EvalResult(unlocked=True, progress=count, progress_target=threshold)
        return EvalResult(progress=count, progress_target=threshold)
    return evaluator


async def _evaluate_d4_japanese(
    db: AsyncSession,
    user_id: UUID,
    payload: dict[str, Any],
    unlocked_now: set[str],
) -> EvalResult:
    count = await _count_country_ilike(db, user_id, "japan")
    if count >= 10:
        return EvalResult(unlocked=True, progress=count, progress_target=10)
    return EvalResult(progress=count, progress_target=10)


async def _evaluate_d5_melodiya(
    db: AsyncSession,
    user_id: UUID,
    payload: dict[str, Any],
    unlocked_now: set[str],
) -> EvalResult:
    count = await _count_label_ilike(db, user_id, ("melodiya", "мелодия"))
    if count >= 10:
        return EvalResult(unlocked=True, progress=count, progress_target=10)
    return EvalResult(progress=count, progress_target=10)


async def _evaluate_d6_uk_collectible(
    db: AsyncSession,
    user_id: UUID,
    payload: dict[str, Any],
    unlocked_now: set[str],
) -> EvalResult:
    count = await _count_uk_collectible(db, user_id)
    if count >= 3:
        return EvalResult(unlocked=True, progress=count, progress_target=3)
    return EvalResult(progress=count, progress_target=3)


async def _evaluate_d7_german(
    db: AsyncSession,
    user_id: UUID,
    payload: dict[str, Any],
    unlocked_now: set[str],
) -> EvalResult:
    count = await _count_country_ilike(db, user_id, "germany")
    if count >= 10:
        return EvalResult(unlocked=True, progress=count, progress_target=10)
    return EvalResult(progress=count, progress_target=10)


async def _evaluate_meta_geography(
    db: AsyncSession,
    user_id: UUID,
    payload: dict[str, Any],
    unlocked_now: set[str],
) -> EvalResult:
    """D3 + любые 3 из D4–D7."""
    persisted = await db.execute(
        select(UserAchievement.code).where(
            UserAchievement.user_id == user_id,
            UserAchievement.code.in_(GEOGRAPHY_CODES),
            UserAchievement.is_unlocked.is_(True),
        )
    )
    have = set(persisted.scalars().all()) | (unlocked_now & GEOGRAPHY_CODES)
    deep = {D4_CODE, D5_CODE, D6_CODE, D7_CODE}
    ok = (D3_CODE in have) and len(have & deep) >= 3
    # Прогресс: 0..4 (D3 + до 3 глубоких), таргет 4.
    progress = (1 if D3_CODE in have else 0) + min(len(have & deep), 3)
    if ok:
        return EvalResult(unlocked=True, progress=4, progress_target=4)
    return EvalResult(progress=progress, progress_target=4)


_GEOGRAPHY_TRIGGERS = (COLLECTION_ITEM_ADDED, DAILY_TICK)


DEFINITIONS: list[AchievementDefinition] = [
    AchievementDefinition(
        code=D1_CODE,
        title_ru="Космополит",
        description_ru="Пластинки из 5 разных стран.",
        description_done_ru="5 стран в коллекции.",
        series="geography",
        tier=AchievementTier.SIMPLE,
        is_hidden=False,
        triggers=_GEOGRAPHY_TRIGGERS,
        evaluator=_make_distinct_country_evaluator(5),
        icon_slug="d1_country_x5",
    ),
    AchievementDefinition(
        code=D2_CODE,
        title_ru="Глобус",
        description_ru="15 стран в коллекции.",
        description_done_ru="15 стран собрано.",
        series="geography",
        tier=AchievementTier.NOTABLE,
        is_hidden=False,
        triggers=_GEOGRAPHY_TRIGGERS,
        evaluator=_make_distinct_country_evaluator(15),
        icon_slug="d2_country_x15",
    ),
    AchievementDefinition(
        code=D3_CODE,
        title_ru="Кругосветка",
        description_ru="30 стран.",
        description_done_ru="30 стран собрано.",
        series="geography",
        tier=AchievementTier.RARE,
        is_hidden=False,
        triggers=_GEOGRAPHY_TRIGGERS,
        evaluator=_make_distinct_country_evaluator(30),
        icon_slug="d3_country_x30",
    ),
    AchievementDefinition(
        code=D4_CODE,
        title_ru="Из Токио",
        description_ru="10 японских прессов.",
        description_done_ru="10 японских прессов собрано.",
        series="geography",
        tier=AchievementTier.RARE,
        is_hidden=False,
        triggers=_GEOGRAPHY_TRIGGERS,
        evaluator=_evaluate_d4_japanese,
        icon_slug="d4_japanese_x10",
    ),
    AchievementDefinition(
        code=D5_CODE,
        title_ru="Мелодия",
        description_ru="10 пластинок лейбла Melodiya.",
        description_done_ru="10 пластинок «Мелодии» собрано.",
        series="geography",
        tier=AchievementTier.RARE,
        is_hidden=False,
        triggers=_GEOGRAPHY_TRIGGERS,
        evaluator=_evaluate_d5_melodiya,
        icon_slug="d5_melodiya_x10",
    ),
    AchievementDefinition(
        code=D6_CODE,
        title_ru="Британский почерк",
        description_ru="3 коллекционки из UK.",
        description_done_ru="3 коллекционки из UK собрано.",
        series="geography",
        tier=AchievementTier.RARE,
        is_hidden=False,
        triggers=_GEOGRAPHY_TRIGGERS,
        evaluator=_evaluate_d6_uk_collectible,
        icon_slug="d6_uk_collectible_x3",
    ),
    AchievementDefinition(
        code=D7_CODE,
        title_ru="Made in Germany",
        description_ru="10 пластинок из Германии.",
        description_done_ru="10 немецких прессов собрано.",
        series="geography",
        tier=AchievementTier.RARE,
        is_hidden=False,
        triggers=_GEOGRAPHY_TRIGGERS,
        evaluator=_evaluate_d7_german,
        icon_slug="d7_german_x10",
    ),
    AchievementDefinition(
        code=META_CODE,
        title_ru="Атлас",
        description_ru="D3 + любые 3 из D4–D7.",
        description_done_ru="D3 и три ветки D4–D7 закрыты.",
        series="geography",
        tier=AchievementTier.EPIC,
        is_hidden=False,
        triggers=(COLLECTION_ITEM_ADDED, DAILY_TICK),
        evaluator=_evaluate_meta_geography,
        is_meta=True,
        flavor_ru="Карта легла на полку.",
        icon_slug="meta_geography",
    ),
]
