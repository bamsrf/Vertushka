# Радикальный редизайн Вертушка — "Editorial Gradient"

**Ветка**: `redesign/v2`
**Статус**: План утверждён, готов к реализации

---

## Проблема текущего состояния

Текущий "Blue Gradient Edition" — косметическая перекраска:
- Заголовки 18px по центру — скучно, нет характера
- Карточки одинаковые везде — серый фон + текст снизу
- Таб-бар с торчащей scan-кнопкой — устаревший паттерн
- Нет анимаций взаимодействия
- Нет визуальной иерархии

---

## Референсы

| # | Источник | Что берём |
|---|----------|-----------|
| 1 | **Trove app** | Floating pill tab bar, blur, spring zoom иконок |
| 2 | **LINEUP app** | Огромная bold типографика, контрасты, акценты |
| 3 | **Weather app** | Гигантские заголовки, минимализм, editorial |
| 4 | **Abstract art** | Палитра: deep navy → royal blue → periwinkle → lavender → soft pink |

---

## Цветовая палитра (без изменений)

Текущие цвета остаются — они уже верные:
```
deepNavy:     #0A0B3B    royalBlue:    #3B4BF5
electricBlue: #5B6AF5    periwinkle:   #8B9CF7
lavender:     #C5B8F2    softPink:     #F0C4D8
background:   #FAFBFF    surface:      #F0F2FA
```

---

## Фаза 0: Зависимости

```bash
cd "Вертушка/Mobile"
npx expo install @react-native-masked-view/masked-view
```

Нужно для GradientText. Остальное (`expo-blur`, `expo-linear-gradient`, `react-native-reanimated`) уже стоит.

---

## Фаза 1: Тема — `constants/theme.ts`

### Добавить editorial Typography:
```typescript
heroTitle: {
  fontSize: 64,
  fontFamily: 'Inter_800ExtraBold',
  lineHeight: 68,
  letterSpacing: -2,
}
display: {
  fontSize: 48,
  fontFamily: 'Inter_800ExtraBold',
  lineHeight: 52,
  letterSpacing: -1.5,
}
```

### Добавить Gradients:
```typescript
export const Gradients = {
  blue: ['#3B4BF5', '#5B6AF5'] as const,
  bluePink: ['#3B4BF5', '#8B9CF7', '#F0C4D8'] as const,
  blueLight: ['#5B6AF5', '#8B9CF7'] as const,
  overlay: ['transparent', 'rgba(10, 11, 59, 0.7)'] as const,
};
```

### Усилить тени:
```typescript
lg: {
  shadowColor: '#3B4BF5',
  shadowOffset: { width: 0, height: 12 },
  shadowOpacity: 0.15,
  shadowRadius: 32,
  elevation: 12,
}
```

---

## Фаза 2: Новые и переписанные компоненты

### 2.1 `components/GradientText.tsx` — СОЗДАТЬ

Текст с градиентом через MaskedView + LinearGradient.

```typescript
import MaskedView from '@react-native-masked-view/masked-view';
import { LinearGradient } from 'expo-linear-gradient';

interface GradientTextProps {
  children: React.ReactNode;
  colors?: readonly string[];  // default: Gradients.blue
  style?: TextStyle;
  start?: { x: number; y: number };
  end?: { x: number; y: number };
}

// Реализация:
// <MaskedView maskElement={<Text style={style}>{children}</Text>}>
//   <LinearGradient colors={colors}>
//     <Text style={[style, { opacity: 0 }]}>{children}</Text>
//   </LinearGradient>
// </MaskedView>
```

Использовать для:
- Заголовков экранов ("Поиск", "Коллекция", "Профиль")
- Активных иконок в навигации (опционально)
- Акцентных элементов (цена медиана, и т.д.)

---

### 2.2 `components/GlassTabBar.tsx` — ПОЛНОСТЬЮ ПЕРЕПИСАТЬ

**Сейчас:**
```
┌──────────────────────────────────────────┐
│  🔍        [  📷  ]        💿 Коллекция  │  ← scan торчит вверх
└──────────────────────────────────────────┘
  ^^ прилипает к краям, скруглён только сверху
```

**Новый дизайн (по Trove):**
```
         ┌─────────────────────────┐
         │   🔍      📷      💿    │  ← floating pill
         └─────────────────────────┘
              ^^^ 20px от низа, 16px от краёв
```

**Технические требования:**

| Свойство | Значение |
|----------|----------|
| Position | absolute, bottom: 20, left: 16, right: 16 |
| Border radius | 32 (полностью скруглённый pill) |
| Background | BlurView intensity=60 + rgba(250,251,255,0.85) overlay |
| Shadow | lg (усиленный) |
| Height | 64px |
| Иконки | 26px, все 3 таба равноценные (убрать scan-кнопку!) |
| Иконки неактивные | textMuted, opacity 0.5 |
| Иконки активные | royalBlue, scale 1.25 (spring: damping 12, stiffness 180) |
| Индикатор | Линия 3px height × 28px width сверху активной иконки, gradient blue |
| Лейблы | УБРАТЬ текстовые подписи — только иконки |

**Анимации:**
- Spring zoom: `withSpring(1.25, { damping: 12, stiffness: 180 })`
- Индикатор: `withTiming` перемещение по горизонтали, 250ms
- Opacity иконки: `withTiming(isFocused ? 1 : 0.5, { duration: 200 })`

---

### 2.3 `components/RecordCard.tsx` — РАДИКАЛЬНО ПЕРЕПИСАТЬ

**Два варианта через prop `variant: 'compact' | 'expanded'`**

#### Вариант "compact" (для SearchScreen):
```
┌─────────────────────┐
│                     │
│     [ОБЛОЖКА]       │  ← borderRadius: 16, занимает всю карточку
│                     │
│  ▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓ │  ← gradient overlay (transparent → dark)
│  ARTIST NAME        │  ← белый 12px uppercase
│  Album Title        │  ← белый 16px bold
└─────────────────────┘
```

- Вся информация поверх обложки на gradient overlay
- Год: badge в правом верхнем углу (pill, полупрозрачный белый)
- Нет отдельной информационной панели

#### Вариант "expanded" (для CollectionScreen):
```
┌─────────────────────┐
│                     │
│     [ОБЛОЖКА]       │  ← borderRadius top: 16, aspect 1:1
│                     │
├─────────────────────┤
│ Artist Name     ♡   │  ← 12px серый / heart icon справа
│ Album Title         │  ← 16px bold чёрный
│ 2023                │  ← 12px серый #999
└─────────────────────┘
    ^^ белый фон, padding 12, borderRadius bottom: 16
```

- Чёткое разделение: обложка / информация
- Heart icon: absolute, right:12, bottom:12
  - Активный: gradient fill (royalBlue → periwinkle)
  - Неактивный: серый контур
- Белый фон карточки, shadow md

#### Анимация нажатия (оба варианта):
```typescript
// Используем Pressable + react-native-reanimated
const scale = useSharedValue(1);

const onPressIn = () => {
  scale.value = withTiming(0.96, { duration: 100 });
};
const onPressOut = () => {
  scale.value = withTiming(1, { duration: 150 });
};
```

---

### 2.4 `components/Header.tsx` — ПОЛНОСТЬЮ ПЕРЕПИСАТЬ

**Сейчас:**
```
┌──────────────────────────────┐
│ [👤]    Коллекция    [Выбрать] │  ← 18px по центру
└──────────────────────────────┘
```

**Новый дизайн:**
```
┌──────────────────────────────┐
│                         [👤]  │  ← аватар 40x40 справа
│                               │
│ Коллекция                     │  ← 48-64px GradientText, left-aligned
│                               │
└──────────────────────────────┘
    ^^ нет тени, чистый белый фон
```

**Props остаются те же**, но layout меняется:
- `title`: рендерится как `<GradientText style={Typography.display}>` (или heroTitle для главных экранов)
- `showProfile`: аватар перемещён в правый верхний угол
- `showBack`: стрелка влево, 24px, без фона, самостоятельная строка
- `rightAction`: рядом с аватаром или вместо аватара
- Padding: safeAreaTop + 8

**Для экранов поиска/коллекции** — Header НЕ используется, заголовок встроен прямо в экран (для максимальной гибкости layout).

---

## Фаза 3: Экраны

### 3.1 `app/(tabs)/search.tsx` — ПЕРЕПИСАТЬ

**Сейчас:**
```
[Header: "Поиск" 18px центр]
[Search input: серый, скруглённый 14px]
[Artist card: серый фон]
[Grid: одинаковые карточки]
```

**Новый дизайн:**
```
[SafeArea top]
[Avatar 40x40 справа сверху]
["Поиск" — 64px GradientText left-aligned]
[Search input: 52px height, borderRadius 26, фон #F5F5F7]
  - Иконка поиска: синий градиент
  - При фокусе: синяя обводка 2px
[Artist card — ПОЛНОСТЬЮ НОВЫЙ:]
  - Gradient blue фон (royalBlue → electricBlue)
  - Аватар 72px с белой обводкой 3px
  - Имя артиста: белый 22px bold
  - Стрелка: белая иконка на rgba(255,255,255,0.2)
[Section "Релизы": 28px bold чёрный]
[Grid: RecordCard variant="compact" — overlay стиль]
```

---

### 3.2 `app/(tabs)/collection.tsx` — ПЕРЕПИСАТЬ

**Сейчас:**
```
[Header: "Коллекция" 18px центр]
[SegmentedControl]
[Grid: одинаковые карточки]
```

**Новый дизайн:**
```
[SafeArea top]
["Коллекция" — 64px GradientText left-aligned]  [Кнопка "Выбрать"]
    ^^ кнопка: прозрачный фон, gradient border 2px, gradient text, borderRadius 20
[SegmentedControl — обновлённый]
  - Высота 48px
  - Активный текст: чёрный bold 700
  - Неактивный: серый #666
[Grid: RecordCard variant="expanded" — белые карточки с инфо]
```

---

### 3.3 `app/(tabs)/index.tsx` (Scanner) — МИНОРНЫЕ ИЗМЕНЕНИЯ

- Модалка результатов: заголовок побольше (28px bold)
- Карточки результатов: variant="compact"
- Остальное без изменений (камера — специфичный экран)

---

### 3.4 `app/profile.tsx` — ОБНОВИТЬ СТИЛИ

```
[SafeArea top]
["Профиль" — 48px GradientText]    [X close]
[Avatar 100px]
[Display name 28px bold]
[Stats cards: значения 36px bold, усиленные тени]
[Link card: без изменений]
[Settings: убрать borderBottom → gap между card-like блоками]
```

---

### 3.5 `app/record/[id].tsx` — ОБНОВИТЬ СТИЛИ

- Обложка: borderRadius 24 (вместо 18)
- Title: 36px bold
- Price median: GradientText
- Actions container: BlurView фон вместо solid white
- Artist card: аватар с gradient border

---

## Фаза 4: UI компоненты

### 4.1 `components/ui/SegmentedControl.tsx`
- Высота: paddingVertical 10 (вместо 8)
- Активный текст: **чёрный, fontWeight 700** (не royalBlue!)
- Неактивный текст: серый #666666, fontWeight 500
- Контейнер: высота 48px

### 4.2 `components/ui/Button.tsx`
- Primary: gradient blue фон (LinearGradient), белый текст, shadow md
- borderRadius: 16

### 4.3 `components/ui/Input.tsx`
- borderRadius: 26 (pill-like)
- Focus: gradient blue border

### 4.4 `components/RecordGrid.tsx`
- Новый проп `cardVariant: 'compact' | 'expanded'` → передаётся в RecordCard
- Staggered fade-in анимация:
  ```typescript
  // Каждая карточка появляется с задержкой +50ms
  const delay = index * 50;
  entering={FadeInUp.delay(delay).duration(300)}
  ```

---

## Анимации (сводка)

| Элемент | Анимация | Параметры |
|---------|----------|-----------|
| Tab icon (active) | Spring scale | 1.0 → 1.25, damping: 12, stiffness: 180 |
| Tab indicator | Sliding | withTiming, 250ms |
| Tab icon opacity | Fade | 0.5 → 1.0, 200ms |
| Segmented control | Sliding bg | withTiming, 200ms |
| Card press | Scale down/up | 0.96 (100ms) → 1.0 (150ms) |
| Heart icon press | Scale burst | 1.0 → 1.3 → 1.0, 400ms |
| Cards loading | Staggered FadeInUp | +50ms delay per card, 300ms duration |

---

## Порядок реализации

```
 1. npx expo install @react-native-masked-view/masked-view
 2. constants/theme.ts — heroTitle, display, Gradients, усиленные тени
 3. components/GradientText.tsx — СОЗДАТЬ
 4. components/GlassTabBar.tsx — ПОЛНОСТЬЮ ПЕРЕПИСАТЬ (floating pill)
 5. components/RecordCard.tsx — ПЕРЕПИСАТЬ (compact / expanded)
 6. components/Header.tsx — ПЕРЕПИСАТЬ (huge left-aligned GradientText)
 7. components/ui/SegmentedControl.tsx — обновить высоту и цвета
 8. components/RecordGrid.tsx — cardVariant + staggered animation
 9. app/(tabs)/search.tsx — editorial заголовок, overlay cards
10. app/(tabs)/collection.tsx — editorial заголовок, expanded cards
11. app/(tabs)/index.tsx — минор стилей модалки
12. app/profile.tsx — editorial стиль
13. app/record/[id].tsx — обновить стили
14. components/ui/Button.tsx — gradient primary, borderRadius 16
15. components/ui/Input.tsx — borderRadius 26
```

---

## Сравнительная таблица: Было → Стало

| Элемент | Было (скриншот) | Стало |
|---------|-----------------|-------|
| Заголовки | 18px, центр, plain text | **48-64px, left-aligned, GradientText** |
| Tab bar | Scan-кнопка торчит, прилипает к краям | **Floating pill, отступы 20/16, все табы равные** |
| Tab анимации | Базовый spring 1.15x | **Spring zoom 1.25x + indicator slide + opacity** |
| Cards (поиск) | Серый фон + текст снизу | **Overlay: текст на gradient поверх обложки** |
| Cards (коллекция) | Серый фон + текст снизу | **Белый фон + shadow + heart icon + press scale** |
| Header | Центрированный layout | **Left-aligned гигантский заголовок, аватар справа** |
| Search input | borderRadius 14, серый | **borderRadius 26 (pill), gradient focus border** |
| Artist card | Серый фон, маленький | **Gradient blue фон, большой аватар, белый текст** |
| Анимации загрузки | Нет | **Staggered FadeInUp с задержкой** |
| Card press | Нет | **Scale 0.96 → 1.0** |
| Button primary | Solid color | **Gradient blue** |

---

## Файлы

### Создать (1)
| Файл | Описание |
|------|----------|
| `components/GradientText.tsx` | Текст с градиентом через MaskedView |

### Полностью переписать (4)
| Файл | Что меняется |
|------|-------------|
| `components/GlassTabBar.tsx` | Floating pill, все табы равные, spring zoom, indicator |
| `components/RecordCard.tsx` | Два варианта: compact (overlay) / expanded (card) + press animation |
| `components/Header.tsx` | Huge left-aligned GradientText, аватар справа |
| `app/(tabs)/search.tsx` | Editorial заголовок, pill search, gradient artist card, overlay cards |

### Существенно обновить (6)
| Файл | Что меняется |
|------|-------------|
| `constants/theme.ts` | heroTitle, display, Gradients, усиленные тени |
| `app/(tabs)/collection.tsx` | Editorial заголовок, gradient "Выбрать", expanded cards |
| `app/profile.tsx` | Editorial заголовки, усиленные stat cards |
| `app/record/[id].tsx` | Обложка borderRadius 24, blur actions, GradientText цена |
| `components/RecordGrid.tsx` | cardVariant prop, staggered FadeInUp |
| `components/ui/SegmentedControl.tsx` | Высота 48, чёрный активный текст |

### Минорные изменения (3)
| Файл | Что меняется |
|------|-------------|
| `components/ui/Button.tsx` | Gradient primary, borderRadius 16 |
| `components/ui/Input.tsx` | borderRadius 26 |
| `app/(tabs)/index.tsx` | Стили модалки результатов |

### НЕ меняется (логика)
- `lib/store.ts` — Zustand stores
- `lib/api.ts` — API клиент
- `lib/types.ts` — типы
- `app/_layout.tsx` — root layout (шрифты уже загружены)
- `app/(tabs)/_layout.tsx` — уже использует GlassTabBar
