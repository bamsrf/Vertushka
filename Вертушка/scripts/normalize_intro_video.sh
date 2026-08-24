#!/usr/bin/env bash
#
# Приводит фон интро-ролика маскота к цвету фона приложения (#FAFBFF).
#
# Зачем. MascotIntro показывает квадратное видео 960×960 «contain» поверх
# подложки — если фон кадров хоть на пару уровней отличается от подложки и от
# splash.backgroundColor, квадрат видео проступает прямоугольником, а переход
# «native splash → интро» читается как вспышка. Исходник от анимационной студии
# приезжает с фоном #FAFAFA, который вдобавок плавает по ходу ролика
# (#FEFEFE в первую секунду) из-за компрессии.
#
# Что делает. Все почти-белые пиксели (min(R,G,B) ≥ 248) прибиваются ровно к
# #FAFBFF; в зоне 235..248 — линейное подмешивание, чтобы на антиалиасинге
# контуров не появилось гало. Цветные пиксели (min канала < 235) не трогаются.
# После перекодирования край кадра декодируется ровно в #FAFBFF.
#
# Прогонять при КАЖДОЙ замене assets/video/intro-mascot.mp4 — иначе вернётся
# видимый квадрат. Проверка результата — в конце скрипта.
#
# Usage: scripts/normalize_intro_video.sh <input.mp4> [output.mp4]
set -euo pipefail

IN="${1:?укажи исходный mp4}"
OUT="${2:-${IN%.mp4}-normalized.mp4}"

# Целевой цвет = Colors.background из Mobile/constants/theme.ts и
# splash.backgroundColor из Mobile/app.json. Держать втроём в паре.
R=250 G=251 B=255
# Ниже LO пиксель не трогаем, выше HI — прибиваем к цели ровно.
LO=235 HI=248

W="clip((min(min(r(X,Y),g(X,Y)),b(X,Y))-${LO})/$((HI - LO)),0,1)"
FLATTEN="format=gbrp,geq=\
r='r(X,Y)+${W}*(${R}-r(X,Y))':\
g='g(X,Y)+${W}*(${G}-g(X,Y))':\
b='b(X,Y)+${W}*(${B}-b(X,Y))',format=yuv420p"

# Теги цвета намеренно не проставляем: исходник без них, а несимметричная
# пара «декод как одно, кодирование как другое» сдвинет фон на пару уровней.
# -an — у ролика нет звуковой дорожки и не должно быть (см. MascotIntro).
ffmpeg -v error -y -i "$IN" -vf "$FLATTEN" -an \
  -c:v libx264 -profile:v high -level 3.1 -preset slow -crf 19 \
  -pix_fmt yuv420p -movflags +faststart "$OUT"

echo "→ $OUT ($(du -h "$OUT" | cut -f1))"
echo "Цвет края по кадрам (должен быть fafbff):"
for t in 0.0 1.2 3.0 5.6; do
  printf '  t=%-4s ' "$t"
  ffmpeg -v error -ss "$t" -i "$OUT" -frames:v 1 \
    -vf "format=rgb24,crop=1:1:0:0" -f rawvideo -pix_fmt rgb24 - | xxd -p
done
