"""Серия «Полная дискография» (H* + META_depth).

⚠️ КАРКАС / SCAFFOLDING. Все evaluator-ы возвращают `unlocked=False`.

Самая глубокая серия — зависит от Discogs `/artists/{id}/releases` и
`/labels/{id}/releases`. Тяжёлые проверки выполняются в `daily_tick`, не на
каждый `collection_item_added`.

ЗАВИСИМОСТИ перед Phase 4:
- Стабильный кэш Discogs-ответов (артисты, лейблы, мастера).
- Динамические коды: `H2:<artist-slug>`, `H4:<master-slug>`, `H5:<label-slug>` —
  кладутся в `UserAchievement.code` как составной ключ. UI-стороне нужно
  показывать имя из `ach_metadata.artist_name|label_name|master_name`.
- Дубли META_depth: META_depth закрывается ОДНОЙ парой H2+H4+H5 любых,
  повторные не дают «новых META».

См. PLAN_ACHIEVEMENTS_V2.md §4.10.

Состав:
- H1 «Поклонник»       — 5 пластинок одного артиста
- H2 «Полная»          — все студийные альбомы артиста (динамическое H2:<slug>)
- H3 «Сравнил»         — 3+ разных пресса одного мастера
- H4 «Археолог»        — 5+ разных прессов одного мастера (динамическое H4:<slug>)
- H5 «Лейбл-фанат»     — 20 пластинок одного лейбла из топ-100 (динамическое H5:<slug>)
- META_depth «Учёный»  — H2 + H4 + H5 (любые). Награда: title с именем артиста.
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


H1_CODE = "H1_artist_x5"
H2_CODE = "H2_artist_studio_full"          # динамический префикс H2:<artist-slug>
H3_CODE = "H3_master_pressings_3"
H4_CODE = "H4_master_pressings_5"          # динамический префикс H4:<master-slug>
H5_CODE = "H5_label_x20"                   # динамический префикс H5:<label-slug>
META_CODE = "META_depth"
DISCOGRAPHY_CODES = {H1_CODE, H2_CODE, H3_CODE, H4_CODE, H5_CODE}


async def _stub(
    db: AsyncSession,
    user_id: UUID,
    payload: dict[str, Any] | None,
    unlocked_now: set[str],
) -> EvalResult:
    return EvalResult(unlocked=False)


DEFINITIONS: list[AchievementDefinition] = [
    AchievementDefinition(
        code=H1_CODE,
        title_ru="Поклонник",
        description_ru="5 пластинок одного артиста.",
        description_done_ru="5 пластинок одного артиста собрано.",
        series="discography",
        tier=AchievementTier.SIMPLE,
        is_hidden=False,
        triggers=(COLLECTION_ITEM_ADDED,),
        evaluator=_stub,
        icon_slug="h1_artist_x5",
    ),
    AchievementDefinition(
        code=H2_CODE,
        title_ru="Полная",
        description_ru="Собрал все студийные альбомы артиста.",
        description_done_ru="Полная студийная дискография собрана.",
        series="discography",
        tier=AchievementTier.EPIC,
        is_hidden=False,
        triggers=(COLLECTION_ITEM_ADDED, DAILY_TICK),
        evaluator=_stub,
        flavor_ru="Discogs больше нечего показать.",
        icon_slug="h2_artist_studio_full",
    ),
    AchievementDefinition(
        code=H3_CODE,
        title_ru="Сравнил",
        description_ru="3+ разных пресса одного мастера.",
        description_done_ru="3 пресса одного мастера собрано.",
        series="discography",
        tier=AchievementTier.RARE,
        is_hidden=False,
        triggers=(COLLECTION_ITEM_ADDED, DAILY_TICK),
        evaluator=_stub,
        icon_slug="h3_master_pressings_3",
    ),
    AchievementDefinition(
        code=H4_CODE,
        title_ru="Археолог",
        description_ru="5+ разных прессов одного мастера.",
        description_done_ru="5 прессов одного мастера собрано.",
        series="discography",
        tier=AchievementTier.EPIC,
        is_hidden=False,
        triggers=(COLLECTION_ITEM_ADDED, DAILY_TICK),
        evaluator=_stub,
        icon_slug="h4_master_pressings_5",
    ),
    AchievementDefinition(
        code=H5_CODE,
        title_ru="Лейбл-фанат",
        description_ru="20 пластинок одного лейбла.",
        description_done_ru="20 пластинок одного лейбла собрано.",
        series="discography",
        tier=AchievementTier.RARE,
        is_hidden=False,
        triggers=(COLLECTION_ITEM_ADDED, DAILY_TICK),
        evaluator=_stub,
        icon_slug="h5_label_x20",
    ),
    AchievementDefinition(
        code=META_CODE,
        title_ru="Учёный",
        description_ru="H2 + H4 + H5 (любые).",
        description_done_ru="H2, H4 и H5 закрыты.",
        series="discography",
        tier=AchievementTier.LEGEND,
        is_hidden=False,
        triggers=(COLLECTION_ITEM_ADDED, DAILY_TICK),
        evaluator=_stub,
        is_meta=True,
        flavor_ru="Тиражи признали тебя.",
        icon_slug="meta_depth",
    ),
]
