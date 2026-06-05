"""Реестр определений ачивок.

Каждая ачивка описывается через AchievementDefinition. Evaluator получает
сессию БД, user_id и payload события и возвращает EvalResult.

Имена тиров — финальные (см. PLAN_ACHIEVEMENTS_V2.md §3.1):
  💧 Простая → 🔵 Заметная → 🌸 Редкая → 🌌 Эпическая → ⚫ Легенда.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Awaitable, Callable, TYPE_CHECKING

if TYPE_CHECKING:
    from uuid import UUID
    from sqlalchemy.ext.asyncio import AsyncSession


class AchievementTier(str, Enum):
    SIMPLE = "simple"      # 💧 Простая
    NOTABLE = "notable"    # 🔵 Заметная
    RARE = "rare"          # 🌸 Редкая
    EPIC = "epic"          # 🌌 Эпическая
    LEGEND = "legend"      # ⚫ Легенда


TIER_LABELS_RU: dict[AchievementTier, str] = {
    AchievementTier.SIMPLE: "Простая",
    AchievementTier.NOTABLE: "Заметная",
    AchievementTier.RARE: "Редкая",
    AchievementTier.EPIC: "Эпическая",
    AchievementTier.LEGEND: "Легенда",
}


@dataclass
class EvalResult:
    """Результат проверки одного evaluator-а."""
    unlocked: bool = False
    progress: int | None = None
    progress_target: int | None = None
    metadata: dict[str, Any] | None = None


@dataclass(frozen=True)
class AchievementDefinition:
    code: str
    title_ru: str
    description_ru: str
    series: str                # 'foundation', 'scale', 'gifts', 'random'
    tier: AchievementTier
    is_hidden: bool
    triggers: tuple[str, ...]
    evaluator: Callable[
        ["AsyncSession", "UUID", dict[str, Any] | None, set[str]],
        Awaitable[EvalResult],
    ]
    is_meta: bool = False       # Мета-ачивка серии (выдаётся после всех остальных)
    flavor_ru: str = ""
    icon_slug: str = ""         # имя SVG-файла без .svg (для Mobile assets)
    description_done_ru: str = ""  # текст в прошедшем времени, когда ачивка открыта


# --- Реестр (заполняется в конце файла после импорта definitions) ---
_DEFINITIONS: list[AchievementDefinition] = []
_BY_CODE: dict[str, AchievementDefinition] = {}
_BY_TRIGGER: dict[str, list[AchievementDefinition]] = {}


def register(*defs: AchievementDefinition) -> None:
    """Регистрирует список определений. Идёт в порядке передачи."""
    for d in defs:
        if d.code in _BY_CODE:
            raise ValueError(f"Achievement code conflict: {d.code}")
        _BY_CODE[d.code] = d
        _DEFINITIONS.append(d)
        for trigger in d.triggers:
            _BY_TRIGGER.setdefault(trigger, []).append(d)


def get_definition(code: str) -> AchievementDefinition | None:
    return _BY_CODE.get(code)


def all_definitions() -> list[AchievementDefinition]:
    """Все зарегистрированные ачивки в порядке регистрации."""
    return list(_DEFINITIONS)


def get_definitions_for_event(event: str) -> list[AchievementDefinition]:
    """Определения, реагирующие на это событие, в порядке регистрации.

    Важно: мета-ачивки должны идти ПОСЛЕ обычных (это гарантируется порядком
    регистрации внутри файла серии — мета регистрируется последней).
    """
    return list(_BY_TRIGGER.get(event, ()))


def reset_registry() -> None:
    """Только для тестов."""
    _DEFINITIONS.clear()
    _BY_CODE.clear()
    _BY_TRIGGER.clear()


# Загружаем определения. Порядок важен: серии раньше, рандом — после.
# Внутри серии: обычные ачивки → мета-ачивка.
#
# Серии-каркасы (rarity / geography / eras / genres / invitations / discography
# + J2–J6 в gifts.py) — это SCAFFOLDING. Их evaluator-ы возвращают
# `unlocked=False`, поэтому ничего не выдают пользователям. Каталог-эндпоинт
# отдаёт их как «навсегда залоченные», чтобы Mobile-команда видела сетку серий
# в UI и проверяла верстку до прихода финальных дизайнов/копирайта.
def _load_definitions() -> None:
    # Импорты внутри функции, чтобы избежать циклов и регистрировать в нужном порядке.
    from app.services.achievements.definitions.series import foundation as _foundation
    from app.services.achievements.definitions.series import scale as _scale
    from app.services.achievements.definitions.series import gifts as _gifts
    from app.services.achievements.definitions.series import community as _community
    from app.services.achievements.definitions.series import rarity as _rarity
    from app.services.achievements.definitions.series import geography as _geography
    from app.services.achievements.definitions.series import eras as _eras
    from app.services.achievements.definitions.series import genres as _genres
    from app.services.achievements.definitions.series import invitations as _invitations
    from app.services.achievements.definitions.series import discography as _discography
    from app.services.achievements.definitions import random as _random

    # Реальная логика (Phase 0 / Phase 1)
    register(*_foundation.DEFINITIONS)
    register(*_scale.DEFINITIONS)
    register(*_gifts.DEFINITIONS)
    register(*_community.DEFINITIONS)
    # Каркасы (Phase 2–4) — evaluator всегда False
    register(*_rarity.DEFINITIONS)
    register(*_geography.DEFINITIONS)
    register(*_eras.DEFINITIONS)
    register(*_genres.DEFINITIONS)
    register(*_invitations.DEFINITIONS)
    register(*_discography.DEFINITIONS)
    # Рандом — после всех серий
    register(*_random.DEFINITIONS)


_load_definitions()
