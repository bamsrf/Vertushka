"""Жанровые чипы Маркета не должны собирать чужие релизы.

Реальный случай 12.08: в чипе Classical висели Beyoncé «Cowboy Carter» и Genesis
Owusu. Причина — паттерн `%contemporary%` матчился по `r.style`, а Discogs
пишет туда «Contemporary R&B». Тесты фиксируют оба слоя защиты: сузившиеся
паттерны и запрет смотреть в style у строгих жанров.
"""
import pytest

from app.api.market import (
    GENRES,
    GENRE_STRICT,
    _GENRE_PATTERNS,
    _filters_clause,
    _genre_match_sql,
)


def _matches(pattern_list: list[str], value: str) -> bool:
    """Питон-эквивалент ILIKE ANY: паттерны у нас только с `%` по краям/внутри."""
    import re

    for pat in pattern_list:
        rx = "^" + ".*".join(re.escape(part) for part in pat.split("%")) + "$"
        if re.match(rx, value, re.IGNORECASE):
            return True
    return False


@pytest.mark.parametrize(
    "style",
    ["Contemporary R&B", "Contemporary Jazz", "Contemporary Gospel", "Neo Soul"],
)
def test_classical_patterns_do_not_catch_contemporary_rnb(style):
    assert not _matches(_GENRE_PATTERNS["classical"], style)


@pytest.mark.parametrize(
    "genre",
    ["Classical", "Baroque", "Opera", "Modern Classical", "Classical, Stage & Screen"],
)
def test_classical_patterns_still_catch_real_classical(genre):
    assert _matches(_GENRE_PATTERNS["classical"], genre)


def test_strict_genre_ignores_style_column():
    sql = _genre_match_sql("classical", "p")
    assert "r.style" not in sql
    assert "r.genre ILIKE ANY(:p)" == sql


def test_non_strict_genre_still_matches_style():
    # Recall-кейс: genre='Electronic' + style='Trap' обязан попадать в hiphop.
    sql = _genre_match_sql("hiphop", "p")
    assert "r.genre ILIKE ANY(:p)" in sql and "r.style ILIKE ANY(:p)" in sql


def test_multi_genre_builds_or_with_separate_params():
    sql, params = _filters_clause(["classical", "rock"], False, False, False)
    # Каждому жанру — свой bind-параметр, иначе строгий и нестрогий не склеить.
    assert set(params) == {"genre_pats_classical", "genre_pats_rock"}
    assert " OR " in sql
    assert "r.style ILIKE ANY(:genre_pats_rock)" in sql
    assert "r.style ILIKE ANY(:genre_pats_classical)" not in sql


def test_unknown_genre_key_is_ignored():
    assert _filters_clause(["definitely-not-a-genre"], False, False, False) == ("", {})


def test_strict_keys_are_known_genres():
    assert GENRE_STRICT <= {key for key, _label, _pats in GENRES}
