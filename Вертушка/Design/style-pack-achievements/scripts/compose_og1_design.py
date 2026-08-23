#!/usr/bin/env python3
"""Подложка-эмаль для маскота «Первой сотни».

Остальные design-PNG — сами по себе эмалевые значки (форма арта = форма пина),
а маскот — персонаж на прозрачном фоне, в шите он «парил» без подложки.
Собираем как в стайл-паке: тёмный кант → золотое кольцо (вертикальный градиент,
как в gen_og1_pin.py) → эмаль слоновой кости → маскот.

    python3 compose_og1_design.py <mascot.png> <out.png>
"""
import sys

from PIL import Image, ImageDraw

SIZE = 512
NAVY = (11, 20, 56, 255)        # #0B1438
IVORY = (251, 245, 234, 255)    # #FBF5EA
GOLD_TOP = (242, 199, 112)      # #F2C770
GOLD_BOTTOM = (168, 126, 50)    # #A87E32

R_OUTER = 250      # тёмный кант
R_GOLD = 243       # золотое кольцо
R_ENAMEL = 224     # эмаль
R_PINLINE = 214    # тонкая золотая линия на эмали
MASCOT_BOX = 384   # сторона квадрата под маскота


def _circle(draw: ImageDraw.ImageDraw, r: int, fill) -> None:
    c = SIZE // 2
    draw.ellipse((c - r, c - r, c + r, c + r), fill=fill)


def _gold_gradient_disc(r: int) -> Image.Image:
    """Диск с вертикальным градиентом золота (маска-круг поверх градиента)."""
    grad = Image.new("RGBA", (SIZE, SIZE))
    for y in range(SIZE):
        t = y / (SIZE - 1)
        color = tuple(
            int(GOLD_TOP[i] + (GOLD_BOTTOM[i] - GOLD_TOP[i]) * t) for i in range(3)
        ) + (255,)
        ImageDraw.Draw(grad).line([(0, y), (SIZE, y)], fill=color)
    mask = Image.new("L", (SIZE, SIZE), 0)
    _circle(ImageDraw.Draw(mask), r, 255)
    disc = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    disc.paste(grad, (0, 0), mask)
    return disc


def main(mascot_path: str, out_path: str) -> None:
    canvas = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    draw = ImageDraw.Draw(canvas)

    _circle(draw, R_OUTER, NAVY)
    canvas.alpha_composite(_gold_gradient_disc(R_GOLD))
    draw = ImageDraw.Draw(canvas)
    _circle(draw, R_ENAMEL, IVORY)
    c = SIZE // 2
    draw.ellipse(
        (c - R_PINLINE, c - R_PINLINE, c + R_PINLINE, c + R_PINLINE),
        outline=tuple(int((GOLD_TOP[i] + GOLD_BOTTOM[i]) / 2) for i in range(3)) + (255,),
        width=4,
    )

    mascot = Image.open(mascot_path).convert("RGBA")
    mascot.thumbnail((MASCOT_BOX, MASCOT_BOX), Image.LANCZOS)
    x = (SIZE - mascot.width) // 2
    y = (SIZE - mascot.height) // 2
    canvas.alpha_composite(mascot, (x, y))

    canvas.save(out_path, "PNG", optimize=True)
    print(f"OK: {out_path} ({SIZE}×{SIZE})")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    main(sys.argv[1], sys.argv[2])
