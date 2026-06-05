"""Серия «Охота за редкостями» (C* + META_rarity).

⚠️ КАРКАС / SCAFFOLDING.

Финальные дизайны и тексты ещё не утверждены — все evaluator-ы возвращают
`unlocked=False`. Каталог-эндпоинт отдаёт эти ачивки как «навсегда залоченные»,
чтобы Mobile-команда могла видеть структуру серии в UI и проверять верстку.

Зависимости перед запуском Phase 3:
- Поля `Record.is_collectible`, `Record.is_limited`, `Record.is_hot` — см.
  `docs/plans/RARITY_BADGES_PLAN.md`. Discogs-первопресс выпилен (нет надёжной
  разметки), серия строится вокруг трёх флагов.
- Анти-фарм: тот же `ANTIFARM_COOLDOWN=24h`, что в B-серии.

Состав (см. PLAN_ACHIEVEMENTS_V2.md §4.3):
- C1 «Тираж ограничен» (5 лимиток)
- C2 «По счёту»       (25 лимиток)
- C3 «Сокровище»      (1 коллекционка)
- C4 «Шкаф редкостей» (5 коллекционок)
- C5 «Кладовая»       (15 коллекционок)
- C6 «Хочу горячего»  (5 hot в вишлисте одновременно)
- C7 «Тренд на полке» (10 hot в коллекции)
- META_rarity «Грааль» (C2 + C5 + C7)
"""
from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.achievements.events import (
    COLLECTION_ITEM_ADDED,
    WISHLIST_ITEM_ADDED,
)
from app.services.achievements.registry import (
    AchievementDefinition,
    AchievementTier,
    EvalResult,
)


C1_CODE = "C1_limited_x5"
C2_CODE = "C2_limited_x25"
C3_CODE = "C3_collectible_x1"
C4_CODE = "C4_collectible_x5"
C5_CODE = "C5_collectible_x15"
C6_CODE = "C6_hot_in_wishlist"
C7_CODE = "C7_hot_in_collection"
META_CODE = "META_rarity"
RARITY_CODES = {C1_CODE, C2_CODE, C3_CODE, C4_CODE, C5_CODE, C6_CODE, C7_CODE}


async def _stub(
    db: AsyncSession,
    user_id: UUID,
    payload: dict[str, Any] | None,
    unlocked_now: set[str],
) -> EvalResult:
    """Заглушка: всегда False. Реальная логика — Phase 3."""
    return EvalResult(unlocked=False)


DEFINITIONS: list[AchievementDefinition] = [
    AchievementDefinition(
        code=C1_CODE,
        title_ru="Тираж ограничен",
        description_ru="Добавь 5 лимиток в коллекцию.",
        description_done_ru="5 лимиток в коллекции.",
        series="rarity",
        tier=AchievementTier.SIMPLE,
        is_hidden=False,
        triggers=(COLLECTION_ITEM_ADDED,),
        evaluator=_stub,
        icon_slug="c1_limited_x5",
    ),
    AchievementDefinition(
        code=C2_CODE,
        title_ru="По счёту",
        description_ru="Добери 25 лимиток.",
        description_done_ru="25 лимиток собрано.",
        series="rarity",
        tier=AchievementTier.RARE,
        is_hidden=False,
        triggers=(COLLECTION_ITEM_ADDED,),
        evaluator=_stub,
        icon_slug="c2_limited_x25",
    ),
    AchievementDefinition(
        code=C3_CODE,
        title_ru="Сокровище",
        description_ru="Найди первую коллекционку.",
        description_done_ru="Первая коллекционка найдена.",
        series="rarity",
        tier=AchievementTier.NOTABLE,
        is_hidden=False,
        triggers=(COLLECTION_ITEM_ADDED,),
        evaluator=_stub,
        icon_slug="c3_collectible_x1",
    ),
    AchievementDefinition(
        code=C4_CODE,
        title_ru="Шкаф редкостей",
        description_ru="5 коллекционок на полке.",
        description_done_ru="5 коллекционок на полке.",
        series="rarity",
        tier=AchievementTier.RARE,
        is_hidden=False,
        triggers=(COLLECTION_ITEM_ADDED,),
        evaluator=_stub,
        icon_slug="c4_collectible_x5",
    ),
    AchievementDefinition(
        code=C5_CODE,
        title_ru="Кладовая",
        description_ru="15 коллекционок.",
        description_done_ru="15 коллекционок собрано.",
        series="rarity",
        tier=AchievementTier.EPIC,
        is_hidden=False,
        triggers=(COLLECTION_ITEM_ADDED,),
        evaluator=_stub,
        icon_slug="c5_collectible_x15",
    ),
    AchievementDefinition(
        code=C6_CODE,
        title_ru="Хочу горячего",
        description_ru="5 горячих пластинок одновременно в вишлисте.",
        description_done_ru="5 горячих пластинок в вишлисте.",
        series="rarity",
        tier=AchievementTier.NOTABLE,
        is_hidden=False,
        triggers=(WISHLIST_ITEM_ADDED,),
        evaluator=_stub,
        icon_slug="c6_hot_in_wishlist",
    ),
    AchievementDefinition(
        code=C7_CODE,
        title_ru="Тренд на полке",
        description_ru="10 горячих пластинок в коллекции.",
        description_done_ru="10 горячих пластинок в коллекции.",
        series="rarity",
        tier=AchievementTier.RARE,
        is_hidden=False,
        triggers=(COLLECTION_ITEM_ADDED,),
        evaluator=_stub,
        icon_slug="c7_hot_in_collection",
    ),
    # META — всегда последний
    AchievementDefinition(
        code=META_CODE,
        title_ru="Грааль",
        description_ru="Открой C2 + C5 + C7.",
        description_done_ru="C2, C5 и C7 открыты.",
        series="rarity",
        tier=AchievementTier.EPIC,
        is_hidden=False,
        triggers=(COLLECTION_ITEM_ADDED, WISHLIST_ITEM_ADDED),
        evaluator=_stub,
        is_meta=True,
        flavor_ru="Не каждая полка дотянет.",
        icon_slug="meta_rarity",
    ),
]
