# VinylSpinner — план переноса дизайна в код

Полный порядок изменений. Каждый шаг изолирован — можно делать и коммитить по одному.

---

## Затрагиваемые файлы

```
Backend/
  app/services/discogs.py          # +vinyl_color_raw в get_release()
  app/schemas/record.py            # +vinyl_color_raw поле в RecordResponse
  app/api/records.py               # читать vinyl_color_raw из discogs_data
  scripts/backfill_vinyl_colors.py # ✅ уже создан — бэкфилл существующих записей

Mobile/
  lib/types.ts                     # +vinyl_color_raw в VinylRecord
  lib/vinylColor.ts                # ✅ уже создан
  components/VinylColorTag.tsx     # 🆕 новый — цветной тег в metaRow
  components/VinylSpinner.tsx      # 🆕 новый — анимированная пластинка
  app/record/[id].tsx              # интеграция обоих компонентов
```

> **Миграция БД не нужна.** `vinyl_color_raw` хранится внутри существующей
> колонки `discogs_data` (JSONB) — по тому же паттерну что `artist_id`
> и `artist_thumb_image_url`.

---

## Шаг 1 — Бэкенд: извлечь vinyl_color_raw из Discogs

**Файл:** `Backend/app/services/discogs.py`  
**Функция:** `get_release()` — строки 356–363

```python
# БЫЛО:
formats = data.get("formats", [])
format_type = formats[0].get("name") if formats else None
format_desc = ", ".join(formats[0].get("descriptions", [])) if formats else None

# СТАЛО — добавить одну строку:
formats = data.get("formats", [])
format_type = formats[0].get("name") if formats else None
format_desc = ", ".join(formats[0].get("descriptions", [])) if formats else None
vinyl_color_raw = formats[0].get("text") if formats else None  # ← новое
```

В словарь `result` (строка ~402) добавить поле:

```python
result = {
    ...
    "format_description": format_desc,
    "vinyl_color_raw": vinyl_color_raw,   # ← новое
    ...
}
```

> ⚠️ Кэш Redis хранит старый ответ 7 дней (TTL_RELEASE). После деплоя
> тест делать на свежем release_id или сбросить кэш: `redis-cli FLUSHDB`.

---

## Шаг 2 — Бэкенд: пробросить vinyl_color_raw через records.py

**Файл:** `Backend/app/api/records.py`

В трёх местах где читается `discogs_data` — добавить одну строку рядом с
`artist_id` и `artist_thumb_image_url`:

**Место 1 — строки 374–378** (эндпоинт GET /records/{id}):
```python
discogs_data = record.discogs_data or {}
response.artist_id = discogs_data.get("artist_id")
response.artist_thumb_image_url = discogs_data.get("artist_thumb_image_url")
response.vinyl_color_raw = discogs_data.get("vinyl_color_raw")   # ← новое
```

**Место 2 — строки 404–408** (эндпоинт GET /records/discogs/{discogs_id}, ветка "запись уже в БД"):
```python
discogs_data = record.discogs_data or {}
response.artist_id = discogs_data.get("artist_id")
response.artist_thumb_image_url = discogs_data.get("artist_thumb_image_url")
response.vinyl_color_raw = discogs_data.get("vinyl_color_raw")   # ← новое
```

**Место 3 — строки 443–445** (та же функция, ветка "запись создана из Discogs"):
```python
response.artist_id = record_data.get("artist_id")
response.artist_thumb_image_url = record_data.get("artist_thumb_image_url")
response.vinyl_color_raw = record_data.get("vinyl_color_raw")   # ← новое
```

---

## Шаг 3 — Бэкенд: добавить поле в Pydantic схему

**Файл:** `Backend/app/schemas/record.py`  
**Класс:** `RecordResponse` — после строки 55

```python
format_type: str | None
format_description: str | None
vinyl_color_raw: str | None = None   # ← новое, default None для совместимости
barcode: str | None
```

`RecordCreate` и модель SQLAlchemy трогать не нужно — поле не колонка,
а ключ внутри существующего JSONB `discogs_data`.

---

## Шаг 3 — Фронтенд: добавить поле в тип

**Файл:** `Mobile/lib/types.ts`  
**Интерфейс:** `VinylRecord` — после строки 52

```typescript
format_type?: string;
format_description?: string;
vinyl_color_raw?: string;    // ← новое
barcode?: string;
```

---

## Шаг 4 — Новый компонент: VinylColorTag

**Файл:** `Mobile/components/VinylColorTag.tsx` — создать с нуля

Это pill-тег для `metaRow` (строка 419 в `record/[id].tsx`).

**Логика:**
- `vinyl_color_raw` прогоняется через `parseVinylColor()` из `lib/vinylColor.ts`
- Если `isColored: false` → компонент не рендерится (`null`)
- Если `isColored: true` → pill с цветом + пульсирующее свечение

**Визуал:**
- Pill: `paddingHorizontal: 8`, `paddingVertical: 3`, `borderRadius: BorderRadius.full`
- Фон: `primaryColor` с opacity `0.15`
- Граница: `1px solid primaryColor` с opacity `0.5`
- Текст: название цвета (первое слово из `vinyl_color_raw`, обрезать до 12 символов),
  `fontSize: 12`, `Inter_500Medium`, цвет = `primaryColor`
- Иконка: маленький закрашенный круг ●, `6px`, цвет = `primaryColor`

**Анимация (только если `isColored: true`):**
```
glow = useSharedValue(0)
→ withRepeat(withSequence(
    withTiming(1, { duration: 1200 }),
    withTiming(0, { duration: 1200 })
  ), -1)

animatedStyle = {
  shadowColor: primaryColor,
  shadowOpacity: interpolate(glow, [0,1], [0.1, 0.55]),
  shadowRadius: interpolate(glow, [0,1], [2, 10]),
  shadowOffset: { width: 0, height: 0 },
  elevation: interpolate(glow, [0,1], [1, 6]),
}
```

**Props:**
```typescript
interface VinylColorTagProps {
  vinylColorRaw: string | undefined | null;
}
```

---

## Шаг 5 — Новый компонент: VinylSpinner

**Файл:** `Mobile/components/VinylSpinner.tsx` — создать с нуля

Только авто-ротация, без жестов.

**Props:**
```typescript
interface VinylSpinnerProps {
  colorConfig: VinylColorConfig;
  size?: number;        // default 220
  labelName?: string;
}
```

**Анимация:**
```typescript
const rotation = useSharedValue(0);

useEffect(() => {
  rotation.value = withRepeat(
    withTiming(360, { duration: 1800, easing: Easing.linear }),
    -1
  );
}, []);

const animatedStyle = useAnimatedStyle(() => ({
  transform: [{ rotate: `${rotation.value}deg` }],
}));
```

**SVG-структура (снаружи внутрь):**
1. Radial gradient определение (`<defs>`) — от `primaryColor 100%` центр
   до `primaryColor затемнённый на 30%` край
2. Основной диск — `<Circle>` r=110, fill="url(#radialGrad)"
3. Бороздки — 24 кольца, r от 44 до 105, интервал 2.5px,
   `strokeWidth=0.4`, `stroke=primaryColor`, `strokeOpacity=0.18`
4. Specular arc (блик) — `<Ellipse>` cx=-20 cy=-35, rx=70 ry=42,
   rotation=-35°, fill радиальный градиент от `white opacity 0.26` до `transparent`
5. Edge shadow — `<Circle>` r=109, fill="none",
   stroke="black", strokeWidth=4, strokeOpacity=0.25
6. Центральный лейбл — `<Circle>` r=38, fill="#1C1D3A"
7. Тонкое кольцо лейбла — `<Circle>` r=38, fill="none",
   stroke="white", strokeWidth=1, strokeOpacity=0.08
8. Отверстие — `<Circle>` r=4, fill="#000"
9. Текст лейбла — `<SvgText>` первые 5 символов лейбла, fontSize=6,
   fill="#8A8FAA", letterSpacing=2, textAnchor="middle", y=-10

**Для `type='translucent'`:** `fillOpacity=0.65` на основном диске  
**Для `type='marble'`:** 2-3 SVG Path с кривыми Безье + `feGaussianBlur stdDeviation=1.5`  
**Для `type='splatter'`:** 10 Polygon произвольной формы + 25 маленьких Circle

**Обёртка компонента** (не внутри SVG, в RN View):
- Тёмный круг подложки: `width/height=260`, `borderRadius=130`, `bg=#12133A`
- Свечение: `shadowColor=primaryColor`, `shadowOpacity=0.35`, `shadowRadius=20`,
  `elevation=16`
- Spinner поверх через `position: absolute`

---

## Шаг 6 — Интеграция в record/[id].tsx

### 6а — Импорты (добавить в начало файла)
```typescript
import { VinylColorTag } from '../../components/VinylColorTag';
import { VinylSpinner } from '../../components/VinylSpinner';
import { parseVinylColor } from '../../lib/vinylColor';
```

### 6б — VinylColorTag в metaRow (строки 419–438)

Добавить четвёртым элементом в `<View style={styles.metaRow}>`,
после блока `country`:

```tsx
<VinylColorTag vinylColorRaw={record.vinyl_color_raw} />
```

`metaRow` уже имеет `flexWrap: 'wrap'` — тег встанет в строку автоматически,
при необходимости перенесётся на следующую строку.

### 6в — VinylSpinner между Издание и Жанр (после строки 458)

```tsx
{/* Цвет винила */}
{(() => {
  const colorConfig = parseVinylColor(record.vinyl_color_raw);
  if (!colorConfig.isColored) return null;
  return (
    <View style={styles.vinylSpinnerContainer}>
      <VinylSpinner
        colorConfig={colorConfig}
        labelName={record.label ?? undefined}
        size={220}
      />
      <Text style={styles.vinylDisclaimer}>
        Это визуальный прототип — реальный цвет может отличаться
      </Text>
    </View>
  );
})()}
```

### 6г — Новые стили (добавить в StyleSheet.create)

```typescript
vinylSpinnerContainer: {
  alignItems: 'center',
  paddingVertical: Spacing.lg,
  marginHorizontal: Spacing.md,
  marginBottom: Spacing.md,
},
vinylDisclaimer: {
  ...Typography.caption,
  color: Colors.textMuted,
  textAlign: 'center',
  marginTop: Spacing.sm,
},
```

---

## Тест-чеклист

| Кейс | Release ID | Ожидаемый результат |
|---|---|---|
| Синий, solid | `28058949` | Синий тег в metaRow + синий спиннер |
| Фиолетовый, solid | `7240348` | Фиолетовый тег + спиннер |
| Янтарный, translucent | `7240348` (2й диск) | Янтарный тег с opacity 0.72 |
| Зелёный | `20895619` | Зелёный тег + спиннер |
| Чёрный (обычный) | любой стандартный | Тег не рендерится, спиннер не рендерится |
| `vinyl_color_raw = null` | новая запись без Discogs | Тег не рендерится, спиннер не рендерится |

---

## Бэкфилл существующих записей

**Файл:** `Backend/scripts/backfill_vinyl_colors.py` — уже создан.

Скрипт проходит по всем записям в БД у которых есть `discogs_id`,
запрашивает Discogs API (`/releases/{id}`), берёт `formats[0].text`
и кладёт результат в `discogs_data['vinyl_color_raw']` — без новых колонок и миграций.

### Сначала — сухой прогон (сколько записей затронет):
```bash
cd Вертушка/Backend
python -m scripts.backfill_vinyl_colors --dry-run
```

### Полный запуск локально:
```bash
python -m scripts.backfill_vinyl_colors
```
По умолчанию: 1.6 сек между запросами (~37 req/min), батчи по 50 записей.
Вывод в лог: `[42/318] 20895619 — Tyler - Call Me If You Get Lost → "Seafoam Green"`.

### На сервере (после деплоя бэкенда):
```bash
ssh deploy@85.198.85.12 'cd ~/vertushka && \
  source Вертушка/Backend/.env && \
  python -m Вертушка.Backend.scripts.backfill_vinyl_colors --batch-size 30'
```

### Флаги:
| Флаг | Описание |
|---|---|
| `--dry-run` | Только считает, ничего не пишет |
| `--limit N` | Остановиться после N записей (для теста) |
| `--delay S` | Секунд между запросами (default 1.6) |
| `--batch-size N` | Записей на транзакцию (default 50) |
| `--force` | Перезаписать даже уже заполненные |

### Идемпотентность:
Скрипт пропускает записи где ключ `vinyl_color_raw` уже есть в `discogs_data`.
Можно запускать повторно без риска — лишних запросов к Discogs не будет.

### После запуска:
Redis кэш (`TTL_RELEASE = 7 дней`) не трогаем — при следующем открытии
записи API поднимет свежий `discogs_data` из БД и вернёт цвет.

---

## Порядок деплоя (полный, с бэкфиллом)

```bash
# 1. Деплой бэкенда
git add Backend/app/services/discogs.py \
        Backend/app/schemas/record.py \
        Backend/app/api/records.py \
        Backend/scripts/backfill_vinyl_colors.py
git commit -m "feat: vinyl_color_raw — extract, expose, backfill script"
git push && ssh deploy@85.198.85.12 'cd ~/vertushka && bash Вертушка/Backend/scripts/deploy.sh'

# 2. Бэкфилл существующих записей (запускать ПОСЛЕ деплоя)
python -m scripts.backfill_vinyl_colors --dry-run   # сначала проверить
python -m scripts.backfill_vinyl_colors             # потом запустить

# 3. Деплой мобилки
git add Mobile/lib/types.ts \
        Mobile/lib/vinylColor.ts \
        Mobile/components/VinylColorTag.tsx \
        Mobile/components/VinylSpinner.tsx \
        "Mobile/app/record/[id].tsx"
git commit -m "feat: vinyl color tag + spinner component"
```

---

## Что точно не трогать

- Модель БД (`VinylRecord` в SQLAlchemy) — поле не хранится, только проходит через API
- `RecordBrief` — краткая схема для списков, цвет там не нужен
- `RecordCard.tsx`, `RecordGrid.tsx` — не трогать
- Существующий `format_description` — не удалять, используется в других местах
- Redis TTL — не менять, старые кэшированные релизы вернут `vinyl_color_raw: null`,
  это нормально, компонент просто не покажется
