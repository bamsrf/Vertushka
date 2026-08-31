# Antiheat — план борьбы с нагревом устройства

> Living document. Аудит + каталог решений против перегрева/разряда на мобильных экранах Вертушки.
> Пока это **аудит и стратегия** — не список задач к немедленному исполнению.
> Связано: перф-история (`2b65eb8` constant rail speed, `bd8f24e` VinylSpinner под Reduce Motion, `3cbd143` пауза рейлов/градиента).

---

## 0. Context

Пользователь сообщил: телефон греется при работе с Поиском. Точечный фикс уже сделан (`3cbd143` — пауза `AutoRail`/`AnimatedGradientText`, когда невидимы). Но аудит показал: это **системная** проблема, а не единичный баг. По всему приложению — ~10 бесконечных анимаций, почти ни одна не простаивает, когда невидима, и только один компонент уважает Reduce Motion. Этот документ фиксирует, **что именно физически греет устройство**, где это в нашем коде, и какие решения применимы — чтобы дальше не латать по жалобам, а закрыть класс проблем.

---

## 1. Физика: что именно греет телефон

Нагрев = побочный продукт энергопотребления. Телефон не умеет рассеивать тепло как десктоп, поэтому **устойчивая** нагрузка на CPU/GPU быстро копит тепло → thermal throttling (устройство само себя замедляет) ([Bugnet: why games overheat](https://bugnet.io/blog/why-does-my-game-overheat-phones)). Конкретные драйверы:

1. **Непрерывная работа GPU/CPU без пауз.** Анимация, которая крутится всегда (даже невидимая), не даёт железу «отдохнуть» — главный источник устойчивого power draw.
2. **GPU overdraw** — GPU рисует пиксели, которые потом перекрываются другими и не видны в кадре. Чистая потраченная энергия ([Android: reduce overdraw](https://developer.android.com/topic/performance/rendering/overdraw), [Android: inspect GPU rendering](https://developer.android.com/topic/performance/rendering/inspect-gpu-rendering)). Наш кейс — **два полноэкранных `MarketBackground` друг над другом**.
3. **Высокая частота кадров.** На ProMotion/120 Гц декоративный цикл крутится в 2× кадров против 60 — вдвое больше работы GPU без видимой пользы. Кап до 60 fps резко срезает тепло ([Bugnet: overheating & throttling](https://bugnet.io/blog/how-to-fix-mobile-game-overheating-thermal-throttling)).
4. **Дорогие эффекты композитора** — тени (bitmap-рендер), блюр, сложные шейдеры/градиенты, особенно если пересобираются **каждый кадр**. `shadow` на low-memory устройствах советуют избегать; градиенты дешевле теней, но per-frame градиент под маской — дорого ([Semaphore: RN performance](https://semaphore.io/blog/react-native-performance)).
5. **Пересборка изображения каждый кадр** — движущиеся обложки в рейле = композитинг картинок на каждом кадре.
6. **Длинные списки без оптимизации** — измерение каждого элемента, отсутствие клиппинга невидимых → лишний CPU/GPU ([RN 2026 perf guide](https://www.agilesoftlabs.com/blog/2026/03/react-native-performance-optimization)).

**Важно про измерение:** нагрев/jank в **dev-билде кратно преувеличены** — Reanimated и RN в release компилируются с оптимизациями ([Reanimated Performance](https://docs.swmansion.com/react-native-reanimated/docs/guides/performance/)). Любой фикс валидировать в release.

---

## 2. Аудит Вертушки: где это у нас

Полный инвентарь непрерывных аниматоров (grep по `withRepeat`/`useFrameCallback`/`Animated.loop`):

| Компонент | Тип | Множитель | Пауза вне видимости | Reduce Motion | Драйвер нагрева (§1) |
|---|---|---|---|---|---|
| `AutoRail` | frame-callback | 2 на Поиске | ✅ `3cbd143` | ❌ | 1, 5 |
| `AnimatedGradientText` | ∞ withRepeat + **MaskedView+LinearGradient/кадр** | заголовки 4 экранов | ✅ `3cbd143` | ❌ | 1, 4 |
| **`RarityAura`** | **∞ ×3** (rotation+pulse+shimmer) | **на каждой rare-карточке** сетки | ❌ | ❌ | 1, 4 |
| `AchievementPin` | Animated.loop | списки достижений/уведомлений | ❌ | ❌ | 1 |
| `MarketBackground` ×2 | scroll-driven градиенты | 2 полноэкранных слоя стек | n/a (оба смонтированы) | ❌ | **2 (overdraw)** |
| `VinylSpinner` | ∞ rotation | лоадеры | частично | ✅ (единственный) | 1 |
| `radar`/`onboarding`/`VinylColorTag`/`RarityAura` shimmer | ∞ withRepeat | разное | ❌ | ❌ | 1 |
| Все анимации | — | — | — | — | **3 (нет fps-капа на 120 Гц)** |

**Топ-подозреваемые по нагреву:**
1. **`RarityAura`** — 3 бесконечные анимации × N rare-карточек в сетке, ноль пауз. Вероятно, крупнее рейлов.
2. **`AnimatedGradientText`** — самая дорогая единичная анимация: `MaskedView` + пересборка нативного `LinearGradient` каждый кадр (§1.4). ×4 экрана.
3. **Два `MarketBackground`** — полноэкранный overdraw (§1.2).
4. **Отсутствие fps-капа** — на 120-Гц айфонах всё декоративное крутится вдвое дороже (§1.3).

---

## 3. Каталог решений (что применимо к нам)

### A. Паузить всё, что невидимо — обобщённый примитив (наибольший эффект)
Вынести логику из `3cbd143` в переиспользуемый хук `usePausableRepeat` / `useVisibleAnimation`:
- запускает анимацию только когда `useIsFocused() && !paused && !useReducedMotion()`;
- worklet-гейт через shared value (без гонки старт/стоп — урок фикса залипшей витрины);
- раскатать на `RarityAura`, `AchievementPin`, `VinylColorTag`, radar/onboarding.
Закрывает драйвер §1.1 для всего приложения.

### B. Пауза по видимости элемента в списках
Для `RarityAura`/`AchievementPin`: `FlatList.onViewableItemsChanged` → карточка ушла за экран (но ещё в window) → её анимации замирают. Без этого off-screen карточки в буфере FlatList продолжают крутиться.

### C. Уважать системный Reduce Motion — app-wide
Прецедент есть (`VinylSpinner`, `bd8f24e`). Распространить через тот же хук (§A). Двойная польза: доступность + батарея. Многим декоративным ∞-циклам при Reduce Motion лучше просто встать в статичный кадр.

### D. Срезать GPU overdraw (§1.2)
- Не держать **два** полноэкранных `MarketBackground` одновременно: пока `committed=false`, market-фон не нужен → лениво монтировать / размонтировать при выходе.
- Проверить сетки на лишние непрозрачные слои (фон карточки поверх фона экрана) — Android «Debug GPU overdraw» покажет красные зоны.

### E. Кап частоты кадров для декоративных циклов (§1.3)
- Оценить, крутятся ли ∞-анимации на 120 Гц. Если да — для чисто декоративных (shimmer/gradient/aura) ограничить эффективный fps (более медленный `duration`/throttle кадрового шага) — визуально незаметно, GPU вдвое легче.

### F. Пересмотреть `AnimatedGradientText` (§1.4)
Самая дорогая анимация. Варианты по возрастанию радикальности:
- пауза вне фокуса (уже сделано) + Reduce Motion → статичный градиент;
- один-два цикла при появлении экрана, затем покой (не бесконечно);
- заменить per-frame `MaskedView+LinearGradient` на статический градиент-текст, если движение не критично для бренда.

### G. Гигиена списков (§1.6)
Для `RecordGrid`/сеток: `getItemLayout` (фикс-высота карточек), `removeClippedSubviews`, рассмотреть FlashList как drop-in ([shadowlist/FlashList](https://github.com/azimgd/shadowlist)). У `expo-image` — явные width/height и `cachePolicy` (уже есть местами).

### H. Тени → градиенты
Аудит `shadow*`/`elevation` на карточках: тени = bitmap-рендер, дороги при анимации/множестве. Где можно — заменять на градиент/бордер ([Semaphore](https://semaphore.io/blog/react-native-performance)).

---

## 4. Приоритизация (impact × усилие)

| P | Решение | Что закрывает | Усилие |
|---|---|---|---|
| **P0** | §A хук `usePausableRepeat` + §B пауза `RarityAura` по видимости/фокусу | Топ-подозреваемый #1, класс проблем | M |
| **P1** | §F `AnimatedGradientText` → Reduce-Motion/статик | Топ #2, дорогой per-frame gradient | S |
| **P1** | §D лениво монтировать market-`MarketBackground` | Overdraw #3 | S |
| **P2** | §C Reduce Motion app-wide + §E fps-кап декоративного | Батарея на 120 Гц, доступность | M |
| **P3** | §G/§H гигиена списков и теней | Хвост | M |

---

## 5. Как измерять (обязательно в release-сборке)

- **iOS:** Xcode Instruments → Energy Log / Animation Hitches; Reanimated/Perf Monitor — UI+JS fps. Цель: idle-экран не держит стабильные 60/120 fps впустую.
- **Android:** Developer Options → **Debug GPU Overdraw** (красные зоны = стек слоёв), Profile HWUI rendering; `dumpsys gfxinfo`.
- **Термо/потребление:** наблюдать температуру/разряд на реальном устройстве до/после; dev-билд не показатель (§1, release-caveat).
- **Метод:** зафиксировать сцену (Поиск idle, сетка коллекции из rare-карточек, вход/выход из Маркета), мерить одну переменную за раз.

---

## 6. Открытые вопросы
- Крутятся ли наши ∞-анимации на 120 Гц или RN сам капит их — проверить на ProMotion-устройстве.
- `RarityAura`: сколько rare-карточек типично видно у активного коллекционера (определяет реальный множитель).
- Готовы ли пожертвовать «живым» градиент-заголовком ради статики (§F) — продуктовое решение.

---

## Источники
- [Reanimated — Performance](https://docs.swmansion.com/react-native-reanimated/docs/guides/performance/)
- [Android — Reduce overdraw](https://developer.android.com/topic/performance/rendering/overdraw) · [Inspect GPU rendering](https://developer.android.com/topic/performance/rendering/inspect-gpu-rendering)
- [Bugnet — why games overheat / throttling](https://bugnet.io/blog/how-to-fix-mobile-game-overheating-thermal-throttling)
- [Semaphore — RN performance](https://semaphore.io/blog/react-native-performance) · [RN perf 2026 guide](https://www.agilesoftlabs.com/blog/2026/03/react-native-performance-optimization)
- [ShadowList / FlashList](https://github.com/azimgd/shadowlist)
