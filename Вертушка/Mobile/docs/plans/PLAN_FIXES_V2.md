# Фиксы после редизайна v2 — "Fixes & Polish"

**Ветка**: `redesign/v2`
**Статус**: Готов к реализации
**Базируется на**: `PLAN_REDESIGN_V2.md` (всё уже реализовано)

---

## Список фиксов

| # | Название | Файлы |
|---|----------|-------|
| 1 | Сузить таб-бар + исправить тень на белом | `components/GlassTabBar.tsx`, `constants/theme.ts` |
| 2 | Haptic feedback на кнопки таба | `components/GlassTabBar.tsx` |
| 3 | Уменьшить шрифт заголовков + Arial Black + "Выбрать" под заголовком | `constants/theme.ts`, `app/(tabs)/collection.tsx` |
| 4 | Убрать синий фильтр на камере сканера | `app/(tabs)/index.tsx` |
| 5 | AnimatedGradientText компонент + заголовки всех разделов | `components/AnimatedGradientText.tsx`, `constants/theme.ts`, 3 экрана |

---

## Фикс 1: Сузить таб-бар + тень на белом

**Файл**: `components/GlassTabBar.tsx`

**Проблема**: Таб-бар занимает почти всю ширину экрана (отступы по 16px), выглядит "прилипшим" к краям. Тень на белом фоне почти не видна (синий цвет тени сливается с фоном).

**Что менять в стилях**:

```typescript
// БЫЛО:
container: {
  position: 'absolute',
  bottom: 20,
  left: 16,
  right: 16,
  ...Shadows.lg,
},

// СТАЛО:
container: {
  position: 'absolute',
  bottom: 28,
  alignSelf: 'center',
  width: '65%',   // Компактный пилл как в референсе Trove
  ...Shadows.tabBar,  // Новая тень (см. ниже)
},
blurContainer: {
  borderRadius: 36,  // Чуть больше для узкого пилла
  overflow: 'hidden',
  height: 60,        // Чуть ниже, соответствует ширине
},
```

**Добавить в `constants/theme.ts`** — новая нейтральная тень для таб-бара:

```typescript
export const Shadows = {
  // ... существующие sm, md, lg ...
  tabBar: {
    shadowColor: '#000000',       // Нейтральный чёрный, не синий
    shadowOffset: { width: 0, height: 8 },
    shadowOpacity: 0.14,
    shadowRadius: 24,
    elevation: 14,
  },
};
```

> На iOS `shadowColor: '#000'` с `shadowOpacity: 0.14` даёт мягкую серую тень, которая хорошо видна на белом фоне. Синяя тень (`#3B4BF5`) сливается с белым.

---

## Фикс 2: Haptic feedback на таб-кнопки

**Файл**: `components/GlassTabBar.tsx`

**Проблема**: При нажатии на иконки в нижнем баре нет тактильного отклика.

**Изменения**:

1. Добавить импорт в начало файла:
```typescript
import * as Haptics from 'expo-haptics';
```

2. В функции `TabIcon`, в `onPress` prop компонента `TouchableOpacity` добавить вызов haptic **перед** навигацией. Так как `onPress` сейчас передаётся снаружи, лучше обернуть его в `GlassTabBar`:

```typescript
// В GlassTabBar, в map по routes, onPress оборачиваем:
const onPress = () => {
  Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light); // добавить
  const event = navigation.emit({ ... });
  if (!isFocused && !event.defaultPrevented) {
    navigation.navigate(route.name, route.params);
  }
};
```

> `expo-haptics` уже есть в зависимостях Expo — отдельная установка не нужна.

---

## Фикс 3: Размер заголовков + Arial Black + "Выбрать" под заголовком

### 3.1 Изменить `heroTitle` в `constants/theme.ts`

**Проблема**: `fontSize: 64` — слишком большой, элементы справа от заголовка (кнопка "Выбрать", аватар) сдвигаются или обрезаются.

```typescript
// БЫЛО:
heroTitle: {
  fontSize: 64,
  fontFamily: 'Inter_800ExtraBold',
  lineHeight: 68,
  letterSpacing: -2,
},
display: {
  fontSize: 48,
  fontFamily: 'Inter_800ExtraBold',
  lineHeight: 52,
  letterSpacing: -1.5,
},

// СТАЛО:
heroTitle: {
  fontSize: 46,
  fontFamily: 'Arial Black',    // Системный шрифт iOS, нет установки
  lineHeight: 50,
  letterSpacing: -1.5,
},
display: {
  fontSize: 36,
  fontFamily: 'Arial Black',
  lineHeight: 40,
  letterSpacing: -1,
},
```

> **Arial Black на iOS**: доступен как системный шрифт. PostScript name — `Arial-BoldMT` или `Arial Black`. Через `fontFamily: 'Arial Black'` должен работать нативно. Если нет — fallback `fontWeight: '900'` + `fontFamily: 'System'`.

### 3.2 Кнопка "Выбрать" под заголовком — `app/(tabs)/collection.tsx`

**Проблема**: В `titleRow` (flexDirection: 'row') заголовок "Коллекция" и кнопка "Выбрать" стоят рядом — при большом шрифте кнопка вылезает за экран.

**Изменение layout**: сменить с row на column, кнопка идёт отдельной строкой после заголовка.

```typescript
// БЫЛО:
titleRow: {
  flexDirection: 'row',
  alignItems: 'flex-end',
  justifyContent: 'space-between',
  marginBottom: Spacing.md,
},

// СТАЛО:
titleRow: {
  flexDirection: 'column',
  alignItems: 'flex-start',
  marginBottom: Spacing.md,
  gap: Spacing.sm,
},
```

И скорректировать `headerButtonWrapper`, убрав `position: 'relative'` — кнопки теперь в потоке под заголовком:

```typescript
headerButtonWrapper: {
  alignItems: 'flex-start',
  justifyContent: 'center',
  minHeight: 36,
},
```

---

## Фикс 4: Убрать синий фильтр на камере

**Файл**: `app/(tabs)/index.tsx`

**Проблема**: Оверлей поверх камеры имеет `backgroundColor: Colors.overlay` = `'rgba(10, 11, 59, 0.5)'` (тёмно-синий), что даёт синий фильтр поверх изображения с камеры.

**Изменение** (строка ~216):

```typescript
// БЫЛО:
overlay: {
  ...StyleSheet.absoluteFillObject,
  backgroundColor: Colors.overlay,  // 'rgba(10, 11, 59, 0.5)' — синий!
},

// СТАЛО:
overlay: {
  ...StyleSheet.absoluteFillObject,
  backgroundColor: 'rgba(0, 0, 0, 0.25)',  // Нейтральный тёмный оверлей
},
```

> Оверлей нужно оставить (иначе текст заголовка и уголки сканера не будут читаться), просто убрать синий оттенок.

---

## Фикс 5: AnimatedGradientText

### 5.0 Добавить палитру в `constants/theme.ts`

Добавить секцию после `Gradients`:

```typescript
export const AnimatedGradientPalette = {
  colors: [
    '#2D3E8F',  // Тёмно-синий
    '#4A6FDB',  // Насыщенный синий
    '#6B9EF5',  // Средне-синий
    '#93C4FF',  // Светло-синий
    '#C8D9F7',  // Очень светло-синий
    '#E8CEEB',  // Светло-розово-фиолетовый
    '#F5B5D8',  // Светло-розовый
  ] as const,
  // Пресеты — тройки цветов для градиента
  presets: [
    ['#2D3E8F', '#4A6FDB', '#6B9EF5'],
    ['#4A6FDB', '#6B9EF5', '#93C4FF'],
    ['#6B9EF5', '#93C4FF', '#C8D9F7'],
    ['#93C4FF', '#C8D9F7', '#E8CEEB'],
    ['#C8D9F7', '#E8CEEB', '#F5B5D8'],
    ['#E8CEEB', '#F5B5D8', '#93C4FF'],
    ['#F5B5D8', '#6B9EF5', '#2D3E8F'],
  ] as const,
};
```

### 5.1 Создать `components/AnimatedGradientText.tsx`

Зависимости (все уже установлены):
- `react-native-reanimated` ✓
- `expo-linear-gradient` ✓
- `@react-native-masked-view/masked-view` ✓

Ключевая логика компонента:
- `useSharedValue(0)` — progress от 0 до 1
- `withRepeat(withTiming(1, { duration, easing: Easing.inOut(Easing.ease) }), -1)`
- `useState(currentGradientIndex)` — меняется через `setInterval` каждые `duration` мс
- `useAnimatedProps` с `interpolateColor` для плавной смены трёх цветов градиента
- `AnimatedLinearGradient = Animated.createAnimatedComponent(LinearGradient)`
- Обёртка: `MaskedView` с текстом как `maskElement` + `AnimatedLinearGradient` как содержимое

```typescript
interface AnimatedGradientTextProps {
  children: React.ReactNode;
  style?: TextStyle | TextStyle[];
  duration?: number;  // default: 3500
}
```

> Ключевые детали реализации:
> - `React.memo` для мемоизации
> - Cleanup `clearInterval` в `useEffect` return
> - Invisible text `opacity: 0` внутри градиента для правильного размера

### 5.2 Заменить `GradientText` на `AnimatedGradientText` в заголовках

Затронутые экраны:

| Экран | Файл | Строка |
|-------|------|--------|
| Коллекция | `app/(tabs)/collection.tsx` | `<GradientText style={Typography.heroTitle}>Коллекция</GradientText>` |
| Поиск | `app/(tabs)/search.tsx` | аналогично с "Поиск" |
| Профиль | `app/profile.tsx` | аналогично с "Профиль" |

Замена одинаковая для всех:
```typescript
// БЫЛО:
import { GradientText } from '../../components/GradientText';
<GradientText style={Typography.heroTitle}>Коллекция</GradientText>

// СТАЛО:
import { AnimatedGradientText } from '../../components/AnimatedGradientText';
<AnimatedGradientText style={Typography.heroTitle}>Коллекция</AnimatedGradientText>
```

> Статический `GradientText` остаётся для других применений (цена, акценты и т.д.). `AnimatedGradientText` только для заголовков разделов.

---

## Порядок реализации

```
1. constants/theme.ts
   - Добавить Shadows.tabBar (нейтральный чёрный)
   - Уменьшить heroTitle (64→46) и display (48→36)
   - Сменить fontFamily на 'Arial Black'
   - Добавить AnimatedGradientPalette

2. components/GlassTabBar.tsx
   - Сузить: width '65%', alignSelf 'center', bottom 28
   - Тень Shadows.tabBar
   - borderRadius 36, height 60
   - Добавить Haptics.impactAsync в onPress

3. app/(tabs)/index.tsx
   - overlay backgroundColor → 'rgba(0, 0, 0, 0.25)'

4. components/AnimatedGradientText.tsx
   - Создать компонент

5. app/(tabs)/collection.tsx
   - titleRow: column layout
   - headerButtonWrapper: убрать relative positioning
   - GradientText → AnimatedGradientText

6. app/(tabs)/search.tsx
   - GradientText → AnimatedGradientText для заголовка "Поиск"

7. app/profile.tsx
   - GradientText → AnimatedGradientText для заголовка "Профиль"
```

---

## Проверочный список

- [ ] Таб-бар компактный, не прилипает к краям
- [ ] Тень видна на белом фоне
- [ ] При нажатии на таб — haptic отклик
- [ ] Заголовки "Коллекция", "Поиск", "Профиль" — ~46px, Arial Black
- [ ] Кнопка "Выбрать" — под заголовком "Коллекция", не рядом
- [ ] Ни один элемент не зарезается/перекрывается после уменьшения шрифта
- [ ] Сканер открывается без синего фильтра, камера чистая
- [ ] Заголовки разделов плавно меняют градиент (синий → розовый → синий)
- [ ] AnimatedGradientText не тормозит скролл (memo + Reanimated UI thread)

---

## Что не трогаем

- `lib/store.ts`, `lib/api.ts`, `lib/types.ts` — логика без изменений
- `components/GradientText.tsx` — остаётся для статических акцентов
- Остальные экраны и компоненты — без изменений
