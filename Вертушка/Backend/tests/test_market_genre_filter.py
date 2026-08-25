"""Жанровые чипы Маркета не должны собирать чужие релизы.

Реальный случай 12.08: в чипе Classical висели Beyoncé «Cowboy Carter» и Genesis
Owusu — паттерн `%contemporary%` матчился по `r.style`, куда Discogs пишет
«Contemporary R&B». Лечили сужением паттернов и запретом смотреть в style.

С 25.08 защита другая, структурная: чип решается по `r.genre` (закрытый словарь
из 15 верхнеуровневых жанров Discogs), а `r.style` смотрим только когда жанра
нет вовсе. Тесты фиксируют оба слоя: словарь разводится без пересечений, и
стиль не может перетащить запись в чужой чип, пока жанр заполнен.
"""
import re

import pytest

from app.api.market import (
    GENRES,
    _GENRE_PATTERNS,
    _GENRE_STYLE_PATTERNS,
    _filters_clause,
    _genre_match_sql,
)
from app.services.genre_vocab import DISCOGS_GENRES


def _matches(pattern_list: list[str], value: str) -> bool:
    """Питон-эквивалент ILIKE ANY: паттерны у нас только с `%` по краям/внутри."""
    for pat in pattern_list:
        rx = "^" + ".*".join(re.escape(part) for part in pat.split("%")) + "$"
        if re.match(rx, value, re.IGNORECASE):
            return True
    return False


def _chips_for_genre(genre: str) -> set[str]:
    """Ключи чипов, в которые попадёт запись с таким `r.genre`."""
    return {key for key in _GENRE_PATTERNS if _matches(_GENRE_PATTERNS[key], genre)}


@pytest.mark.parametrize("genre", DISCOGS_GENRES)
def test_every_discogs_genre_lands_in_exactly_one_chip(genre):
    """Ни один верхнеуровневый жанр не теряется и не двоится.

    Это и есть причина, по которой матч перевели на `r.genre`: внутри словаря
    Discogs ни одно имя не является подстрокой другого, поэтому раскладка
    однозначна — в отличие от стилей, где Pop Rock честно содержит и «pop», и
    «rock».
    """
    assert len(_chips_for_genre(genre)) == 1, _chips_for_genre(genre)


def test_multi_genre_record_lands_in_all_its_chips():
    # Discogs склеивает жанры через ", " — запись обязана попасть в оба чипа.
    assert _chips_for_genre("Electronic, Rock") == {"electronic", "rock"}


def test_folk_world_country_is_one_chip_despite_commas():
    # Единственное имя словаря с запятыми внутри: сплит по "," разорвал бы его
    # на три несуществующих жанра, подстрочный матч — нет.
    assert _chips_for_genre("Folk, World, & Country") == {"folk"}


@pytest.mark.parametrize(
    "style",
    ["Contemporary R&B", "Contemporary Jazz", "Contemporary Gospel", "Neo Soul"],
)
def test_classical_never_matches_by_style(style):
    # У классики запасных style-паттернов нет вовсе — ровно тот баг 12.08.
    assert not _matches(_GENRE_STYLE_PATTERNS["classical"], style)
    assert "r.style" not in _genre_match_sql("classical", "p", "s")


def test_style_is_only_consulted_when_genre_is_empty():
    sql = _genre_match_sql("hiphop", "p", "s")
    # Ветка по стилю существует (recall для записей без жанра)…
    assert "r.style ILIKE ANY(:s)" in sql
    # …но включается только при пустом жанре: иначе genre='Rock' + style='Trap'
    # утащил бы рок в хип-хоп, как было до 25.08.
    assert "NOT (r.genre IS NOT NULL AND r.genre <> '') AND r.style" in sql


def test_pop_chip_does_not_swallow_rock_with_pop_style():
    """genre='Rock', style='Pop Rock' — это рок и только рок."""
    assert _chips_for_genre("Rock") == {"rock"}
    # Стиль в этом случае вообще не смотрится, но проверим и его набор:
    # он не должен быть причиной попадания в pop при заполненном жанре.
    sql = _genre_match_sql("pop", "p", "s")
    assert sql.index("r.genre ILIKE ANY(:p)") < sql.index("r.style ILIKE ANY(:s)")


def test_multi_genre_builds_or_with_separate_params():
    sql, params = _filters_clause(["classical", "rock"], False, False, False)
    # Каждому жанру — свой bind-параметр; у классики style-набора нет, значит и
    # параметра под него быть не должно (иначе asyncpg получит лишний bind).
    assert set(params) == {"genre_pats_classical", "genre_pats_rock", "style_pats_rock"}
    assert " OR " in sql
    assert "r.style ILIKE ANY(:style_pats_rock)" in sql
    assert "style_pats_classical" not in sql


def test_unknown_genre_key_is_ignored():
    assert _filters_clause(["definitely-not-a-genre"], False, False, False) == ("", {})


def test_chip_keys_are_unique():
    keys = [key for key, _label, _g, _s in GENRES]
    assert len(keys) == len(set(keys))
