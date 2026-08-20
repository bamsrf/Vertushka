"""Генерация share-card PNG для ачивок.

Phase 1: PIL-композиция. SVG-пины ещё не нарисованы дизайнером — пока рендерим
плейсхолдер (круг с инициалом из icon_slug + название). Когда появятся реальные
SVG, переключим на cairosvg для растеризации.

Размеры (см. PLAN_ACHIEVEMENTS_V2.md §8.4):
- 1080×1920 (Instagram Stories, основной формат)
- 1080×1080 (Instagram Feed) — кроп
- 1080×1350 (Instagram Portrait) — кроп

Композиция (по умолчанию для 9:16):
  градиентный фон (цвет тира)
  крупная иконка (700×700 в центре, чуть выше середины)
  название ачивки (под иконкой)
  «<Тир> · <дата>» (мелким)
  внизу: аватар + @username + лого vinyl-vertushka.ru
"""
from __future__ import annotations

import io
import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Iterable

from PIL import Image, ImageDraw, ImageFont

from app.services.achievements.registry import (
    AchievementDefinition,
    AchievementTier,
    TIER_LABELS_RU,
)

logger = logging.getLogger(__name__)


TIER_BG_COLORS: dict[AchievementTier, tuple[str, str]] = {
    # (верхний → нижний) для линейного градиента
    AchievementTier.SIMPLE: ("#C7DEED", "#A5C8E1"),
    AchievementTier.NOTABLE: ("#7E9DE6", "#5B7DD8"),
    AchievementTier.RARE: ("#F2B6D2", "#E89AC0"),
    AchievementTier.EPIC: ("#2F3AA8", "#1B237D"),
    AchievementTier.LEGEND: ("#2E2E40", "#0A0A1A"),
}


@dataclass
class ShareCardSize:
    width: int
    height: int


SIZE_STORIES = ShareCardSize(1080, 1920)
SIZE_FEED = ShareCardSize(1080, 1080)
SIZE_PORTRAIT = ShareCardSize(1080, 1350)


def _hex_to_rgb(s: str) -> tuple[int, int, int]:
    s = s.lstrip("#")
    return tuple(int(s[i:i + 2], 16) for i in (0, 2, 4))  # type: ignore[return-value]


def _vertical_gradient(size: ShareCardSize, top: str, bottom: str) -> Image.Image:
    img = Image.new("RGB", (size.width, size.height), top)
    top_rgb = _hex_to_rgb(top)
    bottom_rgb = _hex_to_rgb(bottom)
    pixels = img.load()
    for y in range(size.height):
        t = y / max(size.height - 1, 1)
        r = int(top_rgb[0] * (1 - t) + bottom_rgb[0] * t)
        g = int(top_rgb[1] * (1 - t) + bottom_rgb[1] * t)
        b = int(top_rgb[2] * (1 - t) + bottom_rgb[2] * t)
        for x in range(size.width):
            pixels[x, y] = (r, g, b)
    return img


def _load_font(size: int) -> ImageFont.ImageFont:
    """Пробуем системные пути в порядке предпочтения, fallback на default."""
    candidates: Iterable[str] = (
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/Library/Fonts/Arial Bold.ttf",
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
        "/System/Library/Fonts/SFNS.ttf",
    )
    for path in candidates:
        try:
            return ImageFont.truetype(path, size)
        except (OSError, IOError):
            continue
    return ImageFont.load_default()


def _draw_placeholder_pin(
    draw: ImageDraw.ImageDraw,
    icon_slug: str,
    center: tuple[int, int],
    diameter: int,
    tier: AchievementTier,
) -> None:
    """Временный плейсхолдер до появления реальных SVG.

    Рисует эмалевый круг с инициалом из icon_slug. Будет заменён на
    cairosvg.svg2png в Phase 1.5, когда дизайнер сдаст ассеты.
    """
    cx, cy = center
    r = diameter // 2
    # Внешняя обводка (металлическая кайма)
    metal_color = _hex_to_rgb(TIER_BG_COLORS[tier][0])
    metal_color = tuple(min(255, c + 60) for c in metal_color)
    draw.ellipse(
        [cx - r, cy - r, cx + r, cy + r],
        fill=metal_color,
    )
    # Внутренний эмалевый круг
    inner_r = r - 16
    draw.ellipse(
        [cx - inner_r, cy - inner_r, cx + inner_r, cy + inner_r],
        fill=_hex_to_rgb(TIER_BG_COLORS[tier][1]),
    )
    # Буква-инициал
    letter = "".join(ch for ch in icon_slug.upper() if ch.isalnum())[:2] or "?"
    font = _load_font(diameter // 3)
    bbox = draw.textbbox((0, 0), letter, font=font)
    tw = bbox[2] - bbox[0]
    th = bbox[3] - bbox[1]
    draw.text(
        (cx - tw / 2, cy - th / 2 - bbox[1]),
        letter,
        fill=(255, 255, 255),
        font=font,
    )


def _draw_text_centered(
    draw: ImageDraw.ImageDraw,
    text: str,
    y: int,
    width: int,
    font: ImageFont.ImageFont,
    fill: tuple[int, int, int] = (255, 255, 255),
) -> int:
    bbox = draw.textbbox((0, 0), text, font=font)
    tw = bbox[2] - bbox[0]
    draw.text(((width - tw) / 2, y), text, fill=fill, font=font)
    return bbox[3] - bbox[1]


def render_share_card(
    defn: AchievementDefinition,
    *,
    username: str,
    unlocked_at: datetime | None = None,
    size: ShareCardSize = SIZE_STORIES,
    evidence_text: str | None = None,
) -> bytes:
    """Рендерит PNG share-card. Возвращает bytes для возврата в API."""
    top, bottom = TIER_BG_COLORS[defn.tier]
    canvas = _vertical_gradient(size, top, bottom)
    draw = ImageDraw.Draw(canvas)

    # Пин в центре, чуть выше середины
    diameter = int(size.width * 0.62)
    pin_cy = int(size.height * 0.40)
    _draw_placeholder_pin(
        draw,
        defn.icon_slug or defn.code,
        (size.width // 2, pin_cy),
        diameter,
        defn.tier,
    )

    # Название ачивки
    title_y = pin_cy + diameter // 2 + 60
    title_font = _load_font(int(size.width * 0.075))
    title = defn.title_ru if not defn.is_hidden else defn.title_ru
    _draw_text_centered(draw, title, title_y, size.width, title_font)

    # Тир + дата
    tier_label = TIER_LABELS_RU.get(defn.tier, defn.tier.value)
    date_str = ""
    if unlocked_at:
        date_str = unlocked_at.strftime("%d.%m.%Y")
    sub_text = f"{tier_label}  ·  {date_str}" if date_str else tier_label
    sub_font = _load_font(int(size.width * 0.035))
    _draw_text_centered(
        draw,
        sub_text,
        title_y + int(size.width * 0.10),
        size.width,
        sub_font,
        fill=(230, 230, 235),
    )

    # Улика «за какую музыку» — короткая строка под тиром. Только музыка,
    # без людей и цен (карточка уходит в публичные Stories).
    if evidence_text:
        ev_font = _load_font(int(size.width * 0.030))
        _draw_text_centered(
            draw,
            evidence_text,
            title_y + int(size.width * 0.16),
            size.width,
            ev_font,
            fill=(210, 210, 220),
        )

    # Нижний блок: username + домен
    bottom_font = _load_font(int(size.width * 0.038))
    bottom_y = size.height - int(size.height * 0.10)
    _draw_text_centered(draw, f"@{username}", bottom_y, size.width, bottom_font)
    site_font = _load_font(int(size.width * 0.025))
    _draw_text_centered(
        draw,
        "vinyl-vertushka.ru",
        bottom_y + int(size.width * 0.055),
        size.width,
        site_font,
        fill=(200, 200, 210),
    )

    buf = io.BytesIO()
    canvas.save(buf, "PNG", optimize=True)
    return buf.getvalue()


def render_for_format(
    defn: AchievementDefinition,
    *,
    username: str,
    unlocked_at: datetime | None,
    fmt: str,
    evidence_text: str | None = None,
) -> bytes:
    """fmt: 'stories' | 'feed' | 'portrait'."""
    size_map = {
        "stories": SIZE_STORIES,
        "feed": SIZE_FEED,
        "portrait": SIZE_PORTRAIT,
    }
    size = size_map.get(fmt, SIZE_STORIES)
    return render_share_card(
        defn,
        username=username,
        unlocked_at=unlocked_at,
        size=size,
        evidence_text=evidence_text,
    )
