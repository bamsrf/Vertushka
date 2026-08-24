"""Пасхалка «Шестьдесят девять» (R_sixty_nine) — счёт и кулдаун.

Две регрессии сразу.

1. Счёт шёл по ВСЕМ коллекциям юзера (join Collection по user_id), а папки —
   это отдельные Collection с копиями тех же пластинок. «Ровно 69» ловилось не
   тем числом, которое юзер видит на экране коллекции.

2. Условие «сутки тишины» проверял только daily_tick в 6:00 UTC, а
   COLLECTION_ITEM_ADDED выдать пасхалку не может по построению — добавление
   само обнуляет кулдаун. Набравший порог вечером ждал почти двое суток.
   Отсюда третий триггер COOLDOWN_TICK.

Живой БД нет: evaluator ходит в неё единственным execute() за парой
(уникальных, последнее добавление) — его подменяет FakeSession. Запрос при
этом сохраняем и компилируем, чтобы проверить, по какой коллекции он считает.
"""
from datetime import datetime, timedelta

import pytest

from app.services.achievements.definitions import eggs as E
from app.services.achievements.events import (
    COLLECTION_ITEM_ADDED,
    COOLDOWN_TICK,
    DAILY_TICK,
)

USER = "00000000-0000-0000-0000-000000000069"


class _FakeResult:
    def __init__(self, row):
        self._row = row

    def one(self):
        return self._row


class FakeSession:
    """Стаб под evaluator: отдаёт (count, last_added) и помнит запрос."""

    def __init__(self, count, last_added):
        self._row = (count, last_added)
        self.stmt = None

    async def execute(self, stmt, *_args, **_kwargs):
        self.stmt = stmt
        return _FakeResult(self._row)


def _evaluator():
    return E._make_exact_count(69)


async def _run(count, last_added):
    db = FakeSession(count, last_added)
    result = await _evaluator()(db, USER, {}, set())
    return result, db


# --- Кулдаун -------------------------------------------------------------------

@pytest.mark.asyncio
async def test_exact_count_with_silence_unlocks():
    long_ago = datetime.utcnow() - E.EXACT_COUNT_COOLDOWN - timedelta(minutes=1)
    result, _ = await _run(69, long_ago)
    assert result.unlocked is True


@pytest.mark.asyncio
async def test_fresh_add_keeps_it_locked():
    # Ровно порог, но пластинку добавили только что — юзер ещё в процессе.
    result, _ = await _run(69, datetime.utcnow() - timedelta(hours=1))
    assert result.unlocked is False


@pytest.mark.asyncio
async def test_just_under_cooldown_keeps_it_locked():
    # Граница: 23:59 после добавления — ещё рано.
    almost = datetime.utcnow() - E.EXACT_COUNT_COOLDOWN + timedelta(minutes=1)
    result, _ = await _run(69, almost)
    assert result.unlocked is False


@pytest.mark.asyncio
async def test_empty_collection_does_not_unlock():
    result, _ = await _run(0, None)
    assert result.unlocked is False


# --- Порог ---------------------------------------------------------------------

@pytest.mark.parametrize("count", [68, 70, 138])
@pytest.mark.asyncio
async def test_other_counts_do_not_unlock(count):
    # 138 = 69 × 2: ровно то, что раньше давал двойной счёт по папкам.
    long_ago = datetime.utcnow() - E.EXACT_COUNT_COOLDOWN - timedelta(hours=1)
    result, _ = await _run(count, long_ago)
    assert result.unlocked is False


# --- Только основная коллекция -------------------------------------------------

@pytest.mark.asyncio
async def test_counts_main_collection_only():
    """Запрос обязан сужаться до одной коллекции, а не идти по всем юзерским.

    Признак сужения — сабквери с ORDER BY sort_order ... LIMIT 1. Если кто-то
    вернёт join по Collection.user_id, папки снова полезут в счёт.
    """
    long_ago = datetime.utcnow() - E.EXACT_COUNT_COOLDOWN - timedelta(hours=1)
    _, db = await _run(69, long_ago)
    sql = str(db.stmt.compile(compile_kwargs={"literal_binds": False}))
    assert "sort_order" in sql
    assert "LIMIT" in sql.upper()
    assert "collection_items.collection_id = (" in sql


# --- Триггеры ------------------------------------------------------------------

def _definition(code):
    return next(d for d in E.DEFINITIONS if d.code == code)


def test_sixty_nine_listens_to_hourly_cooldown_tick():
    triggers = _definition(E.R_SIXTY_NINE).triggers
    assert COOLDOWN_TICK in triggers
    # Суточный тик остаётся страховкой, add — совместимость с ядром.
    assert DAILY_TICK in triggers
    assert COLLECTION_ITEM_ADDED in triggers


def test_exact_count_registry_matches_definition():
    # Фоновая задача отбирает кандидатов по этому реестру: разъедется —
    # пасхалка перестанет доезжать в срок.
    assert E.EXACT_COUNT_ACHIEVEMENTS == {E.R_SIXTY_NINE: 69}


def test_description_mentions_the_silence():
    defn = _definition(E.R_SIXTY_NINE)
    assert "сутки" in defn.description_ru
    assert "сутки" in defn.description_done_ru
