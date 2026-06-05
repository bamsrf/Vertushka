"""Серия «Кругосветка» (D* + META_geography).

⚠️ КАРКАС / SCAFFOLDING. Все evaluator-ы возвращают `unlocked=False`.

Использует `Record.country` (Discogs-нормализованное). Реальная имплементация —
Phase 3. См. PLAN_ACHIEVEMENTS_V2.md §4.4.

Состав:
- D1 «Космополит»       — 5 разных стран
- D2 «Глобус»           — 15 стран
- D3 «Кругосветка»      — 30 стран
- D4 «Из Токио»         — 10 японских прессов
- D5 «Мелодия»          — 10 пластинок Melodiya / country=USSR
- D6 «Британский почерк» — 3 коллекционки country=UK (зависит от RARITY_BADGES_PLAN)
- D7 «Made in Germany»  — 10 пластинок Germany / West Germany
- META_geography «Атлас» — D3 + любые 3 из D4–D7. Награда: тема «Globus».
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


D1_CODE = "D1_country_x5"
D2_CODE = "D2_country_x15"
D3_CODE = "D3_country_x30"
D4_CODE = "D4_japanese_x10"
D5_CODE = "D5_melodiya_x10"
D6_CODE = "D6_uk_collectible_x3"
D7_CODE = "D7_german_x10"
META_CODE = "META_geography"
GEOGRAPHY_CODES = {D1_CODE, D2_CODE, D3_CODE, D4_CODE, D5_CODE, D6_CODE, D7_CODE}


async def _stub(
    db: AsyncSession,
    user_id: UUID,
    payload: dict[str, Any] | None,
    unlocked_now: set[str],
) -> EvalResult:
    return EvalResult(unlocked=False)


DEFINITIONS: list[AchievementDefinition] = [
    AchievementDefinition(
        code=D1_CODE,
        title_ru="Космополит",
        description_ru="Пластинки из 5 разных стран.",
        description_done_ru="5 стран в коллекции.",
        series="geography",
        tier=AchievementTier.SIMPLE,
        is_hidden=False,
        triggers=(COLLECTION_ITEM_ADDED,),
        evaluator=_stub,
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
        triggers=(COLLECTION_ITEM_ADDED,),
        evaluator=_stub,
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
        triggers=(COLLECTION_ITEM_ADDED,),
        evaluator=_stub,
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
        triggers=(COLLECTION_ITEM_ADDED,),
        evaluator=_stub,
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
        triggers=(COLLECTION_ITEM_ADDED,),
        evaluator=_stub,
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
        triggers=(COLLECTION_ITEM_ADDED,),
        evaluator=_stub,
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
        triggers=(COLLECTION_ITEM_ADDED,),
        evaluator=_stub,
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
        evaluator=_stub,
        is_meta=True,
        flavor_ru="Карта легла на полку.",
        icon_slug="meta_geography",
    ),
]
