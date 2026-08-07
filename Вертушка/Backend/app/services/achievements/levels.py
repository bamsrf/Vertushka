"""Лестница архетипов «Физика звука» — серверное зеркало Mobile/lib/archetype.ts.

Зачем дубль: уровень считается на клиенте (hero-блок ачивок), но пуш «ты взял
новый уровень» может отправить только бэкенд — в момент открытия ачивки. Обе
таблицы обязаны совпадать, иначе push объявит уровень, которого юзер не увидит.

ИНВАРИАНТ: LEVELS и TIER_WEIGHT здесь идентичны Mobile/lib/archetype.ts.
Меняешь пороги/веса — правь оба файла в одном коммите.
Проверяется тестом Backend/tests/test_achievement_levels.py.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user_achievement import UserAchievement
from app.services.achievements.registry import (
    AchievementTier,
    all_definitions,
    get_definition,
)

logger = logging.getLogger(__name__)


# Очки за тир. Геометрия x3 — см. PLAN_ACHIEVEMENTS_ARCHETYPES_V3.md.
TIER_WEIGHT: dict[str, int] = {
    AchievementTier.SIMPLE.value: 1,
    AchievementTier.NOTABLE.value: 3,
    AchievementTier.RARE.value: 10,
    AchievementTier.EPIC.value: 30,
    AchievementTier.LEGEND.value: 100,
}


@dataclass(frozen=True)
class LevelDef:
    key: str
    label: str
    threshold: int
    flavor: str


LEVELS: tuple[LevelDef, ...] = (
    LevelDef("silence", "Тишь", 0, "Ты ещё не нажал на play. Но уже пришёл."),
    LevelDef("rustle", "Шорох", 7, "Игла коснулась. Всё остальное — дело времени."),
    LevelDef(
        "echo", "Эхо", 15,
        "Что-то услышанное однажды не уходит. Оно возвращается.",
    ),
    LevelDef("wave", "Волна", 25, "Ты больше не слушаешь музыку. Ты в ней."),
    LevelDef(
        "resonance", "Резонанс", 50,
        "Правильная пластинка в правильный момент — это физика, не случайность.",
    ),
    LevelDef(
        "overtone", "Обертон", 100,
        "Слышишь то, чего нет в нотах. Значит, слух уже другой.",
    ),
    LevelDef(
        "amplitude", "Амплитуда", 250,
        "Твоя коллекция давит на воздух. Это чувствуют все, кто входит в комнату.",
    ),
    LevelDef(
        "frequency", "Частота", 425,
        "Ты настроен точнее большинства. Фальшь слышна за три такта.",
    ),
    LevelDef("tuning_fork", "Камертон", 675, "К тебе приходят сверяться. Ты — точка отсчёта."),
    LevelDef("primal_sound", "Первозвук", 1050, "Было время до тебя. Теперь от тебя считают."),
)


# Что НЕ идёт в зачёт уровня:
#   invitations — реферальной программы нет, ачивки недостижимы;
#   K5/K6 (is_hidden вне random) — выпилены из грида в v2.1.
# Пасхалки (random) в зачёт ИДУТ, хотя и помечены скрытыми: они открываются
# по-настоящему и показываются отдельным счётчиком в hero.
_EXCLUDED_SERIES = frozenset({"invitations"})


def resolve_definition(code: str):
    """Определение по коду, включая ДИНАМИЧЕСКИЕ коды.

    Динамические ачивки хранятся в БД как `H2:king-crimson`, а в реестре
    зарегистрированы под полным именем `H2_artist_studio_full` — прямой
    `get_definition` по такому коду возвращает None, и ачивка молча стоила бы
    0 XP. Поэтому для кода с двоеточием ищем определение по префиксу.
    """
    defn = get_definition(code)
    if defn is not None:
        return defn
    prefix, sep, _rest = code.partition(":")
    if not sep:
        return None
    for candidate in all_definitions():
        if candidate.code.split("_", 1)[0] == prefix:
            return candidate
    return None


def counts_toward_level(code: str) -> bool:
    """Учитывается ли ачивка в XP-счётчике уровня."""
    defn = resolve_definition(code)
    if defn is None:
        return False
    if defn.series in _EXCLUDED_SERIES:
        return False
    # Скрытая и при этом не пасхалка — это выпиленные K5/K6.
    if defn.is_hidden and defn.series != "random":
        return False
    return True


def weight_for_code(code: str) -> int:
    """Очки за конкретную ачивку по её тиру.

    Неизвестный код или ачивка вне видимого каталога → 0.
    """
    defn = resolve_definition(code)
    if defn is None or not counts_toward_level(code):
        return 0
    return TIER_WEIGHT.get(defn.tier.value, 0)


def level_index_for_score(score: int) -> int:
    """Индекс уровня 0..9 для набранных очков."""
    idx = 0
    for i, level in enumerate(LEVELS):
        if score >= level.threshold:
            idx = i
        else:
            break
    return idx


async def compute_score(db: AsyncSession, user_id: UUID) -> int:
    """Суммарный XP по всем открытым ачивкам юзера.

    Считается по ЗАМОРОЖЕННЫМ значениям (`xp_awarded`): сколько ачивка стоила
    в момент, когда юзер её взял. Поэтому сумма не может уменьшиться, даже
    если вес тира потом поменяется.

    `xp_awarded IS NULL` — строка из времён до заморозки, для неё падаем на
    текущий вес тира. После бэкфилла миграцией таких быть не должно.
    """
    rows = await db.execute(
        select(UserAchievement.code, UserAchievement.xp_awarded).where(
            UserAchievement.user_id == user_id,
            UserAchievement.is_unlocked.is_(True),
        )
    )
    return sum(
        xp if xp is not None else weight_for_code(code)
        for code, xp in rows.all()
    )


@dataclass(frozen=True)
class LevelUp:
    """Факт перехода на новый уровень."""
    level: LevelDef
    previous: LevelDef
    score: int
    index: int


async def detect_level_up(
    db: AsyncSession,
    user_id: UUID,
    *,
    unlocked_codes: list[str],
) -> LevelUp | None:
    """Проверяет, перевёл ли текущий батч ачивок юзера на новый уровень.

    Score «до» восстанавливаем вычитанием весов только что открытых ачивок —
    так не нужна отдельная колонка с последним уровнем и нет расхождения при
    бэкфиллах. Возвращает None, если уровень не изменился.

    За один батч можно перепрыгнуть несколько ступеней (легенда за 100 XP) —
    тогда сообщаем про финальную.
    """
    if not unlocked_codes:
        return None

    # Только что открытые ачивки заморожены текущим весом (_persist делает это
    # в той же транзакции), поэтому вычесть можно по нему же.
    delta = sum(weight_for_code(code) for code in unlocked_codes)
    if delta <= 0:
        return None

    score_after = await compute_score(db, user_id)
    score_before = max(0, score_after - delta)

    idx_after = level_index_for_score(score_after)
    idx_before = level_index_for_score(score_before)
    if idx_after <= idx_before:
        return None

    return LevelUp(
        level=LEVELS[idx_after],
        previous=LEVELS[idx_before],
        score=score_after,
        index=idx_after,
    )
