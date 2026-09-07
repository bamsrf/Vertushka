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


# ---- Замусоренные store-native названия (legacy до чистки title_raw) ------- #

from app.services.discogs_index import _store_native_dedup_key


def test_noisy_title_strips_artist_year_format():
    # «ABBA – 2021 – Voyage — Виниловая пластинка» → «voyage» == Discogs
    assert _store_native_dedup_key(
        "ABBA – 2021 – Voyage — Виниловая пластинка", "ABBA"
    ) == _norm_title("Voyage")


def test_noisy_title_colored_vinyl_paren():
    assert _store_native_dedup_key(
        "Power Up (цветной винил)", "AC/DC"
    ) == _norm_title("Power Up")


def test_clean_title_unchanged():
    # чистое название (kultura/новые парсеры) — ключ = сам альбом
    assert _store_native_dedup_key("Футуроархаика", "Boulevard Depo") == _norm_title("Футуроархаика")


def test_genuinely_new_not_matched_to_discogs():
    # новый альбом не совпадёт с чужим Discogs-названием
    assert _store_native_dedup_key("Starlight", "7he Myriads") != _norm_title("Voyage")
