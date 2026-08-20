#!/usr/bin/env python3
"""App Store скриншоты Вертушки.

Собирает кадры 1290x2796 (слот 6.7"/6.9"): светлый фирменный градиент из
Mobile/constants/theme.ts (light-палитра T.gradients.onboarding — кобальт, розовый,
ember) и мокап iPhone с реальным скриншотом приложения.

    python3 Design/appstore/build.py

Исходники — Design/appstore/src/*.png (полноразмерные скриншоты 1179x2556).
Кадры без исходника пропускаются с предупреждением.
Результат — Design/appstore/export/*.png.
"""
from __future__ import annotations

import base64
import pathlib
import struct
import subprocess

ROOT = pathlib.Path(__file__).resolve().parent
REPO = ROOT.parent.parent
SRC = ROOT / "src"
EXPORT = ROOT / "export"
SHOTS = EXPORT / "_shots"
MASCOT = REPO / "Design/Logo/Статика/Vert_vpose1.png"
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"

W, H = 1290, 2796
SCREEN_W = 840          # ширина экрана внутри мокапа
BEZEL = 12              # рамка корпуса
PHONE_TOP = 790
MASCOT_W = 545          # маскот у нижнего левого угла мокапа

# ── палитра ───────────────────────────────────────────────────────────
# Светлая гамма приложения, а не тёмный мир Маркета. Значения — из light-веток
# theme.ts: bg.base, brand.cobalt/cobaltSoft, accent.ember, розовый из
# T.gradients.onboarding.light. Отсюда же берёт цвета build_svg.py.
PALETTE = {
    "angle": 168,
    "stops": [(0.0, "#FBFAF8"), (0.42, "#F1F4FC"), (1.0, "#E2E9FB")],
    "ink": "#0B1438",           # заголовок
    "subAlpha": 0.64,           # подпись — тот же ink, но мягче
    "groove": "#2A4BD7",
    "grooveAlpha": 0.16,
    "grooveGroup": 0.55,
    "vignette": ("#0B1438", 0.09),
    "halo": ("#5C7AE8", 0.26),
    "tagInk": "#B8431B",
    "tagBg": ("#E85A2A", 0.12),
    "tagBorder": ("#E85A2A", 0.34),
    "shadow": ("#0B1438", 0.30),
}


def rgba(spec: tuple[str, float]) -> str:
    """('#0B1438', .3) -> 'rgba(11,20,56,0.3)'"""
    hexed, a = spec
    r, g, b = (int(hexed[i:i + 2], 16) for i in (1, 3, 5))
    return f"rgba({r},{g},{b},{a})"


FONTS = {
    "RubikMonoOne": REPO / "Mobile/assets/fonts/RubikMonoOne-Regular.ttf",
    "Inter800": REPO / "Mobile/node_modules/@expo-google-fonts/inter/800ExtraBold/Inter_800ExtraBold.ttf",
    "Inter600": REPO / "Mobile/node_modules/@expo-google-fonts/inter/600SemiBold/Inter_600SemiBold.ttf",
    "Inter500": REPO / "Mobile/node_modules/@expo-google-fonts/inter/500Medium/Inter_500Medium.ttf",
}

SLIDES = [
    {
        "slug": "01-scan",
        "shot": "scan.png",
        "tag": "СКАНЕР",
        "title": "Наведи камеру —\nи она в коллекции",
        "sub": "Штрихкод или обложка — узнаём релиз\nпо базе Discogs за пару секунд.",
        "glow": "radial-gradient(1200px 1000px at 86% 0%, rgba(92,122,232,.66), transparent 62%),"
                "radial-gradient(1050px 950px at -10% 26%, rgba(42,75,215,.38), transparent 62%)",
        "pool": "rgba(232,180,192,.60),rgba(232,90,42,.16) 48%",
    },
    {
        "slug": "02-market",
        "shot": "market.png",
        "tag": "МАРКЕТ",
        "title": "Весь винил магазинов\nв одном поиске",
        "sub": "33 000 пластинок в наличии прямо сейчас —\nактуальные цены из магазинов.",
        "glow": "radial-gradient(1150px 950px at 92% 0%, rgba(92,122,232,.68), transparent 62%),"
                "radial-gradient(1020px 920px at -10% 24%, rgba(42,75,215,.40), transparent 60%)",
        "pool": "rgba(255,164,120,.58),rgba(232,90,42,.18) 48%",
    },
    {
        "slug": "03-value",
        "shot": "value.png",
        "tag": "ОЦЕНКА",
        "title": "Сколько стоит\nтвоя полка",
        "sub": "Показываем топ самых дорогих\nпластинок из твоей коллекции.",
        "glow": "radial-gradient(1200px 980px at 90% 0%, rgba(150,124,240,.64), transparent 62%),"
                "radial-gradient(1040px 940px at -10% 28%, rgba(42,75,215,.38), transparent 62%)",
        "pool": "rgba(232,180,192,.66),rgba(150,124,240,.20) 48%",
        "mascot": True,
    },
    {
        "slug": "04-collection",
        "shot": "collection.png",
        "tag": "КОЛЛЕКЦИЯ",
        "title": "Следи и пополняй\nсвой каталог",
        "sub": "Сохраняй свои релизы, сортируй\nпо папкам, веди вишлист.",
        "glow": "radial-gradient(1180px 980px at 88% 0%, rgba(92,122,232,.66), transparent 62%),"
                "radial-gradient(1020px 920px at -10% 26%, rgba(232,180,192,.54), transparent 60%)",
        "pool": "rgba(92,122,232,.52),rgba(232,180,192,.24) 48%",
    },
    {
        "slug": "05-achievements",
        "shot": "achievements.png",
        "tag": "АЧИВКИ",
        "title": "Собирай по пути\nачивки",
        "sub": "Пасхалки найти труднее всего.",
        "glow": "radial-gradient(1180px 980px at 90% 0%, rgba(255,179,71,.56), transparent 62%),"
                "radial-gradient(1040px 940px at -10% 26%, rgba(42,75,215,.40), transparent 62%)",
        "pool": "rgba(255,164,120,.60),rgba(232,90,42,.18) 48%",
    },
    {
        "slug": "06-radar",
        "shot": "radar.png",
        "tag": "РАДАР",
        "title": "Сообщим, как в магазине\nпоявится твоя пластинка",
        "sub": "Радар следит за твоим вишлистом\nи отталкивается от желаемой цены.",
        "glow": "radial-gradient(1200px 1000px at 88% 0%, rgba(150,124,240,.66), transparent 62%),"
                "radial-gradient(1050px 950px at -10% 26%, rgba(42,75,215,.56), transparent 62%)",
        "pool": "rgba(150,124,240,.56),rgba(92,122,232,.22) 48%",
    },
]


def png_size(path: pathlib.Path) -> tuple[int, int]:
    head = path.read_bytes()[16:24]
    return struct.unpack(">II", head)


def data_uri(path: pathlib.Path, mime: str) -> str:
    return f"data:{mime};base64,{base64.b64encode(path.read_bytes()).decode()}"


def font_faces() -> str:
    return "\n".join(
        f"@font-face{{font-family:'{name}';"
        f"src:url({data_uri(path, 'font/ttf')}) format('truetype');font-display:block;}}"
        for name, path in FONTS.items()
    )


def resample(src: pathlib.Path, width: int, name: str) -> pathlib.Path:
    """Ресайз ровно под ширину на макете — апскейла в браузере быть не должно."""
    SHOTS.mkdir(parents=True, exist_ok=True)
    out = SHOTS / name
    subprocess.run(["sips", "--resampleWidth", str(width), str(src), "--out", str(out)],
                   check=True, capture_output=True)
    return out


def base_gradient() -> str:
    stops = ",".join(f"{c} {int(p * 100)}%" for p, c in PALETTE["stops"])
    return f"linear-gradient({PALETTE['angle']}deg,{stops})"


def html_for(slide: dict, faces: str) -> str:
    shot_path = resample(SRC / slide["shot"], SCREEN_W, slide["shot"])
    sw, sh = png_size(shot_path)
    frame_w, frame_h = sw + BEZEL * 2, sh + BEZEL * 2
    pool_top = PHONE_TOP + frame_h - 300
    shot = data_uri(shot_path, "image/png")
    mascot = (
        f'<div class="mascot"><img src="{data_uri(resample(MASCOT, MASCOT_W, "mascot.png"), "image/png")}"></div>'
        if slide.get("mascot") else ""
    )
    P = PALETTE
    return f"""<meta charset="utf-8">
<style>
{faces}
*{{margin:0;padding:0;box-sizing:border-box}}
html,body{{width:{W}px;height:{H}px;overflow:hidden;background:{P['stops'][0][1]}}}
.stage{{position:relative;width:{W}px;height:{H}px;overflow:hidden;
  background:{slide['glow']},{base_gradient()};
  font-family:'Inter500',-apple-system,sans-serif;-webkit-font-smoothing:antialiased}}

/* канавки пластинки — фирменный элемент T.grooves */
.grooves{{position:absolute;width:1700px;height:1700px;right:-560px;top:-420px;border-radius:50%;
  background:repeating-radial-gradient(circle,{rgba((P['groove'], P['grooveAlpha']))} 0 1.5px,transparent 1.5px 17px);
  -webkit-mask-image:radial-gradient(circle,#000 30%,rgba(0,0,0,.35) 60%,transparent 76%);
  opacity:{P['grooveGroup']}}}
.vignette{{position:absolute;inset:0;
  background:radial-gradient(130% 82% at 50% 46%,transparent 56%,{rgba(P['vignette'])} 100%)}}
/* мягкое пятно у нижней грани корпуса — сажает мокап на фон */
.pool{{position:absolute;left:50%;transform:translateX(-50%);top:{pool_top}px;
  width:1420px;height:660px;border-radius:50%;filter:blur(30px);
  background:radial-gradient(closest-side,{slide['pool']},transparent 78%)}}
.halo{{position:absolute;left:50%;transform:translateX(-50%);top:{PHONE_TOP - 130}px;
  width:1120px;height:900px;border-radius:50%;filter:blur(30px);
  background:radial-gradient(closest-side,{rgba(P['halo'])},transparent 70%)}}

.copy{{position:absolute;left:96px;right:96px;top:124px}}
.tag{{display:inline-block;font-family:'RubikMonoOne';font-size:23px;letter-spacing:4.5px;
  color:{P['tagInk']};padding:15px 28px 12px;border-radius:999px;
  background:{rgba(P['tagBg'])};border:1.5px solid {rgba(P['tagBorder'])}}}
h1{{margin-top:36px;font-family:'Inter800';font-size:86px;line-height:95px;letter-spacing:-2.6px;
  color:{P['ink']};white-space:pre-line}}
.rule{{margin-top:32px;width:128px;height:7px;border-radius:99px;
  background:linear-gradient(90deg,#E85A2A,#FFB347)}}
p{{margin-top:34px;font-size:46px;line-height:62px;letter-spacing:-.4px;white-space:pre-line;
  color:{rgba((P['ink'], P['subAlpha']))}}}

/* мокап iPhone */
.phone{{position:absolute;left:50%;transform:translateX(-50%);top:{PHONE_TOP}px;
  width:{frame_w}px;height:{frame_h}px;padding:{BEZEL}px;border-radius:86px;
  background:linear-gradient(152deg,#6B7288 0%,#0C1020 20%,#05070F 52%,#0C1020 78%,#565D72 100%);
  box-shadow:0 64px 130px {rgba((P['ink'], P['shadow'][1]))},0 20px 48px {rgba((P['ink'], 0.20))},
             inset 0 0 0 1.5px rgba(255,255,255,.18)}}
.phone::after{{content:'';position:absolute;inset:0;border-radius:86px;pointer-events:none;
  background:linear-gradient(202deg,rgba(255,255,255,.18) 0%,transparent 24%,
             transparent 76%,rgba(255,255,255,.10) 100%)}}
.screen{{width:100%;height:100%;border-radius:75px;overflow:hidden;background:#000;
  box-shadow:inset 0 0 0 1px rgba(255,255,255,.12)}}
.screen img{{display:block;width:100%;height:100%}}

.mascot{{position:absolute;left:-52px;bottom:-8px;width:{MASCOT_W}px;
  filter:drop-shadow(0 26px 40px rgba(11,20,56,.28))}}
.mascot img{{display:block;width:100%}}
</style>
<div class="stage">
  <div class="grooves"></div>
  <div class="vignette"></div>
  <div class="halo"></div>
  <div class="pool"></div>
  <div class="copy">
    <span class="tag">{slide['tag']}</span>
    <h1>{slide['title']}</h1>
    <div class="rule"></div>
    <p>{slide['sub']}</p>
  </div>
  <div class="phone"><div class="screen"><img src="{shot}"></div></div>
  {mascot}
</div>"""


def main() -> None:
    EXPORT.mkdir(parents=True, exist_ok=True)
    faces = font_faces()
    for slide in SLIDES:
        if not (SRC / slide["shot"]).exists():
            print(f"— {slide['slug']}: нет src/{slide['shot']}, пропускаю")
            continue
        page = EXPORT / f"{slide['slug']}.html"
        out = EXPORT / f"{slide['slug']}.png"
        page.write_text(html_for(slide, faces), encoding="utf-8")
        subprocess.run(
            [CHROME, "--headless=new", "--disable-gpu", "--hide-scrollbars",
             "--force-device-scale-factor=1", f"--window-size={W},{H}",
             f"--screenshot={out}", str(page)],
            check=True, capture_output=True,
        )
        page.unlink()
        print(f"✓ {out.relative_to(REPO)}")


if __name__ == "__main__":
    main()
