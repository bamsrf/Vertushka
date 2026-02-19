# План редизайна Вертушка — "Blue Gradient Edition"

**Ветка**: `redesign/v2` (откат = `git checkout main`)

## Концепция

Новый визуальный стиль объединяет:
- **Цветовая палитра**: сине-розовый градиент (deep navy → royal blue → lavender → soft pink)
- **Типографика**: bold editorial стиль — крупные заголовки, Inter font с полной кириллицей
- **Навигация**: glass morphism floating tab bar с spring-анимациями
- **Карточки**: мягкие тени с синим подтоном, обновлённая типографика

---

## Цветовая палитра

```typescript
// Основная градиентная палитра
deepNavy:     '#0A0B3B'   // фоны, основной текст
royalBlue:    '#3B4BF5'   // основной акцент — кнопки, активные элементы
electricBlue: '#5B6AF5'   // hover/pressed состояния
periwinkle:   '#8B9CF7'   // вторичный акцент — иконки, подписи
lavender:     '#C5B8F2'   // декор, бордеры
softPink:     '#F0C4D8'   // лайки, бейджи
blushPink:    '#F8E4EE'   // surface альтернатива

// Нейтральные
background:   '#FAFBFF'   // чуть голубоватый белый
surface:      '#F0F2FA'   // карточки, инпуты
surfaceHover: '#E8EBFA'   // hover на surface
text:         '#0A0B3B'   // = deepNavy
textSecondary:'#5A5F8A'
textMuted:    '#9A9EBF'
border:       '#E0E3F0'
divider:      '#ECEEF7'

// Состояния
error:        '#E5484D'
success:      '#30A46C'
warning:      '#F5A623'

// Специальные
overlay:      'rgba(10, 11, 59, 0.5)'
cardShadow:   'rgba(59, 75, 245, 0.08)'
glassBg:      'rgba(250, 251, 255, 0.85)'
```

---

## Фаза 0: Подготовка

### 0.1 Установка зависимостей
```bash
cd "Вертушка/Mobile"
npx expo install expo-blur expo-linear-gradient @expo-google-fonts/inter
```

- `expo-blur` — BlurView для glass morphism таб-бара
- `expo-linear-gradient` — градиенты для декоративных элементов
- `@expo-google-fonts/inter` — шрифт Inter (SF Pro аналог, полная кириллица)

### 0.2 Загрузка шрифтов в `app/_layout.tsx`
```typescript
import {
  Inter_400Regular,
  Inter_500Medium,
  Inter_600SemiBold,
  Inter_700Bold,
  Inter_800ExtraBold,
} from '@expo-google-fonts/inter';
```

---

## Фаза 1: Обновление темы

### Файл: `constants/theme.ts` (РЕДАКТИРОВАТЬ)

Полная замена цветов, типографики, теней, скруглений.

**Colors** — палитра из раздела выше.

**Typography** — обновлённая с Inter:
```
h1: Inter_800ExtraBold, 34px, lineHeight 40, letterSpacing -1
h2: Inter_700Bold, 28px, lineHeight 34, letterSpacing -0.5
h3: Inter_600SemiBold, 22px, lineHeight 28
h4: Inter_600SemiBold, 18px, lineHeight 24
body: Inter_400Regular, 16px, lineHeight 24
bodyBold: Inter_600SemiBold, 16px, lineHeight 24
bodySmall: Inter_400Regular, 14px, lineHeight 20
caption: Inter_400Regular, 12px, lineHeight 16
button: Inter_600SemiBold, 16px, lineHeight 24, letterSpacing 0.3
buttonSmall: Inter_500Medium, 14px, lineHeight 20, letterSpacing 0.2
```

**Shadows** — с синим подтоном:
```
sm: shadowColor '#3B4BF5', offset {0,2}, opacity 0.06, radius 4
md: shadowColor '#3B4BF5', offset {0,4}, opacity 0.08, radius 12
lg: shadowColor '#3B4BF5', offset {0,8}, opacity 0.12, radius 24
```

**BorderRadius** — чуть мягче:
```
sm: 10, md: 14, lg: 18, xl: 26, full: 9999
```

**Spacing** — без изменений (xs:4, sm:8, md:16, lg:24, xl:32, xxl:48).

---

## Фаза 2: Компоненты

### 2.1 `components/RecordCard.tsx` (РЕДАКТИРОВАТЬ)

- Фон карточки: `surface` (#F0F2FA)
- Убрать borderWidth, заменить на `cardShadow` тень
- Скругления: 18px (BorderRadius.lg)
- Артист: `textSecondary`, Inter 12px, uppercase, letterSpacing: 1
- Название: `text`, Inter_600SemiBold 14px
- Мета (год/страна): `textMuted`, Inter 12px
- Плейсхолдер: `surface` фон + иконка `periwinkle`
- Бейдж "Забронировано": gradient royalBlue → periwinkle

### 2.2 `components/Header.tsx` (РЕДАКТИРОВАТЬ)

- Убрать borderBottom → subtle shadow
- Фон: `background` (#FAFBFF)
- Заголовок: Inter_700Bold, `deepNavy`
- Аватар: бордер 2px `lavender`
- Плейсхолдер аватара: gradient royalBlue → periwinkle

### 2.3 `components/ui/SegmentedControl.tsx` (РЕДАКТИРОВАТЬ)

- Контейнер: `surface` фон, borderRadius: 14
- Индикатор: `background` с subtle blue shadow
- Текст активный: `royalBlue`, Inter_600SemiBold
- Текст неактивный: `textMuted`, Inter_400Regular

### 2.4 `components/GlassTabBar.tsx` (СОЗДАТЬ — ключевой компонент)

Floating glass tab bar:
```
┌──────────────────────────────────────┐
│  🔍 Поиск    📷(blob)    💿 Коллекция │  ← glass pill
└──────────────────────────────────────┘
```

- Позиция: absolute, bottom, полная ширина
- Фон: BlurView (expo-blur) intensity 80 + glassBg overlay
- borderRadius: xl сверху
- Центральная кнопка скана: 64x64, gradient royalBlue→electricBlue, shadow lg
- Анимация при переключении:
  - Неактивная иконка: `textMuted`, scale 1.0
  - Активная: `royalBlue`, scale 1.15, spring анимация ("glass zoom")
  - Лейбл: fade-in только для активного таба
- Реализация: react-native-reanimated (withSpring, withTiming)
- Интеграция: `<Tabs tabBar={(props) => <GlassTabBar {...props} />}>`

---

## Фаза 3: Экраны

### 3.1 `app/(tabs)/_layout.tsx` (РЕДАКТИРОВАТЬ)

- Подключить GlassTabBar как кастомную tabBar
- Убрать стандартные tabBarStyle
- Загрузка Inter шрифтов (если не в _layout.tsx корневом)

### 3.2 `app/(tabs)/collection.tsx` (РЕДАКТИРОВАТЬ)

- backgroundColor: `background` (#FAFBFF)
- Стили кнопок: бордер `lavender`, текст `deepNavy`
- Selection footer: glass morphism фон
- Все цвета → из обновлённой темы

### 3.3 `app/(tabs)/search.tsx` (РЕДАКТИРОВАТЬ)

- Search input: фон `surface`, borderRadius: 14, иконка `periwinkle`
- Filter button активный: `royalBlue` фон
- Filter modal: glass morphism overlay
- Filter chips: активный = `royalBlue`, неактивный = `surface` + `border`
- Artist card: `surface` фон, аватар с `lavender` бордером
- Section titles: Inter_700Bold, `deepNavy`
- History: `surface` фон, иконки `periwinkle`

### 3.4 `app/(tabs)/index.tsx` — Scanner (РЕДАКТИРОВАТЬ)

- Overlay: `rgba(10, 11, 59, 0.5)`
- Scanner corners: `lavender` цвет рамки
- Loading badge: glass morphism (BlurView)
- Results modal: фон `#FAFBFF`

### 3.5 `app/_layout.tsx` (РЕДАКТИРОВАТЬ)

- Добавить загрузку Inter fonts в useFonts
- contentStyle backgroundColor: `#FAFBFF`

---

## Фаза 4: Общие UI компоненты

### 4.1 `components/ui/Button.tsx` (РЕДАКТИРОВАТЬ)
- Primary: gradient royalBlue→electricBlue, белый текст, shadow md
- Secondary: `surface` фон, `royalBlue` текст
- borderRadius: 14

### 4.2 `components/ui/Input.tsx` (РЕДАКТИРОВАТЬ)
- Фон: `surface`
- Бордер focus: `royalBlue`
- Бордер default: `border`

### 4.3 `components/RecordGrid.tsx` (РЕДАКТИРОВАТЬ)
- RefreshControl tintColor: `royalBlue`
- ActivityIndicator color: `royalBlue`
- Empty text: `textMuted`

---

## Фаза 5: Дополнительные экраны

### 5.1 `app/profile.tsx` — акценты `royalBlue`/`lavender`
### 5.2 `app/record/[id].tsx` — фон `background`, акценты из палитры
### 5.3 `app/(auth)/login.tsx`, `register.tsx` — кнопки с новой палитрой

---

## Порядок реализации

```
Фаза 0: deps + fonts
  ↓
Фаза 1: theme.ts (палитра, типографика)
  ↓
Фаза 2: компоненты (RecordCard, Header, SegmentedControl, GlassTabBar)
  ↓
Фаза 3: экраны (tabs layout, collection, search, scanner, root layout)
  ↓
Фаза 4: UI компоненты (Button, Input, RecordGrid)
  ↓
Фаза 5: остальные экраны (profile, record detail, auth)
```

---

## Стратегия отката

Всё на ветке `redesign/v2`. Main не тронут.

```bash
# Вернуться к старому дизайну:
git checkout main

# Принять новый дизайн:
git checkout main
git merge redesign/v2

# Посмотреть разницу:
git diff main..redesign/v2 --stat
```

---

## Файлы для создания (1 новый)

| # | Файл | Описание |
|---|------|----------|
| 1 | `components/GlassTabBar.tsx` | Glass morphism таб-бар |

## Файлы для редактирования

| # | Файл | Что меняется |
|---|------|-------------|
| 1 | `constants/theme.ts` | Вся палитра, типографика, тени, скругления |
| 2 | `app/_layout.tsx` | Загрузка Inter шрифтов, фон |
| 3 | `app/(tabs)/_layout.tsx` | GlassTabBar, убрать стандартную tabBar |
| 4 | `app/(tabs)/collection.tsx` | Стили |
| 5 | `app/(tabs)/search.tsx` | Стили |
| 6 | `app/(tabs)/index.tsx` | Стили сканера |
| 7 | `components/RecordCard.tsx` | Стили карточки |
| 8 | `components/Header.tsx` | Стили хедера |
| 9 | `components/RecordGrid.tsx` | Цвета |
| 10 | `components/ui/SegmentedControl.tsx` | Стили |
| 11 | `components/ui/Button.tsx` | Стили |
| 12 | `components/ui/Input.tsx` | Стили |

## Не меняется (логика)

- `lib/store.ts` — сторы Zustand
- `lib/api.ts` — API клиент
- `lib/types.ts` — типы
