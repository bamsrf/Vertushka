#!/usr/bin/env python3
"""Экспорт кадров App Store в послойный SVG для Figma.

Тот же макет, что и PNG, но векторный и разобранный по слоям: фон, канавки,
свечения, каждая строка текста, корпус мокапа. Тексты остаются <text> — в Figma
приезжают редактируемыми текстовыми слоями, а не картинкой.

    python3 Design/appstore/build_svg.py

Скриншоты НЕ вшиваются: на месте экрана остаётся пустой слот «Экран-вставить-скриншот».
PNG кладётся в него уже внутри Figma. Поэтому файлы весят килобайты, а не мегабайты.

Сознательно не используются SVG-фильтры (blur, drop-shadow): Figma при импорте
растрирует слои с фильтрами, и вся послойность теряется. Мягкие тени и свечения
собраны на градиентах — см. README.
"""
from __future__ import annotations

import pathlib
import re

import build as B
import measure as M

OUT = B.ROOT / "figma"
# аспект исходников (iPhone 15/16 Pro) — на случай, если src/ нет, он не в git
FALLBACK_ASPECT = 2556 / 1179

GLOW_RE = re.compile(
    r"radial-gradient\((\d+)px (\d+)px at (-?\d+)% (-?\d+)%, "
    r"rgba\((\d+),(\d+),(\d+),([\d.]+)\), transparent (\d+)%\)"
)
EMBER_RE = re.compile(r"rgba\((\d+),(\d+),(\d+),([\d.]+)\),rgba\((\d+),(\d+),(\d+),([\d.]+)\) (\d+)%")


def esc(t: str) -> str:
    return t.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def n(v: float) -> str:
    """Короткая запись числа: 96.0 -> 96, 853.5 -> 853.5."""
    return f"{round(v, 2):g}"


def shot_size(name: str) -> tuple[int, int]:
    src = B.SRC / name
    if src.exists():
        sw, sh = B.png_size(src)
        return B.SCREEN_W, round(B.SCREEN_W * sh / sw)
    return B.SCREEN_W, round(B.SCREEN_W * FALLBACK_ASPECT)


def css_angle_line(deg: float, w: float, h: float) -> tuple[float, float, float, float]:
    """Концы градиентной линии CSS-угла в пользовательских координатах SVG."""
    import math
    a = math.radians(deg)
    dx, dy = math.sin(a), -math.cos(a)
    length = abs(w * math.sin(a)) + abs(h * math.cos(a))
    cx, cy = w / 2, h / 2
    return (cx - dx * length / 2, cy - dy * length / 2,
            cx + dx * length / 2, cy + dy * length / 2)


def build(slide: dict) -> str:
    geo = M.measure(slide)
    sw, sh = shot_size(slide["shot"])
    frame_w, frame_h = sw + B.BEZEL * 2, sh + B.BEZEL * 2
    phone_x = (B.W - frame_w) / 2
    ember_cy = B.PHONE_TOP + frame_h - 300 + 330
    halo_cy = B.PHONE_TOP - 130 + 450

    defs: list[str] = []
    body: list[str] = []

    # ── фон ────────────────────────────────────────────────────────────
    P = B.PALETTE
    x1, y1, x2, y2 = css_angle_line(P["angle"], B.W, B.H)
    stops = "".join(f'<stop offset="{n(off)}" stop-color="{col}"/>' for off, col in P["stops"])
    defs.append(
        f'<linearGradient id="gBase" gradientUnits="userSpaceOnUse" '
        f'x1="{n(x1)}" y1="{n(y1)}" x2="{n(x2)}" y2="{n(y2)}">{stops}</linearGradient>'
    )
    bg = [f'<rect id="Фон-градиент" x="0" y="0" width="{B.W}" height="{B.H}" fill="url(#gBase)"/>']

    for i, m in enumerate(GLOW_RE.finditer(slide["glow"]), 1):
        rx, ry, px, py, r, g, b, a, stop = m.groups()
        cx, cy = B.W * int(px) / 100, B.H * int(py) / 100
        defs.append(
            f'<radialGradient id="gGlow{i}">'
            f'<stop offset="0" stop-color="rgb({r},{g},{b})" stop-opacity="{a}"/>'
            f'<stop offset="{int(stop)/100}" stop-color="rgb({r},{g},{b})" stop-opacity="0"/>'
            "</radialGradient>"
        )
        bg.append(f'<ellipse id="Свет-{i}" cx="{n(cx)}" cy="{n(cy)}" rx="{rx}" ry="{ry}" fill="url(#gGlow{i})"/>')

    # виньетка: CSS-эллипс 130%/82%, за его пределами цвет последнего стопа
    vrx, vry = B.W * 1.30, B.H * 0.82
    sx = vrx / vry
    defs.append(
        f'<radialGradient id="gVign" gradientUnits="userSpaceOnUse" cx="645" cy="1286" r="{n(vry)}" '
        f'gradientTransform="translate({n(645 * (1 - sx))},0) scale({n(sx)},1)">'
        f'<stop offset=".56" stop-color="{P["vignette"][0]}" stop-opacity="0"/>'
        f'<stop offset="1" stop-color="{P["vignette"][0]}" stop-opacity="{P["vignette"][1]}"/>'
        "</radialGradient>"
    )
    bg.append(f'<rect id="Виньетка" x="0" y="0" width="{B.W}" height="{B.H}" fill="url(#gVign)"/>')
    body.append('<g id="Фон">' + "".join(bg) + "</g>")

    # ── канавки пластинки: реальные окружности вместо repeating-gradient ──
    rings = []
    for r in range(17, 647, 17):
        t = r / 850
        mask = 1.0 if t <= .30 else (1 - (t - .30) / .30 * .65 if t <= .60 else max(0.0, .35 * (1 - (t - .60) / .16)))
        rings.append(f'<circle cx="1000" cy="430" r="{r}" stroke="{P["groove"]}" '
                     f'stroke-opacity="{n(P["grooveAlpha"] * mask)}" fill="none"/>')
    body.append(f'<g id="Канавки" opacity="{P["grooveGroup"]}" stroke-width="1.5">' + "".join(rings) + "</g>")

    # ── свечения ───────────────────────────────────────────────────────
    defs.append(
        '<radialGradient id="gHalo">'
        '<stop offset="0" stop-color="#8CAAFF" stop-opacity=".30"/>'
        '<stop offset=".70" stop-color="#8CAAFF" stop-opacity="0"/></radialGradient>'
    )
    body.append(f'<ellipse id="Гало" cx="645" cy="{n(halo_cy)}" rx="560" ry="450" fill="url(#gHalo)"/>')

    e = EMBER_RE.search(slide["pool"])
    r1, g1, b1, a1, r2, g2, b2, a2, mid = e.groups()
    defs.append(
        '<radialGradient id="gEmber">'
        f'<stop offset="0" stop-color="rgb({r1},{g1},{b1})" stop-opacity="{a1}"/>'
        f'<stop offset="{int(mid)/100}" stop-color="rgb({r2},{g2},{b2})" stop-opacity="{a2}"/>'
        f'<stop offset=".78" stop-color="rgb({r2},{g2},{b2})" stop-opacity="0"/></radialGradient>'
    )
    body.append(f'<ellipse id="Пятно-под-мокапом" cx="645" cy="{n(ember_cy)}" rx="710" ry="330" fill="url(#gEmber)"/>')

    # ── текст ──────────────────────────────────────────────────────────
    p, tag = geo["pill"], geo["tag"]
    tag_bg, tag_bg_a = P["tagBg"]
    tag_br, tag_br_a = P["tagBorder"]
    tag_ink, ink, sub_a = P["tagInk"], P["ink"], P["subAlpha"]
    txt = [
        f'<rect id="Плашка-фон" x="{n(p["x"])}" y="{n(p["y"])}" width="{n(p["w"])}" height="{n(p["h"])}" '
        f'rx="{n(p["h"] / 2)}" fill="{tag_bg}" fill-opacity="{tag_bg_a}" stroke="{tag_br}" stroke-opacity="{tag_br_a}" stroke-width="1.5"/>',
        f'<text id="Плашка-текст" x="{n(tag["x"])}" y="{n(tag["y"])}" font-family="Rubik Mono One" '
        f'font-size="{M.TAG["size"]}" letter-spacing="{M.TAG["track"]}" fill="{tag_ink}">{esc(slide["tag"])}</text>',
    ]
    for i, (line, box) in enumerate(zip(slide["title"].split("\n"), geo["h1"]), 1):
        txt.append(
            f'<text id="Заголовок-{i}" x="{n(box["x"])}" y="{n(box["y"])}" font-family="Inter" font-weight="800" '
            f'font-size="{M.H1["size"]}" letter-spacing="{M.H1["track"]}" fill="{ink}">{esc(line)}</text>'
        )
    defs.append(
        '<linearGradient id="gRule" x1="0" y1="0" x2="1" y2="0">'
        '<stop offset="0" stop-color="#E85A2A"/><stop offset="1" stop-color="#FFB347"/></linearGradient>'
    )
    ru = geo["rule"]
    txt.append(
        f'<rect id="Линейка" x="{n(ru["x"])}" y="{n(ru["y"])}" width="{M.RULE["w"]}" height="{M.RULE["h"]}" '
        f'rx="{M.RULE["h"] / 2}" fill="url(#gRule)"/>'
    )
    for i, (line, box) in enumerate(zip(slide["sub"].split("\n"), geo["sub"]), 1):
        txt.append(
            f'<text id="Подпись-{i}" x="{n(box["x"])}" y="{n(box["y"])}" font-family="Inter" font-weight="500" '
            f'font-size="{M.SUB["size"]}" letter-spacing="{M.SUB["track"]}" fill="{ink}" fill-opacity="{sub_a}">{esc(line)}</text>'
        )
    body.append('<g id="Текст">' + "".join(txt) + "</g>")

    # ── мокап ──────────────────────────────────────────────────────────
    defs.append(
        '<radialGradient id="gShadow">'
        '<stop offset="0" stop-color="#030614" stop-opacity=".55"/>'
        '<stop offset="1" stop-color="#030614" stop-opacity="0"/></radialGradient>'
    )
    bx1, by1, bx2, by2 = css_angle_line(152, frame_w, frame_h)
    defs.append(
        f'<linearGradient id="gBody" gradientUnits="userSpaceOnUse" x1="{n(phone_x + bx1)}" y1="{n(B.PHONE_TOP + by1)}" '
        f'x2="{n(phone_x + bx2)}" y2="{n(B.PHONE_TOP + by2)}">'
        '<stop offset="0" stop-color="#6B7288"/><stop offset=".20" stop-color="#0C1020"/>'
        '<stop offset=".52" stop-color="#05070F"/><stop offset=".78" stop-color="#0C1020"/>'
        '<stop offset="1" stop-color="#565D72"/></linearGradient>'
    )
    hx1, hy1, hx2, hy2 = css_angle_line(202, frame_w, frame_h)
    defs.append(
        f'<linearGradient id="gGloss" gradientUnits="userSpaceOnUse" x1="{n(phone_x + hx1)}" y1="{n(B.PHONE_TOP + hy1)}" '
        f'x2="{n(phone_x + hx2)}" y2="{n(B.PHONE_TOP + hy2)}">'
        '<stop offset="0" stop-color="#fff" stop-opacity=".18"/>'
        '<stop offset=".24" stop-color="#fff" stop-opacity="0"/>'
        '<stop offset=".76" stop-color="#fff" stop-opacity="0"/>'
        '<stop offset="1" stop-color="#fff" stop-opacity=".10"/></linearGradient>'
    )
    screen_x, screen_y = phone_x + B.BEZEL, B.PHONE_TOP + B.BEZEL
    defs.append(
        f'<clipPath id="clipScreen"><rect x="{n(screen_x)}" y="{n(screen_y)}" width="{sw}" height="{sh}" rx="75"/></clipPath>'
    )
    body.append(
        '<g id="Мокап">'
        f'<ellipse id="Тень" cx="645" cy="{n(B.PHONE_TOP + frame_h - 30)}" rx="{n(frame_w * .62)}" ry="130" fill="url(#gShadow)"/>'
        f'<rect id="Корпус" x="{n(phone_x)}" y="{B.PHONE_TOP}" width="{frame_w}" height="{frame_h}" rx="86" '
        'fill="url(#gBody)" stroke="#FFFFFF" stroke-opacity=".18" stroke-width="1.5"/>'
        f'<g id="Экран-вставить-скриншот" clip-path="url(#clipScreen)">'
        f'<rect x="{n(screen_x)}" y="{n(screen_y)}" width="{sw}" height="{sh}" fill="#05070F"/>'
        f'<image href="../src/{slide["shot"]}" x="{n(screen_x)}" y="{n(screen_y)}" width="{sw}" height="{sh}"/>'
        "</g>"
        f'<rect id="Блик" x="{n(phone_x)}" y="{B.PHONE_TOP}" width="{frame_w}" height="{frame_h}" rx="86" fill="url(#gGloss)"/>'
        "</g>"
    )

    mw = B.MASCOT_W
    mh = round(mw * 2322 / 2322)
    body.append(
        f'<image id="Маскот" href="../../Logo/Статика/Vert_vpose1.png" '
        f'x="-52" y="{n(B.H + 8 - mh)}" width="{mw}" height="{mh}"/>'
    )

    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{B.W}" height="{B.H}" '
        f'viewBox="0 0 {B.W} {B.H}" fill="none">\n'
        "<defs>" + "".join(defs) + "</defs>\n" + "\n".join(body) + "\n</svg>\n"
    )


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for slide in B.SLIDES:
        if not (B.SRC / slide["shot"]).exists():
            print(f"— {slide['slug']}: нет src/{slide['shot']}, пропускаю")
            continue
        out = OUT / f"{slide['slug']}.svg"
        out.write_text(build(slide), encoding="utf-8")
        print(f"✓ {out.relative_to(B.REPO)}  {out.stat().st_size // 1024} КБ")


if __name__ == "__main__":
    main()
