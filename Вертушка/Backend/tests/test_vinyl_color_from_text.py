"""Цвет винила из текста объявления: ловим издание, не название альбома.

Функция общая — `infer_vinyl_color`, её же зовут парсеры магазинов. Здесь
проверяются две вещи, добавленные ради фильтра Маркета: общий маркер «цветной
винил» без уточнения цвета и строгий режим `require_cue` для вызывающих,
которым нечем вырезать название альбома.

Цвет парсят два маленьких магазина из девяти, поэтому весь «цветной» пул
Маркета — около 800 карточек, и жанровый срез по нему даёт десятки. Текст при
этом цвет содержит: «(цветной винил)» стоит в заголовке у 883 позиций
plastinka_com.

Главный риск здесь — ложные срабатывания: цветовых слов в названиях альбомов
больше, чем в описаниях изданий. Поэтому цвет засчитывается только вплотную к
слову-носителю, и тесты держат именно эту границу.
"""
import pytest

from app.services.scrapers.extractors import COLORED_UNSPECIFIED, infer_vinyl_color
from app.services.vinyl_color import color_family, is_colored_vinyl


@pytest.mark.parametrize("title", [
    "Black Sabbath",
    "Blue Train",
    "The White Album",
    "Kind Of Blue",
    "Yellow Submarine",
    "Розовый слон",
    "Deep Purple",
    "Post Self Coloured",
])
def test_colour_word_in_album_title_is_not_a_colour(title):
    assert infer_vinyl_color(title, require_cue=True) is None


@pytest.mark.parametrize("title,expected", [
    ("Garip (цветной винил)", COLORED_UNSPECIFIED),
    ("Todd (2LP, цветной винил)", COLORED_UNSPECIFIED),
    ("In Utero (Orange Vinyl)", "orange"),
    ("Nevermind (Clear Vinyl)", "clear"),
    # Конкретный цвет не должен схлопываться в общий маркер, даже когда слово
    # «цветной» стоит между ним и носителем.
    ("Romantic (оранжевый цветной винил)", "orange"),
])
def test_colour_next_to_medium_is_picked_up(title, expected):
    assert infer_vinyl_color(title, require_cue=True) == expected


def test_colour_in_title_does_not_leak_into_edition():
    """«Fear Of A Black Planet (цветной винил)» — цветной, но НЕ чёрный.

    Самый коварный случай: цветовое слово стоит в названии альбома, а маркер
    издания рядом и общий. Возьми мы «black» — пластинка вылетела бы из чипа
    как чёрная, хотя магазин прямо пишет обратное.
    """
    color = infer_vinyl_color("Fear Of A Black Planet (цветной винил)", require_cue=True)

    assert color == COLORED_UNSPECIFIED
    assert is_colored_vinyl(color)


def test_generic_marker_has_no_family_but_counts_as_colored():
    """Общий маркер — не семья цвета, и это намеренно.

    `color_family` доказывает КОНФЛИКТ (чёрный листинг ↔ зелёная запись), и
    «цветной» не конфликтует ни с чем. А фильтру Маркета нужен другой вопрос —
    «цветной ли вообще», у него своя функция.
    """
    assert color_family(COLORED_UNSPECIFIED) is None
    assert is_colored_vinyl(COLORED_UNSPECIFIED) is True


@pytest.mark.parametrize("raw,expected", [
    ("Orange", True),
    ("чёрный", False),
    ("Black", False),
    ("180 Gram", False),
    ("Gatefold, Jewel Case", False),
    (None, False),
    ("", False),
])
def test_is_colored_vinyl_matches_family_semantics(raw, expected):
    assert is_colored_vinyl(raw) is expected


def test_free_pass_needs_the_album_name_cut_out():
    """Свободный проход ищет цвет где угодно — им можно пользоваться только
    вырезав название альбома, иначе «Blue Train» приезжает синим винилом."""
    assert infer_vinyl_color("Blue Train") == "blue"
    assert infer_vinyl_color("Blue Train", exclude=["Blue Train"]) is None
    assert infer_vinyl_color("Blue Train", require_cue=True) is None
