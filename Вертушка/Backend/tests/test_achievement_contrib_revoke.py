"""Вклад (K8–K10): считаем только живые ручные релизы.

Дыра: релиз добавляли, забирали «Стажёра» и тут же удаляли — ачивка
оставалась, а счётчик прогресса не умел уменьшаться (гейт «только вверх» в
_persist). Получалось, что удалённый релиз навсегда числился вкладом.

Теперь K8–K10 помечены revocable: ядро прогоняет их даже по открытой ачивке,
прогресс ходит в обе стороны, а при падении ниже порога анлок снимается
вместе с замороженным XP. Живой БД у тестов нет — сессия подменяется стабом.
"""
import uuid

import pytest

from app.services.achievements import evaluator as core
from app.services.achievements.definitions.series import community as C
from app.services.achievements.events import (
    DAILY_TICK,
    USER_RECORD_CREATED,
    USER_RECORD_DELETED,
)
from app.services.achievements.registry import (
    AchievementDefinition,
    AchievementTier,
    EvalResult,
    get_definition,
    get_definitions_for_event,
)

USER = uuid.UUID("00000000-0000-0000-0000-000000000008")


# ── счётчик вклада ──────────────────────────────────────────────────────── #

class _CountSession:
    """Стаб под evaluator: отдаёт число и помнит запрос."""

    def __init__(self, count):
        self._count = count
        self.stmt = None

    async def scalar(self, stmt, *_args, **_kwargs):
        self.stmt = stmt
        return self._count


async def _contrib(threshold, count):
    db = _CountSession(count)
    result = await C._make_contrib_evaluator(threshold)(db, USER, {}, set())
    return result, db


@pytest.mark.asyncio
async def test_contrib_counts_only_alive_statuses():
    _, db = await _contrib(1, 0)
    values = set()
    for raw in db.stmt.compile().params.values():
        # IN (...) приходит одним expanding-параметром — списком.
        values.update(raw if isinstance(raw, (list, tuple)) else [raw])
    assert "user" in values  # source='user'
    # approved — живая запись, merged — слитая с Discogs (вклад состоялся).
    assert {"approved", "merged"} <= values
    # Удалённые автором и снятые по жалобе в счёт не идут.
    assert "deleted" not in values
    assert "rejected" not in values


@pytest.mark.asyncio
async def test_contrib_progress_follows_count():
    result, _ = await _contrib(5, 3)
    assert result.unlocked is False
    assert (result.progress, result.progress_target) == (3, 5)

    result, _ = await _contrib(5, 5)
    assert result.unlocked is True


def test_contrib_definitions_are_revocable_and_listen_to_delete():
    for code in (C.K8_CODE, C.K9_CODE, C.K10_CODE):
        defn = get_definition(code)
        assert defn is not None
        assert defn.revocable is True, code
        assert set(defn.triggers) == {
            USER_RECORD_CREATED,
            USER_RECORD_DELETED,
            DAILY_TICK,
        }, code
    codes = {d.code for d in get_definitions_for_event(USER_RECORD_DELETED)}
    assert {C.K8_CODE, C.K9_CODE, C.K10_CODE} <= codes


def test_wanted_and_community_stay_permanent():
    # Отзыв — точечная механика вклада, а не новое правило для всех ачивок.
    for code in (C.K1_CODE, C.K14_CODE, C.META_CODE):
        assert get_definition(code).revocable is False, code


# ── ядро: отзыв анлока ──────────────────────────────────────────────────── #

class _FakeUA:
    def __init__(self, code, *, is_unlocked, progress, xp_awarded):
        self.code = code
        self.is_unlocked = is_unlocked
        self.unlocked_at = "было"
        self.progress = progress
        self.progress_target = 5
        self.xp_awarded = xp_awarded
        self.ach_metadata = None


class _Scalars:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


class _Result:
    def __init__(self, rows):
        self._rows = rows

    def scalars(self):
        return _Scalars(self._rows)


class _CoreSession:
    """Минимальная сессия под _emit_impl: одна выборка строк + no-op запись."""

    def __init__(self, rows):
        self._rows = rows
        self.added = []
        self.commits = 0
        self.deletes = 0

    async def execute(self, stmt, *_args, **_kwargs):
        if getattr(stmt, "is_delete", False):
            self.deletes += 1
            return None
        rows, self._rows = self._rows, []
        return _Result(rows)

    def add(self, obj):
        self.added.append(obj)

    async def flush(self):
        return None

    async def commit(self):
        self.commits += 1

    async def rollback(self):
        return None


def _stub_def(*, code, unlocked, progress, revocable):
    async def _eval(_db, _user, _payload, _unlocked_now):
        return EvalResult(
            unlocked=unlocked, progress=progress, progress_target=5
        )

    return AchievementDefinition(
        code=code,
        title_ru="Стаб",
        description_ru="",
        series="contribution",
        tier=AchievementTier.SIMPLE,
        is_hidden=False,
        triggers=(USER_RECORD_DELETED,),
        evaluator=_eval,
        revocable=revocable,
    )


async def _emit(monkeypatch, defn, row):
    monkeypatch.setattr(
        core, "get_definitions_for_event", lambda _event: [defn]
    )
    db = _CoreSession([row] if row is not None else [])
    unlocked = await core._emit_impl(db, USER, USER_RECORD_DELETED, {})
    return unlocked, row, db


@pytest.mark.asyncio
async def test_revocable_unlock_is_taken_back(monkeypatch):
    row = _FakeUA("STUB_rev", is_unlocked=True, progress=1, xp_awarded=1)
    defn = _stub_def(code="STUB_rev", unlocked=False, progress=0, revocable=True)

    unlocked, row, db = await _emit(monkeypatch, defn, row)

    assert unlocked == []          # отзыв — не анлок, пуша быть не должно
    # «Ты открыл X» для снятой ачивки из ленты уходит.
    assert db.deletes == 1
    assert row.is_unlocked is False
    assert row.unlocked_at is None
    assert row.xp_awarded is None  # уровень не держится за удалённый вклад
    assert row.progress == 0       # счётчик поехал вниз


@pytest.mark.asyncio
async def test_revocable_progress_can_decrease_while_unlocked(monkeypatch):
    # Было 20 из 20, один релиз удалили: ачивка порога ещё держится (порог 5),
    # но «20» в счётчике врать не должно.
    row = _FakeUA("STUB_rev", is_unlocked=True, progress=20, xp_awarded=1)
    defn = _stub_def(code="STUB_rev", unlocked=True, progress=19, revocable=True)

    unlocked, row, _db = await _emit(monkeypatch, defn, row)

    assert unlocked == []           # повторный анлок не празднуем заново
    assert row.is_unlocked is True
    assert row.unlocked_at == "было"
    assert row.progress == 19


@pytest.mark.asyncio
async def test_plain_unlock_survives_failing_condition(monkeypatch):
    row = _FakeUA("STUB_plain", is_unlocked=True, progress=3, xp_awarded=1)
    defn = _stub_def(
        code="STUB_plain", unlocked=False, progress=0, revocable=False
    )

    unlocked, row, _db = await _emit(monkeypatch, defn, row)

    assert unlocked == []
    assert row.is_unlocked is True
    assert row.xp_awarded == 1
    assert row.progress == 3


@pytest.mark.asyncio
async def test_revocable_unlocks_normally_first_time(monkeypatch):
    defn = _stub_def(code="STUB_rev", unlocked=True, progress=5, revocable=True)

    unlocked, _row, db = await _emit(monkeypatch, defn, None)

    assert unlocked == ["STUB_rev"]
    assert len(db.added) == 1
    assert db.added[0].is_unlocked is True
