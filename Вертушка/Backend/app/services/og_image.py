"""
Генерация OG-изображений для публичных профилей.
Размер: 1200x630px PNG.

Картинка повторяет вёрстку hero-блока публичной страницы (`public_profile.html`):
тот же ивори-фон с радиальными подсветками, та же стеклянная карточка стоимости
и те же fun stats. Превью в мессенджере и сама страница должны читаться как одна
вещь.
"""
import asyncio
import io
import logging
from pathlib import Path

import httpx
from PIL import Image, ImageDraw, ImageFilter, ImageFont

logger = logging.getLogger(__name__)

WIDTH = 1200
HEIGHT = 630
PAD = 56

# === Палитра — 1:1 с :root в public_profile.html ===
IVORY = (245, 240, 234)            # #F5F0EA
PEARL = (247, 244, 238)            # #F7F4EE
COBALT = (58, 75, 224)             # #3A4BE0
PERIWINKLE = (154, 168, 255)       # #9AA8FF
LAVENDER = (201, 184, 255)         # #C9B8FF
BLUSH = (246, 199, 208)            # #F6C7D0
SKY = (189, 212, 255)              # #BDD4FF
PEACH = (247, 212, 184)            # #F7D4B8
INK = (27, 29, 38)                 # #1B1D26
SLATE = (107, 112, 128)            # #6B7080

FONTS_DIR = Path(__file__).parent.parent / "web" / "static" / "fonts"

# Правый визуальный блок: коллаж 2×2 из обложек.
COVER_SIZE = 208
COVER_GAP = 14
GRID_W = COVER_SIZE * 2 + COVER_GAP
GRID_X = WIDTH - PAD - GRID_W
GRID_Y = (HEIGHT - GRID_W) // 2

# Левая колонка
COL_X = PAD
COL_W = GRID_X - PAD - 48
CARD_RADIUS = 26

_font_cache: dict[tuple[str, int, str], ImageFont.FreeTypeFont] = {}


def _font(size: int, weight: str = "Regular", mono: bool = False) -> ImageFont.FreeTypeFont:
    """Шрифт нужного начертания. Inter Tight / JetBrains Mono — те же, что на странице.

    Оба файла вариативные, поэтому вес выставляется через именованную инстанцию.
    Если шрифты не доехали (их кладёт репозиторий, а не образ) — деградируем до
    дефолтного PIL-шрифта: подпись станет уродливой, но роут не упадёт.
    """
    key = (weight, size, "mono" if mono else "sans")
    cached = _font_cache.get(key)
    if cached is not None:
        return cached

    path = FONTS_DIR / ("JetBrainsMono.ttf" if mono else "InterTight.ttf")
    try:
        font = ImageFont.truetype(str(path), size)
        font.set_variation_by_name(weight)
    except Exception as e:
        logger.warning("OG font %s (%s) unavailable: %s", path.name, weight, e)
        font = ImageFont.load_default()

    _font_cache[key] = font
    return font


# ---------------------------------------------------------------- рисовалки

def _background() -> Image.Image:
    """Ивори-подложка с двумя радиальными подсветками — как `html` на странице.

    Градиенты считаются на крошечном холсте (в 20 раз меньше) и растягиваются
    LANCZOS: радиальная заливка достаточно плавная, чтобы апскейл был неотличим,
    а попиксельный цикл по 1200×630 в питоне стоил бы заметных миллисекунд.
    """
    sw, sh = WIDTH // 20, HEIGHT // 20
    img = Image.new("RGB", (sw, sh), IVORY)

    # (цвет, центр в долях холста, радиусы в долях, макс. альфа)
    layers = [
        (PERIWINKLE, (0.92, -0.04), (0.75, 1.02), 0.82),
        (SKY, (0.04, 0.02), (0.57, 0.83), 0.60),
        (BLUSH, (0.30, 1.06), (0.45, 0.60), 0.30),
    ]
    for color, (cx, cy), (rx, ry), alpha in layers:
        mask = Image.new("L", (sw, sh), 0)
        px = mask.load()
        cx_p, cy_p = cx * sw, cy * sh
        rx_p, ry_p = max(rx * sw, 1e-6), max(ry * sh, 1e-6)
        for y in range(sh):
            dy = (y - cy_p) / ry_p
            for x in range(sw):
                dx = (x - cx_p) / rx_p
                d = (dx * dx + dy * dy) ** 0.5
                if d >= 1.0:
                    continue
                # CSS-градиент гаснет к `transparent 62%` — повторяем мягкий спад.
                px[x, y] = int(alpha * 255 * (1.0 - d) ** 1.6)
        img.paste(Image.new("RGB", (sw, sh), color), (0, 0), mask)

    return img.resize((WIDTH, HEIGHT), Image.LANCZOS)


def _shadow(size: tuple[int, int], draw_fn, blur: int, offset: tuple[int, int], alpha: int) -> Image.Image:
    """Мягкая тень под произвольной фигурой."""
    layer = Image.new("RGBA", size, (0, 0, 0, 0))
    draw_fn(ImageDraw.Draw(layer))
    layer = layer.filter(ImageFilter.GaussianBlur(blur))
    if alpha < 255:
        layer.putalpha(layer.getchannel("A").point(lambda v: v * alpha // 255))
    shifted = Image.new("RGBA", size, (0, 0, 0, 0))
    shifted.paste(layer, offset)
    return shifted


def _rounded_cover(img: Image.Image, size: int, radius: int = 14) -> Image.Image:
    """Обложка со скруглением и тонкой светлой обводкой."""
    img = img.convert("RGB").resize((size, size), Image.LANCZOS)
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, size - 1, size - 1], radius=radius, fill=255)
    out = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    out.paste(img, (0, 0), mask)
    ImageDraw.Draw(out).rounded_rectangle(
        [0, 0, size - 1, size - 1], radius=radius, outline=(255, 255, 255, 150), width=2
    )
    return out


def _cover_placeholder(size: int, radius: int = 14) -> Image.Image:
    """Заглушка вместо обложки — перламутровый квадрат с кобальтовой ноткой."""
    out = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(out)
    d.rounded_rectangle([0, 0, size - 1, size - 1], radius=radius, fill=PEARL + (235,))
    d.rounded_rectangle(
        [0, 0, size - 1, size - 1], radius=radius, outline=(255, 255, 255, 170), width=2
    )
    c, r = size / 2, size * 0.16
    d.ellipse([c - r, c - r, c + r, c + r], outline=PERIWINKLE + (200,), width=3)
    d.ellipse([c - 4, c - 4, c + 4, c + 4], fill=PERIWINKLE + (200,))
    return out


# ---------------------------------------------------------------- текст

def _text_width(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont) -> float:
    return draw.textlength(text, font=font)


def _tracked(
    draw: ImageDraw.ImageDraw, xy: tuple[int, int], text: str,
    font: ImageFont.FreeTypeFont, fill, tracking: float,
) -> None:
    """Текст с межбуквенным интервалом — PIL сам letter-spacing не умеет."""
    x, y = xy
    for ch in text:
        draw.text((x, y), ch, font=font, fill=fill)
        x += draw.textlength(ch, font=font) + tracking


def _ellipsize(
    draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont, max_w: float
) -> str:
    if _text_width(draw, text, font) <= max_w:
        return text
    while text and _text_width(draw, text + "…", font) > max_w:
        text = text[:-1]
    return (text or "") + "…"


def _draw_parts(
    draw: ImageDraw.ImageDraw, xy: tuple[int, int], parts: list[dict],
    max_w: float, size: int = 21,
) -> None:
    """Рисует факт: жирные куски — кобальтом полужирным, остальное — чернилами.

    Если строка не влезает, режется по последнему куску, а не по всей строке —
    так число в начале факта («127 пластинок из 80-х») остаётся видимым.
    """
    x, y = xy
    regular = _font(size, "Medium")
    bold = _font(size, "Bold")
    for part in parts:
        font = bold if part["bold"] else regular
        remaining = max_w - (x - xy[0])
        if remaining <= 12:
            break
        text = _ellipsize(draw, part["text"], font, remaining)
        draw.text((x, y), text, font=font, fill=COBALT if part["bold"] else INK)
        x += _text_width(draw, text, font)


# ---------------------------------------------------------------- загрузка

async def _fetch_image(client: httpx.AsyncClient, url: str) -> Image.Image | None:
    try:
        resp = await client.get(url)
        resp.raise_for_status()
        return Image.open(io.BytesIO(resp.content))
    except Exception as e:
        logger.warning("OG: failed to load image %s: %s", url, e)
        return None


async def _fetch_all(cover_urls: list[str], avatar_url: str | None):
    """Обложки и аватар качаются одним клиентом параллельно.

    Раньше обложки шли последовательно — четыре round-trip'а подряд упирались
    в таймаут превьюшника у мессенджеров.
    """
    # UA обязателен: CDN Discogs отдаёт 403 на запросы без него.
    headers = {"User-Agent": "Vertushka/1.0 (+https://vinyl-vertushka.ru)"}
    async with httpx.AsyncClient(timeout=8, follow_redirects=True, headers=headers) as client:
        tasks = [_fetch_image(client, u) for u in cover_urls[:4]]
        tasks.append(_fetch_image(client, avatar_url) if avatar_url else _noop())
        results = await asyncio.gather(*tasks)
    return list(results[:-1]), results[-1]


async def _noop():
    return None


# ---------------------------------------------------------------- аватар

def _draw_avatar(base: Image.Image, x: int, y: int, size: int,
                 avatar: Image.Image | None, username: str) -> None:
    """Аватар в кольце-конусе — упрощение conic-gradient из `.avatar-ring`."""
    ring = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(ring)
    # Конический градиент секторами: шесть опорных цветов из CSS.
    stops = [BLUSH, LAVENDER, PERIWINKLE, SKY, PEACH, BLUSH]
    steps = 60
    for i in range(steps):
        t = i / steps * (len(stops) - 1)
        i0 = int(t)
        f = t - i0
        c0, c1 = stops[i0], stops[min(i0 + 1, len(stops) - 1)]
        color = tuple(int(a + (b - a) * f) for a, b in zip(c0, c1))
        a0 = 140 + i * 360 / steps
        d.pieslice([0, 0, size - 1, size - 1], a0, a0 + 360 / steps + 1, fill=color + (255,))

    inner = size - 12
    inner_img = Image.new("RGBA", (inner, inner), (0, 0, 0, 0))
    if avatar is not None:
        inner_img.paste(avatar.convert("RGB").resize((inner, inner), Image.LANCZOS), (0, 0))
    else:
        di = ImageDraw.Draw(inner_img)
        di.ellipse([0, 0, inner - 1, inner - 1], fill=PEARL + (255,))
        initials = (username or "")[:2].lower()
        di.text(
            (inner / 2, inner / 2 + 1), initials,
            font=_font(int(inner * 0.38), "SemiBold"), fill=COBALT, anchor="mm",
        )
    mask = Image.new("L", (inner, inner), 0)
    ImageDraw.Draw(mask).ellipse([0, 0, inner - 1, inner - 1], fill=255)
    ring.paste(inner_img, (6, 6), mask)

    ring_mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(ring_mask).ellipse([0, 0, size - 1, size - 1], fill=255)
    ring.putalpha(ring_mask)

    def _blob(dr):
        dr.ellipse([x, y + 6, x + size, y + size + 6], fill=(154, 168, 255, 150))

    base.alpha_composite(_shadow((WIDTH, HEIGHT), _blob, 12, (0, 6), 255))
    base.alpha_composite(ring, (x, y))


# ---------------------------------------------------------------- сборка

def _format_rub(value: float) -> str:
    return f"{int(value):,}".replace(",", " ")


async def generate_profile_og_image(
    username: str,
    display_name: str | None,
    collection_count: int,
    cover_urls: list[str],
    *,
    custom_title: str | None = None,
    wishlist_count: int = 0,
    collection_value_rub: float | None = None,
    monthly_delta: float | None = None,
    fun_stats: list[dict] | None = None,
    avatar_url: str | None = None,
) -> io.BytesIO:
    """
    Генерирует OG-изображение 1200x630 в стиле публичной страницы.

    Layout:
    ┌──────────────────────────────────────────────────────┐
    │ ВЕРТУШКА · ПРОФИЛЬ                                   │
    │ (○) @username                          ┌────┬────┐   │
    │     подпись профиля                    │    │    │   │
    │ ┌───────────────────────────┐          ├────┼────┤   │
    │ │ СТОИМОСТЬ КОЛЛЕКЦИИ       │          │    │    │   │
    │ │ 248 500 ₽                 │          └────┴────┘   │
    │ │ (127 · 14 в в/л · +3 200) │                        │
    │ │ · Самая дорогая: 42 000 ₽ │                        │
    │ │ · Топ-артист: Tyler       │                        │
    │ └───────────────────────────┘                        │
    │ vinyl-vertushka.ru                                   │
    └──────────────────────────────────────────────────────┘
    """
    covers, avatar = await _fetch_all(cover_urls, avatar_url)

    # Вся отрисовка — чистый CPU (PIL): фон, тени с GaussianBlur, ресайзы,
    # PNG-optimize — суммарно сотни миллисекунд. Прод живёт на одном
    # uvicorn-воркере, синхронный рендер в async-роуте морозил event loop
    # целиком (все запросы, не только og-image). to_thread уводит его в пул.
    return await asyncio.to_thread(
        _render_og_image,
        username=username,
        display_name=display_name,
        collection_count=collection_count,
        covers=covers,
        avatar=avatar,
        custom_title=custom_title,
        wishlist_count=wishlist_count,
        collection_value_rub=collection_value_rub,
        monthly_delta=monthly_delta,
        fun_stats=fun_stats,
    )


def _render_og_image(
    *,
    username: str,
    display_name: str | None,
    collection_count: int,
    covers: list,
    avatar: Image.Image | None,
    custom_title: str | None,
    wishlist_count: int,
    collection_value_rub: float | None,
    monthly_delta: float | None,
    fun_stats: list[dict] | None,
) -> io.BytesIO:
    """Синхронный PIL-рендер. Вызывается ТОЛЬКО через asyncio.to_thread."""
    base = _background().convert("RGBA")

    # === Правый блок: коллаж обложек ===
    tiles = list(covers) + [None] * (4 - len(covers))
    for i, cover in enumerate(tiles[:4]):
        row, col = divmod(i, 2)
        x = GRID_X + col * (COVER_SIZE + COVER_GAP)
        y = GRID_Y + row * (COVER_SIZE + COVER_GAP)

        def _blob(dr, x=x, y=y):
            dr.rounded_rectangle(
                [x + 6, y + 10, x + COVER_SIZE - 6, y + COVER_SIZE + 6],
                radius=14, fill=(27, 29, 38, 90),
            )

        base.alpha_composite(_shadow((WIDTH, HEIGHT), _blob, 14, (0, 0), 255))
        tile = _rounded_cover(cover, COVER_SIZE) if cover else _cover_placeholder(COVER_SIZE)
        base.alpha_composite(tile, (x, y))

    draw = ImageDraw.Draw(base)

    # === Левая колонка ===
    _tracked(
        draw, (COL_X, PAD - 2), "ВЕРТУШКА · ПРОФИЛЬ",
        _font(15, "Medium", mono=True), SLATE, tracking=2.2,
    )

    avatar_size = 68
    avatar_y = PAD + 42
    _draw_avatar(base, COL_X, avatar_y, avatar_size, avatar, username)

    name_x = COL_X + avatar_size + 18
    name_max = COL_W - avatar_size - 18
    subtitle = (custom_title or display_name or "").strip()
    if subtitle:
        draw.text(
            (name_x, avatar_y + 4), _ellipsize(draw, f"@{username}", _font(34, "SemiBold"), name_max),
            font=_font(34, "SemiBold"), fill=INK,
        )
        draw.text(
            (name_x, avatar_y + 42), _ellipsize(draw, subtitle, _font(19, "Regular"), name_max),
            font=_font(19, "Regular"), fill=SLATE,
        )
    else:
        draw.text(
            (name_x, avatar_y + 16), _ellipsize(draw, f"@{username}", _font(34, "SemiBold"), name_max),
            font=_font(34, "SemiBold"), fill=INK,
        )

    # === Стеклянная карточка ===
    # Высоту считаем до отрисовки: подложка должна знать, сколько строк в неё
    # ляжет, иначе последний факт вываливается за скругление.
    facts = (fun_stats or [])[:3]
    has_value = collection_value_rub is not None and collection_value_rub > 0

    summary: list[str] = []
    if has_value:
        summary.append(f"{collection_count} в коллекции")
    if wishlist_count > 0:
        summary.append(f"{wishlist_count} в вишлисте")
    if monthly_delta:
        sign = "+" if monthly_delta > 0 else "−"
        summary.append(f"{sign}{_format_rub(abs(monthly_delta))} ₽ за месяц")

    card_x0, card_y0 = COL_X, avatar_y + avatar_size + 30
    card_x1 = COL_X + COL_W
    card_y1 = card_y0 + 134 + (48 if summary else 14) + len(facts) * 34

    def _card_blob(dr):
        dr.rounded_rectangle(
            [card_x0 + 16, card_y0 + 22, card_x1 - 16, card_y1 + 10],
            radius=CARD_RADIUS, fill=(27, 29, 38, 58),
        )

    base.alpha_composite(_shadow((WIDTH, HEIGHT), _card_blob, 20, (0, 0), 255))

    card = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    cd = ImageDraw.Draw(card)
    cd.rounded_rectangle(
        [card_x0, card_y0, card_x1, card_y1], radius=CARD_RADIUS,
        fill=(255, 255, 255, 168), outline=(255, 255, 255, 220), width=2,
    )
    base.alpha_composite(card)
    draw = ImageDraw.Draw(base)

    tx = card_x0 + 26
    ty = card_y0 + 22
    inner_w = COL_W - 52

    label = "Стоимость коллекции" if has_value else "Коллекция"
    _tracked(draw, (tx, ty), label.upper(), _font(12, "Medium"), SLATE, tracking=1.4)

    ty += 24
    if has_value:
        value_font = _font(50, "SemiBold")
        value_text = _format_rub(collection_value_rub)
        draw.text((tx, ty), value_text, font=value_font, fill=INK)
        vx = tx + _text_width(draw, value_text, value_font) + 10
        draw.text((vx, ty + 16), "₽", font=_font(30, "Medium"), fill=SLATE)
    else:
        value_font = _font(50, "SemiBold")
        value_text = str(collection_count)
        draw.text((tx, ty), value_text, font=value_font, fill=INK)
        vx = tx + _text_width(draw, value_text, value_font) + 10
        draw.text((vx, ty + 16), "пластинок", font=_font(24, "Medium"), fill=SLATE)

    # Строка-сводка: счётчики + дельта за месяц.
    ty += 66
    if summary:
        pill_text = "  ·  ".join(summary)
        pill_font = _font(17, "Medium")
        pill_w = _text_width(draw, _ellipsize(draw, pill_text, pill_font, inner_w - 28), pill_font)
        pill = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
        ImageDraw.Draw(pill).rounded_rectangle(
            [tx, ty, tx + pill_w + 28, ty + 34], radius=17,
            fill=(255, 255, 255, 150), outline=(58, 75, 224, 42), width=1,
        )
        base.alpha_composite(pill)
        draw = ImageDraw.Draw(base)
        draw.text(
            (tx + 14, ty + 7), _ellipsize(draw, pill_text, pill_font, inner_w - 28),
            font=pill_font, fill=COBALT,
        )
        ty += 48
    else:
        ty += 14

    # Fun stats: эмодзи со страницы тут не годятся — в slim-образе нет цветного
    # эмодзи-шрифта, они вышли бы тофу-квадратами. Вместо иконки — кобальтовая
    # точка-буллет.
    for fact in facts:
        draw.ellipse([tx + 2, ty + 10, tx + 10, ty + 18], fill=PERIWINKLE)
        _draw_parts(draw, (tx + 22, ty), fact["parts"], inner_w - 22, size=20)
        ty += 34

    # === Подпись ===
    _tracked(
        draw, (COL_X, HEIGHT - PAD - 8), "vinyl-vertushka.ru",
        _font(16, "Medium", mono=True), SLATE, tracking=0.6,
    )

    buffer = io.BytesIO()
    base.convert("RGB").save(buffer, format="PNG", optimize=True)
    buffer.seek(0)
    return buffer
