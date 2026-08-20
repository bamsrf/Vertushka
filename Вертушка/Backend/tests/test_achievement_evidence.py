"""Улики ачивок: «за какую музыку получено».

Проверяем чистые части: сборку текста (коротко, только музыка), соответствие
реестра билдеров реальным кодам ачивок (опечатка = молча без улики) и то, что
ядро мержит улику в metadata, не затирая рабочее состояние evaluator-а.
"""
import pytest

from app.services.achievements import evidence as EV
from app.services.achievements.evaluator import _attach_evidence
from app.services.achievements.registry import EvalResult, get_definition

USER = "00000000-0000-0000-0000-000000000001"


# --- Текст -------------------------------------------------------------------

def test_single_record_text():
    meta = {"evidence": {"records": [{"artist": "Talk Talk", "title": "Laughing Stock"}]}}
    assert EV.evidence_text(meta) == "Talk Talk — Laughing Stock"


def test_count_appends_short_tail():
    meta = {
        "evidence": {
            "records": [{"artist": "Portishead", "title": "Dummy"}],
            "count": 25,
        }
    }
    assert EV.evidence_text(meta) == "Portishead — Dummy · и ещё 24"


def test_note_is_appended():
    meta = {
        "evidence": {
            "records": [{"artist": "A", "title": "B"}],
            "note": "1975 → 2025",
        }
    }
    assert EV.evidence_text(meta) == "A — B · 1975 → 2025"


def test_long_line_is_truncated():
    meta = {"evidence": {"records": [{"artist": "X" * 60, "title": "Y" * 60}]}}
    text = EV.evidence_text(meta)
    assert text.endswith("…") and len(text) <= 48


def test_count_of_one_has_no_tail():
    meta = {"evidence": {"records": [{"artist": "A", "title": "B"}], "count": 1}}
    assert EV.evidence_text(meta) == "A — B"


def test_legacy_discography_metadata_still_readable():
    assert EV.evidence_text({"artist_name": "King Crimson"}) == "King Crimson"
    assert EV.evidence_text({"label_name": "Melodiya"}) == "Melodiya"


def test_no_evidence_returns_none():
    assert EV.evidence_text(None) is None
    assert EV.evidence_text({}) is None
    assert EV.evidence_text({"evidence": {}}) is None
    assert EV.evidence_text({"streak": 5}) is None


# --- Реестр билдеров -----------------------------------------------------------

def test_all_builder_codes_are_registered_achievements():
    EV.get_evidence_builder("__warmup__")  # инициализирует реестр
    for code in EV._REGISTRY:
        assert get_definition(code) is not None, f"Улика на несуществующий код: {code}"


def test_key_series_are_covered():
    for code in ("C3_collectible_x1", "MV_crown_jewel", "J2_gift_done",
                 "R_palindrome", "D5_melodiya_x10", "BX1_first_box"):
        assert EV.get_evidence_builder(code) is not None, code


# --- Merge в ядре ---------------------------------------------------------------

@pytest.mark.asyncio
async def test_attach_evidence_merges_without_clobbering_state(monkeypatch):
    async def fake_builder(db, user_id, payload):
        return {"records": [{"artist": "A", "title": "B"}]}

    monkeypatch.setattr(EV, "get_evidence_builder", lambda code: fake_builder)
    result = EvalResult(unlocked=True, metadata={"streak": 10})
    await _attach_evidence(None, USER, "E_digitizer", {}, result)
    assert result.metadata["streak"] == 10
    assert result.metadata["evidence"]["records"][0]["artist"] == "A"


@pytest.mark.asyncio
async def test_attach_evidence_swallows_builder_errors(monkeypatch):
    async def broken(db, user_id, payload):
        raise RuntimeError("boom")

    monkeypatch.setattr(EV, "get_evidence_builder", lambda code: broken)
    result = EvalResult(unlocked=True)
    await _attach_evidence(None, USER, "C3_collectible_x1", {}, result)
    assert result.metadata is None  # ачивка не пострадала, улики просто нет
