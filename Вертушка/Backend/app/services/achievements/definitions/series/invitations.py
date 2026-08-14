"""Серия «Глас наружу» (INV* + META_evangelist).

⛔ СЕРИЯ ОТКЛЮЧЕНА. Реферальной программы в приложении нет, поэтому:
- `_group_series` в app/api/achievements.py пропускает series == "invitations" —
  секции нет в каталоге;
- `_EXCLUDED_SERIES` в levels.py убирает серию из XP уровня;
- все эвалюаторы здесь — `_stub`, ачивки не открываются и пуши не летят.
Модуль остаётся каркасом: когда появятся приглашения, снять три этих замка
и заменить `_stub` на реальные проверки.

⚠️ КАРКАС / SCAFFOLDING. Все evaluator-ы возвращают `unlocked=False`.

ЗАВИСИМОСТИ перед запуском Phase 2/3:
- Поле `User.referred_by_user_id`.
- Реферальная атрибуция: `?ref=<username>` на ссылке публичного профиля
  + deferred deep link (Branch / Firebase Dynamic Links).
- Эмиссия `referred_user_registered` в `auth.py` после регистрации.
- Эмиссия `referred_user_activated` из `daily_tick` при достижении приведённым
  юзером ≥10 пластинок и возраста ≥30 дней.

См. PLAN_ACHIEVEMENTS_V2.md §4.9.

Состав:
- INV_first         «Сарафан»     — 1 регистрация по ссылке
- INV_three         «Расходится»  — 3 регистрации
- INV_ten           «Тренд»       — 10 регистраций
- INV_active_circle «Живой круг»  — ≥5 приведённых активны (≥30д, ≥10 пластинок)
- INV_chain         «Цепочка»     — кто-то из приведённых сам кого-то привёл
- INV_from_showcase «Из витрины»  — приведённый юзер добавил пластинку из Витрины
                                    в первые 7 дней. (Требует фичи Витрины.)
- META_evangelist   «Эпидемия»    — INV_ten + INV_active_circle + INV_chain.
                                    Награда: title «Эпидемиолог» + холографическая рамка.
"""
from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.achievements.events import (
    DAILY_TICK,
    REFERRED_USER_ACTIVATED,
    REFERRED_USER_REGISTERED,
)
from app.services.achievements.registry import (
    AchievementDefinition,
    AchievementTier,
    EvalResult,
)


INV_FIRST_CODE = "INV_first"
INV_THREE_CODE = "INV_three"
INV_TEN_CODE = "INV_ten"
INV_ACTIVE_CIRCLE_CODE = "INV_active_circle"
INV_CHAIN_CODE = "INV_chain"
INV_FROM_SHOWCASE_CODE = "INV_from_showcase"
META_CODE = "META_evangelist"
INVITATION_CODES = {
    INV_FIRST_CODE,
    INV_THREE_CODE,
    INV_TEN_CODE,
    INV_ACTIVE_CIRCLE_CODE,
    INV_CHAIN_CODE,
    INV_FROM_SHOWCASE_CODE,
}


async def _stub(
    db: AsyncSession,
    user_id: UUID,
    payload: dict[str, Any] | None,
    unlocked_now: set[str],
) -> EvalResult:
    return EvalResult(unlocked=False)


DEFINITIONS: list[AchievementDefinition] = [
    AchievementDefinition(
        code=INV_FIRST_CODE,
        title_ru="Сарафан",
        description_ru="Кто-то зарегистрировался по твоей ссылке.",
        description_done_ru="Первый друг пришёл по ссылке.",
        series="invitations",
        tier=AchievementTier.SIMPLE,
        is_hidden=False,
        triggers=(REFERRED_USER_REGISTERED,),
        evaluator=_stub,
        icon_slug="inv_first",
    ),
    AchievementDefinition(
        code=INV_THREE_CODE,
        title_ru="Расходится",
        description_ru="3 регистрации по твоей ссылке.",
        description_done_ru="3 друга пришли по ссылке.",
        series="invitations",
        tier=AchievementTier.NOTABLE,
        is_hidden=False,
        triggers=(REFERRED_USER_REGISTERED,),
        evaluator=_stub,
        icon_slug="inv_three",
    ),
    AchievementDefinition(
        code=INV_TEN_CODE,
        title_ru="Тренд",
        description_ru="10 регистраций.",
        description_done_ru="10 друзей пришли по ссылке.",
        series="invitations",
        tier=AchievementTier.RARE,
        is_hidden=False,
        triggers=(REFERRED_USER_REGISTERED,),
        evaluator=_stub,
        icon_slug="inv_ten",
    ),
    AchievementDefinition(
        code=INV_ACTIVE_CIRCLE_CODE,
        title_ru="Живой круг",
        description_ru="≥5 приведённых активны ≥30 дней и имеют ≥10 пластинок.",
        description_done_ru="Круг из 5 активных друзей собран.",
        series="invitations",
        tier=AchievementTier.RARE,
        is_hidden=False,
        triggers=(REFERRED_USER_ACTIVATED, DAILY_TICK),
        evaluator=_stub,
        icon_slug="inv_active_circle",
    ),
    AchievementDefinition(
        code=INV_CHAIN_CODE,
        title_ru="Цепочка",
        description_ru="Приведённый тобой сам кого-то привёл.",
        description_done_ru="Приглашённый тобой сам привёл нового человека.",
        series="invitations",
        tier=AchievementTier.EPIC,
        is_hidden=False,
        triggers=(REFERRED_USER_REGISTERED, DAILY_TICK),
        evaluator=_stub,
        icon_slug="inv_chain",
    ),
    AchievementDefinition(
        code=INV_FROM_SHOWCASE_CODE,
        title_ru="Из витрины",
        description_ru="По твоей ссылке кто-то добавил пластинку из Витрины в первые 7 дней.",
        description_done_ru="Друг взял пластинку с Витрины.",
        series="invitations",
        tier=AchievementTier.NOTABLE,
        is_hidden=False,
        triggers=(REFERRED_USER_REGISTERED, DAILY_TICK),
        evaluator=_stub,
        icon_slug="inv_from_showcase",
    ),
    AchievementDefinition(
        code=META_CODE,
        title_ru="Эпидемия",
        description_ru="Открой «Тренд», «Живой круг» и «Цепочку».",
        description_done_ru="«Тренд», «Живой круг» и «Цепочка» закрыты.",
        series="invitations",
        tier=AchievementTier.LEGEND,
        is_hidden=False,
        triggers=(REFERRED_USER_REGISTERED, REFERRED_USER_ACTIVATED, DAILY_TICK),
        evaluator=_stub,
        is_meta=True,
        flavor_ru="Слышно даже по соседям.",
        icon_slug="meta_evangelist",
    ),
]
