# Inventory дизайн-элементов Вертушки (M1 prep)

**Контекст:** ROADMAP M1 «Дизайн-система v2 + Маскот». Документ — **дескриптивный реестр** того, что в приложении есть прямо сейчас: какие визуальные поверхности, компоненты, токены, тексты, состояния и форматы. Вектор новой айдентики (тон палитры, темперамент маскота, иконографический стиль и т.д.) — отдельная задача и в этом документе **не задаётся**.

Цель — иметь полный список «вот всё, что нужно учесть, чтобы при смене айдентики ничего не выпало», который можно отдать в Claude Design как исходник для серии узких брифов.

**Источники:** [ROADMAP.md](../../../ROADMAP.md), [Mobile/](../../../Mobile/) (актуальная копия — `Desktop/Cursor/Вертушка`), формат брифов — [`docs/plans/design/RARITY_DESIGN_BRIEF.md`](RARITY_DESIGN_BRIEF.md).

---

## 1. Маскот: форматы и поверхности

Концепцию маскота не прорабатываем здесь — фиксируем только в каких форматах он будет нужен и где должен появиться.

### 1.1 Технические форматы

| Формат | Спека | Где живёт |
|---|---|---|
| App Icon iOS | 1024×1024 PNG, без прозрачности и скруглений (Apple HIG) | `Mobile/assets/images/icon.png` |
| Adaptive Icon Android | 1024×1024 foreground + 1024×1024 background, safe zone 66×66 dp | `Mobile/assets/images/adaptive-icon.png` |
| Favicon (web) | 48×48 / 96×96 PNG | `Mobile/assets/images/favicon.png` |
| Splash Screen | 1284×2778 base + Android variants, resizeMode contain | `Mobile/assets/images/splash-icon.png` |
| Loading-state in-app | Lottie / PNG-sequence / SVG-анимация под reanimated; ~220px (как VinylSpinner) | `Mobile/assets/mascot/loading/` (новая) |
| Empty-states | Static SVG / PNG ~280×280, прозрачный фон | `Mobile/assets/mascot/empty/` |
| Error-states | Static SVG / PNG ~240×240 | `Mobile/assets/mascot/error/` |
| Onboarding hero | 4 иллюстрации, 1080×1080 | `Mobile/assets/mascot/onboarding/` |
| Achievement-unlock | Lottie 120×120 | `Mobile/assets/mascot/celebrate.json` |
| Gift-booking banner | Static ~200×120 | `Mobile/assets/mascot/gift.png` |
| Google Play Feature Graphic | 1024×500 PNG | downstream-deliverable |
| App Store Screenshots | iPhone 6.7" (1290×2796) и 6.5" (1242×2688), 5–10 шт | downstream-deliverable |

### 1.2 Минимальный набор поз (по Roadmap §M1)

`idle` · `scanning` · `gift` · `achievement-unlock` · `empty-state` · `error` · `loading` · `celebrating` — 6–8 поз/состояний.

---

## 2. Дизайн-токены — что сейчас в `Mobile/constants/theme.ts`

### 2.1 Цветовая палитра (18 токенов)

- **Градиентная база:** `deepNavy #0A0B3B` → `royalBlue #3B4BF5` → `electricBlue #5B6AF5` → `periwinkle #8B9CF7` → `lavender #C5B8F2` → `softPink #F0C4D8` → `blushPink #F8E4EE`
- **Нейтральная база:** `background #FAFBFF`, `surface #F0F2FA`, `surfaceHover #E8EBFA`
- **Текст:** `text #0A0B3B`, `textSecondary #5A5F8A`, `textMuted #9A9EBF`
- **Состояния:** `error #E5484D`, `success #30A46C`, `warning #F5A623`
- **Границы:** `border #E0E3F0`, `divider #ECEEF7`
- **Спецэффекты:** `overlay rgba(10,11,59,0.5)`, `cardShadow`, `glassBg`

### 2.2 Параллельные палитры (живут вне theme.ts)

- **Ivory/cobalt** в `app/user/[username]/index.tsx` — публичный профиль PR-5: `ivory #F4EEE6`, `ivorySoft #F0EBE2`, `cobalt #3A4BE0`, `blush #F6C7D0`, `sky #BDD4FF`, `lavender #C9B8FF`, `ink #1B1D26`, `slate #6B7080`, плюс ~28 inline rgba.
- **Rarity-палитры** в `components/RarityAura.tsx` — gold (`#F4D27A / #B8860B / #6B4423`), silver/violet (`#C0C0D8 / #6B4DCE / #2A1F4E`), ember (`#FFB347 / #FF5E3A / #B22222`).
- **Onboarding blob-gradient** в `app/onboarding.tsx` — `#0F1B4C / #C5B8F2 / #F0C4D8 / #5B6AF5`.
- **Collection value dark gradient** в `app/collection/value.tsx` — `#2D3E8F / #4A6FDB / #6B5EC2 / #5B3FA0 / #8B4DA8 / #C75895`.
- **AutoRail** имеет собственный PALETTE-объект (ink/mute/lavender/periwinkle/cobalt).

### 2.3 Типография

13 стилей через **Inter** (5 весов: Regular 400 / Medium 500 / SemiBold 600 / Bold 700 / ExtraBold 800):

| Стиль | Размер | Вес | Line-height |
|---|---|---|---|
| heroTitle | 46 | Bold | 50 |
| display | 36 | ExtraBold | 40 |
| h1 | 34 | ExtraBold | 38 |
| h2 | 28 | Bold | 32 |
| h3 | 22 | Bold | 26 |
| h4 | 18 | SemiBold | 22 |
| body | 16 | Regular | 22 |
| bodyBold | 16 | SemiBold | 22 |
| bodySmall | 14 | Regular | 20 |
| button | 16 | SemiBold | 20 (letterSpacing +0.3) |
| buttonSmall | 14 | Medium | 18 |
| caption | 12 | Regular | 16 |

Также подключены: **RubikMonoOne-Regular** (используется в одном месте — лейбл в центре VinylSpinner), **SpaceMono-Regular** (загружается, но в коде не используется).

### 2.4 Spacing / Radius / Shadows / Sizes

- **Spacing:** `xs 4 / sm 8 / md 16 / lg 24 / xl 32 / xxl 48`.
- **BorderRadius:** `sm 10 / md 14 / lg 18 / xl 26 / full 9999`.
- **Shadows:** 4 preset'а — `sm` (elevation 2), `md` (elevation 4), `lg` (elevation 12), `tabBar` (elevation 14, специальный для нижней панели).
- **ComponentSizes:** `buttonHeight 56`, `buttonHeightSmall 44`, `inputHeight 56`, `tabBarHeight 84`, `headerHeight 56`, иконки 20/24/32.
- **Gradients (готовые наборы):** `blue` (royalBlue → electricBlue), `bluePink` (3 stops через lavender), `blueLight`, `overlay`, плюс 7 анимированных preset'ов и `darkPresets`.

### 2.5 Animation-константы (живут в коде компонентов, не в theme)

- VinylSpinner rotation: 1800ms linear infinite.
- RarityAura collectible: rotating gradient 8s + cover sweep-blink 10s.
- RarityAura limited: pulse 4s.
- RarityAura hot: pulse 2s + heat-haze breathing (opacity 0.4 ↔ 0.7).
- GlassTabBar indicator: spring zoom (1.0 → 1.25, damping 12, stiffness 180), opacity 0.5 → 1.0 за 200ms.
- RecordCard press: scale 0.96.
- VinylColorTag glow: 2.4s (1.2s in / 1.2s out), shadowOpacity 0.1 ↔ 0.55.
- SegmentedControl indicator slide: 200ms linear.
- AnimatedGradientText: 3500ms cycle между preset'ами.
- AutoRail auto-scroll: 30s loop, 2.5s resume delay после взаимодействия.

### 2.6 Хардкод-инвентарь (объёмы по `Mobile/`)

- ~50+ hex-цветов в 20+ файлах вне theme.
- ~95 строк rgba/hsla вне theme.
- ~257 строк с literal borderRadius / shadowOpacity / elevation в .tsx.
- Топ-файлы по плотности: `app/(tabs)/search.tsx` (1468 строк, ~38 хардкодов), `app/user/[username]/index.tsx` (1282, ~40+28 rgba), `app/profile.tsx` (1040, ~22), `components/RarityAura.tsx` (579, ~23), `app/onboarding.tsx` (466, ~12).

---

## 3. Иконография

- **Библиотека:** `@expo/vector-icons` Ionicons. Единственный источник иконок.
- **Объём использования:** ~100 уникальных иконок в ~30 файлах.
- **Часто используемые:** `disc` / `disc-outline`, `heart` / `heart-outline`, `star` / `star-outline`, `search-outline`, `scan-outline`, `person-outline`, `gift-outline`, `copy-outline`, `share-outline`, `ellipsis-vertical`, `chevron-forward`, `arrow-back-outline`, `calendar-outline`, `globe-outline`, `folder-outline`, `trash-outline`, `close`, `checkmark`, `checkmark-circle`, `alert-circle-outline`, `cash-outline`, `download-outline`, `notifications-outline`, `help-circle-outline`, `refresh-outline`, `pencil-outline`, `grid-outline`, `list-outline`, `filter-outline`, `play`, `pause`, `play-circle`, `time-outline`, `people-outline`, `person-add-outline`, `cloud-offline`, `map-outline`.
- **Размеры в коде:** 18–24 px в UI, 48–56 px в decorative-блоках.
- **Кастомные SVG:** в проекте нет (всё через Ionicons), кроме внутренней SVG-разметки винила в `VinylSpinner.tsx`.

---

## 4. Иллюстрации и ассеты

- `Mobile/assets/images/icon.png` — App Icon (~22 KB).
- `Mobile/assets/images/adaptive-icon.png` — Android adaptive (~17 KB).
- `Mobile/assets/images/splash-icon.png` — Splash (~17 KB).
- `Mobile/assets/images/favicon.png` — Favicon (~1.4 KB).
- `Mobile/assets/images/folder-placeholder.png` — placeholder папки (~736 KB, самый тяжёлый ассет).
- **Lottie-файлов нет.** **Видео нет.** **Кастомных SVG-иллюстраций нет.** **Background-картинок нет.**

---

## 5. Реестр компонентов

### 5.1 Визуально-нагруженные

| Компонент | Файл | Назначение | Варианты |
|---|---|---|---|
| RarityAura + TierLabel + TierFeatureBlock + TierCoverEffects | `components/RarityAura.tsx` | Подсветка редких пластинок | 3 активных тира (collectible / limited / hot), inline label, full aura wrapper, in-cover effects, detail-page block |
| RecordCard | `components/RecordCard.tsx` | Карточка пластинки | 3 variants: `compact` (overlay), `expanded` (card), `list` (row); selection mode; booked badge; gradient placeholder |
| RecordGrid | `components/RecordGrid.tsx` | FlatList container | 1 / 2 columns; rich или simple empty; loading footer; refresh control; staggered FadeInUp |
| VinylSpinner | `components/VinylSpinner.tsx` | Loading-винил | 4 типа vinyl (solid / cic / marble / splatter), translucent flag, 26 grooves, центральный лейбл «Вертушка / 33⅓ RPM», 1800ms rotation |
| GlassTabBar | `components/GlassTabBar.tsx` | Bottom nav | 3 таба (Search / Index / Collection), BlurView pill, spring zoom, gradient indicator |
| AnimatedGradientText | `components/AnimatedGradientText.tsx` | Анимированный текст-градиент | Cycling по 3–5 presets |
| GradientText | `components/GradientText.tsx` | Static gradient | Default `Gradients.blue`, custom colors |

### 5.2 UI-примитивы

| Компонент | Варианты |
|---|---|
| Button (`ui/Button.tsx`) | primary (gradient) / secondary / outline / ghost; default / small; loading / disabled |
| Input (`ui/Input.tsx`) | text / password (eye toggle) / multiline / email / numeric; default / focused / error / disabled; left/right icons; label + error text |
| Card (`ui/Card.tsx`) | elevated / flat / outlined; padding none/small/default/large |
| SegmentedControl (`ui/SegmentedControl.tsx`) | N segments; sliding indicator (200ms) |
| ActionSheet (`ui/ActionSheet.tsx`) | bottom sheet, items с иконкой и destructive-флагом |

### 5.3 Карточные / list-компоненты

| Компонент | Назначение |
|---|---|
| ArtistCard | Круглый аватар 100×100 + имя |
| VersionCard | Версия мастер-релиза: 80×80 cover + title + страна/год + label/cat# + format + tier label |
| UserListItem | Аватар 40×40 + displayName + @username |
| AutoRail | Горизонтальный авто-скроллящийся rail (30s loop), gradient overlay, своя PALETTE |

### 5.4 Layout / служебные

| Компонент | Назначение |
|---|---|
| Header | Top bar: back / inline title / display title (GradientText 36px) / avatar (40×40 gradient placeholder) |
| Section | Collapsible section с chevron + LayoutAnimation |
| OfflineBanner | Top banner с cloud-offline icon |
| ErrorBoundary | Centered fallback: alert-circle (52px) + title + message + retry |

### 5.5 Бейджи / теги / маркеры

| Компонент | Назначение |
|---|---|
| VinylColorTag | Pill с цветом винила, 60+ named палитр (Красный, Мятный и т.п.), glow pulse 2.4s |
| TierLabel (внутри RarityAura) | Inline 11px Bold цветной текст для тиров |
| Inline бейджи года/формата | Не вынесены в компонент — живут как View+Text в RecordCard и VersionCard |
| Booked badge в RecordCard | Gradient pill (royalBlue → periwinkle) + gift icon |

### 5.6 Модалки / overlays

| Компонент | Назначение |
|---|---|
| AddRecordsModal | Search + select + batch add |
| FolderPickerModal | Folder tree + create new |
| OnboardingOverlay | Tour overlay с highlight-targets и tooltip-bubbles |
| `lib/toast.ts` | Toast-функция (error / success / info), без визуального компонента — нативные алерты или inline текст |

### 5.7 Анимационные обёртки

- В `RecordCard` используется `AnimatedPressable` (scale 0.96 on press).
- В остальных местах — `TouchableOpacity` (activeOpacity 0.7–0.9).
- `react-native-reanimated` используется в RarityAura, VinylSpinner, GlassTabBar, RecordGrid (FadeInUp), AnimatedGradientText, VinylColorTag, SegmentedControl.

---

## 6. Реестр экранов (`Mobile/app/`)

### 6.1 Tab navigation

`(tabs)/_layout.tsx` → GlassTabBar: Поиск / Сканер / Коллекция.

### 6.2 Search — `(tabs)/search.tsx`

Header + input + clear; фильтры (Тип / Страна / Год); история поиска (горизонтальный scroll); 4 раздела результатов (Releases / Masters / Artists / Users); RecordGrid 3-col.
- **Empty:** «Ничего не найдено».
- **Loading:** ActivityIndicator.

### 6.3 Scanner — `(tabs)/index.tsx`

CameraView; Segmented (Штрихкод / Фото); кнопка «Сфотографировать»; ShowResults модалка с списком найденных + RecordCard'ами + кнопками Открыть / Добавить / В вишлист.
- **Empty:** «Винил с таким штрихкодом не найден в базе Discogs».
- **Toast success:** «Винил / CD / Кассета / Бокс-сет добавлен(а) в коллекцию».

### 6.4 Collection — `(tabs)/collection.tsx`

Header (avatar slot слева); Segmented (В наличии / Вишлист); меню (grid/list toggle, фильтр формата, папки, выбрать-режим); RecordGrid с рарити-аурами; card «Стоимость коллекции» → `/collection/value`.
- **Empty:** «Нет ничего в коллекции» / «Вишлист пуст».
- **Selection:** checkbox'ы + bottom action sheet (Удалить / Переместить в папку).

### 6.5 Profile (modal) — `app/profile.tsx`

Header «Профиль» (AnimatedGradientText) + close-X; avatar + edit; @username + display name + email; статистика 2×2 (collection / wishlist / following / followers); share-link card (copy / share); «Я дарю» rail (GiftGivenItem); settings-list (Стоимость / Edit profile / Экспорт / Уведомления / Планы / Помощь / Запустить онбординг); Logout; Danger Zone (Delete account).
- **Empty «Я дарю»:** banner «Дари друзьям музыку — Забронируй пластинку из вишлиста друга».
- **ActionSheetIOS:** аватар (Галерея / Камера / Удалить).
- **Alerts:** export type, отмена бронирования, удаление аккаунта.

### 6.6 Record detail — `record/[id].tsx`

Cover (full-width 1:1) → Title (display) → Artist card (clickable) → Meta-row (год / формат / страна / vinyl-color) → Издание (label + cat#) → VinylSpinner + disclaimer (если is_colored) → Жанр + Style → секция «Особенности» (TierFeatureBlock × N для активных тиров) → «Примерная стоимость» (RUB range + USD note + курс + множитель) → Tracklist → Bottom actions (BlurView).
- **Bottom states:** «Добавлено» (X копий) + ... menu / «Добавить» + «В вишлист».
- **Loading:** central VinylSpinner.
- **Error:** alert-circle + текст + back.

### 6.7 Artist — `artist/[id].tsx`

Hero + name + filter chips (Альбомы / EP / Синглы) + сортировка + RecordGrid 3-col.
- **Empty:** «Релизов не найдено».

### 6.8 Master + Versions — `master/[id]/{index,versions}.tsx`

Index: cover + title + artist + год + жанр + tracklist + кнопка «Все версии».
Versions: фильтр по формату + список VersionCard + pagination.

### 6.9 Folder — `folder/[id].tsx`

Header + folder name + ... menu (Переименовать / Добавить пластинки / Удалить папку / Удалить выбранные). RecordGrid + selection.
- **Empty:** «Папка пуста».

### 6.10 Public profile — `user/[username]/index.tsx`

Avatar + name + статистика + Follow button; Segmented (Коллекция / Вишлист); FormatFilter chip; view toggle; RecordGrid + AutoRail для highlights; animated vinyl decoration.
- **Параллельная палитра ivory/cobalt — живёт здесь.**

### 6.11 Social list — `social/list.tsx`

Segmented (Подписки / Подписчики) + UserListItem список.
- **Empty:** «Пока нет подписчиков» / «Вы ни на кого не подписаны».

### 6.12 Settings (3 экрана)

- `settings/edit-profile.tsx` — display name, bio, до 4 favorites (star toggle), update.
- `settings/notifications.tsx` — VinylToggle'ы по типам уведомлений + permission request + Linking «Перейти в настройки iOS».
- `settings/share-profile.tsx` — VinylToggle'ы видимости (collection/wishlist/prices/year/format) + favorites.

### 6.13 Collection value — `collection/value.tsx`

AnimatedValue (0 → итог за 2000ms) RUB + USD; самая дорогая пластинка card; top-10 list.
- **Свой dark gradient preset вне theme.**

### 6.14 Onboarding — `onboarding.tsx`

4 welcome-слайда: Animated gradient bg + 3 blobs + BlurView (Android RGBA fallback) + Ionicon hero + eyebrow (uppercase 11px) + title (36px Bold) + body (16px) + dot paginator + CTA («Далее» / «Поехали!») + Skip top-right.
- Слайды: 1) Знакомство (disc-outline), 2) Каталог (search-outline), 3) Сканер (scan-outline), 4) Подарки (gift-outline).
- 10-шаговый интерактивный тур через `OnboardingOverlay` + `useTourTarget` hook.

### 6.15 Auth (5 экранов)

`(auth)/login.tsx` / `register.tsx` / `verify-code.tsx` / `forgot-password.tsx` / `reset-password.tsx`.
Logo (LinearGradient синий→фиолетовый + disc icon) + название «Вертушка» + tagline + inputs.

### 6.16 404 — `+not-found.tsx`

disc-outline (64px, grey) + «Страница не найдена» + кнопка «Назад».

---

## 7. Информационные блоки и описания

### 7.1 Карточка пластинки (record/[id])

10 секций: Cover · Title · Artist (clickable card) · Meta-row (year / format / country / vinyl-color) · Издание (label / catalog#) · VinylSpinner + disclaimer (если is_colored) · Жанр + Style · Особенности (рарити TierFeatureBlock'ами) · Примерная стоимость (диапазон) · Tracklist · Bottom actions.

### 7.2 Описания тиров рарити (видимый юзер-копирайт)

Активные в продукте — 3 тира:

| Тир | Label | Описание (in-app) | Анимация | Палитра |
|---|---|---|---|---|
| collectible | «Коллекционка» | «Дорогая (≥$100), почти не продаётся, мало у кого есть» | rotating gradient 8s + cover sweep-blink 10s | gold / champagne / bronze |
| limited | «Лимитка» | «Специальное издание» (Test Pressing / Promo / Numbered / White Label) | violet pulse 4s | silver / violet / indigo |
| hot | «Популярно» / «HOT» | «Высокий спрос на Discogs» | ember pulse 2s + heat-haze breathing | amber / coral / red |

В архиве (флаги в коде есть, в UI скрыты): `first_press`, `canon`.

**Точки UI с рарити:** карточка в коллекции (grid + list), карточка в поиске, карточка на публичном профиле, секция «Особенности» на детали, VersionCard.

### 7.3 Профиль и статистика

- Аватар-tap → ActionSheetIOS (Галерея / Камера / Удалить).
- Статистика 2×2: «В коллекции» / «В вишлисте» / «Подписки» / «Подписчики».
- Card «Ваш профиль» с URL `https://vinyl-vertushka.ru/@username`, кнопки Copy / Share.
- «Я дарю» — горизонтальный rail GiftGivenItem (cover + получатель + статус «Активно» / «Вручено»), swipe-to-delete.
- Settings list: Стоимость коллекции / Редактировать профиль / Экспорт данных / Уведомления / Планы Вертушки / Помощь / Запустить онбординг.
- Logout button.
- Danger Zone: «Опасная зона» + «Аккаунт и все данные будут безвозвратно удалены через 30 дней» + «Удалить аккаунт».
- Версия: «Вертушка v1.0.0».

### 7.4 Цены

- Карточка «Примерная стоимость»: «от X · ~Y · до Z» (тысячи через пробел).
- Caption: «Discogs: $XX · курс YY ₽ · × Z.ZZ».
- В Collection value: огромный AnimatedValue RUB + USD итог + top-10 most expensive.

### 7.5 Подарки (gift-booking)

- В профиле — горизонтальный rail GiftGivenItem (cover + аватар получателя + статус).
- Empty-banner — «Дари друзьям музыку — Забронируй пластинку из вишлиста друга».

---

## 8. Ачивки (M5, иконки появятся в M1)

**Источник:** [`docs/plans/achievements/PLAN_ACHIEVEMENTS.md`](../achievements/PLAN_ACHIEVEMENTS.md). 84 ачивки, разбитые на категории. Активный MVP-этап — категории A + B (14 ачивок).

**Категории требующие иконок:**

- 🎵 A — Первые шаги (foundation)
- 📚 B — Размер коллекции (vertical scale)
- 💎 C — Редкости
- 🌍 D — География
- 📅 E — Эпохи
- 🎼 F — Жанры и стили
- 💿 G — Форматы
- 🏛 H — Дискографии и мастера
- 🛠 I — Состояние и забота
- 🎁 J — Подарки
- 👥 K — Социальная сеть
- 💰 L — Стоимость коллекции
- 🔍 M — Открыватель и поисковик
- 🥚 N — Easter eggs
- 🎂 O — Юбилеи
- (Расширения) P — Цвет винила deep, Q — Public profile, R — Фото, S — Множ. коллекции, T — Wishlist deep, U — Gift edge cases, V — Discography deep, W — Search deep.

**Дизайн-сущности по PLAN_ACHIEVEMENTS:**

- Зал трофеев (UI-экран ачивок) с прогресс-барами «как канавки пластинки — спираль от центра к краю».
- 14 иконок MVP (A1–A7, B1–B7).
- Анлок-анимация (toast / overlay) с маскотом «celebrating».
- Push-уведомление визуал.
- Бейдж в профиле «X из Y ачивок».

---

## 9. Tone of voice + копирайт inventory

**Принципы tone-of-voice (из ROADMAP §0):** «Хранитель полки» — тёплый, ироничный, не детский. Не «коллекционер», а «Хранитель Сторон Б».

**Категории копирайта (объёмы):**

| Тип | Примерный объём | Где живёт |
|---|---|---|
| Empty-state тексты | ~15 строк | Inline в экранах |
| Toast success / error / info | ~30 строк | Inline + `lib/toast.ts` |
| Описания рарити-тиров | 3 строки | `components/RarityAura.tsx` константы |
| Flavor texts ачивок | 84 строки | `docs/plans/achievements/PLAN_ACHIEVEMENTS.md` |
| Onboarding 4 welcome (eyebrow/title/body) | 12 фраз | `app/onboarding.tsx` |
| Onboarding tour-tooltips | 10 шагов | `OnboardingOverlay` |
| Settings-лейблы | ~12 строк | `app/profile.tsx`, `settings/*.tsx` |
| Disclaimers | ~5 строк | `record/[id].tsx`, `profile.tsx` |
| Auth-формы (errors / labels / CTA) | ~20 строк | `(auth)/*.tsx` |
| Action sheets / Alert.prompt | ~10 строк | `profile.tsx`, `folder/[id].tsx` и др. |
| Push-уведомления | будущее (M5) | — |

**Итого:** ~80–100 уникальных русских строк интерфейса, ~84 flavor-текста ачивок.

---

## 10. Empty / Loading / Error матрица (где сейчас стоят и где нужны иллюстрации маскота)

| Экран | Empty | Loading | Error |
|---|---|---|---|
| Search | «Ничего не найдено» (text) | ActivityIndicator | — |
| Scanner | «Винил с таким штрихкодом не найден» (модалка) | ActivityIndicator | Нет permission / ошибка распознавания |
| Collection (В наличии) | «Нет ничего в коллекции» (text + disc-outline) | ActivityIndicator | — |
| Collection (Вишлист) | «Вишлист пуст» (text) | ActivityIndicator | — |
| Record detail | — | central VinylSpinner | alert-circle + сообщение + back |
| Artist | «Релизов не найдено» | ActivityIndicator | — |
| Master / Versions | «Версий не найдено» | ActivityIndicator | Toast «Не удалось загрузить» |
| Folder | «Папка пуста» | ActivityIndicator | Toast |
| Public profile | «Нет записей в коллекции» / «Вишлист пуст» | ActivityIndicator | — |
| Social list | «Пока нет подписчиков» / «Вы ни на кого не подписаны» | ActivityIndicator | — |
| Profile «Я дарю» | banner «Дари друзьям музыку» | ActivityIndicator | — |
| Settings (любой) | — | ActivityIndicator | Toast |
| Onboarding | — | — | — |
| Auth | — | — | inline validation + «Ошибка входа» |
| 404 / not-found | disc-outline + «Страница не найдена» | — | — |
| Achievement unlock (M5) | — | — | — (toast при анлоке) |
| Splash | — | static splash | — |

---

## 11. Карта поверхностей маскота

| # | Поверхность | Экран / Состояние |
|---|---|---|
| 1 | App Icon iOS / Android | system level |
| 2 | Splash | launch |
| 3 | Onboarding slide 1 | welcome / Знакомство |
| 4 | Onboarding slide 2 | catalog / Каталог |
| 5 | Onboarding slide 3 | scanner / Сканер |
| 6 | Onboarding slide 4 | gifts / Подарки |
| 7 | Collection empty | «Нет ничего в коллекции» |
| 8 | Wishlist empty | «Вишлист пуст» |
| 9 | Folder empty | «Папка пуста» |
| 10 | Search no results | «Ничего не найдено» |
| 11 | Search loading | ActivityIndicator-замена |
| 12 | Scanner no permission | error |
| 13 | Scanner not found | модалка результатов пуста |
| 14 | Record detail loading | central spinner-замена |
| 15 | Record detail error | alert-circle screen |
| 16 | Artist empty | «Релизов не найдено» |
| 17 | Public profile empty | пусто (чужая полка) |
| 18 | Social list empty | «Пока нет подписчиков» |
| 19 | Profile «Я дарю» empty | banner «Дари друзьям музыку» |
| 20 | Profile «Я дарю» loading | rail loading |
| 21 | 404 / not-found | disc + текст |
| 22 | Achievement unlock | toast / overlay (M5) |
| 23 | Gift booking success | toast / banner |
| 24 | Settings → Help (placeholder) | — |
| 25 | App Store feature graphic | downstream-deliverable |
| 26 | App Store screenshots (5–10) | downstream-deliverable |

---

## 12. Анимации, которые сейчас работают на айдентику

- **RarityAura collectible** — rotating gradient 8s + sweep-blink 10s.
- **RarityAura limited** — pulse 4s.
- **RarityAura hot** — pulse 2s + heat-haze breathing на cover.
- **VinylSpinner rotation** — 1800ms linear infinite, реалистичная пластинка с грэвюром, центральный лейбл.
- **GlassTabBar indicator** — spring zoom (1.0 → 1.25) + opacity fade.
- **RecordCard press** — scale 0.96.
- **VinylColorTag glow** — 2.4s pulse через shadowOpacity / shadowRadius.
- **AnimatedGradientText** — 3500ms cycling по preset'ам.
- **SegmentedControl indicator** — 200ms slide.
- **AutoRail auto-scroll** — 30s loop.
- **RecordGrid FadeInUp** — staggered 50ms на enter.
- **Onboarding blob-gradient** — анимированный фон с 3 движущимися blob'ами.

---

## Файлы-источники для дальнейших брифов

- [`Mobile/constants/theme.ts`](Mobile/constants/theme.ts) — все токены.
- [`Mobile/app.json`](Mobile/app.json) — App Icon / Splash / bundle конфигурация.
- [`Mobile/assets/`](Mobile/assets/) — текущие ассеты.
- [`Mobile/components/`](Mobile/components/) — 22 компонента.
- [`Mobile/app/`](Mobile/app/) — 25 экранов.
- [`docs/plans/achievements/PLAN_ACHIEVEMENTS.md`](../achievements/PLAN_ACHIEVEMENTS.md) — каталог 84 ачивок.
- [`docs/plans/collection/RARITY_BADGES_PLAN.md`](../collection/RARITY_BADGES_PLAN.md) — рарити-теги (актуальная логика — 3 тира, canon и first_press в архиве).
- [`docs/plans/design/RARITY_DESIGN_BRIEF.md`](RARITY_DESIGN_BRIEF.md) — формат брифа, на который ориентируются будущие пакеты для Claude Design.
- [`docs/plans/design/VINYL_SPINNER_PLAN.md`](VINYL_SPINNER_PLAN.md) — план VinylSpinner / VinylColorTag.
- [`ROADMAP.md`](../../../ROADMAP.md) — общий контекст M1.
