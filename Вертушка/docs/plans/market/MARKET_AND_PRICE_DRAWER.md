# Маркет + Сравнение цен — спека для Design Claude

> **Аудитория:** Design Claude, который будет рисовать макеты в Pencil и потом отдавать в имплементацию.
> **Родительский документ:** [OFFERS_UX.md](OFFERS_UX.md) — там подробности по Hot Stock pill, чипу «В продаже» и уведомлениям; здесь мы фокусируемся на **двух главных нереализованных кусках**: полноценный раздел «Маркет» с магическим переходом фона и swipe-сравнение цен в вишлисте.
> **Ассеты:** референсы фона и стиля будут лежать в `Design/market/` (фон + мокапы стилистики). Логотипы магазинов — `Design/store-logos/{slug}.png` (юзер донесёт).

---

## 0. Статус всех 5 фич OFFERS_UX.md (что готово / что нет)

| # | Фича | Backend | Mobile | Статус |
|---|---|---|---|---|
| 1 | Уведомления вишлиста (точный матч) | Модель + enum готовы | toggle есть, NotificationItem — нет нового типа | 🟡 Half — нужен cron + push-доставка + alt-version тип |
| 1.b | Уведомления вишлиста (alt-version) | Enum не добавлен | Нет | 🔴 Not started |
| 2 | **Hot Stock pill** | Endpoint `RecordOffersSummary` нет | `HotStockTag.tsx` нет, в RecordCard не встроен | 🔴 Not started (детальная спека в OFFERS_UX.md §2) |
| 3 | Чип «В продаже» в поиске | `?in_stock_only=true` не реализован | Чип не добавлен | 🔴 Not started |
| 4 | **Маркет** — раздел | `GET /api/market/new-arrivals` ✅ есть; остальные endpoints нет | `MiniPriceBadge` нет, AutoRail не расширен, экрана нет | 🔴 Not started — **пересмотрено**, см. §1 |
| 5 | **Swipe-сравнение цен** | `?include_master_versions=true` нет | Swipeable wrap нет, OffersDrawer/BottomSheet нет | 🔴 Not started — детали в §2 |

**Дополнительно (вне OFFERS_UX.md, готово в Backend):**
- ✅ Парсеры: korobkavinyla, plastinka_com, vinyl_ru, stoprobotvinyl (4 магазина, ~10k+ листингов)
- ✅ Affiliate Phase A (clicks-tracking + wrap_url с subid)
- ✅ `GET /api/market/new-arrivals` (с COALESCE-fallback'ами для format_type и cover)

**Заблокировано данными:** Hot Stock pill и Маркет имеют смысл при ≥3 магазинах и ≥3k активных листингов. По состоянию на 2026-05-19 — 4 магазина, ~5500 листингов (Коробка ~5400 + plastinka 3 + vinyl_ru 3 + stoprobotvinyl 0 → краулы в фоне). Готовность данных будет ~через сутки.

---

## 1. Маркет — полноценный раздел (полная переработка Фичи 4)

> **Что изменилось** относительно OFFERS_UX.md §4: ранее планировался **второй AutoRail** в `search.tsx` без отдельного экрана. Сейчас юзер просит **полноценный раздел** с эффектом «потайной двери» — постепенная смена темы фона при скролле + дополнительная идентичность.

### 1.1 Концепция «потайная дверь»

Маркет — это **скрытая комната** под привычным поиском. Не таб, не модал, не отдельный route в навигации. Юзер скроллит вниз на экране поиска → мир вокруг постепенно меняется → он оказывается «в другой части приложения», не покидая экран. Когнитивно это работает как:

- **Дискогс-поиск** (текущий контент search.tsx) — холодный, кобальтовый, серьёзный → «архив знаний»
- **Маркет** (новый раздел ниже) — насыщенный, тёплый, более «органический» → «жизнь, рынок, движение прямо сейчас»

Эта дихотомия (архив vs. рынок) — главный концептуальный аргумент за отдельную айдентику. Без неё две карусели подряд (Дискогс-новинки + Маркет-новинки) сольются в один длинный лист, и юзер не почувствует переход.

### 1.2 Точки входа

Две, по убывающей вероятности:

1. **Скролл вниз** на `(tabs)/search.tsx` → юзер просто продолжает листать и попадает в Маркет. Магия проявляется в фоне (см. §1.3).
2. **Тап «Смотреть все →»** на Hot Stock-секции «В наличии сейчас» (которая визуально остаётся в верхней части search-экрана как AutoRail — это «дверь»). При тапе — программный scroll до Y-координаты Маркета + animated background transition.

**Что НЕ делаем:**
- ❌ Отдельный таб в bottom navigation
- ❌ Отдельный route `/market` (роутинг останется внутри `(tabs)/search.tsx`)
- ❌ Кнопку «Открыть Маркет» в виде CTA — было бы слишком прямолинейно

### 1.3 Анатомия magic-transition (фон-морфинг)

Технически реализуется через `useAnimatedScrollHandler` (Reanimated 3) + два absolute-positioned слоя `LinearGradient`:

```
┌────────────────────────────────────────────┐
│   <View style={styles.container}>          │
│     <Animated.View style={bgLayerSearch}/> │  ← обычный фон Discogs (opacity: searchAlpha)
│     <Animated.View style={bgLayerMarket}/> │  ← фон Маркета (opacity: 1 - searchAlpha)
│     <Animated.ScrollView>                  │
│       [Discogs-секции, header, AutoRail]   │
│       [───── transition zone ─────]        │  ← scroll 400-700px
│       [Маркет-секции]                      │
│     </Animated.ScrollView>                 │
│   </View>                                  │
└────────────────────────────────────────────┘
```

**Параметры transition:**
- `scrollY` отслеживается через `useAnimatedScrollHandler({ onScroll: e => scrollY.value = e.contentOffset.y })`
- `searchAlpha = interpolate(scrollY, [400, 700], [1, 0], Extrapolation.CLAMP)` — фон Discogs гаснет с 400 до 700 px
- `marketAlpha = interpolate(scrollY, [400, 700], [0, 1], Extrapolation.CLAMP)` — фон Маркета зажигается там же
- В transition-zone [400, 700] оба слоя одновременно частично видны → **физическое смешение** двух градиентов через `mix-blend-mode` или просто overlay

**Что меняется кроме фона** в transition-zone:
- **StatusBar tint** (через `expo-status-bar`): `'dark'` → `'light'` плавно на середине (~550px) — иначе на тёмном фоне иконки статус-бара не видны
- **Tab bar tint** (если он не fully translucent): можно добавить ту же интерполяцию
- **Tint иконки активного таба Search** (если её достаём из layout): subtle ember-glow когда юзер в маркете — подсказка «ты сейчас глубже»

**Что НЕ меняется:**
- Карточки уже-видимых Discogs-секций не меняют цвет шрифтов — иначе теряется читабельность во время скролла. Они «вытекают» вверх из кадра и заменяются маркет-секциями со своей типографикой.

### 1.4 Sticky-состояние Маркета

**Решение:** persisted через Zustand persist (`Mobile/lib/store.ts` → `useMarketStore`). Юзер опустил один раз → при следующем заходе на Search экран сразу скроллится к Маркету (с animated bg fade-in уже в открытом состоянии). Переживает рестарт приложения.

**Состояние:**
```typescript
interface MarketStore {
  // Y-координата скролла на search.tsx, persisted
  searchScrollY: number;
  setSearchScrollY: (y: number) => void;
  // Признак "в маркете сейчас" — используем для tab-icon glow (§1.10)
  isInMarket: boolean;  // derived: searchScrollY >= 600
}
```

**При mount экрана** `search.tsx`:
1. Если `searchScrollY > 0` (юзер был где-то), вызываем `scrollRef.current?.scrollTo({ y: searchScrollY, animated: false })` — без анимации, мгновенно. Иначе flicker.
2. Фон сразу применяется через initial value `scrollY.value = searchScrollY`.

**Когда сбрасывается:** только если юзер свайпом доскроллит **выше** Discogs-секций (scrollY < 100). Тогда `setSearchScrollY(0)`. Это решает проблему «случайно опустил один раз — теперь всегда открыто».

### 1.5 Float-кнопка «Выйти из Маркета»

Когда `searchScrollY > 1200` (юзер глубоко в Маркете, ниже первой витрины магазина), в правом нижнем углу появляется компактная floating-кнопка:

```
   ┌────────────────────┐
   │ ↑  Выйти из Маркета│
   └────────────────────┘
```

| Слой | Token |
|---|---|
| Position | absolute, right: 20, bottom: 96 (выше bottom tab bar) |
| Background | `BlurView intensity={32} tint="dark"` |
| Border | 0.5pt `rgba(255,255,255,0.18)` |
| Border radius | `BorderRadius.full` |
| Padding | 14h / 10v |
| Icon `arrow-up` 14pt + label 12pt/600w `#FFFFFF` |
| Shadow | `Shadows.glassDeep` |
| Animation | Появление: `opacity 0→1 + translateY 12→0` 240ms `Easing.out`. Исчезновение симметрично. |
| `Pressable hitSlop` | 12 |

**Поведение тапа:** `scrollRef.current?.scrollTo({ y: 0, animated: true })` + параллельная анимация фона обратно (она и так привязана к scrollY, так что отдельно ничего не запускаем). 600ms duration scroll.

**Когда не показываем:**
- При scrollY < 1200 (юзер ещё видит Hot Stock-карусель — нет смысла «выходить»)
- В первые 800ms после mount экрана (защита от flicker при initial scroll-restore)

### 1.6 Header Маркета

Жирный заголовок, как у других разделов (Coллекция, Поиск), но **отличающийся** — приметный, чтобы юзер понял «я в другом месте».

```
┌─────────────────────────────────────────────┐
│                                              │
│  МАРКЕТ ◉                                    │  ← 32pt / 800w, letter-spacing -0.5
│  ─────                                       │  ← thin underline 1.5pt accent.ember, длина 56dp
│  В наличии сейчас · 4 магазина · 5 437 шт.   │  ← 13pt / 500w, opacity 0.7
│                                              │
└─────────────────────────────────────────────┘
```

| Слой | Token |
|---|---|
| Заголовок «МАРКЕТ» | 32pt / 800w (heaviest), uppercase, letter-spacing -0.5, color `#FFFFFF` |
| После заголовка inline `disc` icon | 24pt, color `accent.ember`, opacity 0.85. **Без вращения** в header (вращение оставляем на AutoRail в Hot Stock-секции, см. §4 OFFERS_UX.md). |
| Underline | 56dp wide × 1.5pt high, color `accent.ember`, прижата к baseline заголовка, offset -8dp ниже |
| Subtitle | 13pt / 500w `#FFFFFF` opacity 0.7. Шаблон: «В наличии сейчас · {N} магазинов · {sum} шт.» |

**Sticky-поведение:** при дальнейшем скролле header collapses в компактный sticky-bar высотой 56dp с маленьким «МАРКЕТ» 17pt / 700w и тем же disc. Аналогично паттерну в `(tabs)/collection.tsx`.

### 1.7 Поиск внутри Маркета

Под header — TextInput для поиска по всем in-stock пластинкам.

```
┌─────────────────────────────────────────────┐
│  ┌─────────────────────────────────────┐    │
│  │ 🔍  Найти в магазинах…              │    │
│  └─────────────────────────────────────┘    │
└─────────────────────────────────────────────┘
```

| Слой | Token |
|---|---|
| Background | `BlurView intensity={24} tint="dark"` (стекло на градиентном фоне) |
| Border | 0.5pt `rgba(255,255,255,0.2)` |
| Border radius | `BorderRadius.lg` (12dp) |
| Padding | 14h / 12v |
| Icon `magnifying-glass` 16pt opacity 0.6 (слева) |
| Input | 15pt / 500w `#FFFFFF`, placeholder color `rgba(255,255,255,0.5)` |
| Clear button (×) | 16pt, появляется когда `value.length > 0`, hitSlop 8 |

**Поведение:**
- Debounced 250ms (`use-debounce` или ручной useRef)
- При empty value → показываем витрины по магазинам (§1.8)
- При query.length >= 2 → fetch `/api/market/search?q=...&format=...` → результаты сеткой 2 колонки (см. §1.10)
- При query пустой и юзер тапает по input → не открывается доп.панель, просто фокус и витрины остаются

**Дефолтная сортировка результатов:** **по минимальной цене (asc)**. Sort-меню в Phase 1 НЕ добавляем — если юзер захочет «по новизне», добавим в Phase 2 dropdown справа от input'а.

### 1.8 Чипы форматов (всегда видны)

Ниже поиска — горизонтальная полоса чипов. **Видимы всегда**, не скрываются при scroll и при наборе текста. Это явное заявление «вот фильтры по типу носителя».

```
┌─────────────────────────────────────────────┐
│  [Все] [◉ Винил] [◎ CD] [▭ Кассеты]         │
└─────────────────────────────────────────────┘
```

Чипы — мультивыбор НЕ нужен; это radio (один активный за раз). Default = «Все».

| Состояние | Visual |
|---|---|
| Inactive | BlurView 18 + border 0.5pt `rgba(255,255,255,0.15)`, текст 12pt/600w `#FFFFFF` opacity 0.7, иконка тонкая (duotone) 14pt |
| Active | `LinearGradient` `Gradients.hotStock` (`[brand.cobaltDeep, brand.cobalt, accent.ember]`), border 0, текст `#FFFFFF` opacity 1, иконка filled 14pt, glow ember opacity 0.25 |

Иконки:
- **Все** — `vinyl-record` duotone (нейтрально)
- **Винил** — `disc` (мы уже используем для Hot Stock)
- **CD** — `compact-disc` (Phosphor)
- **Кассеты** — `cassette-tape` (Phosphor) — у нас в `Icon.tsx` wrapper уже должен быть; если нет — добавить

**Backend mapping:** активный чип → query param `format=vinyl|cd|cassette` к `/api/market/search` и к `/api/market/new-arrivals` (для витрин). Серверная фильтрация по `store_listings.format_raw` через нормализатор `infer_format`:
- `vinyl` → matches `LP`, `2xLP`, `EP`, `Single`, `12"`, `7"`, `10"`
- `cd` → matches `CD`, `SACD`
- `cassette` → matches `Cassette`

**Box Set** (4-й вариант формата в наших данных) — не показываем в чипах в Phase 1, отнесём к Винилу (он чаще всего и есть LP-box). Если будет много CD-боксов — добавим отдельный чип в Phase 2.

### 1.9 До-поиск state: витрины по магазинам

Когда search input пустой — экран Маркета состоит из **N горизонтальных каруселей**, по одной на магазин. Это самая «живая» часть Маркета: юзер скроллит вертикально → видит карусели магазинов → внутри каждой может скроллить горизонтально и смотреть товары.

**Структура:**

```
┌─────────────────────────────────────────────┐
│  ┌─────┐ Коробка Винила     →   В наличии   │  ← header магазина
│  │ logo│ 1 240 пластинок            1 240   │
│  └─────┘                                     │
│                                              │
│  [◉card][◉card][◉card][◉card][◉card]…       │  ← horizontal scroll
│                                              │
│  ─────────────────                           │  ← separator
│                                              │
│  ┌─────┐ Plastinka.com     →    В наличии    │
│  │ logo│ 580 пластинок              580     │
│  └─────┘                                     │
│                                              │
│  [◉card][◉card][◉card]…                      │
│                                              │
│  …и т.д. для каждого активного магазина      │
└─────────────────────────────────────────────┘
```

**Header магазина:**
| Слот | Token |
|---|---|
| Logo | 44×44, BorderRadius 8dp (мягко скруглённый квадрат, не круг — это не аватар, а логотип бренда). Загружается из `Mobile/assets/store-logos/{slug}.png` |
| Название магазина | 17pt / 700w `#FFFFFF` |
| Subtitle «N пластинок» | 11pt / 500w `#FFFFFF` opacity 0.6 |
| Right tail | «В наличии · N» в формате 11pt mono `#FFFFFF` opacity 0.5 |
| → arrow | 14pt, прижата к правой стороне header'а, hitSlop 12 |

**Тап на header (включая arrow):** открывает **полную витрину магазина** — отдельный экран `/market/store/[slug]` (новый route, см. §1.10). Это даёт «магазины как сущность» — функциональность, которая в исходном OFFERS_UX.md планировалась как Phase 2 (Фича 4.9). Здесь делаем сразу.

**Карточка в карусели:** копия маркет-карточки из §4.3 OFFERS_UX.md — обложка 108×108, артист, название, мета `2024 · LP · ◉ 4 990 ₽`. **Один листинг = один товар**. Если у пластинки в этом магазине ровно один листинг — показываем его цену. Если у пластинки есть листинги в N магазинах одного и того же релиза — здесь, в карусели этого магазина, показываем ТОЛЬКО цену этого магазина (не агрегированную).

**Порядок магазинов:** по rating desc (поле `stores.rating` в БД). На равных — алфавит. В Phase 2 добавим пользовательский pin/unpin.

**Сколько товаров в карусели:** 15-20 (достаточно для горизонтального скролла, без перегруза). В конце карусели последняя карточка — кликабельная «Все 1 240 →» (опять же ведёт на `/market/store/[slug]`).

**Эмпти-state для магазина:** если у магазина < 5 in-stock листингов — НЕ показываем его карусель совсем (иначе раздел будет «пустым» — три карточки в карусели смотрятся убого). Магазин появится когда наберёт критическую массу.

### 1.10 Результаты поиска (после ввода текста)

Когда юзер набрал в поиске что-то (`query.length >= 2`):
- Витрины **исчезают** (плавно: opacity 1→0 за 180ms).
- На их место — сетка 2 колонки (тот же `RecordGrid` из существующего поиска) с результатами `/api/market/search?q=...&format=...&sort=price_asc`.
- Карточка в сетке = существующий `RecordCard` variant `compact` + `HotStockTag` (Фича 2) с **агрегированной минимальной ценой** по всем магазинам. Под ценой — мини-tail `· в N магазинах` если N > 1.

**Дедупликация на бекенде:** один record_id → одна карточка в сетке. Минимальная цена + кол-во магазинов. Эта же логика уже работает в `/api/market/new-arrivals` (см. `Backend/app/api/offers.py`), просто переиспользуем pattern в новом search endpoint.

**Пустой результат:**
```
┌─────────────────────────────────────────────┐
│           [иллюстрация — пустая полка]      │
│                                              │
│   Не нашли «khruangbin mordechai» в продаже │
│                                              │
│   Зато на Discogs есть:                     │
│   [→ Посмотреть в архиве]                    │
└─────────────────────────────────────────────┘
```

Кнопка «Посмотреть в архиве» → scroll-to-top (фон возвращается в обычный) + при достижении searchY ≈ 0 происходит programmatic focus главного search input и подстановка той же query. Юзер видит результаты Discogs.

### 1.11 Карточка пластинки → детальный экран (агрегат по магазинам)

Тап по карточке пластинки в Маркете (как в витрине, так и в результатах поиска) → стандартный `/record/[discogs_id]` экран. **Никаких новых записей-экранов**. Только две детали:

1. **Сразу автоскролл** к `OffersBlock` ниже (как при deep-link из push-уведомления; уже реализовано query-param `scroll_to=offers`).
2. **Hint в header detail-экрана**: если юзер пришёл из Маркета (определяем по `router params: from=market`), показываем subtle breadcrumb-тип маркер «← К Маркету» в top-bar вместо стандартного back-arrow. Тап → `router.back()`.

В OffersBlock рендерим все офферы из всех магазинов по этой пластинке (этот endpoint `/api/records/{id}/offers` уже работает). Кнопка «Купить» на каждом → POST `/offers/{id}/click` → wrap_url → `Linking.openURL(url)`.

### 1.12 Витрина одного магазина (`/market/store/[slug]`)

Новый route, открывается по тапу на header магазина в витрине (§1.9).

**Layout:** копия Маркета по структуре, но фильтрованная:
- Header экрана: лого 64×64 + название магазина 22pt/700w + subtitle «В наличии · N пластинок · средняя цена X ₽» + back-arrow слева
- TextInput для поиска внутри магазина — тот же визуал что в Маркете, но scope только текущий магазин
- Чипы форматов (те же 4)
- Сетка 2 колонки `RecordGrid` с пластинками из этого магазина, отсортированных по first_seen_at desc (новинки сверху), потом по цене

**Фон экрана:** тот же градиент Маркета (нет смены темы относительно Маркета — это его подраздел).

**Без витрин других магазинов** — это страница одного бренда.

### 1.13 Дизайн-токены и фон Маркета

**Базовый фон Маркета:** используем референс юзера (`Design/market/bg-reference.png`). Технически — `LinearGradient` или (если стилистика требует) `Image` со static-asset фоном. Параметры по референсу:

- Доминирующая палитра: фиолетовый (`#3D1A6B`-ish) → насыщенный синий (`#3066FF`-ish) → персиковый (`#FF7A4A` / `#F8A57A`)
- Текстура «grain» — лёгкий шум по всему фону (даёт «органическое», не плоское ощущение)
- Композиция: тёмное пятно в верхнем-левом квадранте + световой акцент в правом-нижнем (по референсу)

**Реализация (рекомендация для Design Claude):** комбинация `LinearGradient` + наложенная `Image` (grain texture как png 0.5 opacity overlay). Это даёт контроль и динамику. Полностью статичный PNG-фон тоже допустим, но потеряем гибкость в Pencil.

**Если решаем градиентом** — добавить в `Mobile/constants/theme.ts`:
```typescript
Gradients.marketBg = {
  colors: ['#3D1A6B', '#5E3299', '#3066FF', '#F8A57A'],
  locations: [0, 0.35, 0.65, 1],
  start: { x: 0.2, y: 0 },
  end: { x: 1, y: 1 },
}
```
Реальные значения подберёт Design Claude по референсу.

**Типография в Маркете:**
- Заголовки и крупные тексты — `#FFFFFF` (на тёмно-насыщенном градиенте читается отлично)
- Subtitles — `#FFFFFF` opacity 0.7
- Цены/badges — `#FFFFFF` opacity 1
- Service text (кол-во товаров, мета) — `#FFFFFF` opacity 0.5-0.6

**Никаких «холодных» textPrimary/textSecondary** из обычной темы — в Маркете другая палитра, всё через rgba(255,255,255,*).

### 1.14 Логотипы магазинов

**Хранение:** `Design/store-logos/{slug}.png` (источник от юзера) → копия в `Mobile/assets/store-logos/{slug}.png` для bundled access.

**Слоты:** `korobkavinyla`, `plastinka_com`, `vinyl_ru`, `stoprobotvinyl` (плюс будущие).

**Размеры:** оригинал 256×256 PNG со скруглёнными углами 24dp или прозрачным фоном. В коде resize до 44×44 (header в витрине) и 64×64 (заголовок витрины одного магазина).

**Fallback:** если PNG отсутствует — рендерим **monogram-badge** из первой буквы названия магазина в круге `brand.cobaltDeep`. Это гарантирует UI не ломается до момента когда юзер донесёт лого.

**Также:** для bottom-sheet в Swipe-сравнении (§2.4) нужен **маленький логотип-тэг** 24×24 рядом с ценой каждого оффера. Используем тот же ассет.

### 1.15 Backend API контракт

**Новые endpoints:**

```python
# 1. Список активных магазинов с метриками (для витрин)
GET /api/market/stores
→ list[MarketStoreInfo]:
  - slug, name, logo_url, rating
  - in_stock_count        # сколько листингов in_stock
  - avg_price_rub         # средняя цена
  - new_today_count       # появилось за 24ч

# 2. Карусель товаров магазина (для §1.9, заменяет /api/market/new-arrivals в этой роли)
GET /api/market/stores/{slug}/listings?limit=20&sort=newest
→ list[MarketCarouselItem]
  (existing schema, см. /api/market/new-arrivals в Backend/app/api/offers.py)

# 3. Поиск по всему Маркету
GET /api/market/search?q=string&format=vinyl|cd|cassette|null&sort=price_asc|newest&limit=50
→ list[MarketSearchItem]:
  - record_id, discogs_id, artist, title, year, format, cover_image_url
  - min_price_rub        # минимальная по всем магазинам
  - stores_with_stock    # сколько магазинов имеют этот release in_stock
  - cheapest_store_slug  # для логотипа в карточке если нужно
  - first_seen_at        # для индикации новизны

# 4. Витрина одного магазина (для /market/store/[slug])
GET /api/market/stores/{slug}/all?q=&format=&sort=&limit=&offset=
→ paginated list[MarketSearchItem]  # с пагинацией
```

**Расширение existing endpoints:**

```python
# Из §2 OFFERS_UX.md — для Hot Stock pill
POST /api/records/offers/summary
body: { "discogs_ids": [...] }
→ { discogs_id: RecordOffersSummary }

# Из §5 OFFERS_UX.md — для Swipe-drawer
GET /api/records/{id}/offers?include_master_versions=true
→ { offers: [...], summary: RecordOffersSummary }
```

**Materialized view для скорости:**
```sql
CREATE MATERIALIZED VIEW market_store_stats AS
SELECT
  s.id, s.slug, s.name, s.logo_url, s.rating,
  COUNT(sl.id) FILTER (WHERE sl.status='in_stock' AND sl.last_seen_at >= now() - interval '7 days') AS in_stock_count,
  AVG(sl.price_rub) FILTER (WHERE sl.status='in_stock') AS avg_price_rub,
  COUNT(sl.id) FILTER (WHERE sl.first_seen_at >= now() - interval '24 hours' AND sl.status='in_stock') AS new_today_count
FROM stores s
LEFT JOIN store_listings sl ON sl.store_id = s.id
WHERE s.is_active = true
GROUP BY s.id;
```
Refresh раз в час; быстро отдаётся в `/api/market/stores`.

**Cache:** Redis TTL 15-30 мин для `/api/market/stores`, 10 мин для `/api/market/search`. Инвалидация при заметных изменениях (по аналогии с `invalidate_market_feed`).

---

## 2. Swipe-сравнение цен в вишлисте (Фича 5, расширенная спека)

> **Зачем:** юзер открыл вишлист (50 пластинок), видит на каждой «предварительная стоимость». Не понимает, где **прямо сейчас можно купить**. Swipe-drawer переводит цену из абстрактной в конкретную: «вот эти три магазина продают именно сейчас за X-Y-Z ₽».

### 2.1 Карточка вишлиста с язычком

В `(tabs)/collection.tsx` (вишлист) карточка получает справа торчащий вертикальный «язычок», только если `summary.in_stock_count >= 1`. Иначе — без язычка.

```
┌──────────────────────────────────────────┐╲
│ ┌────┐ Khruangbin – Mordechai           │ ╲  ← язычок-индикатор
│ │обл │ ◉ 4 990 ₽ · в 3 магазинах        │   ╲ «Сравнить →»
│ └────┘ Добавлена 12 марта                │  ╱  4dp wide на правом краю,
└──────────────────────────────────────────┘ ╱   gradient cobalt→ember
```

**Геометрия язычка:**
- Положение: `position: absolute, right: 0, top: 12, bottom: 12` (тянется на всю высоту карточки минус 12dp сверху/снизу)
- Ширина: 4dp (в покое) → плавно расширяется до 14dp при первом swipe gesture
- Border radius: 4dp 0 0 4dp (закругление только с левой стороны)
- Background: `Gradients.hotStock` (вертикальный, cobalt сверху → ember снизу)
- При первом mount экрана → лёгкая pulse-анимация 1 раз (scale 1→1.05→1, 400ms), чтобы юзер увидел сигнал. Только при первом открытии вишлиста (сохраняем в Zustand `hasSeenSwipeHint`).

**Поведение:** виден только если есть offers (`summary.in_stock_count >= 1`). Карточки без offers — без язычка (не дразним пустотой).

### 2.2 Drawer (после swipe-left)

Юзер свайпает карточку влево → она сдвигается на 280dp → справа разворачивается **компактный drawer**:

```
        ┌────────────────────────────────────┐
[карт.] │  Сравнить цены  ◉ от 4 890 ₽       │  ← header drawer'а
сдвинута├────────────────────────────────────┤
влево   │  🏪 Plastinka.com   4 890 ₽   →    │
        │  🏪 Коробка Винила  4 990 ₽   →    │  ← топ-3 offers по цене
        │  🏪 Vinylpark       5 200 ₽   →    │
        ├────────────────────────────────────┤
        │  +2 ещё в магазинах →               │
        └────────────────────────────────────┘
```

**Header drawer'а** (показывает `HotStockTag` size=md, variant=`inStockMulti`):
- 14pt/600w «Сравнить цены» слева
- `HotStockTag` справа со значением `от {min_price} ₽`
- Background: `BlurView intensity={24} tint="dark"` + border-bottom 0.5pt `rgba(255,255,255,0.1)`

**Строка оффера** (топ-3):
- Лого магазина 28×28 слева
- Название магазина 13pt/500w
- Цена 14pt/700w mono-numerals, color `#FFFFFF`
- Arrow `caret-right` 14pt opacity 0.5
- Background по умолчанию transparent; на hover/press — `rgba(255,255,255,0.05)`
- Padding 12h / 14v
- Tap → POST `/offers/{listing_id}/click` → получаем `final_url` → `Linking.openURL(final_url)` (existing affiliate flow)

**«+N ещё» строка:**
- Текст `«+2 ещё в магазинах →»` 12pt/600w, color `accent.ember`, hitSlop 12
- Tap → открывается `OfferDetailBottomSheet` (§2.3) с полным списком

**Технология свайпа:** `react-native-gesture-handler/ReanimatedSwipeable` (уже в Expo). Параметры:
- `rightThreshold={40}` — после 40dp пальца карточка «защёлкивается» в открытое состояние
- `overshootRight={false}`
- `friction={2}` — лёгкое сопротивление, чтобы свайп ощущался материально
- При тапе вне drawer'а → автозакрытие (через `useSwipeableRef.current?.close()`)

### 2.3 BottomSheet с полным списком (`OfferDetailBottomSheet.tsx`)

Тап на «+N ещё» → bottom-sheet (используем `@gorhom/bottom-sheet`, стандарт RN). Снапы: 60% экрана (preview) и 92% (full).

```
╔═══════════════════════════════════════════╗
║         ─── (drag handle)                  ║
║                                            ║
║  Все варианты — Khruangbin · Mordechai     ║
║  5 предложений · от 4 890 ₽                ║
║                                            ║
║  ┌──────────────────────────────────────┐  ║
║  │ [обл 56×56] 🏪 Plastinka.com  4 890₽ │  ║
║  │             LP · Red · 2020          │  ║
║  │             Артикул: 0656605149318   │  ║
║  │             [МК — состояние]          │  ║
║  │  ╭────────────────────────────────╮  │  ║
║  │  │ КУПИТЬ НА САЙТЕ →              │  │  ║
║  │  ╰────────────────────────────────╯  │  ║
║  └──────────────────────────────────────┘  ║
║                                            ║
║  ┌──────────────────────────────────────┐  ║
║  │ [обл] 🏪 Коробка Винила   4 990 ₽    │  ║
║  │       LP · Red · 2020                │  ║
║  │       Артикул: 0656605149318         │  ║
║  │  [КУПИТЬ НА САЙТЕ →]                 │  ║
║  └──────────────────────────────────────┘  ║
║                                            ║
║  ─── ДРУГАЯ ВЕРСИЯ МАСТЕРА ───              ║  ← group-separator
║                                            ║
║  ┌──────────────────────────────────────┐  ║
║  │ [обл] 🏪 Vinylpark   5 200 ₽   [АЛТ] │  ║
║  │       2xLP · Pink · 2023             │  ║
║  │       Артикул: 0656605149425         │  ║
║  │  [КУПИТЬ НА САЙТЕ →]                 │  ║
║  └──────────────────────────────────────┘  ║
╚═══════════════════════════════════════════╝
```

**Структура одной карточки оффера (`OfferDetailCard`):**
| Слот | Token |
|---|---|
| Обложка 56×56 | rounded 8dp |
| Logo магазина 24×24 inline в header строке |
| Имя магазина | 13pt/600w |
| Цена | 17pt/700w, mono numerals, color `Colors.text` |
| Мета строка | 12pt/400w `Colors.textSecondary` — `LP · Red · 2020` (format · color · year) |
| Артикул | 11pt mono `Colors.textTertiary` — `Артикул: 0656605149318` |
| Состояние | 11pt/600w в маленьком чипе `M`/`NM`/`VG+` если condition != null |
| Бейдж «АЛТ» | если `is_alt_version === true` — chip 10pt/700w ember-coloured, прижат к правому краю строки с именем |
| CTA | `BorderRadius.full`, padding 14h/10v, background `Gradients.hotStock`, текст «КУПИТЬ НА САЙТЕ →» 13pt/700w `#FFFFFF` |

**Группировка:** офферы exact-match (тот же `discogs_id` что в вишлисте) — сверху, отсортированы по цене. Под separator'ом «ДРУГАЯ ВЕРСИЯ МАСТЕРА» — офферы с тем же `discogs_master_id` но другим release, отсортированы по цене.

**Кнопка «КУПИТЬ»:** click flow тот же. POST `/offers/{id}/click` → `Linking.openURL`. На время request — кнопка показывает `ActivityIndicator` (cobalt) вместо стрелки, чтобы юзер не тапнул дважды.

### 2.4 Hot Stock pill в header drawer'а (§2.2)

Передаётся как `<HotStockTag variant="inStockMulti" price={summary.min_price_rub} size="sm" showArrow={false} animated={false} />`. Это **тот же компонент**, что юзер видел на карточке вишлиста — визуальная преемственность («то значение я уже видел, теперь его проявили»).

Без disc-rotation, без entry-анимации — drawer и так движется, дополнительная анимация = визуальный шум.

### 2.5 Acceptance Criteria

1. В вишлисте у карточки с offers справа торчит тонкий gradient-язычок.
2. При первом открытии вишлиста с offers — язычок делает 1 pulse, чтобы юзер заметил.
3. Swipe-left на карточке → drawer с топ-3 офферами по цене + кнопка «+N ещё».
4. Header drawer показывает HotStockTag с агрегированной мин. ценой.
5. Тап на оффер → клик трекинг + переход на сайт магазина.
6. Тап на «+N ещё» → bottom-sheet с полным списком (snap 60% / 92%).
7. Bottom-sheet группирует exact-match и alt-version с separator'ом.
8. Карточки в вишлисте без offers — без язычка (никакой пустоты).
9. Карточка в коллекции (не вишлисте) — drawer работает идентично, но в качестве hint показывает «АЛТ»-версии (она у юзера уже есть).
10. Все клики проходят через affiliate-обёртку (`POST /offers/{id}/click`).

---

## 3. Hot Stock pill (Фича 2) — кратко

Полная спека: [OFFERS_UX.md §2](OFFERS_UX.md#фича-2--hot-stock-индикатор-).

**Что в скоупе Design Claude:**
- `Mobile/components/HotStockTag.tsx` — компонент с 6 состояниями (`inStock`, `inStockMulti`, `altVersion`, `preorder`, `lastOne`, `none`)
- Размещение в `RecordCard.tsx` для всех 3 вариантов (compact, expanded, list)
- Hero-блок «В НАЛИЧИИ СЕЙЧАС» на `record/[id].tsx` под «Примерная стоимость»
- Используется в header drawer'а Swipe-сравнения (§2.4)

**Ключевые правила «когда НЕ показывать»:**
- В коллекции юзера — НЕ показываем `inStock` (только `altVersion` если есть)
- `preorder` — только на детальном экране, не в сетках
- `altVersion` — только в вишлисте/детальном экране/маркете, не на главной

**Связь с Маркетом:** карточки в результатах поиска Маркета (§1.10) и в bottom-sheet деталей пластинки используют `HotStockTag` как главный визуальный якорь цены. Витрины (§1.9) используют **`MiniPriceBadge`** — облегчённый вариант (без gradient-pill, только `◉ + цена`) — потому что в плотной горизонтальной карусели полный pill был бы избыточен.

---

## 4. Чип «В продаже» в обычном поиске (Фича 3) — без изменений

Полная спека: [OFFERS_UX.md §3](OFFERS_UX.md#фича-3--чип-фильтр--в-продаже-в-поиске-).

**Контекст в этом документе:** в основном поиске Discogs (НЕ в Маркете) — добавляется чип-фильтр «В продаже», который при активации:
- Меняет API на `/records/search?in_stock_only=true`
- Показывает только записи, у которых есть offers
- Подсвечивается ember-gradient'ом (как HotStockTag)

**Не пересекается с Маркетом**: в Маркете мы УЖЕ показываем только in-stock — там этот чип не нужен. Чип нужен в **обычном поиске** для тех юзеров, кто остался на Дискогс-уровне и хочет дофильтровать.

---

## 5. Уведомления вишлиста (Фича 1) — без изменений

Полная спека: [OFFERS_UX.md §1](OFFERS_UX.md#фича-1--уведомления-вишлиста-).

**Контекст в этом документе:** уведомления — это второй сценарий «вернуть юзера в Маркет». Push с записью из вишлиста → тап → `/record/[id]?scroll_to=offers` → юзер видит OffersBlock и кнопки «Купить». Маркет = browse-сценарий, Notifications = re-engagement.

---

## 6. Открытые вопросы для Design Claude

Что нужно решить визуально в макетах:

1. **Грейн-текстура фона Маркета** — генерируем процедурно (SVG noise + LinearGradient) или используем bundle-asset PNG? Зависит от того, насколько динамичный фон хочется (если статичный — PNG, если параллакс при скролле — процедурный).
2. **Pulse-анимация в момент перехода search → market** — нужно ли визуально «откликаться» когда фон перешёл за середину transition (например, лёгкий light-burst в центре экрана 200ms)? Или transition должен быть полностью пассивный (только фон меняется)?
3. **Цвет иконки активного таба Search** когда юзер в Маркете — субтильный ember-glow вокруг иконки, или ничего (полагаемся на фон)?
4. **Скелетоны** при загрузке витрин — обычные skeleton-shimmer (как сейчас в Discogs-новинках) или специальные для Маркета (например, обложки-плейсхолдеры с gradient'ом фона маркета)?
5. **Логотипы магазинов** — формат файлов (PNG/SVG), требования к фону (transparent/white box/coloured), фирменные цвета. Юзер донесёт ассеты.
6. **Иконка чипа «Box Set»** в Phase 2 — если будем выделять Box Set из Винила.
7. **Empty-state иллюстрация** для §1.10 «Не нашли в продаже» — стилистически (фотореалистично, минимализм, грэйн) должна совпадать с Маркетом.
8. **Compact (sticky) header «МАРКЕТ»** — какой именно visual'но triggered (по scrollY > X)? Y-порог — 80dp от начала Маркет-секции, кажется разумным; подтверждаем в макете.

---

## 7. Файлы для имплементации (delta к OFFERS_UX.md §«Файлы для имплементации»)

**Новые (специфично для этого документа):**
- `Mobile/components/market/MarketBackground.tsx` — двухслойный анимированный фон с интерполяцией по scrollY
- `Mobile/components/market/MarketHeader.tsx` — большой заголовок «МАРКЕТ ◉» + sticky-режим
- `Mobile/components/market/StoreCarousel.tsx` — горизонтальная витрина одного магазина (логотип header + AutoRail с MiniPriceBadge)
- `Mobile/components/market/StoreLogo.tsx` — компонент с fallback на monogram
- `Mobile/components/market/MarketSearchInput.tsx` — TextInput на blur background
- `Mobile/components/market/FormatChips.tsx` — горизонтальная полоса 4 чипов с ember-active state
- `Mobile/components/market/ExitMarketButton.tsx` — floating-кнопка «↑ Выйти из Маркета»
- `Mobile/app/market/store/[slug].tsx` — экран витрины одного магазина
- `Mobile/components/OfferDetailBottomSheet.tsx` — bottom-sheet полного сравнения (Фича 5)
- `Mobile/components/OffersDrawer.tsx` — компактный swipe-drawer на карточке вишлиста (Фича 5)
- `Mobile/components/WishlistRowWithOffers.tsx` — wrap-компонент для Swipeable (Фича 5)
- `Mobile/lib/marketStore.ts` — Zustand persist для `searchScrollY` и `hasSeenSwipeHint`

**Изменяемые (специфично для этого документа):**
- `Mobile/app/(tabs)/search.tsx` — главное изменение: добавить Маркет-секцию ниже Hot Stock-карусели + двухслойный фон + sticky header
- `Mobile/constants/theme.ts` — добавить `Gradients.marketBg` + (если нужно) bundled grain-texture
- `Mobile/lib/api.ts` — `getMarketStores()`, `getStoreListings(slug)`, `searchMarket(q, format, sort)`, `getOffersSummary(ids)`
- `Mobile/components/AutoRail.tsx` — расширить props (см. OFFERS_UX.md §4.5 + §2.9)
- `Mobile/assets/store-logos/` — каталог для логотипов

**Backend:**
- `Backend/app/api/market.py` — новые endpoints `/market/stores`, `/market/stores/{slug}/listings`, `/market/stores/{slug}/all`, `/market/search`
- `Backend/app/schemas/market.py` — `MarketStoreInfo`, `MarketSearchItem`
- `Backend/alembic/versions/YYYYMMDD_market_store_stats_view.py` — materialized view + cron refresh

---

## 8. Зависимости и порядок имплементации

**Sprint A (база, ~1 неделя):**
1. Backend: `GET /api/market/stores` + materialized view + Redis cache
2. Backend: `POST /api/records/offers/summary` (общий для Hot Stock и Маркета)
3. Mobile: `HotStockTag.tsx` + интеграция в RecordCard + hero-блок на детальном экране (Фича 2 целиком)

**Sprint B (Маркет, ~1.5 недели):**
4. Mobile: `MarketBackground.tsx` + интеграция в `search.tsx`, magic-transition, sticky-state в Zustand persist
5. Mobile: `MarketHeader.tsx` + sticky-collapse
6. Mobile: `FormatChips.tsx` + `MarketSearchInput.tsx`
7. Mobile: `StoreCarousel.tsx` + `StoreLogo.tsx` с fallback
8. Backend: `/api/market/stores/{slug}/listings` + `/api/market/search`
9. Mobile: результаты поиска (`RecordGrid` интеграция)
10. Mobile: `ExitMarketButton.tsx`
11. Mobile: `/market/store/[slug]` route

**Sprint C (Swipe-сравнение, ~3-4 дня):**
12. Backend: `?include_master_versions=true` к `/records/{id}/offers`
13. Mobile: `WishlistRowWithOffers.tsx` + `OffersDrawer.tsx`
14. Mobile: `OfferDetailBottomSheet.tsx`
15. Mobile: интеграция в `(tabs)/collection.tsx` (вишлист)

**Sprint D (Чип + уведомления, параллельно к B-C):**
16. Backend: `?in_stock_only=true` к `/records/search`
17. Mobile: чип в `search.tsx`
18. Backend: cron `notify_wishlist_offers()` + alt-version enum
19. Mobile: новые типы NotificationItem

**Что готово до начала Sprint A:**
- Hot Stock pill (Фича 2) тянет за собой большую часть данных-инфраструктуры; всё остальное переиспользует её summary-endpoint
- Маркет (Фича 4) — самостоятельный, зависит только от наличия данных (≥3 магазина с 1k+ листингами каждый)
- Swipe-drawer (Фича 5) — зависит от Hot Stock pill (он рендерится в header drawer'а)

---

## 9. Связанные документы

- [OFFERS_UX.md](OFFERS_UX.md) — родительский, оригинальная спека всех 5 фич
- [SHOPS_PARSING.md](SHOPS_PARSING.md) — Backend инфраструктура парсеров
- [PARSING.md](PARSING.md) — операционный README, форматы, cron, ресурсы

## 10. Что юзер донесёт отдельно

- 📎 PNG-фон для Маркета (референс уже прикреплён в чате — `Design/market/bg-reference.png`)
- 📎 PNG-мокапы стилистики (референс прикреплён — `Design/market/style-reference.png`)
- 📎 Логотипы магазинов (`korobkavinyla`, `plastinka_com`, `vinyl_ru`, `stoprobotvinyl`) — формат PNG transparent ≥256×256

---

**Готовность документа к передаче в Design Claude: ✅**

Открытые вопросы (§6) — для уточнения в макетной фазе, не блокеры.
