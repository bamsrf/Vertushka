"""
Генерация OG-изображений для публичных профилей.
Размер: 1200x630px PNG.
"""
import io
import logging
from pathlib import Path

import httpx
from PIL import Image, ImageDraw, ImageFont

logger = logging.getLogger(__name__)

# Цвета (из theme)
BG_COLOR = (15, 15, 15)           # #0f0f0f
CARD_COLOR = (37, 37, 37)         # #252525
ACCENT_COLOR = (232, 93, 4)       # #e85d04
TEXT_PRIMARY = (255, 255, 255)     # #ffffff
TEXT_SECONDARY = (160, 160, 160)   # #a0a0a0

WIDTH = 1200
HEIGHT = 630
COVER_SIZE = 220
COVER_GAP = 16
COVER_GRID_X = 60
COVER_GRID_Y = 120


def _get_font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    """Загружает шрифт. Fallback на дефолтный если Montserrat не найден."""
    font_names = [
        "Montserrat-Bold.ttf" if bold else "Montserrat-SemiBold.ttf",
        "Montserrat-Regular.ttf",
        "DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf",
        "Arial Bold.ttf" if bold else "Arial.ttf",
    ]

    # Проверяем шрифты в static
    static_dir = Path(__file__).parent.parent / "web" / "static" / "fonts"
    for name in font_names:
        font_path = static_dir / name
        if font_path.exists():
            return ImageFont.truetype(str(font_path), size)

    # Системные шрифты
    for name in font_names:
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue

    return ImageFont.load_default()


async def _download_cover(url: str, size: int = COVER_SIZE) -> Image.Image | None:
    """Скачивает обложку и ресайзит."""
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            img = Image.open(io.BytesIO(resp.content)).convert("RGB")
            img = img.resize((size, size), Image.LANCZOS)
            return img
    except Exception as e:
        logger.warning(f"Failed to download cover {url}: {e}")
        return None


def _draw_placeholder(draw: ImageDraw.ImageDraw, x: int, y: int, size: int) -> None:
    """Рисует плейсхолдер обложки."""
    draw.rectangle([x, y, x + size, y + size], fill=CARD_COLOR)
    font = _get_font(48)
    draw.text((x + size // 2, y + size // 2), "🎵", fill=TEXT_SECONDARY, font=font, anchor="mm")


async def generate_profile_og_image(
    username: str,
    display_name: str | None,
    collection_count: int,
    collection_value: float | None,
    cover_urls: list[str],
) -> io.BytesIO:
    """
    Генерирует OG-изображение 1200x630.

    Layout:
    ┌────────────────────────────────────────────────┐
    │                                                │
    │  ┌────┐ ┌────┐           ВЕРТУШКА              │
    │  │ 🎵 │ │ 🎵 │                                 │
    │  └────┘ └────┘           @username             │
    │  ┌────┐ ┌────┐           ───────────           │
    │  │ 🎵 │ │ 🎵 │           127 пластинок         │
    │  └────┘ └────┘           ~$2,400               │
    │                                                │
    │                          vinyl-vertushka.ru    │
    └────────────────────────────────────────────────┘
    """
    img = Image.new("RGB", (WIDTH, HEIGHT), BG_COLOR)
    draw = ImageDraw.Draw(img)

    # === Коллаж обложек (2x2, левая часть) ===
    covers: list[Image.Image | None] = []
    for url in cover_urls[:4]:
        cover = await _download_cover(url, COVER_SIZE)
        covers.append(cover)

    # Добиваем до 4 плейсхолдерами
    while len(covers) < 4:
        covers.append(None)

    for i, cover in enumerate(covers[:4]):
        row, col = divmod(i, 2)
        x = COVER_GRID_X + col * (COVER_SIZE + COVER_GAP)
        y = COVER_GRID_Y + row * (COVER_SIZE + COVER_GAP)

        if cover:
            # Скруглённые углы
            mask = Image.new("L", (COVER_SIZE, COVER_SIZE), 0)
            mask_draw = ImageDraw.Draw(mask)
            mask_draw.rounded_rectangle([0, 0, COVER_SIZE, COVER_SIZE], radius=12, fill=255)
            img.paste(cover, (x, y), mask)
        else:
            draw.rounded_rectangle([x, y, x + COVER_SIZE, y + COVER_SIZE], radius=12, fill=CARD_COLOR)

    # === Текстовая часть (правая сторона) ===
    text_x = COVER_GRID_X + 2 * COVER_SIZE + 2 * COVER_GAP + 80
    center_y = HEIGHT // 2

    # Логотип / название приложения
    font_logo = _get_font(28, bold=True)
    draw.text((text_x, center_y - 140), "ВЕРТУШКА", fill=ACCENT_COLOR, font=font_logo)

    # Username
    name = display_name or f"@{username}"
    font_name = _get_font(36, bold=True)
    draw.text((text_x, center_y - 90), name, fill=TEXT_PRIMARY, font=font_name)

    if display_name:
        font_username = _get_font(20)
        draw.text((text_x, center_y - 48), f"@{username}", fill=TEXT_SECONDARY, font=font_username)

    # Разделитель
    sep_y = center_y - 20
    draw.line([(text_x, sep_y), (text_x + 200, sep_y)], fill=CARD_COLOR, width=2)

    # Статистика
    font_stat = _get_font(24, bold=True)
    font_stat_label = _get_font(18)

    draw.text((text_x, center_y + 0), str(collection_count), fill=ACCENT_COLOR, font=font_stat)
    draw.text((text_x + 60, center_y + 4), "пластинок", fill=TEXT_SECONDARY, font=font_stat_label)

    if collection_value:
        value_str = f"~${collection_value:,.0f}"
        draw.text((text_x, center_y + 40), value_str, fill=ACCENT_COLOR, font=font_stat)

    # URL внизу
    font_url = _get_font(16)
    draw.text((text_x, center_y + 120), "vinyl-vertushka.ru", fill=TEXT_SECONDARY, font=font_url)

    # === Экспорт ===
    buffer = io.BytesIO()
    img.save(buffer, format="PNG", optimize=True)
    buffer.seek(0)
    return buffer
