"""Разбор склейки жанров не должен множить «Folk, World, & Country».

Единственное имя словаря Discogs с запятыми внутри. Наивный `split(",")` делал
из одной пластинки три «жанра» и втрое задирал ачивки на разнообразие — до
бэкфилла из дампа это не проявлялось, потому что жанр стоял у сотни записей.
"""
import pytest

from app.services.genre_vocab import DISCOGS_GENRES, split_genres


def test_single_genre():
    assert split_genres("Rock") == ["Rock"]


def test_plain_join():
    assert split_genres("Electronic, Rock") == ["Electronic", "Rock"]


def test_folk_world_country_stays_whole():
    assert split_genres("Folk, World, & Country") == ["Folk, World, & Country"]


def test_folk_world_country_mixed_with_others():
    assert split_genres("Folk, World, & Country, Rock") == [
        "Folk, World, & Country", "Rock",
    ]
    assert split_genres("Rock, Folk, World, & Country") == [
        "Rock", "Folk, World, & Country",
    ]


def test_case_insensitive():
    assert split_genres("folk, world, & country") == ["Folk, World, & Country"]


@pytest.mark.parametrize("value", ["", "   ", None])
def test_empty_input(value):
    assert split_genres(value) == []


def test_unknown_values_pass_through():
    # Юзер может вписать свой жанр руками — словарь не фильтр.
    assert split_genres("Шансон, Rock") == ["Шансон", "Rock"]


@pytest.mark.parametrize("genre", DISCOGS_GENRES)
def test_every_dictionary_name_survives_a_round_trip(genre):
    assert split_genres(genre) == [genre]
