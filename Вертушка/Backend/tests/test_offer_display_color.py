"""Бейдж цвета оффера: чисто чёрный прячем, двухцветный с чёрным — нет."""
import pytest

from app.api.offers import _display_color


@pytest.mark.parametrize("raw", ["Black", "black", "Black, 180g", "Чёрный"])
def test_plain_black_is_hidden(raw):
    assert _display_color(raw) is None


@pytest.mark.parametrize("raw", [
    "Red/Black Splatter",
    "Black & Orange Marbled",
    "Black/White",
    "Translucent Black",
])
def test_black_with_colour_or_finish_keeps_badge(raw):
    assert _display_color(raw) == raw


def test_regular_colour_is_kept():
    assert _display_color("Red") == "Red"
    assert _display_color(None) is None
