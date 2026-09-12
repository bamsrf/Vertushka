"""Цвет пресса из ответа Discogs API — не только formats[0], и не упаковка.

До фикса живой фетч брал `formats[0].get("text")` как есть, тогда как из дампа
цвет грузился через `vinyl_color_from_format_texts`. Два источника одной и той
же записи расходились: у релиза, приехавшего из дампа, цвет был правильный, а у
того же релиза, добытого фетчем, — «Gatefold» или ничего.

Замер прода, из-за которого фикс делался: непустой `vinyl_color_raw` у 6 390
записей, и 2 091 из них (треть) — значения БЕЗ семьи цвета: clear 1 138,
splatter/marble 863, coloured 82, glow 8. На них держатся фильтр «цветной
винил» в Маркете, счётчик цветных в профиле и пасхалка «Светится в темноте».
Поэтому разбор двухпроходный, и половина тестов ниже — про то, что второй
проход не потеряли.
"""
import pytest

from app.services.discogs import _vinyl_color_from_formats


def _fmt(name, text=None, **rest):
    f = {"name": name, "qty": "1", "descriptions": ["LP", "Album"]}
    if text is not None:
        f["text"] = text
    f.update(rest)
    return f


# ---- (а) Цвет ТЕРЯЛСЯ: лежал не в первом формате ------------------------- #

def test_colour_in_second_format_is_found():
    """Vinyl + Box Set: цвет во втором формате, в первом — упаковка."""
    formats = [_fmt("Vinyl", "Gatefold"), _fmt("Box Set", "Red Translucent")]
    assert _vinyl_color_from_formats(formats) == "Red Translucent"


def test_weight_in_first_format_does_not_mask_colour():
    """«180 gram» в formats[0] раньше приезжал ВМЕСТО цвета."""
    formats = [_fmt("Vinyl", "180 gram"), _fmt("Vinyl", "Blue Marbled")]
    assert _vinyl_color_from_formats(formats) == "Blue Marbled"


def test_first_format_without_text_no_longer_loses_colour():
    formats = [_fmt("Vinyl"), _fmt("Vinyl", "Emerald Green")]
    assert _vinyl_color_from_formats(formats) == "Emerald Green"


# ---- (б) Цвет ВЫДУМЫВАЛСЯ из упаковки ------------------------------------ #

def test_packaging_in_first_format_is_not_the_vinyl_colour():
    """«Gold Inner Sleeve» красил чёрную пластинку в золото."""
    formats = [_fmt("Vinyl", "Gold Inner Sleeve")]
    assert _vinyl_color_from_formats(formats) is None


def test_packaging_skipped_but_real_colour_still_found():
    formats = [_fmt("Vinyl", "Metallic Silver Sleeve"), _fmt("Vinyl", "Black")]
    assert _vinyl_color_from_formats(formats) == "Black"


# ---- Неспецифичные маркеры: второй проход -------------------------------- #

@pytest.mark.parametrize("marker", [
    "Clear",
    "Coloured Vinyl",
    "Splatter",
    "Glow In The Dark",
    "Translucent",
])
def test_unspecific_colour_markers_are_kept(marker):
    """Семьи у них нет, но выбрасывать нельзя — на них висят три потребителя.

    Маркет фильтрует «цветной винил», профиль считает цветные, а пасхалка
    E_glow ищет в этом поле подстроку glow. На проде таких значений треть.
    """
    assert _vinyl_color_from_formats([_fmt("Vinyl", marker)]) == marker


def test_concrete_colour_wins_over_unspecific_marker():
    """Первый проход важнее второго: «Clear» есть, но «Yellow» ценнее."""
    formats = [_fmt("Vinyl", "Clear"), _fmt("Vinyl", "Yellow")]
    assert _vinyl_color_from_formats(formats) == "Yellow"


def test_glow_survives_even_behind_packaging():
    formats = [_fmt("Vinyl", "Green Case"), _fmt("Vinyl", "Glow In The Dark")]
    assert _vinyl_color_from_formats(formats) == "Glow In The Dark"


# ---- Мусор по-прежнему не становится цветом ------------------------------ #

@pytest.mark.parametrize("junk", [
    "Gatefold", "180 gram", "Fifth Pressing", "256 kbps", "Pitman",
    "10 Year Anniversary", "Half Speed Cut", "Artbook",
])
def test_noise_gives_no_colour(junk):
    assert _vinyl_color_from_formats([_fmt("Vinyl", junk)]) is None


@pytest.mark.parametrize("formats", [None, [], [{}], [{"name": "Vinyl"}]])
def test_empty_and_textless_input(formats):
    assert _vinyl_color_from_formats(formats) is None


def test_non_dict_entries_do_not_crash():
    """Ответ API приходит из сети — в списке может оказаться что угодно."""
    assert _vinyl_color_from_formats(["Vinyl", None, _fmt("Vinyl", "Red")]) == "Red"
