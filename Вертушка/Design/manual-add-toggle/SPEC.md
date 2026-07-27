# Manual-Add Vinyl Toggle — спецификация

Floating-кнопка входа в «Добавить пластинку вручную» (`source='user'`, экран
`Mobile/app/record/manual.tsx`). Заменяет текущий нижний CTA, который налезает
на затвор/нав-бар (см. `refs/screen-current-overlap.png`).

## Концепция взаимодействия

1. **idle** — в правом нижнем углу экрана сканера висит круглая кнопка-винил
   (FAB), винил медленно крутится (бренд-анимация, как `VinylSpinner`).
2. **tap** — из-под винила влево выезжает pill-тоггл (как iOS day/night switch
   на `refs/ref-daymode-toggle.png`). Слева в pill — подпись **«Добавить
   вручную»**, справа кноб = тот самый винил, теперь **цветной**.
3. **slide** — пользователь тянет кноб-винил влево «в трек»; кноб ускоряет
   вращение, уезжает за левый край с motion-blur → push экрана `record/manual`.
   Тап по pill — фолбэк-триггер (доступность).
4. После возврата/закрытия — тоггл схлопывается обратно в FAB.

## Состояния (для макета и компонента)

| Состояние | Что видно |
|---|---|
| `collapsed` | круг 56px, серый/цветной винил, лёгкий спин, тень |
| `expanded`  | pill ~220×64, текст слева, цветной винил-кноб справа |
| `activated` | кноб уехал влево, motion-trail, текст затухает, glow вверх |

## Токены

| Токен | Значение |
|---|---|
| navy (лейбл винила, текст) | `#1C1D3A` / текст `#23244D` |
| pill bg | `#ECEDF0` |
| groove grey (дефолт винила) | `#C8CCD2` |
| лейбл-текст на виниле | `#B8BCDB` («Вертушка»), `#5C6080` («33⅓ RPM») |
| тень | y0 blur28 opacity .45, цвет = primary винила |
| family-цвета кноба | red `#E53935`, blue `#1E88E5`, green `#43A047`, yellow `#FDD835`, orange `#FB8C00`, purple `#7E57C2` (полная палитра — `palette.md`) |

## Винил-кноб = упрощённый VinylSpinner

Источник истины: `Mobile/components/VinylSpinner.tsx` + `Mobile/lib/vinylColor.ts`.
Готовые векторы — `refs/svg/*.svg`, растровая сетка — `refs/grid.png`.

Структура (256px viewBox, масштабируется):
- диск: радиальный градиент 4 стопа (bright→mid→dark→edge, выводятся из primary
  через `saturate`/`darken`)
- 26 концентрических бороздок (groove), opacity ~0.22
- двойная тёмная обводка у края
- центральный navy-лейбл `#1C1D3A` + «Вертушка» (Rubik Mono One) + дырка `#000`
  + «33⅓ RPM» (Inter)
- статичный белый блик сверху-слева (НЕ вращается)
- типы: `solid` / `translucent` (opacity .85) / `marble` / `splatter` / `cic`

## Рандом-цвет по умолчанию (фича из обсуждения)

При каждом заходе на экран сканера кноб-винил берёт **случайный family-цвет**
из палитры (`pickRandomVinylColor()` → primary hex → `parseVinylColor`-config).
Серый дефолт остаётся фолбэком. Navy-лейбл не трогаем (контраст на любом цвете).
Тип по умолчанию `solid`; `splatter`/`marble` — опционально для «премиум»-ощущения.

## Тайминги анимации (для реализации, Reanimated)

| Переход | Длит. | Кривая |
|---|---|---|
| idle spin (всегда) | 1800ms / оборот | linear, `ReduceMotion.Never` |
| tap → expand pill | 250ms | spring (мягкий) |
| slide кноба | follow gesture | — |
| release → open (выше порога) | 200ms | timing + push |
| release → cancel (ниже порога) | 220ms | spring назад |
| collapse | 250ms | spring |

## Что отдать разработке после макета

`.pen`-компонент `ManualAddVinylToggle` с вариантами `collapsed/expanded/activated`
× цвета кноба, + спека жеста выше. RN-реализация: Reanimated (spin loop +
expand + slide-to-dismiss gesture), переиспользует существующий `VinylSpinner`.
