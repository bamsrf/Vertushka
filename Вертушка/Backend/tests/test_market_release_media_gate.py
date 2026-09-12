"""Чистые решения режима «В Маркет» с карточки релиза.

Здесь — только то, что считается без базы: носитель записи, форма сужающего
предиката и резолв якоря. Само поведение выдачи проверяется по живой схеме в
tests/integration/test_market_release_scope.py: SQL честно судить только
Postgres'ом.

Развилка, на которой всё ломается молча, — гейт носителя. Мастер на Discogs
объединяет винил, CD и mp3, и ошибиться можно в обе стороны: не загейтить —
показать цифру вместо винила, загейтить по неуверенно распознанному формату —
вычеркнуть живой оффер и объявить пластинку отсутствующей.
"""
import uuid

import pytest

from app.api.market import (
    _release_media_key,
    _release_scope_clause,
    _resolve_release_anchor,
)


# ─── Гейт носителя ──────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "format_type, expected",
    [
        ("Vinyl", "vinyl"),
        ("Vinyl, LP, Album", "vinyl"),
        ("CD", "cd"),
        ("Cassette", "cassette"),
    ],
)
def test_media_key_recognises_physical_media(format_type, expected):
    assert _release_media_key(format_type, None) == expected


@pytest.mark.parametrize(
    "format_type, format_description",
    [
        # Носитель неизвестен — гейтить нечем.
        (None, None),
        ("", None),
        # Цифра: физического семейства нет вовсе.
        ("File", "MP3, Album"),
        # Настоящий гибрид носителей: винил и CD в одной коробке.
        ("Vinyl, LP, Album + CD", None),
    ],
)
def test_media_key_gives_up_when_medium_is_not_single_and_physical(
    format_type, format_description
):
    """None значит «не гейтить» — молча вычеркнуть живые офферы хуже, чем
    показать лишнее. Именно на этой развилке выдача расходится со счётчиком."""
    assert _release_media_key(format_type, format_description) is None


def test_vinyl_with_a_download_code_is_still_vinyl():
    """«Vinyl, LP + File» — винил с кодом на скачивание, а не цифра. Признай
    его гибридом — и гейт отключится там, где он как раз обязан работать."""
    assert _release_media_key("Vinyl, LP + File", "Album") == "vinyl"


# ─── Сужение выдачи ─────────────────────────────────────────────────────


def test_scope_without_master_keeps_only_the_record_itself():
    # Store-native: мастера нет, аналогов не существует в принципе.
    sql, params = _release_scope_clause(None, "vinyl")
    assert sql == " AND r.id = :rel_rec"
    assert params == {}


def test_scope_gates_siblings_by_medium_but_never_the_record_itself():
    sql, params = _release_scope_clause("12345", "vinyl")
    head, siblings = sql.split(" OR ", 1)
    # Сама запись проходит без единого условия по формату: предикат смотрит в
    # listing.format_raw, и криво распарсенный магазином формат вычеркнул бы
    # именно тот оффер, ради которого человек сюда шёл.
    assert head == " AND (r.id = :rel_rec"
    assert "format_raw" not in head
    # «Другие версии» — только тот же носитель: мастер на Discogs объединяет
    # винил, CD и mp3-файл.
    assert "r.discogs_master_id = :rel_master" in siblings
    assert "format_raw" in siblings
    assert params["rel_master"] == "12345"


def test_scope_without_media_key_still_excludes_the_anchor_from_siblings():
    """Якорь не должен попасть в выдачу дважды — своей плиткой и как «версия»."""
    sql, _ = _release_scope_clause("12345", None)
    assert "r.id <> :rel_rec" in sql


# ─── Резолв якоря ───────────────────────────────────────────────────────


class _Row:
    def __init__(self, **kw):
        self.__dict__.update(kw)


class _FakeDB:
    """Минимальная замена сессии: отдаёт записи по id, считает запросы."""

    def __init__(self, rows):
        self.rows = {r.id: r for r in rows}
        self.queries = 0

    async def execute(self, stmt, params=None):
        self.queries += 1
        wanted = list(stmt.whereclause.right.value for _ in (0,))[0]
        row = self.rows.get(wanted)

        class _Res:
            def first(self_inner):
                return row

        return _Res()


def _rec(master="777", merged=None, fmt="Vinyl"):
    return _Row(
        id=uuid.uuid4(),
        merged_into_id=merged,
        discogs_master_id=master,
        format_type=fmt,
        format_description=None,
    )


@pytest.mark.asyncio
async def test_anchor_returns_master_and_medium():
    rec = _rec()
    db = _FakeDB([rec])
    assert await _resolve_release_anchor(db, rec.id) == (rec.id, "777", "vinyl")


@pytest.mark.asyncio
@pytest.mark.parametrize("master", [None, "", "0"])
async def test_anchor_treats_empty_master_as_absent(master):
    """`discogs_master_id = '0'` встречается в дампе и мастером не является —
    без нормализации к записи прилипли бы все прочие нули как «версии»."""
    rec = _rec(master=master)
    db = _FakeDB([rec])
    _, resolved_master, _ = await _resolve_release_anchor(db, rec.id)
    assert resolved_master is None


@pytest.mark.asyncio
async def test_anchor_follows_a_merged_record_to_the_winner():
    """Карточка, которую rematch увёл в дубль, обязана показать офферы
    победителя — иначе переход отдаёт пустоту при живом наличии."""
    winner = _rec(master="999")
    loser = _rec(master="777", merged=winner.id)
    db = _FakeDB([winner, loser])
    assert await _resolve_release_anchor(db, loser.id) == (winner.id, "999", "vinyl")


@pytest.mark.asyncio
async def test_anchor_is_none_for_unknown_record():
    db = _FakeDB([])
    assert await _resolve_release_anchor(db, uuid.uuid4()) is None

