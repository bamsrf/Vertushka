"""Разбор носителя для форматных серий ачивок.

Тест держит ровно те случаи, на которых наивная проверка `format_type` врёт:
бокс-сет, спрятанный в описании, семья CD и кассетные плёнки.
"""
import pytest

from app.services.achievements.media_format import (
    BOX_SET,
    CASSETTE,
    CD,
    VINYL,
    parse_media,
)


@pytest.mark.parametrize(
    "format_type,format_description,expected",
    [
        ("Vinyl", "LP, Album", {VINYL}),
        ("Cassette", "Album", {CASSETTE}),
        ("CD", "Album, Reissue", {CD}),
        # CDr / SACD / HDCD — та же семья CD, иначе «25 CD» недосчитывается
        ("CDr", None, {CD}),
        ("SACD", "Hybrid", {CD}),
        # Бокс-сет Discogs держит в описании, а не в format_type
        ("Vinyl", "10×Vinyl, Box Set, Limited Edition", {VINYL, BOX_SET}),
        ("Box Set", "5 x CD, Numbered", {CD, BOX_SET}),
        # Служебные носители в форматные серии не идут
        ("File", "MP3, Album", set()),
        ("DVD", "DVD-Video", set()),
        ("CD", "CD-Video", set()),
        (None, None, set()),
    ],
)
def test_families(format_type, format_description, expected):
    assert set(parse_media(format_type, format_description).families) == expected


@pytest.mark.parametrize(
    "description,expected_qty",
    [
        ("10×Vinyl, Box Set", 10),
        ("5 x CD", 5),
        ("LP, Album", 1),
        (None, 1),
        ("999×File", 1),  # мусор отбрасываем
    ],
)
def test_qty(description, expected_qty):
    assert parse_media("Vinyl", description).qty == expected_qty


def test_type_iv_only_for_cassettes():
    assert parse_media("Cassette", "Album, Metal, Type IV").is_type_iv is True
    assert parse_media("Cassette", "Type II, Chrome").is_type_iv is False
    # «Metal» у винила — это жанр, а не плёнка
    assert parse_media("Vinyl", "LP, Album, Metal").is_type_iv is False


def test_limited_flag():
    assert parse_media("Vinyl", "Box Set, Limited Edition").is_limited is True
    assert parse_media("Vinyl", "Box Set, Numbered").is_limited is True
    assert parse_media("Vinyl", "LP, Album").is_limited is False
