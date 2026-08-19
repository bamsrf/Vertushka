#!/usr/bin/env python3
"""Замер геометрии текста в кадре.

SVG-экспорт должен лечь ровно на PNG, а в SVG нет ни line-height, ни padding —
только абсолютные координаты и бейзлайны. Поэтому текстовый блок рендерится тем
же Chrome с теми же шрифтами, и позиции снимаются из DOM, а не считаются на глаз.
"""
from __future__ import annotations

import json
import re
import subprocess

import build as B

# те же метрики, что в CSS build.py; расхождение ловим ассертом ниже
TAG = {"size": 23, "track": 4.5, "padTop": 15, "padRight": 28, "padBottom": 12, "font": "RubikMonoOne"}
H1 = {"size": 86, "line": 95, "track": -2.6, "top": 36, "font": "Inter800"}
RULE = {"top": 32, "w": 128, "h": 7}
SUB = {"size": 46, "line": 62, "track": -0.4, "top": 34, "font": "Inter500"}
COPY_LEFT, COPY_TOP = 96, 124


def _css_num(v: float) -> str:
    """CSS пишет -.4px, а не -0.4px — приводим к тому же виду для сверки."""
    t = f"{v:g}"
    return t.replace("0.", ".").replace("-.0", "-.") if t.startswith(("0.", "-0.")) else t


def _assert_css_in_sync() -> None:
    """CSS живёт в build.py — если там поменяли кегль, замеры молча разъедутся."""
    css = (B.ROOT / "build.py").read_text()
    for probe in (
        f"font-size:{TAG['size']}px;letter-spacing:{_css_num(TAG['track'])}px",
        f"font-size:{H1['size']}px;line-height:{H1['line']}px;letter-spacing:{_css_num(H1['track'])}px",
        f"font-size:{SUB['size']}px;line-height:{SUB['line']}px;letter-spacing:{_css_num(SUB['track'])}px",
        f"left:{COPY_LEFT}px;right:{COPY_LEFT}px;top:{COPY_TOP}px",
    ):
        if probe not in css:
            raise SystemExit(f"measure.py разошёлся с CSS в build.py: не нашёл «{probe}»")


def measure(slide: dict) -> dict:
    """Отдаёт для плашки и каждой строки абсолютные x/y бейзлайна и ширину."""
    faces = B.font_faces()
    lines_h1 = slide["title"].split("\n")
    lines_sub = slide["sub"].split("\n")
    spans_h1 = "".join(f'<span class="ln">{l}</span>' for l in lines_h1)
    spans_sub = "".join(f'<span class="ln">{l}</span>' for l in lines_sub)
    page = f"""<meta charset="utf-8"><style>
{faces}
*{{margin:0;padding:0;box-sizing:border-box}}
body{{width:{B.W}px;height:{B.H}px}}
.copy{{position:absolute;left:{COPY_LEFT}px;right:{COPY_LEFT}px;top:{COPY_TOP}px}}
.tag{{display:inline-block;font-family:'{TAG['font']}';font-size:{TAG['size']}px;
  letter-spacing:{TAG['track']}px;padding:{TAG['padTop']}px {TAG['padRight']}px {TAG['padBottom']}px;
  border:1.5px solid #000}}
h1{{margin-top:{H1['top']}px;font-family:'{H1['font']}';font-size:{H1['size']}px;
  line-height:{H1['line']}px;letter-spacing:{H1['track']}px}}
.rule{{margin-top:{RULE['top']}px;width:{RULE['w']}px;height:{RULE['h']}px}}
p{{margin-top:{SUB['top']}px;font-family:'{SUB['font']}';font-size:{SUB['size']}px;
  line-height:{SUB['line']}px;letter-spacing:{SUB['track']}px}}
.ln{{display:block;width:max-content}}
.tag .ln{{display:inline-block}}
</style>
<div class="copy">
  <span class="tag" id="tag"><span class="ln">{slide['tag']}</span></span>
  <h1 id="h1">{spans_h1}</h1>
  <div class="rule" id="rule"></div>
  <p id="sub">{spans_sub}</p>
</div>
<div id="out"></div>
<script>
const cv = document.createElement('canvas').getContext('2d');
// бейзлайн = верх бокса + (высота бокса - высота шрифта)/2 + ascent
function metrics(el, size, font) {{
  const b = el.getBoundingClientRect();
  cv.font = size + "px '" + font + "'";
  const m = cv.measureText('Ag');
  const asc = m.fontBoundingBoxAscent, desc = m.fontBoundingBoxDescent;
  return {{x: b.left, y: b.top + (b.height - (asc + desc)) / 2 + asc, w: b.width}};
}}
function lines(sel, size, font) {{
  return [...document.querySelectorAll(sel + ' .ln')].map(el => metrics(el, size, font));
}}
const tb = document.getElementById('tag').getBoundingClientRect();
const rb = document.getElementById('rule').getBoundingClientRect();
document.getElementById('out').textContent = JSON.stringify({{
  pill: {{x: tb.left, y: tb.top, w: tb.width, h: tb.height}},
  tag: metrics(document.querySelector('#tag .ln'), {TAG['size']}, '{TAG['font']}'),
  rule: {{x: rb.left, y: rb.top}},
  h1: lines('#h1', {H1['size']}, '{H1['font']}'),
  sub: lines('#sub', {SUB['size']}, '{SUB['font']}'),
}});
</script>"""
    tmp = B.EXPORT / "_measure.html"
    tmp.parent.mkdir(parents=True, exist_ok=True)
    tmp.write_text(page, encoding="utf-8")
    dom = subprocess.run(
        [B.CHROME, "--headless=new", "--disable-gpu", "--hide-scrollbars",
         f"--window-size={B.W},{B.H}", "--virtual-time-budget=2000", "--dump-dom", str(tmp)],
        check=True, capture_output=True, text=True,
    ).stdout
    tmp.unlink()
    m = re.search(r'<div id="out">(.*?)</div>', dom, re.S)
    if not m:
        raise SystemExit("не удалось снять замеры из DOM")
    return json.loads(m.group(1))


_assert_css_in_sync()

if __name__ == "__main__":
    for s in B.SLIDES:
        print(s["slug"], json.dumps(measure(s), ensure_ascii=False))
