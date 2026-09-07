"""План B: нормализация названия для дедупа store-native против Discogs.

Суть — Discogs приоритетен по обложке, магазины дополняют новыми релизами,
не перекраивают существующие. _norm_title гарантирует, что near-дубль
Discogs-релиза не проскочит как «новый» store-native.
"""
from app.services.discogs_index import _norm_title


def test_strips_parentheticals():
    assert _norm_title("Abbey Road (Remastered)") == _norm_title("Abbey Road")
    assert _norm_title("Kid A [2021 Reissue]") == _norm_title("Kid A")


def test_case_and_punctuation_insensitive():
    assert _norm_title("Discovery!") == _norm_title("discovery")
    assert _norm_title("In Rainbows.") == _norm_title("In Rainbows")
    # Точка-разделитель внутри становится пробелом — «O.K.» и «ok» НЕ равны
    # намеренно (схлопывать «o k»→«ok» = over-нормализация, потеряем разные
    # альбомы). Дедуп ловит скобочные хвосты/регистр/пробелы, не аббревиатуры.


def test_whitespace_collapsed():
    assert _norm_title("The  Dark   Side") == _norm_title("The Dark Side")


def test_distinct_titles_stay_distinct():
    assert _norm_title("Футуроархаика") != _norm_title("Сертоловский Токсик")


def test_empty_and_none():
    assert _norm_title(None) == ""
    assert _norm_title("") == ""
    assert _norm_title("   ") == ""
