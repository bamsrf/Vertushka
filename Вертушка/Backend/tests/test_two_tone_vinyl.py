"""Двухцветный пресс: парсер сохраняет оба цвета, сравнение прессов не
считает его чёрным.

До этого «Red/Black Splatter Vinyl» у магазина превращался в `splatter`,
«Red & Blue Vinyl» — в `blue`: второй цвет терялся ещё до Mobile, который
умеет рисовать cic/marble/splatter вторым цветом. А у записи Discogs семья
двухцветного с чёрным выходила `black`, и «red» листинга с ней конфликтовал.
"""
import pytest

from app.services.scrapers.extractors import infer_vinyl_color
from app.services.vinyl_color import (
    color_family,
    is_colored_vinyl,
    pressing_family,
    sql_pressing_tier,
)


@pytest.mark.parametrize("text,expected", [
    ("Red/Black Splatter Vinyl LP", "red & black splatter"),
    ("Red & Blue Vinyl", "red & blue"),
    ("Black and White Vinyl", "white & black"),
    ("Black & Orange Marbled Vinyl", "orange & black marble"),
    ("Yellow / Black marble LP", "yellow & black marble"),
    ("Красно-чёрный винил", "red & black"),
    ("красный и чёрный винил", "red & black"),
])
def test_two_tone_phrase_keeps_both_colours(text, expected):
    color = infer_vinyl_color(text)
    assert color == expected
    assert is_colored_vinyl(color)


@pytest.mark.parametrize("text,expected", [
    ("RSD26 Orange Vinyl", "orange"),
    ("Limited black vinyl", "black"),
    ("180g Black Vinyl", "black"),
    # Цвет из названия альбома не пристёгивается вторым: фраза только у носителя.
    ("Blue Train red vinyl", "red"),
])
def test_single_colour_unchanged(text, expected):
    assert infer_vinyl_color(text) == expected


def test_title_colour_not_glued_with_require_cue():
    assert infer_vinyl_color("Blue Train", require_cue=True) is None


@pytest.mark.parametrize("raw,expected", [
    ("Red/Black Splatter", "red"),
    ("red & black splatter", "red"),
    ("Black & Orange Marbled", "orange"),
    ("Black", "black"),
    ("Red", "red"),
    ("Clear", None),
    (None, None),
])
def test_pressing_family_prefers_real_colour(raw, expected):
    assert pressing_family(raw) == expected


def test_color_family_priority_untouched():
    """Приоритет семьи трогать нельзя — его ждут бейдж и прочие потребители."""
    assert color_family("Red/Black Splatter") == "black"


def test_sql_tier_compares_pressing_family():
    sql = sql_pressing_tier(
        method_col="m", confidence_col="c",
        listing_color_col="l", record_color_expr="r",
    )
    # black — последняя ветка в CASE, а не первая
    first_black = sql.index("black")
    first_red = sql.index("THEN 'red'")
    assert first_red < first_black
