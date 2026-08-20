"""«Первая сотня» (OG1) — проводка серии «Истоки» и правила зачёта.

Живой БД у тестов нет, поэтому ранговый SQL здесь не гоняется — проверяем
детерминированные части: кто попадает в зачёт (allowlist / отсечка), что серия
корректно зарегистрирована, гейтится в UI и стоит правильный XP. Ранг «< 100»
по построению не зависит от порядка событий (считается из неизменяемых
first added_at), это зафиксировано в docstring evaluator-а.
"""
from datetime import datetime, timedelta

from app.services.achievements.definitions.series import origins as O
from app.services.achievements.definitions.series.formats import GATE_CODE_BY_SERIES
from app.services.achievements.events import COLLECTION_ITEM_ADDED, DAILY_TICK
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
    assert set(defn.triggers) == {COLLECTION_ITEM_ADDED, DAILY_TICK}


def test_og1_reacts_to_both_triggers():
    for event in (COLLECTION_ITEM_ADDED, DAILY_TICK):
        codes = {d.code for d in get_definitions_for_event(event)}
        assert O.OG1_CODE in codes, event


def test_origins_series_is_gated_by_own_pin():
    assert GATE_CODE_BY_SERIES.get("origins") == O.OG1_CODE


def test_og1_counts_toward_level_as_epic():
    assert weight_for_code(O.OG1_CODE) == 30


def test_founders_target_is_hundred():
    assert O.FOUNDERS_TARGET == 100
