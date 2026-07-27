# Manual-Add Vinyl Toggle — пакет для Claude Design

Всё для сборки floating-тоггла входа в «Добавить вручную» (винил-кноб с
рандом-цветом). Контекст: заменяем нижний CTA, который налезает на затвор.

## Содержимое

```
SPEC.md                 — спека: состояния, токены, тайминги, винил-кноб, рандом-цвет
palette.md              — vinyl family-цвета (из lib/vinylColor.ts)
nano-banana-prompt.txt  — промпт для наброска 3 состояний (+ что прикрепить)
refs/
  grid.png              — РЕНДЕР: 8 цветных винилов (solid/translucent/splatter/marble)
  svg/*.svg             — векторные винилы (импорт в Claude Design / pencil)
  vinyl-render.html     — интерактив: открой в браузере, крутятся вживую
  gen.js                — генератор svg (node gen.js) — порт VinylSpinner
  brand/mascot.png      — бренд-маскот
  brand/logo-vinyl.png  — бренд-логотип-винил
```

> Положи рядом свои скрины (опц.): `refs/ref-daymode-toggle.png` (форма pill),
> `refs/screen-current.png` (текущий экран сканера с оверлапом).

## Как использовать

**Вариант 1 — через nano banana → Claude Design**
1. Открой `nano-banana-prompt.txt`, прикрепи `refs/grid.png` (+ свои скрины).
2. Сгенери набросок 3 состояний.
3. В Claude Design собери `.pen` по наброску: токены из SPEC.md, винил-кноб из
   `refs/svg/*.svg`, текст перебей вручную (nano-banana кириллицу ломает).

**Вариант 2 — сразу в Claude Design без nano banana**
1. Импортируй `refs/svg/vinyl-red.svg` как кноб.
2. Собери pill (`#ECEDF0`, 220×64) + текст «Добавить вручную» + кноб справа.
3. Сделай 3 варианта `collapsed/expanded/activated` по SPEC.md.

## Источник истины в коде
- `Mobile/components/VinylSpinner.tsx` — рендер винила (точная копия в svg/)
- `Mobile/lib/vinylColor.ts` — палитра + parseVinylColor
- `Mobile/app/record/manual.tsx` — целевой экран (визард)
- `Mobile/app/(tabs)/index.tsx` — где живёт текущий CTA (заменяем)
