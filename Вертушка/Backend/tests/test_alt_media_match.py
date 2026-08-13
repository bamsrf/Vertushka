"""Совместимость носителей для «другой версии» на радаре.

Баг, ради которого это написано: мастер Discogs объединяет все издания
альбома, и радар предлагал владельцу винилового вишлиста «File, MP3» за
29 990 ₽ как подходящий аналог.
"""
import pytest

from app.services.alt_media_match import (
    CASSETTE,
    CD,
    DIGITAL,
    VINYL,
    alt_media_ok,
    media_families,
)


@pytest.mark.parametrize(
    "format_type,format_description,expected",
    [
        ("Vinyl", "LP, Album", {VINYL}),
        ('Vinyl, 12", 33 ⅓ RPM, EP', None, {VINYL}),
        ("CD", "Album, Reissue", {CD}),
        ("SACD", "Hybrid", {CD}),
        ("Cassette", "Album", {CASSETTE}),
        ("File", "MP3, Album", {DIGITAL}),
        ("File", "FLAC, 24-bit", {DIGITAL}),
        ("Digital", None, {DIGITAL}),
        # Винил с кодом на скачивание остаётся винилом
        ("Vinyl", "LP, Album + File, MP3", {VINYL, DIGITAL}),
        (None, None, set()),
    ],
)
def test_media_families(format_type, format_description, expected):
    assert media_families(format_type, format_description) == expected


@pytest.mark.parametrize(
    "wanted,alt,ok",
    [
        # Тот самый кейс со скриншота
        (("Vinyl", "LP, Album"), ("File", "MP3, Album"), False),
        (("Vinyl", "LP, Album"), ("Vinyl", '12", 45 RPM'), True),
        (("Vinyl", "LP, Album"), ("CD", "Album"), False),
        (("Vinyl", "LP, Album"), ("Cassette", None), False),
        (("CD", "Album"), ("CD", "Album, Remastered"), True),
        (("CD", "Album"), ("File", "FLAC"), False),
        # Носитель альтернативы неизвестен, а желаемый известен → не предлагаем
        (("Vinyl", "LP"), (None, None), False),
        # Желаемый носитель неизвестен: физику пропускаем, цифру — нет
        ((None, None), ("Vinyl", "LP"), True),
        ((None, None), ("File", "MP3"), False),
        ((None, None), (None, None), True),
    ],
)
def test_alt_media_ok(wanted, alt, ok):
    assert alt_media_ok(wanted[0], wanted[1], alt[0], alt[1]) is ok


def test_listing_format_raw_is_fallback():
    """У store-native записи полей Discogs нет — смотрим на формат листинга."""
    assert alt_media_ok("Vinyl", "LP", None, None, alt_format_raw="LP, 180g") is True
    assert alt_media_ok("Vinyl", "LP", None, None, alt_format_raw="MP3") is False
