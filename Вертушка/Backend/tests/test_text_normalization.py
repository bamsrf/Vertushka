"""Smoke-тесты текстовых примитивов поиска и матчинга.

Транслитерация (поиск кириллицей по латинскому Discogs), нормализация
artist/title (симметрия с SQL-зеркалом в matcher), accessory-гейт (защита
Discogs-квоты) и format-family penalty. Тихая регрессия любого = либо
промахи поиска, либо ложные мерджи листингов.
"""
from types import SimpleNamespace

from app.services.discogs import _transliterate
from app.services.listing_matcher import (
    _format_family,
    _is_accessory,
    _normalize_text,
)


class TestTransliterate:
    def test_cyrillic_to_latin(self):
        assert _transliterate("Кино") == "Kino"
        assert _transliterate("Аквариум") == "Akvarium"

    def test_no_cyrillic_returns_none(self):
        # Чисто-латинский запрос не нуждается в транслите.
        assert _transliterate("Beatles") is None

    def test_preserves_case_on_multichar_mapping(self):
        # Ж → ZH когда исходная заглавная.
        assert _transliterate("Жук") == "ZHuk"


class TestNormalizeText:
    def test_strips_punctuation_and_lowercases(self):
        assert _normalize_text("The Beatles!") == "the beatles"

    def test_collapses_whitespace(self):
        assert _normalize_text("  Pink   Floyd  ") == "pink floyd"

    def test_none_and_empty(self):
        assert _normalize_text(None) == ""
        assert _normalize_text("") == ""

    def test_keeps_cyrillic(self):
        assert _normalize_text("Кино — Группа крови") == "кино группа крови"


class TestFormatFamily:
    def test_known_families(self):
        assert _format_family("LP") == "VINYL"
        assert _format_family("CD") == "CD"
        assert _format_family("Cassette") == "CASSETTE"

    def test_unknown_and_none_are_none(self):
        # Box Set / неизвестное → None (penalty не применяется).
        assert _format_family(None) is None


class TestIsAccessory:
    def test_accessory_titles_detected(self):
        for title in ["Значок Pink Floyd", "Постер Nirvana", "Pink Floyd (Pin)"]:
            assert _is_accessory(SimpleNamespace(title_raw=title)), title

    def test_real_record_is_not_accessory(self):
        assert not _is_accessory(SimpleNamespace(title_raw="Pink Floyd - The Wall (LP)"))

    def test_empty_title(self):
        assert not _is_accessory(SimpleNamespace(title_raw=None))
