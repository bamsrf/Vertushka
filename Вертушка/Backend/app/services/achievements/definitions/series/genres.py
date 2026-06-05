"""Серия «Жанры» (F* + META_genres).

⚠️ КАРКАС / SCAFFOLDING. Все evaluator-ы возвращают `unlocked=False`.

Использует `Record.genre` и `Record.style`. Реальная имплементация — Phase 3.
См. PLAN_ACHIEVEMENTS_V2.md §4.6.

Состав:
- F1 «Меломаньяк»  — 5 разных жанров
- F2 «Всеядный»    — 10 разных жанров
- F3 «Селектор»    — 25 Jazz
- F4 «Машинист»    — 25 Electronic
- F5 «Классик»     — 15 Classical
- F6 «Громко»      — 25 Rock
- META_genres «Эрудит» — F2 + любые 3 из F3–F6. Награда: title «Эрудит».
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


F1_CODE = "F1_diversity_5"
F2_CODE = "F2_diversity_10"
F3_CODE = "F3_jazz_x25"
F4_CODE = "F4_electronic_x25"
F5_CODE = "F5_classical_x15"
F6_CODE = "F6_rock_x25"
META_CODE = "META_genres"
GENRE_CODES = {F1_CODE, F2_CODE, F3_CODE, F4_CODE, F5_CODE, F6_CODE}


async def _stub(
    db: AsyncSession,
    user_id: UUID,
    payload: dict[str, Any] | None,
    unlocked_now: set[str],
) -> EvalResult:
    return EvalResult(unlocked=False)


DEFINITIONS: list[AchievementDefinition] = [
    AchievementDefinition(
        code=F1_CODE,
        title_ru="Меломаньяк",
        description_ru="5 разных жанров.",
        description_done_ru="5 жанров в коллекции.",
        series="genres",
        tier=AchievementTier.SIMPLE,
        is_hidden=False,
        triggers=(COLLECTION_ITEM_ADDED,),
        evaluator=_stub,
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
        triggers=(COLLECTION_ITEM_ADDED,),
        evaluator=_stub,
        icon_slug="f2_diversity_10",
    ),
    AchievementDefinition(
        code=F3_CODE,
        title_ru="Селектор",
        description_ru="25 пластинок Jazz.",
        description_done_ru="25 джазовых пластинок собрано.",
        series="genres",
        tier=AchievementTier.RARE,
        is_hidden=False,
        triggers=(COLLECTION_ITEM_ADDED,),
        evaluator=_stub,
        icon_slug="f3_jazz_x25",
    ),
    AchievementDefinition(
        code=F4_CODE,
        title_ru="Машинист",
        description_ru="25 пластинок Electronic.",
        description_done_ru="25 электронных пластинок собрано.",
        series="genres",
        tier=AchievementTier.RARE,
        is_hidden=False,
        triggers=(COLLECTION_ITEM_ADDED,),
        evaluator=_stub,
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
        triggers=(COLLECTION_ITEM_ADDED,),
        evaluator=_stub,
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
        triggers=(COLLECTION_ITEM_ADDED,),
        evaluator=_stub,
        icon_slug="f6_rock_x25",
    ),
    AchievementDefinition(
        code=META_CODE,
        title_ru="Эрудит",
        description_ru="F2 + любые 3 из F3–F6.",
        description_done_ru="F2 и три ветки F3–F6 закрыты.",
        series="genres",
        tier=AchievementTier.EPIC,
        is_hidden=False,
        triggers=(COLLECTION_ITEM_ADDED, DAILY_TICK),
        evaluator=_stub,
        is_meta=True,
        flavor_ru="Шире, чем фон в кафе.",
        icon_slug="meta_genres",
    ),
]
