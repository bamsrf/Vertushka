# Design System v2 — мастер-флоу пакетов для Claude Design

## Контекст

`docs/plans/design/PLAN_DESIGN_SYSTEM_V2.md` — это **inventory**: что в продукте есть прямо сейчас (токены, экраны, состояния, копирайт). Он описывает «что нужно учесть, чтобы при смене айдентики ничего не выпало», но не задаёт **порядок** работы и не превращён в исполнимые брифы.

Этот документ — следующий слой: **flow**, в котором inventory разворачивается в серию пакетов для Claude Design так, чтобы новая айдентика собралась как **система**, а не набор разрозненных экранов. Маскот в этот pipeline не входит — у него отдельная ветка работы. Здесь мы лишь **резервируем под него места** (форматы App Icon / Splash / Loading / Empty / Error / Onboarding) в спеке системы, чтобы любой маскот, пришедший позже, лёг без переделок.

**Желаемый итог pipeline:**
- Единый дизайн-язык (палитра, типографика, motion, иконография), задокументированный для разработки.
- Все ключевые экраны и состояния спроектированы как часть системы.
- `Mobile/constants/theme.ts` — единственный источник токенов (ROADMAP M1 acceptance).
- Параллельные палитры (`ivory/cobalt` в публичном профиле, `RarityAura`-палитры, dark gradient в `collection/value`, AutoRail PALETTE, onboarding blob-gradient) либо нормализованы в систему, либо явно зафиксированы как именованные подсистемы.

---

## Принципы pipeline

1. **Один бриф = одна решаемая дизайн-задача.** Claude Design не имеет общей памяти между сессиями. Каждый пакет должен быть самодостаточным: inputs, constraints, deliverables, acceptance.
2. **Foundation → Components → Surfaces → States → Handoff.** Жёсткий порядок. Любой бриф вниз по стеку зависит от утверждённых верхних. Не запускать B3, пока B1+B2 не закрыты.
3. **Каждый бриф заканчивается tokenized output.** Палитры/размеры/радиусы/duration отдаются числами, а не «вот такой цвет». Иначе handoff в `theme.ts` станет угадайкой.
4. **Маскот резервируется, не проектируется.** В B1 фиксируем форматы и слоты, но не визуальную концепцию.
5. **Шаблон брифа — `RARITY_DESIGN_BRIEF.md`.** Все пакеты пишем в той же структуре (вводная «что приложить» + самостоятельный prompt + tech-constraints + список мокапов), чтобы команде/дизайнеру было одно ментальное окно.
6. **Cleanup — отдельный технический пакет в конце.** Дизайнер не должен вычищать `~50 hex` и параллельные палитры. Сначала чистая спека, потом миграция.

---

## Pipeline (6 пакетов: 5 дизайн-брифов + 1 технический)

```
B1 Brand Foundation
       │
       ├──► B2 Iconography & Visual Vocabulary
       │            │
       └──► B3 Components & Primitives
                    │
                    ▼
             B4 Surface Compositions
                    │
                    ▼
             B5 States Layer (empty/loading/error)
                    │
                    ▼
             H1 Token Handoff & Cleanup
```

---

### B1. Brand Foundation v2

**Цель.** Зафиксировать базовый язык: палитру, типографику, шкалы spacing/radius/shadows, motion principles. Это вход для всего, что ниже.

**Inputs (что приложить дизайнеру):**
- `Mobile/constants/theme.ts` целиком.
- Раздел §2 из inventory (текущие 18 цветов, 13 типографических стилей, scales).
- Скриншоты текущей айдентики: Collection grid, Record detail, Onboarding slide 1, Public profile (`user/[username]`), Auth login. Минимум 5.
- Зафиксированный список параллельных палитр (§2.2 inventory) с пометкой, какие из них нужно унифицировать, а какие оставить как именованные подсистемы (rarity tiers — почти наверняка остаются).
- Tone-of-voice референс из ROADMAP §0 («Хранитель полки», тёплый/ироничный/не детский).

**Ключевые вопросы, которые бриф должен закрыть:**
- Базовая палитра: сколько brand-цветов, сколько neutral, как маппятся на `surface / surfaceHover / border / divider / overlay`. Решение про `deepNavy → blushPink` градиентную ось — остаётся ли как ось бренда или редуцируется.
- Состояния (`error / success / warning`) — пересмотреть в новой палитре, чтобы они не выпадали.
- Типографика: остаёмся на Inter или меняем primary? Что с `RubikMonoOne` (один use-case в VinylSpinner) и `SpaceMono` (загружается, не используется — выкинуть). Шкала размеров — оставляем 13 стилей или сокращаем.
- Motion principles: 3–4 easing-кривые + 3 duration-tier'а (например, `instant 120ms / standard 220ms / expressive 400–800ms`). На них дальше опираются все компоненты.
- Светлая/тёмная тема: только light как сейчас, или dark как обязательство.

**Deliverables:**
- Палитра: ≥12 hex с ролями, документированными словами («surface для карточек на нейтральном фоне», не «#XXX»).
- Type scale: размер / вес / line-height / letter-spacing для каждого стиля.
- Spacing scale (4/8-grid), radius scale, shadow presets — как числа.
- Motion principles: easing-кривые (cubic-bezier), duration-tier'ы, правила «когда какой».
- Mood-board / референсы: 6–10 визуальных референсов с подписями, что именно из них берём.
- **Слоты под маскота:** App Icon 1024², Splash 1284×2778, Loading-state ~220px, Empty ~280px, Error ~240px, Onboarding 1080² ×4, Achievement Lottie 120². В B1 они только размечаются как «здесь будет иллюстрация» с указанием безопасной зоны и фона.

**Acceptance:**
- Палитра проходит контраст-тест AA для основных пар text/surface.
- Каждый токен имеет имя, hex, и описание роли (≥1 предложение).
- Motion principles описаны словами, а не «плавно».

**Затрагиваемые файлы (после H1):** `Mobile/constants/theme.ts`.

---

### B2. Iconography & Visual Vocabulary

**Цель.** Выбрать единый иконографический язык и описать декоративный визуальный словарь (винил, грэвюр, рарити-эффекты).

**Inputs:**
- §3 inventory (~100 уникальных Ionicons в ~30 файлах, размеры 18–24 / 48–56).
- Утверждённое B1 (палитра, motion principles).
- Скриншоты: GlassTabBar, Header, Settings list, RarityAura все 3 тира, VinylSpinner, AutoRail.

**Ключевые вопросы:**
- Остаёмся на Ionicons или едем на свой icon set? Ionicons даёт скорость, кастом — узнаваемость. Если меняем — нужен полный набор тех ~100 иконок (декабинаризованный список из §3 inventory) и решение, делать как `expo-symbols` / SVG sprite / иконочный шрифт.
- Стилевой выбор: line vs filled vs duotone. Вес штриха. Размерные пресеты (18 / 24 / 32).
- Декоративные паттерны винила: нужны ли «канавки» как часть языка (используется в VinylSpinner и предложено в `PLAN_ACHIEVEMENTS` для прогресс-баров)?
- Rarity-тиры: пересмотр трёх палитр (`gold/champagne/bronze`, `silver/violet/indigo`, `amber/coral/red`) под новую базу. Решение — оставить как именованную подсистему `rarity.*` в токенах.
- Графика для пустого пространства, разделителей, illustration-frames (для маскота позже).

**Deliverables:**
- Стайлгайд иконок: weight, corner radius, оптическая сетка, размерные пресеты.
- Если кастом — полный набор `~100` иконок в SVG с именами, маппинг старое-Ionicons → новое.
- Подсистема `rarity.*`: 3 тира × {primary / secondary / accent / glow / animation timing} в токенах.
- Декоративные ассеты (грэвюр-pattern, divider-style) если они становятся частью языка.
- Мокап: одна страница «иконы в действии» — Header, GlassTabBar, Settings, Record detail, Empty state placeholder.

**Acceptance:**
- Иконы читаются на 18px и на 56px без потери смысла.
- Rarity-палитры сохраняют различимость трёх тиров для дальтоников (запасной канал — иконка-маркер или паттерн).

**Затрагиваемые файлы:** все экраны с иконками; `components/RarityAura.tsx`; новая папка `Mobile/assets/icons/` если кастом.

---

### B3. Components & Primitives

**Цель.** Перерисовать компонентную библиотеку на новой палитре + motion + иконах. Это последний слой, который ещё «без контента» — экранов мы пока не трогаем.

**Inputs:**
- §5 inventory (полный реестр компонентов с текущими вариантами).
- Утверждённые B1 + B2.
- Скриншоты текущих компонентов в трёх состояниях (default / pressed / disabled, где применимо).

**Скоуп — два слоя:**

1. **UI-примитивы** (`Mobile/components/ui/`):
   - `Button` — 4 варианта × 2 размера × 3 состояния (default / loading / disabled). Gradient-fill для primary с новой палитры.
   - `Input` — text / password / multiline / email / numeric × {default / focused / error / disabled}, левая/правая иконка, label + error.
   - `Card` — elevated / flat / outlined × 4 padding-уровня.
   - `SegmentedControl` — N сегментов, sliding indicator (motion из B1 standard-tier).
   - `ActionSheet` — bottom sheet с destructive-флагом.

2. **Визуально-нагруженные** (`Mobile/components/`):
   - `RecordCard` — три варианта (`compact` / `expanded` / `list`), selection mode, booked badge, gradient-placeholder.
   - `RecordGrid` — 1/2 col, rich/simple empty (placeholder под маскота из B5), loading footer, refresh, FadeInUp.
   - `RarityAura + TierLabel + TierFeatureBlock + TierCoverEffects` — переутверждение с палитрами из B2.
   - `VinylSpinner` — 4 vinyl-типа, translucent flag, лейбл по центру. Решение: остаётся как loader или уступает место маскоту в B5.
   - `VinylColorTag` — 60+ named палитр + glow pulse.
   - `GlassTabBar` — 3 таба, BlurView pill, spring zoom, gradient indicator.
   - `Header` — back / inline title / display title (GradientText) / avatar slot.
   - `AnimatedGradientText`, `GradientText`, `AutoRail` — переутвердить под новые цвета и motion.

**Deliverables:**
- Для каждого компонента: anatomy + все варианты + все состояния + spacing-разметка + motion-спека (duration / easing / property).
- Один контактный лист «все компоненты на одной странице».
- Tokens-маппинг: каждый компонент → какие токены из B1 он использует.

**Acceptance:**
- Все варианты читаются в `~360px` ширины (узкий iPhone).
- Touch-targets ≥44pt.
- Каждый компонент покрыт тремя состояниями минимум.

**Затрагиваемые файлы:** `Mobile/components/ui/*`, `Mobile/components/{RecordCard,RecordGrid,RarityAura,VinylSpinner,VinylColorTag,GlassTabBar,Header,AnimatedGradientText,GradientText,AutoRail}.tsx`.

---

### B4. Surface Compositions

**Цель.** Собрать компоненты в экраны и проверить, что система работает на реальных композициях. Здесь же разруливается параллельная палитра `ivory/cobalt` (`user/[username]/index.tsx`) и dark gradient в `collection/value`.

**Inputs:**
- §6 inventory (полный реестр экранов).
- Утверждённые B1+B2+B3.
- Скриншоты текущих экранов (по 1 на каждый из приоритетных).

**Скоуп — 7 ключевых поверхностей** (выбраны как покрывающие основные паттерны):

1. **Collection** (`(tabs)/collection.tsx`) — ритм grid'а с rarity-аурами, segmented, card «Стоимость коллекции», selection-mode.
2. **Search** (`(tabs)/search.tsx`) — input + chip-фильтры + история + 4 раздела результатов. Самый плотный экран (1468 строк, ~38 хардкодов) — отдельная задача.
3. **Record detail** (`record/[id].tsx`) — 10 секций, секция «Особенности» с TierFeatureBlock, цена, tracklist, BlurView bottom actions.
4. **Profile (modal)** (`profile.tsx`) — header + avatar + stats 2×2 + share-card + «Я дарю» rail + settings list + danger zone.
5. **Public profile** (`user/[username]/index.tsx`) — **место решения по параллельной палитре `ivory/cobalt`**: либо она становится «alternate skin» для чужих профилей и закрепляется в системе, либо нормализуется в основную.
6. **Onboarding** (`onboarding.tsx`) — 4 welcome-слайда с blob-gradient + interactive tour overlay.
7. **Collection value** (`collection/value.tsx`) — **место решения по dark-gradient preset**: становится ли dark-режим частью системы или это исключение для одного экрана.

**Deliverables:**
- Для каждого экрана: 1 default-state + 2–3 ключевых под-state (selection / loading / filled / etc.).
- Mobile-mockup в реальных пропорциях iPhone 13 mini (375×812) и Pro Max (430×932) — два размера на каждый экран.
- Решение по параллельным палитрам (см. экраны 5 и 7) с обоснованием.
- Анимационная раскадровка для одного «hero»-экрана (Record detail) — 4–6 кадров для transition между states.

**Acceptance:**
- Любой компонент на экранах ссылается на варианты из B3, без локальных hex.
- Параллельные палитры либо удалены, либо явно повышены до именованных подсистем в токенах.
- Auth-экраны и второстепенные экраны (Artist, Master, Versions, Folder, Settings/*) выводимы из этого набора паттернов и не требуют отдельного брифа.

**Затрагиваемые файлы:** все экраны под `Mobile/app/`.

---

### B5. States Layer (empty / loading / error)

**Цель.** Спроектировать матрицу 26 поверхностей из §11 inventory (карта поверхностей маскота) и §10 (empty/loading/error матрица) — но **без рисования самого маскота**. Задача — описать слоты, копирайт, композицию.

**Inputs:**
- §10 + §11 inventory.
- §7 (текущий копирайт empty/loading/error).
- Утверждённые B1+B2+B3+B4.
- Tone-of-voice ROADMAP §0.

**Скоуп:**
- **Empty states** — 11 поверхностей (Collection / Wishlist / Folder / Search / Artist / Public profile / Social list / «Я дарю» / 404 / Scanner not-found / Achievement empty в M5).
- **Loading states** — замена `ActivityIndicator` на единый паттерн. Решение: Vinyl-loader (текущий VinylSpinner) или новый дефолтный лоадер с слотом под маскота.
- **Error states** — 4 поверхности (Record detail / Auth / Toast / ErrorBoundary global) + Scanner permission denied + offline.

**Deliverables:**
- Композиционный темплейт «empty-state»: иллюстрация-слот (размер, безопасная зона, фон) + headline (typography из B1) + body + CTA (Button из B3).
- То же для loading и error.
- Карта 26 поверхностей: для каждой — какой темплейт применить, какой headline+body, что-cTA.
- Ревизия копирайта: каждая текстовая строка проходит через tone-of-voice фильтр. Готовый список замен (старая → новая).
- Чёткий список того, что нужно от маскот-брифа (8 illustration-slots с размерами и эмоциями), но без самих иллюстраций.

**Acceptance:**
- Каждый из 26 слотов имеет темплейт + готовый копирайт + список ассетов (с указанием «требует маскот-иллюстрацию №X»).
- Loading/Error/Empty визуально отличимы в первый взгляд (не сливаются).

**Затрагиваемые файлы:** все экраны (inline empty-states); `app/+not-found.tsx`; `lib/toast.ts`; `components/ErrorBoundary` (если будет вынесен), `OfflineBanner.tsx`.

---

### H1. Token Handoff & Cleanup (технический пакет, не для дизайнера)

**Цель.** Перенести всё, что собрала дизайн-команда, в `Mobile/constants/theme.ts` и вычистить хардкод. Это инжиниринговая задача, исполняется в коде.

**Inputs:**
- Все утверждённые deliverables B1–B5.
- §2.6 inventory (хардкод-инвентарь): ~50 hex в 20+ файлах, ~95 rgba/hsla, ~257 borderRadius/shadowOpacity/elevation literals.

**Состав работы:**
1. **Расширить `theme.ts`** новыми токенами из B1: палитра, types, motion-presets (cubic-bezier + duration-tiers), `rarity.*` подсистема из B2, опциональный `darkPresets` если B4 закрепил dark-режим.
2. **Заменить параллельные палитры:**
   - `ivory/cobalt` в `app/user/[username]/index.tsx` → решение из B4 (либо `theme.skins.ivory.*`, либо удалить и заменить на `theme.colors.*`).
   - `dark gradient` в `app/collection/value.tsx` → решение из B4.
   - `AutoRail` PALETTE → токены.
   - `onboarding` blob-gradient → токены.
   - `RarityAura` локальные палитры → `theme.rarity.*`.
3. **Вычистить хардкод:** `grep -rn "#[0-9a-fA-F]\{3,6\}\|rgba(\|hsla(" Mobile/ --include="*.tsx" --include="*.ts"` должен возвращать только `Mobile/constants/theme.ts`.
4. **Animation-константы** (§2.5 inventory) — централизовать в `theme.motion.*` (1800ms vinyl, 8s/4s/2s rarity, spring presets, etc.). Компоненты ссылаются по имени.
5. **Шрифты:** удалить неиспользуемый `SpaceMono-Regular`. Решить судьбу `RubikMonoOne` (один use-case в VinylSpinner — либо оставить как `theme.typography.label`, либо заменить на Inter ExtraBold).
6. **Ассет-папки** под маскота (`Mobile/assets/mascot/{loading,empty,error,onboarding}/`) создаются пустыми с `.gitkeep`, чтобы импорты можно было заранее прописать.

**Acceptance:**
- `grep` не находит hex/rgba вне `theme.ts` (acceptance из ROADMAP M1).
- Удаление токена из `theme.ts` ломает TypeScript-сборку (т.е. нет дублирующих локальных определений).
- Тесты сборки проходят: `cd Mobile && npm run typecheck` (или эквивалент) + `expo start --no-dev` запускается без ошибок.
- Все 7 ключевых экранов из B4 рендерятся идентично mockup'ам (визуальная diff-проверка вручную на симуляторе iOS + Android).

**Затрагиваемые файлы:** `Mobile/constants/theme.ts`, все .tsx из топ-листа §2.6 inventory (+ остальные с хардкодом), `Mobile/app.json` (шрифты), `package.json` если выкидываем шрифт.

---

## Зависимости и параллелизация

```
B1 ──► B2  ─┐
       │    │
       └────┴──► B3 ──► B4 ──► B5 ──► H1
```

- **B2 и B3 можно запустить параллельно** после утверждения B1, если есть ресурсы у дизайнера. Но B3 ссылается на B2 (иконки в компонентах), поэтому B3 финализируется только после закрытия B2.
- **B4 ждёт обоих** B2 и B3.
- **B5 ждёт B4** (нужны утверждённые композиции, чтобы вписывать states-темплейты).
- **H1 ждёт всё.**
- Маскот-ветка идёт **параллельно** B1–B5 и поставляет ассеты к моменту B5 / H1. В критический путь не входит.

---

## Критические файлы (полный список затрагиваемых)

**Токены и конфиг:**
- [Mobile/constants/theme.ts](Mobile/constants/theme.ts) — H1 переписывает.
- [Mobile/app.json](Mobile/app.json) — App Icon / Splash / шрифты после маскот-ветки.

**Компоненты (B3):**
- [Mobile/components/ui/Button.tsx](Mobile/components/ui/Button.tsx)
- [Mobile/components/ui/Input.tsx](Mobile/components/ui/Input.tsx)
- [Mobile/components/ui/Card.tsx](Mobile/components/ui/Card.tsx)
- [Mobile/components/ui/SegmentedControl.tsx](Mobile/components/ui/SegmentedControl.tsx)
- [Mobile/components/ui/ActionSheet.tsx](Mobile/components/ui/ActionSheet.tsx)
- [Mobile/components/RecordCard.tsx](Mobile/components/RecordCard.tsx)
- [Mobile/components/RecordGrid.tsx](Mobile/components/RecordGrid.tsx)
- [Mobile/components/RarityAura.tsx](Mobile/components/RarityAura.tsx) — большой блок локальных палитр.
- [Mobile/components/VinylSpinner.tsx](Mobile/components/VinylSpinner.tsx)
- [Mobile/components/VinylColorTag.tsx](Mobile/components/VinylColorTag.tsx)
- [Mobile/components/GlassTabBar.tsx](Mobile/components/GlassTabBar.tsx)
- [Mobile/components/Header.tsx](Mobile/components/Header.tsx)
- [Mobile/components/AnimatedGradientText.tsx](Mobile/components/AnimatedGradientText.tsx)
- [Mobile/components/GradientText.tsx](Mobile/components/GradientText.tsx)
- [Mobile/components/AutoRail.tsx](Mobile/components/AutoRail.tsx)

**Экраны (B4 + B5):**
- [Mobile/app/(tabs)/collection.tsx](Mobile/app/(tabs)/collection.tsx)
- [Mobile/app/(tabs)/search.tsx](Mobile/app/(tabs)/search.tsx) — топ по плотности хардкода.
- [Mobile/app/(tabs)/index.tsx](Mobile/app/(tabs)/index.tsx) — Scanner.
- [Mobile/app/record/[id].tsx](Mobile/app/record/[id].tsx)
- [Mobile/app/profile.tsx](Mobile/app/profile.tsx)
- [Mobile/app/user/[username]/index.tsx](Mobile/app/user/[username]/index.tsx) — параллельная палитра ivory/cobalt.
- [Mobile/app/collection/value.tsx](Mobile/app/collection/value.tsx) — параллельный dark-gradient.
- [Mobile/app/onboarding.tsx](Mobile/app/onboarding.tsx) — параллельный blob-gradient.
- [Mobile/app/(auth)/{login,register,verify-code,forgot-password,reset-password}.tsx](Mobile/app/(auth))
- [Mobile/app/+not-found.tsx](Mobile/app/+not-found.tsx)

**Шаблон брифа** для всех B-пакетов: [docs/plans/design/RARITY_DESIGN_BRIEF.md](RARITY_DESIGN_BRIEF.md).

---

## Верификация на каждом этапе

- **После B1:** распечатать палитру + type scale + motion principles на одной A3-странице и пройтись по 5 текущим скриншотам (Collection / Search / Record / Onboarding / Public profile) — нет ли ролей, для которых нет токена.
- **После B2:** взять 5 случайных иконок из текущего набора и проверить, что в новой системе они не выпадают по смыслу.
- **После B3:** собрать contact sheet и сравнить с исходным `Mobile/components/`. Каждый компонент имеет mapping старое-новое.
- **После B4:** сравнить mockup → реальный экран (после H1) на iOS-симуляторе iPhone 13 mini и Pro Max, на Android Pixel 6.
- **После B5:** пройтись по 26 поверхностям из §11 inventory и проверить, что у каждой есть слот + копирайт.
- **После H1:** `grep -rn "#[0-9a-fA-F]\{3,6\}\|rgba(\|hsla(" Mobile/ --include="*.tsx" --include="*.ts"` возвращает только строки из `theme.ts`. `expo start` запускается чисто. Прогон по всем 25 экранам визуально.

---

## Что не входит

- **Концепция маскота, его позы, личность, нарратив.** Отдельная ветка работы — пользователь сказал «не делать маскот-бриф вовсе» в этом pipeline. Здесь только слоты под него.
- **Backend** (`GET /me/profile/og-image` из ROADMAP M1) — относится к публичному профилю и не привязан к айдентике. Отдельная задача.
- **Achievement icons** (M5) — после того, как M1 закроется и появится визуальный язык, ачивки рисуются отдельной серией внутри M5.
- **App Store / Google Play marketing assets** (feature graphic, screenshots) — downstream-deliverable после маскот-ветки и H1.
