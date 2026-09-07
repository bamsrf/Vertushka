"""WS-охват цвета 07.09: skifmusic берёт цвет винила из URL-слага.

Магазин не кладёт цвет в JSON-LD name (он чистый), а кладёт в слаг
`/product/{id}-artist-album-<color>-vinyl-...`. Аудит: ~4200 in-stock
листингов имели цвет в слаге при пустом vinyl_color_raw. Слаг уже в `url`.

Инварианты — реальные URL с прода (снято 07.09).
"""
import pytest

from app.services.scrapers.shops.skifmusic import _slug_words
from app.services.scrapers.extractors import infer_vinyl_color


def _color_from(url: str, name: str, artist=None, album=None):
    """Повторяет вызов из parse_item: name + слаг, вырез артиста/альбома."""
    return infer_vinyl_color(f"{name} {_slug_words(url)}", exclude=[artist, album])


# ---- _slug_words --------------------------------------------------------- #

def test_slug_words_strips_id_and_hyphens():
    assert _slug_words(
        "https://skifmusic.ru/product/769107-flypaper-forget-the-rush-blue-yellow-vinyl-new-vinyl"
    ) == "flypaper forget the rush blue yellow vinyl new vinyl"


def test_slug_words_empty_on_non_product():
    assert _slug_words("https://skifmusic.ru/catalog/") == ""
    assert _slug_words("") == ""


# ---- цвет из слага (реальные прод-URL) ----------------------------------- #

def test_green_vinyl_from_slug():
    c = _color_from(
        "https://skifmusic.ru/product/770024-old-97s-american-primitive-green-vinyl-new-vinyl",
        "Old 97's – American Primitive", "Old 97's", "American Primitive")
    assert c == "green"


def test_pink_vinyl_from_slug():
    c = _color_from(
        "https://skifmusic.ru/product/780283-olivia-rodrigo-drop-dead-7-chewing-gum-pink-vinyl-new-vinyl",
        "Olivia Rodrigo – Drop Dead", "Olivia Rodrigo", "Drop Dead")
    assert c == "pink"


def test_black_yellow_prefers_non_black():
    c = _color_from(
        "https://skifmusic.ru/product/770525-vory-vory-black-yellow-vinyl-new-sealed-vinyl-lp-album",
        "Vory – Vory", "Vory", "Vory")
    assert c == "yellow"


def test_gold_vinyl_from_slug():
    c = _color_from(
        "https://skifmusic.ru/product/775675-chicago-chicago-x-gold-vinyl-new-vinyl",
        "Chicago – Chicago X", "Chicago", "Chicago X")
    assert c == "gold"


def test_marble_colored_from_slug():
    c = _color_from(
        "https://skifmusic.ru/product/778669-drug-church-hit-your-head-marble-colored-vinyl-new-vinyl",
        "Drug Church – Hit Your Head", "Drug Church", "Hit Your Head")
    assert c in ("marble", "coloured")


def test_generic_colored_from_slug():
    c = _color_from(
        "https://skifmusic.ru/product/772223-vic-chesnutt-ghetto-bells-colored-vinyl-new-sealed-lp-album",
        "Vic Chesnutt – Ghetto Bells", "Vic Chesnutt", "Ghetto Bells")
    assert c == "coloured"


# ---- ложных цветов из слага НЕТ ----------------------------------------- #

def test_blues_in_album_not_blue():
    # «...-the-real-folk-blues-...» — «blues» не должно стать blue (границы слова)
    c = _color_from(
        "https://skifmusic.ru/product/782092-john-lee-hooker-the-real-folk-blues-chess-acoustic-sounds-series-new-vinyl",
        "John Lee Hooker – The Real Folk Blues", "John Lee Hooker", "The Real Folk Blues")
    assert c is None


def test_no_color_slug_stays_none():
    c = _color_from(
        "https://skifmusic.ru/product/769522-johnnie-taylor-one-step-from-the-blues-new-vinyl",
        "Johnnie Taylor – One Step From The Blues", "Johnnie Taylor", "One Step From The Blues")
    assert c is None
