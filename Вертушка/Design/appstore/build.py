#!/usr/bin/env python3
"""App Store скриншоты Вертушки.

Собирает кадры 1290x2796 (слот 6.7"/6.9"): фирменный кобальт-градиент из
Mobile/constants/theme.ts (T.gradients.brand + accent.ember) и мокап iPhone
с реальным скриншотом приложения.

    python3 Design/appstore/build.py

Исходники — Design/appstore/src/*.png (полноразмерные скриншоты 1179x2556).
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
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"

W, H = 1290, 2796
SCREEN_W = 840          # ширина экрана внутри мокапа
BEZEL = 12              # рамка корпуса
PHONE_TOP = 790

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
        # холодная кобальтовая волна: у сканера сиреневые уголки рамки
        "glow": "radial-gradient(1200px 1000px at 86% 0%, rgba(139,160,250,.88), transparent 62%),"
                "radial-gradient(1050px 950px at -10% 26%, rgba(58,96,236,.72), transparent 62%)",
        "ember": "rgba(255,158,104,.90),rgba(226,86,48,.40) 48%",
    },
    {
        "slug": "02-market",
        "shot": "market.png",
        "tag": "МАРКЕТ",
        "title": "Весь винил магазинов\nв одном поиске",
        "sub": "33 000 пластинок в наличии прямо сейчас —\nактуальные цены из магазинов.",
        # ember по низу — как на самом экране Маркета
        "glow": "radial-gradient(1150px 950px at 92% 0%, rgba(124,150,248,.86), transparent 62%),"
                "radial-gradient(1020px 920px at -10% 24%, rgba(48,84,226,.72), transparent 60%)",
        "ember": "rgba(255,148,78,.96),rgba(226,86,48,.50) 48%",
    },
    {
        "slug": "03-value",
        "shot": "value.png",
        "tag": "ОЦЕНКА",
        "title": "Сколько стоит\nтвоя полка",
        "sub": "Показываем топ самых дорогих\nпластинок из твоей коллекции.",
        # фиолетово-розовая нота: карточка оценки на экране такая же
        "glow": "radial-gradient(1200px 980px at 90% 0%, rgba(162,132,250,.86), transparent 62%),"
                "radial-gradient(1040px 940px at -10% 28%, rgba(58,96,236,.70), transparent 62%)",
        "ember": "rgba(255,164,146,.92),rgba(214,96,150,.46) 48%",
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


def prepare_shot(name: str) -> pathlib.Path:
    """Ресайз скриншота ровно под ширину экрана мокапа (1:1, без апскейла в браузере)."""
    SHOTS.mkdir(parents=True, exist_ok=True)
    out = SHOTS / name
    subprocess.run(
        ["sips", "--resampleWidth", str(SCREEN_W), str(SRC / name), "--out", str(out)],
        check=True, capture_output=True,
    )
    return out


# лёгкое зерно поверх градиента — снимает бандинг на больших заливках
NOISE = (
    "data:image/svg+xml;utf8,"
    "<svg xmlns='http://www.w3.org/2000/svg' width='240' height='240'>"
    "<filter id='n'><feTurbulence type='fractalNoise' baseFrequency='0.9' numOctaves='3'/></filter>"
    "<rect width='240' height='240' filter='url(%23n)' opacity='0.5'/></svg>"
)


def html_for(slide: dict, faces: str) -> str:
    shot_path = prepare_shot(slide["shot"])
    sw, sh = png_size(shot_path)
    frame_w, frame_h = sw + BEZEL * 2, sh + BEZEL * 2
    ember_top = PHONE_TOP + frame_h - 300
    shot = data_uri(shot_path, "image/png")
    return f"""<meta charset="utf-8">
<style>
{faces}
*{{margin:0;padding:0;box-sizing:border-box}}
html,body{{width:{W}px;height:{H}px;overflow:hidden;background:#0B1438}}
.stage{{position:relative;width:{W}px;height:{H}px;overflow:hidden;
  background:{slide['glow']},
    linear-gradient(172deg,#122159 0%,#1C3688 32%,#2E51DE 70%,#1E3490 100%);
  font-family:'Inter500',-apple-system,sans-serif;-webkit-font-smoothing:antialiased}}

/* канавки пластинки — фирменный элемент T.grooves */
.grooves{{position:absolute;width:1700px;height:1700px;right:-560px;top:-420px;border-radius:50%;
  background:repeating-radial-gradient(circle,rgba(255,255,255,.30) 0 1.5px,transparent 1.5px 17px);
  -webkit-mask-image:radial-gradient(circle,#000 30%,rgba(0,0,0,.35) 60%,transparent 76%);opacity:.55}}
.vignette{{position:absolute;inset:0;
  background:radial-gradient(130% 82% at 50% 46%,transparent 56%,rgba(5,8,26,.38) 100%)}}
.ember{{position:absolute;left:50%;transform:translateX(-50%);top:{ember_top}px;
  width:1420px;height:660px;border-radius:50%;filter:blur(30px);
  background:radial-gradient(closest-side,{slide["ember"]},transparent 78%)}}
.noise{{position:absolute;inset:0;background-image:url("{NOISE}");background-size:240px;
  opacity:.055;mix-blend-mode:overlay}}
/* тёплое свечение под мокапом — отрывает корпус от фона */
.halo{{position:absolute;left:50%;transform:translateX(-50%);top:{PHONE_TOP - 130}px;
  width:1120px;height:900px;border-radius:50%;
  background:radial-gradient(closest-side,rgba(140,170,255,.30),transparent 70%);filter:blur(30px)}}

.copy{{position:absolute;left:96px;right:96px;top:124px}}
.tag{{display:inline-block;font-family:'RubikMonoOne';font-size:23px;letter-spacing:4.5px;
  color:#FFD9C8;padding:15px 28px 12px;border-radius:999px;
  background:rgba(232,90,42,.22);border:1.5px solid rgba(255,169,132,.45);
  box-shadow:0 0 40px rgba(232,90,42,.30)}}
h1{{margin-top:36px;font-family:'Inter800';font-size:86px;line-height:95px;letter-spacing:-2.6px;
  color:#fff;white-space:pre-line;text-shadow:0 8px 44px rgba(5,9,28,.45)}}
.rule{{margin-top:32px;width:128px;height:7px;border-radius:99px;
  background:linear-gradient(90deg,#E85A2A,#FFB347);box-shadow:0 0 26px rgba(232,90,42,.55)}}
p{{margin-top:34px;font-size:46px;line-height:62px;letter-spacing:-.4px;white-space:pre-line;
  color:rgba(255,255,255,.80)}}

/* мокап iPhone */
.phone{{position:absolute;left:50%;transform:translateX(-50%);top:{PHONE_TOP}px;
  width:{frame_w}px;height:{frame_h}px;padding:{BEZEL}px;border-radius:86px;
  background:linear-gradient(152deg,#6B7288 0%,#0C1020 20%,#05070F 52%,#0C1020 78%,#565D72 100%);
  box-shadow:0 64px 140px rgba(3,6,20,.66),0 20px 48px rgba(3,6,20,.45),
             inset 0 0 0 1.5px rgba(255,255,255,.18)}}
.phone::after{{content:'';position:absolute;inset:0;border-radius:86px;pointer-events:none;
  background:linear-gradient(202deg,rgba(255,255,255,.18) 0%,transparent 24%,
             transparent 76%,rgba(255,255,255,.10) 100%)}}
.screen{{width:100%;height:100%;border-radius:75px;overflow:hidden;background:#000;
  box-shadow:inset 0 0 0 1px rgba(255,255,255,.12)}}
.screen img{{display:block;width:100%;height:100%}}
</style>
<div class="stage">
  <div class="grooves"></div>
  <div class="vignette"></div>
  <div class="ember"></div>
  <div class="halo"></div>
  <div class="noise"></div>
  <div class="copy">
    <span class="tag">{slide['tag']}</span>
    <h1>{slide['title']}</h1>
    <div class="rule"></div>
    <p>{slide['sub']}</p>
  </div>
  <div class="phone"><div class="screen"><img src="{shot}"></div></div>
</div>"""


def main() -> None:
    EXPORT.mkdir(parents=True, exist_ok=True)
    faces = font_faces()
    for slide in SLIDES:
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
