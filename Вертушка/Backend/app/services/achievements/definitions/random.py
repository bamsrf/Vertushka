"""Рандомные ачивки (скрытые, без счётчиков, без push).

Phase 1:
- Числовые: R_thirty_three, R_seventy_eight, R_pi (все с 24h cooldown),
  R_palindrome (год пластинки — палиндром).
- Самореферентные: R_self_titled, R_self_aware, R_meta_vertushka, R_long_title.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any
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


R_SELF_TITLED_CODE = "R_self_titled"
R_THIRTY_THREE_CODE = "R_thirty_three"
R_SEVENTY_EIGHT_CODE = "R_seventy_eight"
R_PI_CODE = "R_pi"
R_PALINDROME_CODE = "R_palindrome"
R_SELF_AWARE_CODE = "R_self_aware"
R_META_VERTUSHKA_CODE = "R_meta_vertushka"
R_LONG_TITLE_CODE = "R_long_title"

EXACT_COUNT_COOLDOWN = timedelta(hours=24)
LONG_TITLE_THRESHOLD = 100  # символов

_SELF_AWARE_TOKENS = ("vinyl", "винил", "record", "пластинк", "analog", "аналог")
_META_VERTUSHKA_TOKENS = (
    "turntable", "вертушк", "phonograph", "фонограф",
    "gramophon", "грамофон", "проигрыватель", "spin",
)


def _normalize(s: str | None) -> str:
    return (s or "").strip().lower()


def _contains_any(haystack: str, tokens: tuple[str, ...]) -> bool:
    h = haystack.lower()
    return any(token in h for token in tokens)


# --- Числовые ----------------------------------------------------------------

def _make_exact_count_evaluator(target: int):
    """Ачивка срабатывает при ровно `target` уникальных пластинок И тишине ≥24h."""
    async def evaluator(
        db: AsyncSession,
        user_id: UUID,
        payload: dict[str, Any],
        unlocked_now: set[str],
    ) -> EvalResult:
        row = await db.execute(
            select(
                func.count(func.distinct(CollectionItem.record_id)),
                func.max(CollectionItem.added_at),
            )
            .join(Collection, CollectionItem.collection_id == Collection.id)
            .where(Collection.user_id == user_id)
        )
        count, last_added = row.one()
        count = int(count or 0)
        if count != target or last_added is None:
            return EvalResult()
        if datetime.utcnow() - last_added < EXACT_COUNT_COOLDOWN:
            return EvalResult()
        return EvalResult(unlocked=True)
    return evaluator


def _is_palindrome_year(year: int | None) -> bool:
    if not year or year < 1000:
        return False
    s = str(year)
    return s == s[::-1]


async def _evaluate_palindrome(
    db: AsyncSession,
    user_id: UUID,
    payload: dict[str, Any],
    unlocked_now: set[str],
) -> EvalResult:
    """Пластинка с годом-палиндромом (1991, 2002, 2112 и т.д.)."""
    record = payload.get("record")
    if record is not None and _is_palindrome_year(getattr(record, "year", None)):
        return EvalResult(unlocked=True)
    # Fallback — проверить всю коллекцию (для daily_tick / бэкфилла)
    result = await db.execute(
        select(Record.year)
        .join(CollectionItem, CollectionItem.record_id == Record.id)
        .join(Collection, CollectionItem.collection_id == Collection.id)
        .where(Collection.user_id == user_id, Record.year.isnot(None))
        .limit(2000)
    )
    for (year,) in result.all():
        if _is_palindrome_year(year):
            return EvalResult(unlocked=True)
    return EvalResult()


# --- Самореферентные --------------------------------------------------------

async def _evaluate_self_titled(
    db: AsyncSession,
    user_id: UUID,
    payload: dict[str, Any],
    unlocked_now: set[str],
) -> EvalResult:
    """`title == artist` после strip/lower."""
    record = payload.get("record")
    if record is not None:
        title = _normalize(getattr(record, "title", None))
        artist = _normalize(getattr(record, "artist", None))
        if title and artist and title == artist:
            return EvalResult(unlocked=True)
    result = await db.execute(
        select(Record.title, Record.artist)
        .join(CollectionItem, CollectionItem.record_id == Record.id)
        .join(Collection, CollectionItem.collection_id == Collection.id)
        .where(Collection.user_id == user_id)
        .limit(2000)
    )
    for title, artist in result.all():
        if _normalize(title) and _normalize(title) == _normalize(artist):
            return EvalResult(unlocked=True)
    return EvalResult()


def _make_token_match_evaluator(tokens: tuple[str, ...], check_artist: bool = True):
    """Ачивка: в `title` (опционально и в `artist`) встречается один из токенов."""
    async def evaluator(
        db: AsyncSession,
        user_id: UUID,
        payload: dict[str, Any],
        unlocked_now: set[str],
    ) -> EvalResult:
        record = payload.get("record")
        if record is not None:
            title = getattr(record, "title", None) or ""
            if _contains_any(title, tokens):
                return EvalResult(unlocked=True)
            if check_artist:
                artist = getattr(record, "artist", None) or ""
                if _contains_any(artist, tokens):
                    return EvalResult(unlocked=True)
        # Fallback — пройдемся по коллекции
        result = await db.execute(
            select(Record.title, Record.artist)
            .join(CollectionItem, CollectionItem.record_id == Record.id)
            .join(Collection, CollectionItem.collection_id == Collection.id)
            .where(Collection.user_id == user_id)
            .limit(2000)
        )
        for title, artist in result.all():
            if title and _contains_any(title, tokens):
                return EvalResult(unlocked=True)
            if check_artist and artist and _contains_any(artist, tokens):
                return EvalResult(unlocked=True)
        return EvalResult()
    return evaluator


async def _evaluate_long_title(
    db: AsyncSession,
    user_id: UUID,
    payload: dict[str, Any],
    unlocked_now: set[str],
) -> EvalResult:
    """Длина title > 100 символов."""
    record = payload.get("record")
    if record is not None:
        title = getattr(record, "title", None) or ""
        if len(title) > LONG_TITLE_THRESHOLD:
            return EvalResult(unlocked=True)
    # Fallback — проверить коллекцию
    result = await db.execute(
        select(Record.title)
        .join(CollectionItem, CollectionItem.record_id == Record.id)
        .join(Collection, CollectionItem.collection_id == Collection.id)
        .where(
            Collection.user_id == user_id,
            func.length(Record.title) > LONG_TITLE_THRESHOLD,
        )
        .limit(1)
    )
    return EvalResult(unlocked=bool(result.first()))


DEFINITIONS: list[AchievementDefinition] = [
    # Числовые
    AchievementDefinition(
        code=R_THIRTY_THREE_CODE,
        title_ru="Тридцать три",
        description_ru="В коллекции ровно 33 пластинки — как 33⅓ оборота.",
        series="random",
        tier=AchievementTier.RARE,
        is_hidden=True,
        triggers=(COLLECTION_ITEM_ADDED, DAILY_TICK),
        evaluator=_make_exact_count_evaluator(33),
        flavor_ru="33⅓. Это не число, это скорость.",
        icon_slug="r_thirty_three",
    ),
    AchievementDefinition(
        code=R_SEVENTY_EIGHT_CODE,
        title_ru="Семьдесят восемь",
        description_ru="В коллекции ровно 78 пластинок — как 78 RPM.",
        series="random",
        tier=AchievementTier.RARE,
        is_hidden=True,
        triggers=(COLLECTION_ITEM_ADDED, DAILY_TICK),
        evaluator=_make_exact_count_evaluator(78),
        flavor_ru="78 RPM. Скорость, которую ещё помнят.",
        icon_slug="r_seventy_eight",
    ),
    AchievementDefinition(
        code=R_PI_CODE,
        title_ru="Число Пи",
        description_ru="В коллекции ровно 314 пластинок — первые цифры числа Пи.",
        series="random",
        tier=AchievementTier.EPIC,
        is_hidden=True,
        triggers=(COLLECTION_ITEM_ADDED, DAILY_TICK),
        evaluator=_make_exact_count_evaluator(314),
        flavor_ru="3.14. Случайно ли?",
        icon_slug="r_pi",
    ),
    AchievementDefinition(
        code=R_PALINDROME_CODE,
        title_ru="Палиндром",
        description_ru="Пластинка с годом-палиндромом в коллекции.",
        series="random",
        tier=AchievementTier.RARE,
        is_hidden=True,
        triggers=(COLLECTION_ITEM_ADDED,),
        evaluator=_evaluate_palindrome,
        flavor_ru="Год, который читается одинаково.",
        icon_slug="r_palindrome",
    ),
    # Самореферентные
    AchievementDefinition(
        code=R_SELF_TITLED_CODE,
        title_ru="Тёзка",
        description_ru="Пластинка, где имя артиста совпадает с названием.",
        series="random",
        tier=AchievementTier.RARE,
        is_hidden=True,
        triggers=(COLLECTION_ITEM_ADDED,),
        evaluator=_evaluate_self_titled,
        flavor_ru="Имя и название — близнецы.",
        icon_slug="r_self_titled",
    ),
    AchievementDefinition(
        code=R_SELF_AWARE_CODE,
        title_ru="Самосознание",
        description_ru="Пластинка про саму музыку и пластинки.",
        series="random",
        tier=AchievementTier.RARE,
        is_hidden=True,
        triggers=(COLLECTION_ITEM_ADDED,),
        evaluator=_make_token_match_evaluator(_SELF_AWARE_TOKENS, check_artist=False),
        flavor_ru="Пластинка о пластинке.",
        icon_slug="r_self_aware",
    ),
    AchievementDefinition(
        code=R_META_VERTUSHKA_CODE,
        title_ru="Вертушка",
        description_ru="Пластинка про вертушку — тёзка приложения.",
        series="random",
        tier=AchievementTier.EPIC,
        is_hidden=True,
        triggers=(COLLECTION_ITEM_ADDED,),
        evaluator=_make_token_match_evaluator(_META_VERTUSHKA_TOKENS, check_artist=True),
        flavor_ru="Сама вертушка.",
        icon_slug="r_meta_vertushka",
    ),
    AchievementDefinition(
        code=R_LONG_TITLE_CODE,
        title_ru="Поэма",
        description_ru="Пластинка с очень длинным названием.",
        series="random",
        tier=AchievementTier.RARE,
        is_hidden=True,
        triggers=(COLLECTION_ITEM_ADDED,),
        evaluator=_evaluate_long_title,
        flavor_ru="Название длиннее некоторых песен.",
        icon_slug="r_long_title",
    ),
]
