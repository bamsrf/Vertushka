"""Серия «Машина времени» (E* + META_eras).

⚠️ КАРКАС / SCAFFOLDING. Все evaluator-ы возвращают `unlocked=False`.

Использует `Record.year`. Реальная имплементация — Phase 3.
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

from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

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


async def _stub(
    db: AsyncSession,
    user_id: UUID,
    payload: dict[str, Any] | None,
    unlocked_now: set[str],
) -> EvalResult:
    return EvalResult(unlocked=False)


DEFINITIONS: list[AchievementDefinition] = [
    AchievementDefinition(
        code=E1_CODE,
        title_ru="Шестидесятники",
        description_ru="5 пластинок 1960–1969.",
        description_done_ru="5 пластинок 60-х собрано.",
        series="eras",
        tier=AchievementTier.SIMPLE,
        is_hidden=False,
        triggers=(COLLECTION_ITEM_ADDED,),
        evaluator=_stub,
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
        triggers=(COLLECTION_ITEM_ADDED,),
        evaluator=_stub,
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
        triggers=(COLLECTION_ITEM_ADDED,),
        evaluator=_stub,
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
        triggers=(COLLECTION_ITEM_ADDED,),
        evaluator=_stub,
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
        triggers=(COLLECTION_ITEM_ADDED,),
        evaluator=_stub,
        icon_slug="e5_pre_1960",
    ),
    AchievementDefinition(
        code=E6_CODE,
        title_ru="Десятилетие",
        description_ru="По одной пластинке из каждого года любого 10-летия.",
        description_done_ru="Десятилетие закрыто по годам.",
        series="eras",
        tier=AchievementTier.EPIC,
        is_hidden=False,
        triggers=(COLLECTION_ITEM_ADDED,),
        evaluator=_stub,
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
        evaluator=_stub,
        is_meta=True,
        flavor_ru="Игла прошла через все эпохи.",
        icon_slug="meta_eras",
    ),
]
