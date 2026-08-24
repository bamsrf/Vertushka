#!/usr/bin/env python3
"""Генератор пина OG1 «Первая сотня» — маскот поднимает над головой 100.

Геометрия описана один раз, а обводки (легендарный ободок → тёмный контур →
золотой кант → эмаль) раскладываются по проходам автоматически: руками такое
дублировать — гарантированно разъехаться.

    python3 gen_og1.py Mobile/assets/achievements/pins/OG1_first_hundred.svg
"""
import pathlib, sys

NAVY, GOLD, IVORY, COBALT, PINK = "#0B1438", "url(#g)", "#FBF5EA", "#2A4BD7", "#E89AC0"

HEAD = (50, 52, 20)          # cx, cy, r

# трубки-конечности: путь + толщина эмали
TUBES = [
    ('d="M41 40 L32 24"', 5.8),                          # рука левая
    ('d="M59 40 L68 24"', 5.8),                          # рука правая
    ('d="M46 72 C45 79 44 83 43.5 86.5"', 5.6),          # опорная нога
    ('d="M55.5 72 C63 76 69 76.5 74.5 72.5"', 5.6),      # нога в замахе
]

# кроссовок в локальных координатах: подошва по y=0, носок вправо
SHOE = ('M-9 -0.5 C-9 -5.5 -5.5 -8.5 -0.5 -8.5 C5 -8.5 9 -5 9 -1 '
        'C9 1.6 7.4 2.6 4 2.6 L-6 2.6 C-8 2.6 -9 1.6 -9 -0.5 Z')
SHOE_SOLE = 'M-8.7 0.4 L8.8 -0.6'
SHOE_TRIM = 'M-4.6 -7.4 C-2 -4.4 1.4 -2.4 5.6 -1.8'
SHOES = ["translate(43.5,88.5)", "translate(80.5,68.5) rotate(-36)"]

# цифры: «1» из двух штрихов, нули — обведённые скругления
DIGIT_LINES = ['d="M32.4 8.8 L36.2 5.2 L36.2 17.4"']
DIGIT_RINGS = ['x="47.5" y="6.4" width="5" height="9.2" rx="2.5"',
               'x="60.5" y="6.4" width="5" height="9.2" rx="2.5"']
HANDS = [(30, 21.5), (70, 21.5)]
SPARKS = [(15, 32, 1.15), (86, 50, 1.0), (20, 80, .85)]


def tube_pass(width_add, color, cap="round"):
    return [f'    <path {d} fill="none" stroke="{color}" stroke-width="{w + width_add:g}" '
            f'stroke-linecap="{cap}"></path>' for d, w in TUBES]


def main() -> None:
    cx, cy, r = HEAD
    L, A = [], None
    A = L.append
    A('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100" overflow="visible">')
    A('  <defs>')
    A('    <linearGradient id="g" x1="0" y1="0" x2="0" y2="1">')
    A('      <stop offset="0" stop-color="#F2C770"></stop>')
    A('      <stop offset=".5" stop-color="#D9A84E"></stop>')
    A('      <stop offset="1" stop-color="#A87E32"></stop>')
    A('    </linearGradient>')
    A('    <path id="spark" d="M0 -3.4 Q.6 -.6 3.4 0 Q.6 .6 0 3.4 Q-.6 .6 -3.4 0 Q-.6 -.6 0 -3.4 Z"></path>')
    A('    <g id="shoe">')
    A(f'      <path d="{SHOE}" fill="{IVORY}" stroke="{NAVY}" stroke-width="3.2" stroke-linejoin="round"></path>')
    A(f'      <path d="{SHOE}" fill="none" stroke="{GOLD}" stroke-width="1.7" stroke-linejoin="round"></path>')
    A(f'      <path d="{SHOE_SOLE}" fill="none" stroke="{COBALT}" stroke-width="2.4" stroke-linecap="round"></path>')
    A(f'      <path d="{SHOE_TRIM}" fill="none" stroke="{COBALT}" stroke-width="1.8" stroke-linecap="round"></path>')
    A('    </g>')
    A('    <g id="shoe-rim">')
    A(f'      <path d="{SHOE}" fill="none" stroke="{GOLD}" stroke-width="5" stroke-linejoin="round"></path>')
    A('    </g>')
    A('  </defs>')
    A('')

    # ── легендарный ободок: золото по всему силуэту ──────────────────
    A('  <g id="legend-rim">')
    A(f'    <circle cx="{cx}" cy="{cy}" r="{r + 2.6}" fill="none" stroke="{GOLD}" stroke-width="1.6" '
      f'stroke-opacity=".9"></circle>')
    A('  </g>')
    A('')

    # ── руки и ноги ─────────────────────────────────────────────────
    A('  <g id="limbs">')
    L.extend(tube_pass(3.2, NAVY))
    L.extend(tube_pass(1.7, GOLD))
    L.extend(tube_pass(0, COBALT))
    A('  </g>')
    A('')

    A('  <g id="shoes">')
    for t in SHOES:
        A(f'    <use href="#shoe" transform="{t}"></use>')
    A('  </g>')
    A('')

    # ── голова-пластинка ────────────────────────────────────────────
    A('  <g id="head">')
    A(f'    <circle cx="{cx}" cy="{cy}" r="{r}" fill="{IVORY}" stroke="{NAVY}" stroke-width="3.2"></circle>')
    A(f'    <circle cx="{cx}" cy="{cy}" r="{r}" fill="none" stroke="{GOLD}" stroke-width="1.7"></circle>')
    for gr in (16, 13, 10):
        A(f'    <circle cx="{cx}" cy="{cy}" r="{gr}" fill="none" stroke="#D9A84E" '
          f'stroke-width=".5" stroke-opacity=".6"></circle>')
    A(f'    <path d="M35 45 A17 17 0 0 1 44 35.5" fill="none" stroke="#FFF" stroke-width="1.6" '
      f'stroke-opacity=".85" stroke-linecap="round"></path>')
    A('  </g>')
    A('')

    # ── лицо ────────────────────────────────────────────────────────
    A('  <g id="face">')
    A(f'    <circle cx="38.5" cy="57.5" r="3.2" fill="{PINK}"></circle>')
    A(f'    <circle cx="61.5" cy="57.5" r="3.2" fill="{PINK}"></circle>')
    A(f'    <path d="M39.4 50 A4.2 4.2 0 0 0 47.8 50 Z" fill="{NAVY}"></path>')
    A(f'    <path d="M52.2 50 A4.2 4.2 0 0 0 60.6 50 Z" fill="{NAVY}"></path>')
    A(f'    <path d="M38 44.4 L47.4 47.6" fill="none" stroke="{NAVY}" stroke-width="2.5" stroke-linecap="round"></path>')
    A(f'    <path d="M62 44.4 L52.6 47.6" fill="none" stroke="{NAVY}" stroke-width="2.5" stroke-linecap="round"></path>')
    A(f'    <circle cx="{cx}" cy="54.6" r="1.6" fill="{NAVY}"></circle>')
    A(f'    <path d="M46 60.4 Q50 63.8 54 60.4" fill="none" stroke="{NAVY}" stroke-width="1.9" stroke-linecap="round"></path>')
    A('  </g>')
    A('')

    # ── тонарм-визор ────────────────────────────────────────────────
    A('  <g id="tonearm">')
    for w, col in ((5.2, NAVY), (2.9, GOLD)):
        A(f'    <path d="M74 34.5 L41.5 42.5" fill="none" stroke="{col}" stroke-width="{w}" stroke-linecap="round"></path>')
    for w, col in ((8.6, NAVY), (6, GOLD)):
        A(f'    <path d="M43 41.5 L40 42.3" fill="none" stroke="{col}" stroke-width="{w}" stroke-linecap="round"></path>')
    A('  </g>')
    A('')

    # ── цифры 100 ───────────────────────────────────────────────────
    A('  <g id="numeral" stroke-linecap="round" stroke-linejoin="round">')
    for w, col in ((9.2, NAVY), (6, GOLD)):
        for d in DIGIT_LINES:
            A(f'    <path {d} fill="none" stroke="{col}" stroke-width="{w}"></path>')
        for z in DIGIT_RINGS:
            A(f'    <rect {z} fill="none" stroke="{col}" stroke-width="{w}"></rect>')
    A('  </g>')
    A('')

    # ── ладони-шарики поверх цифр ───────────────────────────────────
    A('  <g id="hands">')
    for hx, hy in HANDS:
        A(f'    <circle cx="{hx}" cy="{hy}" r="5.2" fill="{COBALT}" stroke="{NAVY}" stroke-width="3.2"></circle>')
        A(f'    <circle cx="{hx}" cy="{hy}" r="5.2" fill="none" stroke="{GOLD}" stroke-width="1.7"></circle>')
        A(f'    <path d="M{hx - 3.2} {hy - 2.4} A3.9 3.9 0 0 1 {hx - .4} {hy - 4.5}" fill="none" '
          f'stroke="#FFF" stroke-width="1.1" stroke-opacity=".6" stroke-linecap="round"></path>')
    A('  </g>')
    A('')

    A('  <g id="sparkles" fill="url(#g)">')
    for x, y, s in SPARKS:
        A(f'    <use href="#spark" transform="translate({x},{y}) scale({s})"></use>')
    A('  </g>')
    A('</svg>')

    out = pathlib.Path(sys.argv[1])
    out.write_text("\n".join(L) + "\n", encoding="utf-8")
    print(f"✓ {out}  {out.stat().st_size} Б")


if __name__ == "__main__":
    main()
