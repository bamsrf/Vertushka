"""Серия «Машина времени» (E* + META_eras).

Считает по `Record.year` в ОСНОВНОЙ коллекции (папки не накручивают — см.
_default_collection_id). Год у импортированных из Discogs записей заполняется
обогащением из дампа: `basic_information` его отдаёт не всегда, а без года вся
серия слепа.

E6 считает СКОЛЬЗЯЩЕЕ окно: любые 10 подряд идущих лет, в каждом из которых
есть пластинка. Календарные десятилетия («ровно 1970–1979») отсекали бы
коллекцию 1969–1978, которая ничем не хуже. META_eras, наоборот, календарная —
она про «побывал во всех эпохах», и там десятилетие это ярлык, а не отрезок.

См. PLAN_ACHIEVEMENTS_V2.md §4.5.

Состав:
- E1 «Шестидесятники»  — 5 пластинок 1960–1969
- E2 «Золотой век»     — 10 пластинок 1970–1979
- E3 «Неон»            — 10 пластинок 1980–1989
- E4 «Сегодняшний»     — 5 пластинок последних 3 лет (динамическое окно)
- E5 «Доисторический»  — 1 пластинка <1960
- E6 «Десятилетие»     — по одной пластинке из каждого года любого 10-летия
- META_eras «Век винила» — по 1 пластинке из каждого 10-летия с 1950-х по 2020-е.
                            Награда: тема «Винтаж».
"""
from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.collection import Collection, CollectionItem
from app.models.record import Record
from app.services.achievements.events import COLLECTION_ITEM_ADDED, DAILY_TICK
from app.services.achievements.registry import (
    AchievementDefinition,
    AchievementTier,
    EvalResult,
)


E1_CODE = "E1_60s"
E2_CODE = "E2_70s"
E3_CODE = "E3_80s"
E4_CODE = "E4_modern"
E5_CODE = "E5_pre_1960"
E6_CODE = "E6_decade_full"
META_CODE = "META_eras"
ERAS_CODES = {E1_CODE, E2_CODE, E3_CODE, E4_CODE, E5_CODE, E6_CODE}


# Ширина окна E6 и нижняя граница «века винила».
DECADE_SPAN = 10
META_FIRST_DECADE = 1950


def _default_collection_id(user_id: UUID):
    """Основная коллекция (минимальный sort_order) — папки не накручивают."""
    return (
        select(Collection.id)
        .where(Collection.user_id == user_id)
        .order_by(Collection.sort_order, Collection.created_at)
        .limit(1)
        .scalar_subquery()
    )


async def _count_in_year_range(
    db: AsyncSession, user_id: UUID, year_from: int, year_to: int
) -> int:
    """COUNT(DISTINCT record_id) в основной коллекции с годом в [from, to]."""
    count = await db.scalar(
        select(func.count(func.distinct(CollectionItem.record_id)))
        .join(Record, Record.id == CollectionItem.record_id)
        .where(
            CollectionItem.collection_id == _default_collection_id(user_id),
            Record.year.is_not(None),
            Record.year >= year_from,
            Record.year <= year_to,
        )
    )
    return int(count or 0)


async def _distinct_years(db: AsyncSession, user_id: UUID) -> list[int]:
    """Отсортированный список разных годов в основной коллекции.

    Годы, а не пластинки: E6 и META считают покрытие шкалы времени, и сотня
    альбомов 1979-го для них — это один год.
    """
    rows = await db.execute(
        select(func.distinct(Record.year))
        .join(CollectionItem, CollectionItem.record_id == Record.id)
        .where(
            CollectionItem.collection_id == _default_collection_id(user_id),
            Record.year.is_not(None),
            Record.year > 0,
        )
    )
    return sorted(y for (y,) in rows.all() if y)


def _longest_consecutive_run(years: list[int]) -> int:
    """Самая длинная цепочка подряд идущих лет в отсортированном списке.

    Это и есть прогресс E6: «сколько лет подряд уже закрыто» — величина,
    которую осмысленно показать в полоске прогресса, в отличие от голого
    «да/нет».
    """
    if not years:
        return 0
    best = current = 1
    for prev, cur in zip(years, years[1:]):
        current = current + 1 if cur == prev + 1 else 1
        best = max(best, current)
    return best


async def _evaluate_e1(db, user_id, payload, unlocked_now) -> EvalResult:
    count = await _count_in_year_range(db, user_id, 1960, 1969)
    return EvalResult(unlocked=count >= 5, progress=count, progress_target=5)


async def _evaluate_e2(db, user_id, payload, unlocked_now) -> EvalResult:
    count = await _count_in_year_range(db, user_id, 1970, 1979)
    return EvalResult(unlocked=count >= 10, progress=count, progress_target=10)


async def _evaluate_e3(db, user_id, payload, unlocked_now) -> EvalResult:
    count = await _count_in_year_range(db, user_id, 1980, 1989)
    return EvalResult(unlocked=count >= 10, progress=count, progress_target=10)


async def _evaluate_e4(db, user_id, payload, unlocked_now) -> EvalResult:
    """Окно динамическое: «последние 3 года» от сегодня, а не фиксированные
    даты. Год релиза на Discogs часто опережает календарь (пластинка вышла в
    декабре, год стоит следующий), поэтому верхняя граница — год вперёд."""
    now_year = datetime.utcnow().year
    count = await _count_in_year_range(db, user_id, now_year - 2, now_year + 1)
    return EvalResult(unlocked=count >= 5, progress=count, progress_target=5)


async def _evaluate_e5(db, user_id, payload, unlocked_now) -> EvalResult:
    """Нижняя граница 1900, а не ноль: год 1 или 1000 в дампе — это мусор
    распознавания, а не шеллак начала века."""
    count = await _count_in_year_range(db, user_id, 1900, 1959)
    return EvalResult(unlocked=count >= 1, progress=min(count, 1), progress_target=1)


async def _evaluate_e6(db, user_id, payload, unlocked_now) -> EvalResult:
    """Скользящее окно: 10 подряд идущих лет, в каждом есть пластинка."""
    years = await _distinct_years(db, user_id)
    run = _longest_consecutive_run(years)
    return EvalResult(
        unlocked=run >= DECADE_SPAN,
        progress=min(run, DECADE_SPAN),
        progress_target=DECADE_SPAN,
    )


def _covered_decades(years: list[int], up_to_year: int) -> set[int]:
    """Календарные десятилетия (1950, 1960, …), в которых есть пластинка."""
    return {
        (y // 10) * 10
        for y in years
        if META_FIRST_DECADE <= y <= up_to_year
    }


async def _evaluate_meta_eras(db, user_id, payload, unlocked_now) -> EvalResult:
    """«Век винила» — по пластинке в каждом десятилетии с 1950-х по текущее.

    Цель растёт сама: в 2030-м добавится ещё одно десятилетие, и уже открытая
    ачивка останется открытой (evaluator для unlocked не вызывается), а
    недобравшим просто станет на шаг дальше. Это честнее, чем прибить список
    десятилетий константой и переписывать её раз в десять лет.
    """
    now_year = datetime.utcnow().year
    current_decade = (now_year // 10) * 10
    target = len(range(META_FIRST_DECADE, current_decade + 1, 10))

    years = await _distinct_years(db, user_id)
    covered = _covered_decades(years, now_year)
    progress = len(covered)
    return EvalResult(
        unlocked=progress >= target, progress=progress, progress_target=target
    )


DEFINITIONS: list[AchievementDefinition] = [
    AchievementDefinition(
        code=E1_CODE,
        title_ru="Шестидесятники",
        description_ru="5 пластинок 1960–1969.",
        description_done_ru="5 пластинок 60-х собрано.",
        series="eras",
        tier=AchievementTier.SIMPLE,
        is_hidden=False,
        triggers=(COLLECTION_ITEM_ADDED, DAILY_TICK),
        evaluator=_evaluate_e1,
        icon_slug="e1_60s",
    ),
    AchievementDefinition(
        code=E2_CODE,
        title_ru="Золотой век",
        description_ru="10 пластинок 1970–1979.",
        description_done_ru="10 пластинок 70-х собрано.",
        series="eras",
        tier=AchievementTier.SIMPLE,
        is_hidden=False,
        triggers=(COLLECTION_ITEM_ADDED, DAILY_TICK),
        evaluator=_evaluate_e2,
        icon_slug="e2_70s",
    ),
    AchievementDefinition(
        code=E3_CODE,
        title_ru="Неон",
        description_ru="10 пластинок 1980–1989.",
        description_done_ru="10 пластинок 80-х собрано.",
        series="eras",
        tier=AchievementTier.SIMPLE,
        is_hidden=False,
        triggers=(COLLECTION_ITEM_ADDED, DAILY_TICK),
        evaluator=_evaluate_e3,
        icon_slug="e3_80s",
    ),
    AchievementDefinition(
        code=E4_CODE,
        title_ru="Сегодняшний",
        description_ru="5 пластинок последних 3 лет.",
        description_done_ru="5 свежих пластинок собрано.",
        series="eras",
        tier=AchievementTier.SIMPLE,
        is_hidden=False,
        triggers=(COLLECTION_ITEM_ADDED, DAILY_TICK),
        evaluator=_evaluate_e4,
        icon_slug="e4_modern",
    ),
    AchievementDefinition(
        code=E5_CODE,
        title_ru="Доисторический",
        description_ru="Пластинка ранее 1960 года.",
        description_done_ru="Пластинка старше 1960-го найдена.",
        series="eras",
        tier=AchievementTier.RARE,
        is_hidden=False,
        triggers=(COLLECTION_ITEM_ADDED, DAILY_TICK),
        evaluator=_evaluate_e5,
        icon_slug="e5_pre_1960",
    ),
    AchievementDefinition(
        code=E6_CODE,
        title_ru="Десятилетие",
        description_ru="По одной пластинке из каждого года любого 10-летия.",
        description_done_ru="В коллекции есть пластинка из каждого года одного десятилетия.",
        series="eras",
        tier=AchievementTier.EPIC,
        is_hidden=False,
        triggers=(COLLECTION_ITEM_ADDED, DAILY_TICK),
        evaluator=_evaluate_e6,
        icon_slug="e6_decade_full",
    ),
    AchievementDefinition(
        code=META_CODE,
        title_ru="Век винила",
        description_ru="По 1 пластинке из каждого десятилетия 1950–2020+.",
        description_done_ru="Все десятилетия 1950–2020+ закрыты.",
        series="eras",
        tier=AchievementTier.LEGEND,
        is_hidden=False,
        triggers=(COLLECTION_ITEM_ADDED, DAILY_TICK),
        evaluator=_evaluate_meta_eras,
        is_meta=True,
        flavor_ru="Игла прошла через все эпохи.",
        icon_slug="meta_eras",
    ),
]
