"""Словарь семей цвета: синонимы, приглушённые семьи и ловушки подстроки.

Расширение словаря 12.09 делалось по замеру прода (3 167 различных значений
цвета, 28 339 записей в `records.discogs_data` + `store_listings`). Семьи не
было у 5 396 значений; сюда вынесены ровно те слова, которые в этом хвосте
реально встречались, с их весом — чтобы следующий, кто полезет чистить
словарь, не выкинул рабочий токен как «выдуманный».

Обратная половина теста не менее важна: хвост None населён названиями заводов
(Pitman, Terre Haute, Monarch) и весом пресса, и новые семьи не должны начать
их ловить.
"""
from app.services.vinyl_color import (
    color_family,
    is_colored_vinyl,
    non_black_color_family,
    sql_nonblack_family_regex,
)


# ---- Синонимы к уже существующим семьям (вес по проду) ------------------- #

def test_amber_and_tangerine_are_orange():
    """amber 20 записей, Tangerine 1."""
    assert color_family("amber") == "orange"
    assert color_family("Tangerine") == "orange"


def test_violet_is_purple():
    """violet 6 записей — самый частый пропущенный синоним фиолетового."""
    assert color_family("Violet Translucent") == "purple"
    assert color_family("Lilac") == "purple"


def test_magenta_is_pink():
    assert color_family("Magenta") == "pink"


def test_maroon_is_red():
    assert color_family("Maroon") == "red"
    assert color_family("Burgundy") == "red"


# ---- Новые приглушённые семьи -------------------------------------------- #

def test_grey_family():
    """grey 188 + gray 1 — крупнейшая дыра словаря до расширения."""
    assert color_family("grey") == "grey"
    assert color_family("Gray Marble") == "grey"
    assert color_family("Marbled Moss / Dark Grey") == "grey"


def test_cream_family():
    """cream 93, Beige 3, Ivory 1."""
    assert color_family("Cream") == "cream"
    assert color_family("Beige") == "cream"
    assert color_family("Ivory") == "cream"


def test_brown_family():
    assert color_family("Brown Translucent") == "brown"


def test_new_families_count_as_colored():
    """Серая и кремовая — не чёрные, значит цветные."""
    assert is_colored_vinyl("Grey Marble") is True
    assert is_colored_vinyl("Cream") is True
    assert non_black_color_family("Grey Marble") == "grey"


# ---- Приоритет: яркое выигрывает у приглушённого ------------------------- #

def test_vivid_colour_wins_over_muted():
    """Приглушённые семьи стоят в конце списка именно ради этого."""
    assert color_family("Red / Dark Grey") == "red"
    assert color_family("Silver Grey") == "silver"


# ---- Ловушки подстроки ---------------------------------------------------- #

def test_russian_seriya_is_not_grey():
    """«сер» как префикс ловил бы «серия», «серебро» и «сертификат».

    Единственная семья, где RU-стем пришлось задать с окончаниями.
    """
    assert color_family("серия лимитированная") is None
    assert color_family("сертификат подлинности") is None
    assert color_family("Серебристый") == "silver"
    assert color_family("серый винил") == "grey"


def test_pressing_plants_and_weight_still_have_no_family():
    """Хвост None по замыслу: заводы, вес, битрейт семьи не получают."""
    for noise in ("Pitman Pressing", "Terre Haute", "Monarch", "180 Gram",
                  "256 kbps", "Fifth Pressing"):
        assert color_family(noise) is None, noise


def test_unspecific_markers_deliberately_have_no_family():
    """coloured 2 377 и clear 1 522 — крупнейший хвост, и он остаётся None.

    Они не доказывают конфликт цвета, поэтому семьёй не считаются; «цветной
    ли вообще» отвечает is_colored_vinyl.
    """
    for marker in ("Coloured Vinyl", "Clear", "Splatter", "Marbled"):
        assert color_family(marker) is None, marker
        assert is_colored_vinyl(marker) is True, marker


# ---- SQL-зеркало не должно разъезжаться с Python ------------------------- #

def test_sql_nonblack_regex_covers_every_nonblack_family():
    rx = sql_nonblack_family_regex()
    for fam in ("grey", "cream", "brown", "purple", "orange", "pink", "red"):
        assert fam in rx, fam
    assert "black" not in rx
    # \b Питон-диалекта должен быть переведён в \y (граница слова в Postgres)
    assert chr(92) + "b" not in rx
    assert chr(92) + "y" in rx
