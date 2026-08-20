"""«Спрятанный трек» (R_hidden_track) — без ложных срабатываний.

Ловим регрессию: в Record.tracklist попадали heading-строки Discogs (заголовки
сторон, секция «Bonus Tracks») с пустой позицией — пасхалка редкого тира
открывалась любым переизданием с заголовками, а токен «bonus» матчил обычные
бонус-треки. Теперь: парсер фильтрует type_ != "track", а evaluator засчитывает
ненумерованный трек только при непустой длительности (у heading её нет).

Живой БД нет: _evaluate_hidden_track ходит в неё одним execute за записями
основной коллекции — его подменяет FakeSession.
"""
import pytest

from app.services.achievements.definitions import eggs as E
from app.services.discogs import _parse_release_tracklist

USER = "00000000-0000-0000-0000-000000000001"


class _FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


class FakeSession:
    """Стаб под _main_collection_items: (record, added_at) строки."""

    def __init__(self, records):
        self._rows = [(r, None) for r in records]

    async def execute(self, *_args, **_kwargs):
        return _FakeResult(self._rows)


class FakeRecord:
    _seq = 0

    def __init__(self, tracklist):
        FakeRecord._seq += 1
        self.id = FakeRecord._seq
        self.tracklist = tracklist


# --- Парсер релиза -------------------------------------------------------------

def test_parser_drops_heading_and_index_rows():
    data = {
        "tracklist": [
            {"type_": "heading", "position": "", "title": "Side A", "duration": ""},
            {"type_": "track", "position": "A1", "title": "Intro", "duration": "1:10"},
            {"type_": "index", "position": "", "title": "Suite", "duration": ""},
        ]
    }
    parsed = _parse_release_tracklist(data)
    assert [t["title"] for t in parsed] == ["Intro"]


def test_parser_keeps_tracks_without_explicit_type():
    # API иногда не шлёт type_ — по умолчанию это трек.
    data = {"tracklist": [{"position": "B2", "title": "Song", "duration": "3:33"}]}
    assert len(_parse_release_tracklist(data)) == 1


# --- Evaluator -----------------------------------------------------------------

@pytest.mark.asyncio
async def test_heading_without_duration_does_not_unlock():
    db = FakeSession([
        FakeRecord([
            {"position": "", "title": "Side A", "duration": None},
            {"position": "", "title": "Bonus Tracks", "duration": ""},
            {"position": "A1", "title": "Normal", "duration": "3:00"},
        ])
    ])
    res = await E._evaluate_hidden_track(db, USER, {}, set())
    assert not res.unlocked


@pytest.mark.asyncio
async def test_unnumbered_track_with_duration_unlocks():
    db = FakeSession([
        FakeRecord([
            {"position": "A1", "title": "Song", "duration": "3:00"},
            {"position": "", "title": "…", "duration": "6:66"},
        ])
    ])
    res = await E._evaluate_hidden_track(db, USER, {}, set())
    assert res.unlocked


@pytest.mark.asyncio
async def test_numbered_bonus_track_does_not_unlock():
    db = FakeSession([
        FakeRecord([{"position": "12", "title": "Track 12 (Bonus)", "duration": "2:10"}])
    ])
    res = await E._evaluate_hidden_track(db, USER, {}, set())
    assert not res.unlocked


@pytest.mark.asyncio
async def test_hidden_token_in_title_unlocks_even_with_position():
    db = FakeSession([
        FakeRecord([{"position": "B5", "title": "Untitled Hidden Track", "duration": ""}])
    ])
    res = await E._evaluate_hidden_track(db, USER, {}, set())
    assert res.unlocked


@pytest.mark.asyncio
async def test_garbage_tracklist_is_tolerated():
    db = FakeSession([FakeRecord(["not a dict", None]), FakeRecord(None)])
    res = await E._evaluate_hidden_track(db, USER, {}, set())
    assert not res.unlocked
