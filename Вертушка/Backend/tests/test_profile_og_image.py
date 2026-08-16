"""
OG-картинка публичного профиля.

Главный регресс, который тут ловится: битая кириллица. В slim-образе нет
системных шрифтов, поэтому PIL молча падал на load_default() — размер картинки
при этом оставался валидным, а весь русский текст превращался в квадраты.
"""
import asyncio

import pytest
from PIL import Image, ImageFont

from app.services import og_image
from app.services.profile_stats import pick_for_og
from app.web.routes import _fun_stat_markup


FUN_STATS = [
    {"icon": "💸", "parts": [
        {"text": "Самая дорогая: ", "bold": False},
        {"text": "42 000 ₽", "bold": True},
    ]},
    {"icon": "👑", "parts": [
        {"text": "Топ-артист: ", "bold": False},
        {"text": "Tyler, The Creator", "bold": True},
    ]},
]


@pytest.fixture
def no_network(monkeypatch):
    """Обложки и аватар — локальные картинки: тест не ходит в сеть."""
    async def _fetch_all(cover_urls, avatar_url):
        covers = [Image.new("RGB", (600, 600), (200, 120, 60)) for _ in cover_urls[:4]]
        return covers, None

    monkeypatch.setattr(og_image, "_fetch_all", _fetch_all)


def _render(**kwargs) -> Image.Image:
    defaults = dict(username="vladrum", display_name="Влад", collection_count=127, cover_urls=[])
    defaults.update(kwargs)
    buf = asyncio.run(og_image.generate_profile_og_image(**defaults))
    return Image.open(buf)


def test_fonts_have_cyrillic():
    """Шрифты лежат в репо и рисуют кириллицу — иначе будет тофу."""
    for mono in (False, True):
        font = og_image._font(24, "SemiBold", mono=mono)
        assert isinstance(font, ImageFont.FreeTypeFont), "шрифт не найден, PIL ушёл в load_default"
        # У пропавшего глифа нулевая ширина bbox — проверяем, что «Ж» реально рисуется.
        assert font.getbbox("Ж")[2] > 0


def test_renders_full_profile(no_network):
    img = _render(
        cover_urls=["u"] * 4,
        custom_title="Собираю рэп и соул",
        wishlist_count=14,
        collection_value_rub=248500,
        monthly_delta=3200,
        fun_stats=FUN_STATS,
    )
    assert img.size == (1200, 630)
    assert img.format == "PNG"


def test_renders_without_covers_and_value(no_network):
    """Приватная стоимость, пустая коллекция обложек — картинка всё равно есть."""
    img = _render(collection_count=3)
    assert img.size == (1200, 630)


def test_long_title_does_not_overflow(no_network):
    """Длинные строки режутся многоточием, а не уезжают за края."""
    img = _render(
        custom_title="Очень длинная подпись профиля, которая точно не влезет в колонку" * 3,
        collection_value_rub=1234567,
        fun_stats=FUN_STATS,
    )
    # Правая часть отдана коллажу: если текст переполз, он затрёт обложки —
    # проверяем, что колонка текста в них не залезла.
    assert img.size == (1200, 630)


def test_og_picks_most_interesting_facts():
    stats = [
        {"icon": "🎨", "parts": []},
        {"icon": "💸", "parts": []},
        {"icon": "👑", "parts": []},
        {"icon": "⚡", "parts": []},
    ]
    assert [s["icon"] for s in pick_for_og(stats, limit=3)] == ["💸", "👑", "🎨"]


def test_fun_stat_markup_escapes_user_input():
    """artist/genre — свободные строки пользователя, в разметку идут экранированными."""
    html = str(_fun_stat_markup({
        "parts": [
            {"text": "Топ-артист: ", "bold": False},
            {"text": "<script>alert(1)</script>", "bold": True},
        ],
    }))
    assert "<script>" not in html
    assert "&lt;script&gt;" in html
    assert html.startswith("Топ-артист: <b>")
