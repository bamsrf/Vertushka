"""Цвет пресса из дампа Discogs — берём пластинку, а не конверт.

Discogs держит цвет винила в атрибуте `text` у формата. Поле общего назначения:
рядом с цветом пластинки туда пишут упаковку, вес и что угодно ещё. Замер по
нашим 37 464 записям (дамп 2026-08): цвет распознаётся у 6 436, и 943 из них
описывают НЕ пластинку. Возьми мы их — чёрная пластинка в золотом конверте
приехала бы золотой.
"""
import pytest

from app.services.vinyl_color import (
    color_family,
    is_colored_vinyl,
    vinyl_color_from_format_texts,
)

#: Реальные значения format@text с прода, оба класса.
PACKAGING = [
    "Metallic Silver Sleeve",
    "Gold Inner Sleeve",
    "Green Case",
    "White Embossed Cover",
    "Blue Labels",
    "Simple Black Sleeve",
    "CBS Pressing, Gold Inner Sleeve, 1st Press",
]
VINYL = [
    "Red", "White", "Blue Translucent", "Yellow Marble", "Green Clear",
    "Neon Green", "Red Opaque", "Blue Marbled", "Turquoise", "Sky Blue",
]


@pytest.mark.parametrize("text", PACKAGING)
def test_packaging_colour_is_not_vinyl_colour(text):
    assert vinyl_color_from_format_texts([text]) is None


@pytest.mark.parametrize("text", VINYL)
def test_vinyl_colour_is_taken_as_is(text):
    # Возвращаем исходную строку Discogs, а не семью: семью выведут потребители,
    # а сырое значение честнее хранить.
    assert vinyl_color_from_format_texts([text]) == text
    assert is_colored_vinyl(text)


def test_packaging_is_skipped_but_search_continues():
    """Упаковка отбрасывается покусочно, а не роняет весь релиз."""
    assert vinyl_color_from_format_texts(["Gold Inner Sleeve", "Red"]) == "Red"


def test_non_colour_texts_give_nothing():
    for text in ("Digipak", "180 Gram", "CD1", "192 kbps", "Stickered", "2/2"):
        assert vinyl_color_from_format_texts([text]) is None, text


def test_black_pressing_is_found_but_not_colored():
    """Чёрный — тоже цвет пресса: сохранить стоит, в чип не пускать."""
    color = vinyl_color_from_format_texts(["Black"])

    assert color == "Black"
    assert color_family(color) == "black"
    assert is_colored_vinyl(color) is False


@pytest.mark.parametrize("two_tone", [
    "Red/Black Splatter",
    "Orange With Black Splatter",
    "Black and Purple Marbled",
    "Clear & Black",
    "White And Black Swirl",
    "Blue Transparent w/ Black Haze",
])
def test_two_tone_pressings_count_as_colored(two_tone):
    """Двухцветный пресс — цветной, хотя семья у него «black».

    color_family ставит black первым по приоритету, и через неё все эти
    пластинки считались бы чёрными: в дампе таких 570 из 5 493 значений, 12%.
    А это ровно тот винил, за которым охотятся.
    """
    assert color_family(two_tone) == "black"
    assert is_colored_vinyl(two_tone) is True


@pytest.mark.parametrize("black", ["Black", "Simple Black", "Black Vinyl", "чёрный"])
def test_plain_black_is_still_not_colored(black):
    assert is_colored_vinyl(black) is False


@pytest.mark.parametrize("texts", [None, [], [""], ["   "], [None]])
def test_empty_input(texts):
    assert vinyl_color_from_format_texts(texts) is None
