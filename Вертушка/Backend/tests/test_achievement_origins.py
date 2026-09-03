"""«Первая сотня» (OG1) — проводка серии «Истоки» и правила зачёта.

Живой БД у тестов нет, поэтому ранговый SQL целиком здесь не гоняется —
проверяем детерминированные части: кто попадает в зачёт (allowlist / отсечка),
проводку серии, XP, гейт в UI, а также оба предела выдачи (ранг и
предохранитель на 100 выданных) через стаб сессии, возвращающий счётчики.
"""
from datetime import datetime, timedelta

import pytest

from app.services.achievements.definitions.series import origins as O
from app.services.achievements.definitions.series.formats import GATE_CODE_BY_SERIES
from app.services.achievements.events import DAILY_TICK, USER_REGISTERED
from app.services.achievements.levels import weight_for_code
from app.services.achievements.registry import (
    AchievementTier,
    get_definition,
    get_definitions_for_event,
)


# --- Зачёт -------------------------------------------------------------------

def test_allowlist_users_qualify_regardless_of_age():
    old = O.FOUNDERS_CUTOFF - timedelta(days=400)
    for name in ("hhbbbgcdc7", "genia_pazla", "Andrei", "ANDREI", "  andrei "):
        assert O.is_founder_candidate(name, old), name


def test_pre_cutoff_non_allowlisted_accounts_do_not_qualify():
    old = O.FOUNDERS_CUTOFF - timedelta(seconds=1)
    assert not O.is_founder_candidate("vlad_main", old)
    assert not O.is_founder_candidate("vlad_test_2", old)
    assert not O.is_founder_candidate(None, old)


def test_post_cutoff_accounts_qualify():
    assert O.is_founder_candidate("newcomer", O.FOUNDERS_CUTOFF)
    assert O.is_founder_candidate("newcomer", O.FOUNDERS_CUTOFF + timedelta(days=30))


def test_missing_created_at_does_not_qualify():
    assert not O.is_founder_candidate("newcomer", None)


def test_allowlist_is_lowercase():
    # Сравнение идёт по lower() — сам список обязан быть в нижнем регистре,
    # иначе матч молча перестанет работать.
    assert all(name == name.lower() for name in O.FOUNDER_ALLOWLIST)


# --- Проводка ----------------------------------------------------------------

def test_og1_registered_with_expected_shape():
    defn = get_definition(O.OG1_CODE)
    assert defn is not None
    assert defn.series == "origins"
    assert defn.tier == AchievementTier.EPIC
    assert defn.is_hidden is False
    assert set(defn.triggers) == {USER_REGISTERED, DAILY_TICK}


def test_og1_reacts_to_both_triggers():
    for event in (USER_REGISTERED, DAILY_TICK):
        codes = {d.code for d in get_definitions_for_event(event)}
        assert O.OG1_CODE in codes, event


def test_origins_series_is_gated_by_own_pin():
    assert GATE_CODE_BY_SERIES.get("origins") == O.OG1_CODE


def test_og1_counts_toward_level_as_epic():
    assert weight_for_code(O.OG1_CODE) == 30


def test_founders_target_is_hundred():
    assert O.FOUNDERS_TARGET == 100


# --- Пределы выдачи (ранг + предохранитель) -----------------------------------

class _FakeUser:
    def __init__(self, username="newcomer", created_at=None):
        self.id = "11111111-1111-1111-1111-111111111111"
        self.username = username
        self.created_at = created_at or O.FOUNDERS_CUTOFF + timedelta(days=1)


class _RankSession:
    """Стаб AsyncSession: первый scalar() — юзер, второй — ранг, третий —
    сколько пинов уже выдано."""

    def __init__(self, *, ahead, granted, user=None):
        self._answers = [user or _FakeUser(), ahead, granted]

    async def scalar(self, *_args, **_kwargs):
        return self._answers.pop(0) if self._answers else 0


@pytest.mark.asyncio
async def test_unlocks_inside_both_limits():
    res = await O._evaluate_first_hundred(
        _RankSession(ahead=41, granted=41), "u", {}, set()
    )
    assert res.unlocked


@pytest.mark.asyncio
async def test_rank_beyond_hundred_does_not_unlock():
    res = await O._evaluate_first_hundred(
        _RankSession(ahead=O.FOUNDERS_TARGET, granted=0), "u", {}, set()
    )
    assert not res.unlocked


@pytest.mark.asyncio
async def test_safety_cap_blocks_when_hundred_already_granted():
    # Ранг свободен (кто-то удалил аккаунт и сдвинул очередь), но сотня пинов
    # уже роздана — 101-й не выдаём.
    res = await O._evaluate_first_hundred(
        _RankSession(ahead=99, granted=O.FOUNDERS_TARGET), "u", {}, set()
    )
    assert not res.unlocked


@pytest.mark.asyncio
async def test_non_candidate_does_not_unlock():
    early = _FakeUser("random_old", O.FOUNDERS_CUTOFF - timedelta(days=1))
    res = await O._evaluate_first_hundred(
        _RankSession(ahead=0, granted=0, user=early), "u", {}, set()
    )
    assert not res.unlocked


@pytest.mark.asyncio
async def test_collection_is_not_required():
    # Ни одного обращения к коллекциям: пин теперь за регистрацию.
    import inspect
    src = inspect.getsource(O)
    assert "CollectionItem" not in src
