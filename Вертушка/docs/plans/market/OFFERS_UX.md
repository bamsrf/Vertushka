# UX-расширение для предложений магазинов

> Документ описывает как данные парсера показываются юзеру в приложении.
> Базовая инфра (парсер, БД, API, клик-трекинг) описана в [SHOPS_PARSING.md](SHOPS_PARSING.md).
> Здесь — **только** про UX и фичи, что видит юзер.

---

## 0. Что уже есть (Phase A)

**Только блок «Где купить» на карточке записи** (`/record/[discogs_id]`).
Юзер должен **сам открыть карточку**, чтобы увидеть offer-ы. Это первый шаг, но данные пока «спрятаны».

Дальше расширяемся в 5 направлений (приоритет ↓):

| # | Фича | Приоритет | Сложность | Зависит от |
|---|---|---|---|---|
| 1 | Уведомления о вишлисте (этот релиз **+ другие версии master**) | 🔥 Killer | 3-4 дня | 5+ магазинов |
| 2 | **Hot Stock pill** — gradient-индикатор «в наличии» в карточках и hero-блок на детальном экране | 🔥 Высокий | 2-3 дня | ничего |
| 3 | Чип-фильтр «В продаже» в поиске (ember-gradient в active) | Средний | 1 день | Hot Stock (для согласованности UX) |
| 4 | «Маркет» — второй `AutoRail` на `search.tsx` с кнопкой «Смотреть все →» | Средний | 3-5 дней | 5+ магазинов, 3к+ листингов |
| 5 | Вишлист → swipe-сравнение цен (drawer + Hot Stock pill в header) | Высокий | 3-4 дня | 5+ магазинов |

---

## Фича 1 — Уведомления вишлиста 🔔

> Юзер давно хочет «Khruangbin – Mordechai» (положил в вишлист год назад). Парсер впервые находит её в магазине → юзеру летит push. Тапнул → попал на карточку → купил.

### 1.1 Что юзер видит

**Push на телефоне:**

```
┌─────────────────────────────────────────────┐
│ 🎉 Вертушка                           сейчас│
│ ─────────────────────────────────────────── │
│ Khruangbin — Mordechai из вашего вишлиста   │
│ появилась в Коробке Винила за 4 990 ₽       │
└─────────────────────────────────────────────┘
```

**Экран уведомлений** (`Mobile/app/notifications.tsx`, таб «Личные»):

```
🟢  Появилась в продаже
    Khruangbin — Mordechai
    Коробка Винила — 4 990 ₽
    2 минуты назад                         →
```

**Тап** → открывается карточка записи `/record/16241424` с автоскроллом к блоку «Где купить» (подсвечен 1 сек).

### 1.2 Расширение — «другая версия мастера»

Эта же логика, но триггер другой: юзер положил в вишлист **конкретный пресс** (например 2020 first press), а в магазине появился **другой пресс того же мастер-релиза** (например 2023 repress на цветном виниле).

В нашей БД `Record.discogs_master_id` объединяет все версии одного релиза. Логика:
1. У записи в вишлисте `master_id = 12345`
2. В store_listings появилась новая запись с `record.discogs_master_id = 12345` но другим `discogs_id`
3. → шлём уведомление другого типа

**Push:**
```
┌─────────────────────────────────────────────┐
│ 🎶 Вертушка                           сейчас│
│ ─────────────────────────────────────────── │
│ Другая версия Khruangbin — Mordechai (2023, │
│ Pink Vinyl) появилась в Vinylpark за 5 490 ₽│
└─────────────────────────────────────────────┘
```

В экране уведомлений — отдельная иконка/цвет (фиолетовая? чтобы отличать от точного матча).

### 1.3 Что от Backend

**Новые типы Notification** (модель уже есть, нужно только добавить enum-значения):
- `wishlist_in_stock` — точный матч (уже добавлен юзером сегодня) ✅
- `wishlist_alt_version_in_stock` — другая версия мастера (новый)

**Cron-задача** — `notify_wishlist_offers()` в `app/tasks/wishlist_alerts.py`:
- Запускается каждый день в 04:30 (после `daily_full_crawl_http` в 02:00 + `hourly_match_unmatched` за ночь)
- Алгоритм:
  ```sql
  -- 1. Для каждого активного юзера с включённым notify_wishlist_in_stock:
  -- 2. Точный матч (тип wishlist_in_stock):
  WITH new_offers AS (
    SELECT sl.matched_record_id, MIN(sl.price_rub) AS price, MIN(sl.store_id) AS store
    FROM store_listings sl
    WHERE sl.status = 'in_stock'
      AND sl.first_seen_at >= now() - interval '24 hours'  -- новые с прошлой проверки
      AND sl.matched_record_id IS NOT NULL
    GROUP BY sl.matched_record_id
  )
  SELECT wi.user_id, wi.record_id, no.price, no.store
  FROM wishlist_items wi
  JOIN new_offers no ON no.matched_record_id = wi.record_id
  WHERE NOT EXISTS (  -- защита от дубликатов
    SELECT 1 FROM notifications n
    WHERE n.user_id = wi.user_id
      AND n.type = 'wishlist_in_stock'
      AND n.payload->>'record_id' = wi.record_id::text
      AND n.created_at >= now() - interval '7 days'
  );

  -- 3. Другая версия мастера (тип wishlist_alt_version_in_stock):
  -- Тот же запрос, но JOIN'им через discogs_master_id вместо record_id
  ```
- Создаём Notification + отправляем push через expo-notifications
- В payload пишем: `record_id`, `store_id`, `store_slug`, `price_rub`, `listing_id`

**Идемпотентность:** «not in last 7 days» защищает от спама (если pesticide listing исчезнет на день и появится снова — не повторяем).

**Throttling:** если у юзера 50 пластинок в вишлисте и в один день 30 из них появились — НЕ слать 30 push'ей. Группируем в дайджест:
```
🎉 Вертушка
30 пластинок из вашего вишлиста появились
в магазинах. Откройте, чтобы посмотреть.
```
В экране уведомлений раскрывается список.

### 1.4 Что от Mobile

- `Mobile/components/NotificationItem.tsx` — добавить иконки/текст для `wishlist_in_stock` и `wishlist_alt_version_in_stock`
- Deep-link обработка: тап на push с `record_id=X` → `router.push('/record/X?scroll_to=offers')`
- В `Mobile/app/record/[id].tsx` поддержать query-параметр `scroll_to=offers` → автоскролл к `<OffersBlock />` + 1-сек подсветка (background-цвет → fade)
- Настройки уведомлений (`Mobile/app/settings/notifications.tsx`) — toggle уже есть (`notify_wishlist_in_stock`)

### 1.5 Acceptance Criteria

1. Юзер кладёт пластинку в вишлист → ничего не происходит сразу.
2. Парсер находит её в магазине через сутки → юзер получает push утром.
3. Тап на push → открывается карточка с подсвеченным блоком «Где купить».
4. Если в один день появилось >5 пластинок — один push «N пластинок появилось», без спама.
5. Если включено `notify_wishlist_in_stock=false` — пушей нет, но в feed уведомлений запись есть (юзер может зайти и посмотреть).

---

## Фича 2 — Hot Stock индикатор 🔥

> Раньше карточка показывала только «приблизительную стоимость» — статичный текст из Discogs-статистики. Hot Stock — это претенциозный pill-индикатор, который появляется только когда пластинку реально можно купить, и стоит дороже глазу, чем серая цена-диапазон.

### 2.1 Концепция

**Внутреннее имя компонента: `HotStockTag`** (по аналогии с `VinylColorTag`).

**Философия:** «Кобальт встретил огонь». Базовая палитра приложения — холодный синий (`brand.cobalt`, `royalBlue`). Огонь — `accent.ember` — добавляется только когда **что-то реально доступно к покупке**. Это редкий, дорогой акцент: ember не разбросан по UI, поэтому когда он появляется, глаз цепляется. Цена в индикаторе — единственный «огненный» элемент в кадре, и за счёт контраста с холодной коллекцией он работает как лампочка «открыто» в витрине магазина.

**Что НЕ делаем:** красный «SALE»-баннер, угол-стикер «hot deal», мигающие звёзды, эмодзи в тексте. Эта эстетика дисконт-маркетплейса убивает претенциозность. Вместо этого — холодная типографика, тонкая работа со светом (glow ember), и один огненный градиент как единственное цветовое заявление.

### 2.2 Анатомия `HotStockTag`

Pill той же геометрии что `VinylColorTag`, но с **gradient fill** вместо solid и с «винил-точкой» (`disc` иконка) вместо цветовой точки.

```
┌─────────────────────────────────┐
│ ◉  4 990 ₽           ↗          │
└─────────────────────────────────┘
   ↑     ↑                  ↑
 disc   price            arrow (опц.)
 6dp    13pt/700w         12dp
```

| Слой | Token | Значение |
|---|---|---|
| Background | `LinearGradient` | `[brand.cobaltDeep, brand.cobalt, accent.ember]`, start `{x:0,y:0}`, end `{x:1,y:1}`, locations `[0, 0.55, 1]` |
| Border | 0.5pt | `rgba(255,255,255,0.18)` — тонкая стеклянная обводка |
| Border radius | `BorderRadius.full` | pill |
| Padding | 10/4dp | плотнее чем VinylColorTag — цена смотрится дороже |
| Gap | 6dp | между диском, ценой и стрелкой |
| Shadow | `Shadows.glowEmber` | blur 24, opacity 0.45, color = `accent.ember` (мягкий ореол снаружи) |
| Disc (иконка) | `disc` duotone 12pt | tint = `#FFFFFF`, opacity 0.95 |
| Price text | 13pt / 700w | color `#FFFFFF`, letter-spacing `-0.2`, `font-feature-settings: 'tnum'` (моноширинные цифры → не дрожит) |
| Arrow (опц.) | `arrow-up-right` 10pt | opacity 0.7, появляется только в hero-режиме (детальный экран, drawer) |

**Формат цены:**
- `< 10 000 ₽` → `«4 990 ₽»` (неразрывный пробел-разделитель тысяч, `Math.round`)
- `≥ 10 000 ₽` → `«12 500 ₽»` (без сокращений — претенциозный мерч не пишет «12k»)
- `от X ₽` если в карточке агрегат по нескольким магазинам и они расходятся ≥ 15%

### 2.3 Шесть состояний (state machine)

Один компонент, шесть визуальных режимов. Передаём `<HotStockTag variant="..." price={...} />`.

| Variant | Когда | Визуал | Тон |
|---|---|---|---|
| `inStock` | ≥1 listing с `status=in_stock`, точное совпадение pressing | Полный gradient + glow + disc | Главный «огонь» |
| `inStockMulti` | ≥2 листинга с одинаковым pressing | Gradient + glow + текст `от 4 990 ₽` | Тот же огонь, без агрессии «единичка» |
| `altVersion` | Нет offers на этот release, но есть на другой pressing того же `master_id` | **Outline-вариант**: прозрачный фон, gradient border (1pt) `cobalt→ember`, disc серый, текст `4 990 ₽ · альт.` 12pt/600w, цвет `Colors.text`. Без glow | Шёпот, не крик |
| `preorder` | Все офферы `status=preorder` | Outline + точка `accent.ember` (4dp) + текст `от 4 990 ₽ · предзаказ` | Не «горит», но обещает |
| `lastOne` | Один листинг, `quantity == 1` (если магазин отдаёт; иначе пропускаем) | `inStock` + микро-подпись над pill в hero-кадрах: `«1 экз.»` 10pt | Дефицит — но без капслока |
| `none` | Офферов нет | Компонент возвращает `null` | Карточка остаётся как сейчас |

**Зачем не один цвет:** «в наличии этот пресс» и «есть другой пресс» — психологически разные сигналы. Outline для альт-версии = «я не молчу, но я не главный аргумент покупки». Это сшивает фичу с **Фичей 1** (alt-version нотификация): пользователь сразу понимает, та это пластинка или нет.

### 2.4 Размещение в `RecordCard.tsx`

#### 2.4.1 `compact` (overlay grid 2 колонки) — главная, поиск, коллекция

```
┌──────────────────┐
│ [LP] ◉           │   ← формат-бейдж (как сейчас)
│       │   1973   │   ← год (как сейчас)
│       │          │
│   обложка        │
│                  │
│                  │
│ ╔══════════════╗ │   ← BlurView подложка (intensity 18, tint='dark')
│ ║ ◉ 4 990 ₽   ║ │   ← HotStockTag, прижат в правом нижнем углу overlay
│ ╚══════════════╝ │
│ ARTIST           │
│ Album title      │
└──────────────────┘
```

- Pill размещается **внутри** уже существующего gradient-overlay (`overlay: [transparent, rgba(10,11,59,0.7)]`), правый нижний угол, offset 8dp.
- Под pill — едва видимая `BlurView intensity={18} tint="dark"` шириной = pill + 4dp с каждой стороны. Это даёт «парящий» эффект, даже когда обложка светлая (хип-хоп, поп).
- На обложках где доминирует тёмный — blur почти невидим, но glow ember выдаёт индикатор.
- При `variant="altVersion"` — pill уходит **в верхний** правый угол (под формат-бейджем смещён), чтобы не перекрывать ценность артиста/названия в нижнем блоке. Это вторичный сигнал — место вторичное.

#### 2.4.2 `expanded` (vertical card 92dp text-block)

- HotStockTag встаёт во вторую строку текстового блока, **справа** от мета (год/формат/страна).
- Если строка переполнена — пробуем на отдельной строке снизу как самостоятельный элемент с `alignSelf: 'flex-start'`.
- Высота карточки **не растёт** — иначе порушится `numColumns=2` грид. Если место не находится — fallback на compact-стиль (overlay pill на обложке).

#### 2.4.3 `list` (horizontal row)

- Аватар 56×56 слева → текстовая колонка → справа: вместо текущего chevron — `HotStockTag` целиком.
- Если pill не помещается (узкие телефоны) — сжимаем до **минимальной формы**: `◉ 4 990` (без «₽», без gap-padding).

### 2.5 Hero-момент на детальном экране

В `Mobile/app/record/[id].tsx` блок «Примерная стоимость» сейчас стоит plain text. Заменяем на двухстрочную композицию:

```
ПРИМЕРНАЯ СТОИМОСТЬ                          ← caption / textMuted / uppercase / spacing:1
₽ 8 200 – 12 400                              ← Discogs-диапазон (как сейчас)

В НАЛИЧИИ СЕЙЧАС                              ← caption / textMuted / uppercase / spacing:1
┌──────────────────────┐
│ ◉  от 4 990 ₽   ↗   │  · в 3 магазинах    ← HotStockTag inStockMulti + tail-meta
└──────────────────────┘
```

- Tail-meta: `· в N магазинах` 12pt/400w `Colors.textSecondary`.
- При tap на pill — мягкий scroll к `OffersBlock` ниже + лёгкая подсветка карточки магазина с минимальной ценой (1.5s glow), чтобы взгляд нашёл цель.
- Если **только** `altVersion` — текст: `НЕТ НА ЭТОТ ПРЕСС, НО ЕСТЬ АЛЬТ.` + outline-pill + tail-meta `· другой релиз того же альбома → посмотреть`.

### 2.6 Анимации (микро, но дорого)

Анимаций мало — это часть «претенциозности». Шум недопустим.

1. **Entry в hero-моментах** (детальный экран, drawer): pill появляется с `opacity 0→1, translateY 8→0, scale 0.95→1` за 320ms (`Easing.out(Easing.cubic)`). Glow приходит с задержкой 100ms (`opacity 0→0.45`, 220ms) — сначала pill, потом ореол. Это даёт ощущение «зажглось».
2. **Disc rotation** — **только** в карусели «В наличии сейчас» на поиске (см. Фичу 4) и на детальном экране **один раз** при entry: disc делает один полный оборот за 1.2s, затем замирает.
3. **Pulse glow** — отсутствует. Намеренно отказываемся: у нас уже пульсирует `VinylColorTag` (бронь) и нотификации. Третий пульсар = визуальный мусор.
4. **На карточках в сетке** — никаких анимаций. Только статичный pill + glow. Сетка из 20 карточек где у половины пульсирует огонёк — это головная боль.
5. **При обновлении цены** (background refresh каждые 6ч → cache invalidation): если экран открыт, цена в pill меняется через `crossFade` 200ms (без scale). Это редкий кейс — обычно юзер не увидит, но если увидит — приятно.

### 2.7 Доступность

- Все pill'ы имеют `accessibilityRole="text"` + `accessibilityLabel`:
  - `inStock`: `«В наличии за 4 990 рублей. Нажмите чтобы перейти к предложениям»`
  - `altVersion`: `«Нет этого пресса, но есть альтернативная версия того же альбома за 4 990 рублей»`
  - `preorder`: `«Доступен предзаказ от 4 990 рублей»`
- Цвет gradient'а cobalt→ember на белом фоне даёт WCAG AA для **белого** текста на самой светлой точке (ember `#FF7A4A`): контраст ≥ 4.5. Проверить в светлой теме.
- Outline-вариант (`altVersion`) на белом фоне: текст `Colors.text` — заведомо AAA.
- `Reduce Motion` (iOS / Android system flag) — отключает disc rotation и entry-анимацию. Pill появляется мгновенно, статичный.
- Минимальная hit-area для tap-pill = 44×44 (через `hitSlop`, как у `Icon` в проекте).

### 2.8 Когда **НЕ** показывать (защита от инфляции токена)

Если индикатор появится везде — он перестанет работать. Правила:

1. **Карточка в коллекции пользователя** (у меня уже есть эта пластинка) — не показываем `inStock` совсем. Зачем человеку «купить» то, что у него уже есть? Показываем `altVersion` если есть другой пресс — это апселл.
2. **`preorder`** в `compact`-карточках — не показываем (только на детальном экране). В сетке из 20 карточек предзаказы создают шум; для предзаказов важна детализация (дата релиза), которая в pill не помещается.
3. **`altVersion`** — не показываем в карточках главной (там и так много контента, и пользователь не выбирает конкретный pressing). Только в вишлисте, на детальном экране и в маркете.
4. **Если `listing.last_seen_at` старше 7 дней** — `none` (страховка от устаревших данных, эта же логика уже в `api/offers.py`).

### 2.9 Реюз существующих токенов

Не плодим новое там где можно переиспользовать.

| Что | Откуда | Как используем |
|---|---|---|
| `LinearGradient` | `expo-linear-gradient` (уже в проекте) | Background pill'а + active-чипа |
| `BlurView intensity={18}` | `expo-blur` | Подложка pill'а на overlay-карточке |
| `Icon name="disc"` (duotone/fill) | Phosphor wrapper `components/ui/Icon.tsx` | Точка-винил в pill, иконка в чипе и заголовке Маркета |
| `Icon name="arrow-up-right"` | Phosphor | Hero-режим pill'а |
| `Shadows.glowEmber` | `theme.ts` (уже определён) | Glow вокруг pill'а |
| `BorderRadius.full` + paddings | `theme.ts` | Геометрия pill |
| `VinylColorTag`-pattern | `components/ui/VinylColorTag.tsx` | Структурный референс (НЕ копипаста) |
| `Pressable` + `hitSlop` | RN core, паттерн из `Icon.tsx` | Tap-area |

Новых зависимостей **нет**. Новый файл один: `Mobile/components/HotStockTag.tsx`.

### 2.10 Acceptance Criteria

1. В поиске карточки с offer показывают `HotStockTag` с минимальной ценой в gradient pill.
2. Карточки без offers — без pill (не пустая надпись «Нет предложений»).
3. Pill не ломает grid-layout (`RecordGrid` 2-колоночный, высота карточек не растёт).
4. На детальном экране блок «В наличии сейчас» появляется entry-анимацией только когда summary загрузился.
5. Карточка пластинки которая **уже в коллекции** — не показывает `inStock` (показывает `altVersion` если есть, иначе `none`).
6. Reduce Motion → анимаций нет, pill статичный.
7. Performance: открыть поиск (20 карточек) → результаты с pill за <300 мс (один SQL для всех discogs_ids).

---

## Фича 3 — Чип-фильтр «🟢 В продаже» в поиске 🔍

> Альтернативный сценарий дискавери: «не ищу конкретное, хочу посмотреть что доступно прямо сейчас».

### 3.1 Что юзер видит

В существующем экране поиска (`Mobile/app/(tabs)/search.tsx`) — рядом с уже-существующими чипами (Формат, Страна, Декада):

```
[Все][LP][7"]    [Россия][США][UK]    [🟢 В продаже]
```

При активном чипе:
- Запрос идёт с `?in_stock_only=true`
- Карточки в результатах — гарантированно с бейджем (Фича 2)
- В пустом запросе (без поисковой строки) показываем **топ магазинов** — недавние new arrivals (сортировка по `first_seen_at desc`)

### 3.2 Что от Backend

В `GET /records/search` добавить query-параметр:
```python
in_stock_only: bool = Query(False)
```

Если `true`:
```sql
SELECT r.* FROM records r
JOIN store_listings sl ON sl.matched_record_id = r.id
WHERE sl.status = 'in_stock'
  AND sl.last_seen_at >= now() - interval '7 days'
  AND (r.title ILIKE :q OR r.artist ILIKE :q)
ORDER BY sl.first_seen_at DESC  -- свежие сверху
LIMIT 50;
```

Discogs API в этом режиме НЕ дёргаем (бессмысленно — мы фильтруем по локальным offers).

### 3.3 Что от Mobile

- В `search.tsx` — добавить чип в существующий массив фильтров
- `lib/api.ts:searchRecords()` — добавить параметр `inStockOnly`
- При активном чипе скрывать sub-фильтры (Discogs-параметры неприменимы)

### 3.4 Визуальное выделение активного чипа — ember gradient

Чип следует уже существующему chip-паттерну из `search.tsx` (`FORMAT_OPTIONS` / `COUNTRY_OPTIONS`), **но** активное состояние подсвечивается не cobalt'ом а тем же ember-градиентом что у `HotStockTag` (Фича 2):

| Состояние | Visual |
|---|---|
| Inactive | как обычный чип: border `Colors.surface`, текст `Colors.textSecondary`, иконка `disc` duotone 14pt |
| Active | Gradient fill `[brand.cobaltDeep, brand.cobalt, accent.ember]`, border 0pt, текст `#FFFFFF`/600w, иконка `disc` fill 14pt, glow ember (`opacity: 0.25` — мягче чем у pill) |

Этот «огненный» активный чип = единственный во всём ряду фильтров → визуально сразу видно «я смотрю только то, что реально можно купить». Все остальные чипы остаются в холодной палитре.

**Активация query-param'ом:** при заходе из кнопки «Смотреть все →» (Фича 4) — `router.push('/(tabs)/search?in_stock=1')` → `search.tsx` в `useEffect` читает `useLocalSearchParams().in_stock`, и если `'1'`, сразу активирует чип. Юзер видит уже-применённый фильтр и grid с офферами.

### 3.5 Acceptance Criteria

1. Без чипа — обычный поиск работает как раньше.
2. С чипом и пустой строкой — показываются последние 50 new arrivals.
3. С чипом и строкой — поиск только по локальным записям с offers (быстро, мгновенно).
4. Если ни одной пластинки в продаже — empty-state «Пока ничего нет в магазинах из этого запроса».

---

## Фича 4 — «Маркет» в поиске 🏪

> Полноценная вторая точка дискавери. **Без нового экрана и без перестройки навигации в Phase 1** — переиспользуем существующую механику «Новинки · Discogs» на экране поиска и добавляем рядом такую же карусель «В наличии сейчас» из магазинных офферов.

### 4.1 Где именно

На экране поиска `Mobile/app/(tabs)/search.tsx` уже есть один горизонтальный блок — `AutoRail` с «Новинки · Discogs» (грузится через `api.getNewReleases(24)`). Маркет ставим **вторым** `AutoRail` в homeView (когда поисковый input пустой), ниже Discogs-новинок, до `RecordGrid` с результатами поиска.

Та же геометрия: 108×108 обложка, gap 12px, padding 20px, marginBottom 16px. Полная визуальная симметрия с уже знакомым блоком — юзер не ловит «новую» секцию глазом, он ловит **продолжение** того, что уже видел.

### 4.2 Что показываем

Последние N (24) листингов со статусом `in_stock` из всех магазинов, отсортированные по `first_seen_at desc` (новинки в продаже). **Один листинг = один товар** в карусели; даже если у одного релиза 5 листингов из 5 магазинов — берём только самый дешёвый, чтобы карусель не была заполнена дублями одной обложки.

### 4.3 Карточка маркета — точная копия Discogs-карточки, но с ценой вместо лайков

| Слот | Сейчас (Новинки Discogs) | Здесь (Маркет) |
|---|---|---|
| Обложка 108×108 | Discogs `cover_image_url` | Та же — берём через `matched_record_id → records.cover_image_url` |
| Артист 9pt | `record.artist` | То же |
| Название 11.5pt bold | `record.title` | То же |
| Мета-строка 11pt periwinkle | `2024 · Vinyl · ♥ 245` | `2024 · Vinyl · ◉ 4 990 ₽` ← диск-иконка + цена ВМЕСТО сердечка с want-count |

Точка-винил (`Icon name="disc"` 11pt, цвет = `accent.ember`) + цена (`13pt/700w`, цвет = `Colors.text`) → мини-версия `HotStockTag` без gradient-fill (полный pill в такой плотной карусели был бы избыточен — пользователь УЖЕ понимает что это маркет из заголовка секции).

### 4.4 Заголовок секции

```
В НАЛИЧИИ СЕЙЧАС ◉                       Смотреть все →
Свежие предложения · 12 магазинов
```

- Левая колонка — как сейчас в `AutoRail`: `«В НАЛИЧИИ СЕЙЧАС»` (uppercase, `Colors.royalBlue`, 10pt mono) + subtitle `«Свежие предложения · N магазинов»` 11pt grey.
- После заголовка inline `disc` 12pt opacity 0.6, медленное вращение **1 оборот / 8s**. Это **единственное** место во всём приложении, где иконка крутится без остановки — поэтому действует. Если поставить вращение ещё в 10 местах — приложение начнёт «жужжать».
- Справа сверху (та же baseline что заголовок) — `«Смотреть все →»` 11pt/600w `Colors.royalBlue`, с `Pressable` hitSlop 12. По тапу → `router.push({ pathname: '/(tabs)/search', params: { in_stock: '1' } })` → search фокусирует поле, открывается grid с активным чипом «В продаже» (Фича 3). Это переиспользует уже существующий поиск + `RecordGrid` + чип-фильтры → **не нужен отдельный `/market` route в Phase 1**.

### 4.5 Доработка `AutoRail.tsx`

Чтобы тот же компонент показывал и Discogs-новинки (с `♥`), и маркет (с `◉ ₽`), без forking — добавляем optional props:

```typescript
interface AutoRailProps {
  // ... существующие
  headerActionLabel?: string;              // "Смотреть все →"
  onHeaderActionPress?: () => void;
  itemBadgeRenderer?: (item) => ReactNode; // замена ♥-сердечка на mini-pill (или null)
}
```

Discogs-новинки продолжают рендерить `♥ 245` как раньше (если `itemBadgeRenderer` не передан — fallback на текущую логику). Маркет передаёт `itemBadgeRenderer={(item) => <MiniPriceBadge price={item.min_price_rub} />}`.

### 4.6 Backend

**Новый endpoint `GET /api/market/new-arrivals`:**

```python
@router.get("/market/new-arrivals", response_model=list[MarketCarouselItem])
async def get_new_arrivals(limit: int = Query(24, le=50)) -> list:
    """
    Последние N свежих листингов in_stock — для карусели в поиске.
    Дедуп по matched_record_id: только самый дешёвый листинг на запись.
    """
```

```python
class MarketCarouselItem(BaseModel):
    record_id: UUID
    discogs_id: str
    artist: str
    title: str
    year: int | None
    format: str | None
    cover_image_url: str | None
    min_price_rub: Decimal
    store_slug: str          # для analytics — какой магазин чаще всего «новинит»
    first_seen_at: datetime
```

Redis-кэш 15 минут (карусель не критична к мгновенному обновлению).

**Полный экран маркета — НЕ нужен в Phase 1.** Для «Смотреть все» используем `search.tsx` с pre-applied чипом `in_stock=1` (Фича 3) и `RecordGrid` уже работающим. Это переиспользует:
- search-input (можно сразу искать по уже-в-продаже)
- сетку 2 колонки `RecordGrid`
- все существующие фильтры (Формат, Страна, Декада, плюс новый «В продаже»)
- existing pull-to-refresh + infinite scroll

### 4.7 Mobile (что меняется)

- `Mobile/app/(tabs)/search.tsx` — добавить второй `AutoRail` блок «В наличии сейчас» в homeView; обработать query-param `in_stock=1` для активации чипа при заходе из кнопки «Смотреть все»
- `Mobile/components/AutoRail.tsx` — расширить props (`headerActionLabel`, `onHeaderActionPress`, `itemBadgeRenderer`)
- `Mobile/components/MiniPriceBadge.tsx` — крошечный компонент: `<Icon name="disc"/> + цена` (используется только в этой карусели; полноценный `HotStockTag` тут избыточен)
- `Mobile/lib/api.ts` — `getMarketFeed(limit)` → `GET /api/market/new-arrivals`

### 4.8 Когда включать

Не раньше чем **5+ магазинов** и **3к+ активных листингов**. Иначе:
- Карусель будет «одинокой» (одни и те же 5 пластинок)
- Юзер не получит ощущения «там кипит жизнь» — bad first impression

### 4.9 Phase 2 — отдельный экран `/market` (отложено)

Если карусели + чип-фильтра окажется мало (например, юзер хочет «магазины как сущность» — рейтинги, города, доставка, фильтр по конкретному магазину), завести отдельный route `Mobile/app/market.tsx` с витриной магазинов и расширенным `GET /api/market/listings` (с фильтрами `store_slug`, `min_price`/`max_price`, `sort`). В Phase 1 не делаем — экономим экран и навигацию, фокус на проверке гипотезы «нужно ли вообще много дискавери-точек».

### 4.10 Acceptance Criteria

1. На пустом экране поиска (homeView) видим два горизонтальных блока подряд: «НОВИНКИ · Discogs» (как сейчас) и «В НАЛИЧИИ СЕЙЧАС · N магазинов» (новый).
2. В мета-строке карточек маркета — `◉ 4 990 ₽` вместо `♥ 245`. У карточек Discogs-новинок остаётся `♥ 245` без изменений (регресс).
3. Тап «Смотреть все →» в правом углу заголовка маркета → переходим в search-grid с активным чипом «В продаже» (Фича 3) → grid показывает только записи с офферами.
4. Карусель не появляется если в БД < 10 свежих листингов (защита от «пустоты» в первые дни после релиза).
5. `AutoRail` с Discogs-новинками рендерит `♥`-сердечко как раньше (изменения в props — backward-compatible).

---

## Фича 5 — Вишлист: swipe-сравнение цен 💰

> Юзер открыл вишлист (60 пластинок), видит на каждой «предварительная стоимость». Нет понимания где КОНКРЕТНО можно купить. Swipe-bar решает.

### 5.1 Что юзер видит

**В обычном состоянии** — карточка вишлиста как сейчас, **но** если есть offers — справа торчит вертикальный «язычок»:

```
┌─────────────────────────────────────────┐
│ ┌────┐ Khruangbin – Mordechai           │ ╱╱
│ │[об]│ ~5 990 ₽ предварительная        │╱╱╱← язычок-баннер
│ └────┘ Добавлена 12 марта 2026         │╲╲╲ «Сравнить цены»
└─────────────────────────────────────────┘ ╲╲
                                              ↑ можно тянуть пальцем
```

**После swipe влево** — карточка сдвигается, открывая offers-drawer:

```
        ┌──────────────────────────────────┐
[карт.] │ 🟢 4 990 ₽  Коробка Винила  Buy →│
сдв.    │ 🟢 5 200 ₽  Vinylpark       Buy →│
влево   │ 🟡 4 890 ₽  Plastinka.com   Buy →│ ← топ-3 offers по цене
        │    +2 ещё в магазинах            │
        └──────────────────────────────────┘
```

Тап на конкретный offer → переход на карточку записи с подсвеченным блоком (можно купить прямо там).

**Или** — тап на «+2 ещё» → bottom-sheet с полным списком, описанием каждого варианта (артикул, состояние, vinyl color, ссылка):

```
╔═════════════════════════════════════════╗
║  Все варианты — Khruangbin – Mordechai  ║
║  ─────────────────────────────────────  ║
║  ┌────────────────────────────────────┐ ║
║  │ [обл крупно] 🏪 Коробка Винила     │ ║
║  │              4 990 ₽               │ ║
║  │              LP · Red · 2020       │ ║
║  │              Артикул: 0656605149318│ ║
║  │  ┌────────────────────────────┐    │ ║
║  │  │     КУПИТЬ НА САЙТЕ →      │    │ ║
║  │  └────────────────────────────┘    │ ║
║  └────────────────────────────────────┘ ║
║  ┌────────────────────────────────────┐ ║
║  │ [обл] 🏪 Plastinka.com  4 890 ₽    │ ║
║  │       LP · Black · 2023            │ ║
║  │       Артикул: 0656605149319       │ ║
║  │  [КУПИТЬ НА САЙТЕ →]               │ ║
║  └────────────────────────────────────┘ ║
║  ┌────────────────────────────────────┐ ║
║  │ ... (другие версии мастера)         │ ║
║  └────────────────────────────────────┘ ║
╚═════════════════════════════════════════╝
```

Здесь же подсвечиваем «**Другая версия**» бэйджем, если `discogs_id` отличается от того что в вишлисте.

### 5.2 Hot Stock pill в header drawer

В header drawer (когда юзер свайпнул карточку) показываем тот же `HotStockTag` (Фича 2, `inStockMulti` или `inStock`), что висел на исходной карточке вишлиста:

```
┌──────────────────────────────────────┐
│ Сравнить цены · ◉ от 4 990 ₽        │ ← header drawer'а, pill справа от заголовка
├──────────────────────────────────────┤
│ 🟢 4 990 ₽  Коробка Винила  Buy →   │
│ 🟢 5 200 ₽  Vinylpark       Buy →   │
│ ...                                   │
└──────────────────────────────────────┘
```

Это сшивает свайп-жест с тем же визуальным якорем, который пользователь увидел на карточке — нет когнитивного диссонанса «откуда это значение взялось». Pill в header статичный (без disc-rotation, без entry-анимации — drawer и так двигается, лишняя анимация = шум).

### 5.3 Технические детали (Mobile)

- **Библиотека:** `react-native-gesture-handler` уже стоит в Expo (стандарт). Использовать `Swipeable` от `react-native-gesture-handler/Swipeable`.
- **Компонент** `Mobile/components/WishlistRowWithOffers.tsx`:
  ```tsx
  <Swipeable
    renderRightActions={() => <OffersDrawer record={item.record} />}
    overshootRight={false}
    rightThreshold={40}
  >
    <WishlistRow item={item} />
  </Swipeable>
  ```
- **OffersDrawer** — компактный список топ-3 offers + кнопка «+N ещё»
- При тапе «+N ещё» → opens BottomSheet (`@gorhom/bottom-sheet` — стандарт для RN)
- BottomSheet содержит полный список с полями `OfferDetailCard` (артикул, цвет, состояние, ссылка)

### 5.4 Что от Backend

Уже всё есть! `GET /api/records/{discogs_id}/offers` отдаёт всё. Только надо:
- Для **«другая версия мастера»** — расширить endpoint:
  ```python
  GET /api/records/{discogs_id}/offers?include_master_versions=true
  ```
  → возвращает не только offers именно этой записи, но и offers других записей с тем же `discogs_master_id`. Помечает `is_alt_version: bool` в каждом offer.

### 5.5 Acceptance Criteria

1. В вишлисте карточка с offers — справа язычок «Сравнить цены».
2. Свайп влево раскрывает drawer с топ-3 offers по цене.
3. Тап на «+N ещё» → bottom-sheet с полным списком.
4. В bottom-sheet каждый offer показывает: лого магазина, цену, формат, цвет, артикул, кнопку «Купить на сайте».
5. При тапе «Купить» — клик-трекинг (Phase A) + открытие URL.
6. Если включён `include_master_versions` — alt-версии помечены бейджем.
7. Карточки без offers — без язычка (не дразним пустотой).

---

## Backend backlog (что нужно для всех фич)

### Schema `RecordOffersSummary` (главный аггрегат для Фичи 2)

Чтобы `HotStockTag` знал, какой variant показывать, нужен **аггрегат на уровне записи** (а не массив listings). Возвращаем его как объект в каждом эндпоинте, где встречается `Record`:

```python
class RecordOffersSummary(BaseModel):
    in_stock_count: int               # листингов exact-match со статусом in_stock
    preorder_count: int
    alt_version_count: int            # листинги с тем же master_id, но другим release_id
    min_price_rub: Decimal | None     # для inStock и inStockMulti variant'ов
    min_price_alt_rub: Decimal | None # для altVersion variant
    has_last_one: bool                # ≥1 листинг с quantity == 1
    stores_with_stock: int            # сколько уникальных магазинов в наличии
```

Mobile из этого вычисляет variant:
- `in_stock_count == 1` → `inStock`
- `in_stock_count >= 2` → `inStockMulti`
- `in_stock_count == 0 AND alt_version_count > 0` → `altVersion`
- `in_stock_count == 0 AND preorder_count > 0` → `preorder`
- `has_last_one == true` → префикс к любому inStock-вариант'у
- всё ≠ 0 → `none` (рендерим `null`)

### Новый batch-endpoint для сеток карточек (Фичи 2, 3)

```python
POST /api/records/offers/summary
body: { "discogs_ids": ["123", "456", ...] }   # batch до 100
→    { "123": RecordOffersSummary, "456": RecordOffersSummary, ... }
```

Один запрос Mobile делает на всю видимую сетку (20 карточек поиска / 60 карточек коллекции), мапит summary к карточкам и рисует `HotStockTag`. Под капотом — один SQL по materialized view `record_offers_summary` (см. ниже).

### Новые поля в существующих endpoints

| Endpoint | Новое поле / параметр | Описание |
|---|---|---|
| `GET /records/{id}/offers` | `summary: RecordOffersSummary` | в корне response, плюс существующий `offers: []` |
| `GET /records/{id}/offers` | `?include_master_versions=true` | + alt версии (Фича 5) |
| `GET /records/search` | `?in_stock_only=true` | фильтр (Фича 3) |
| `GET /records/search` | пере-использует `POST /records/offers/summary` на клиенте | (не дублируем поля в search-response) |
| `GET /collections/{id}/items` | то же | (не дублируем) |
| `GET /wishlist/items` | то же | (не дублируем) |
| `GET /market/new-arrivals` | новый endpoint (Фича 4) | дедуп по `matched_record_id`, поле `min_price_rub` в каждом item |
| `GET /market/listings` | **отложено в Phase 2** (Фича 4.9) | только если нужен отдельный экран маркета |

### Новые типы Notification

| Type | Шаблон | Когда |
|---|---|---|
| `wishlist_in_stock` ✅ уже | «{title} из вишлиста появилась в {store}» | Фича 1 |
| `wishlist_alt_version_in_stock` | «Другая версия {title} появилась в {store}» | Фича 1 |
| `wishlist_price_drop` ✅ уже | «{title} подешевела в {store}» (Phase C) | — |

### Новый cron-job

`Backend/app/tasks/wishlist_alerts.py`:
- `notify_wishlist_offers()` — каждый день 04:30, после daily_full_crawl
- `notify_alt_version_offers()` — каждый день 04:35
- Throttling: дайджест если >5 новых для одного юзера

### Миграция

```sql
-- 1. Создаём materialized view для быстрых выборок «record → offers summary»
CREATE MATERIALIZED VIEW record_offers_summary AS
SELECT
  r.id AS record_id,
  r.discogs_id,
  r.discogs_master_id,
  MIN(sl.price_rub) AS min_price,
  COUNT(DISTINCT sl.store_id) AS stores_count,
  MAX(sl.last_seen_at) AS last_offer_at
FROM records r
LEFT JOIN store_listings sl ON sl.matched_record_id = r.id
  AND sl.status = 'in_stock' AND sl.last_seen_at >= now() - interval '7 days'
GROUP BY r.id;

CREATE UNIQUE INDEX idx_ros_record ON record_offers_summary (record_id);
CREATE INDEX idx_ros_discogs ON record_offers_summary (discogs_id);
CREATE INDEX idx_ros_master ON record_offers_summary (discogs_master_id);

-- Refresh раз в час (или после daily_incremental_crawl)
REFRESH MATERIALIZED VIEW CONCURRENTLY record_offers_summary;
```

Materialized view решит проблему производительности для бейджей в search/collection.

---

## Roadmap для UX (5 фич)

### Sprint 1 — Бейдж + Чип (~1 неделя)
- Фича 2 (бейдж в поиске/коллекции/вишлисте) — самое дешёвое и видимое
- Фича 3 (чип «В продаже» в поиске) — добивает дискавери
- **Зависит от:** ничего. Можно делать прямо сейчас, до подключения других магазинов

### Sprint 2 — Уведомления (~1 неделя)
- Фича 1 (уведомления вишлиста: точный матч + alt версия)
- Cron-задача + push-инфра
- **Зависит от:** 3+ магазина (чтобы было «о чём уведомлять»)

### Sprint 3 — Swipe сравнение цен (~1 неделя)
- Фича 5 (вишлист → swipe → drawer + bottom-sheet)
- BottomSheet компонент полный
- **Зависит от:** 3+ магазина

### Sprint 4 — Маркет в поиске (~3-5 дней)
- Фича 4 (второй `AutoRail` «В наличии сейчас» на `search.tsx`, кнопка «Смотреть все →» в search-grid с pre-applied чипом)
- Доработка `AutoRail.tsx` (props `headerActionLabel`, `onHeaderActionPress`, `itemBadgeRenderer`)
- Новый endpoint `GET /api/market/new-arrivals`
- **Зависит от:** 5+ магазинов с 3к+ листингов
- Отложить если данных мало — иначе карусель будет «одинокой»
- **Отдельный экран `/market` НЕ делаем в Phase 1** (см. Фича 4.9 — Phase 2)

### Условный Sprint 5 — Полировка
- A/B сортировки в Маркете (по цене / по магазину / по комиссии)
- Промокоды (Фича из affiliate Phase B-direct)
- Скидки-баннеры («-15% сегодня в Plastinka.com»)
- Соц-доказательство в карточке («Купили через нас 12 раз»)

---

## Дизайн-токены и компоненты

Сводка для имплементатора — что физически создаём, какие токены трогаем, props-интерфейсы.

### Новый компонент `Mobile/components/HotStockTag.tsx`

```typescript
type HotStockVariant =
  | 'inStock'        // gradient + glow, цена
  | 'inStockMulti'   // gradient + glow, "от X ₽"
  | 'altVersion'     // outline, "X ₽ · альт."
  | 'preorder'       // outline + точка ember, "от X ₽ · предзаказ"
  | 'lastOne';       // = inStock + микро-подпись "1 экз." сверху

interface HotStockTagProps {
  variant: HotStockVariant;
  price: number;              // в рублях, целое
  size?: 'sm' | 'md' | 'lg';  // sm — для list-row, md — default, lg — для hero-моментов
  showArrow?: boolean;        // arrow-up-right справа (default true для md/lg, false для sm)
  animated?: boolean;         // entry-анимация (default true в hero, false в сетках)
  onPress?: () => void;       // если задан — Pressable; иначе View
  hitSlop?: number;           // default 12
}
```

Внутри:
- Outer `Pressable` (или `View` если нет `onPress`)
- `LinearGradient` для `inStock`/`inStockMulti`/`lastOne`, обычный `View` с gradient border для `altVersion`/`preorder`
- `<Icon name="disc" />` слева
- `<Text>` с ценой (моноширинные цифры)
- `<Icon name="arrow-up-right" />` справа (опц.)
- `shadow` через `Shadows.glowEmber` (ember-glow только для gradient-вариантов)

### Изменения в `Mobile/constants/theme.ts`

- **Проверить** существование `Shadows.glowEmber` (по справке должен быть; если нет — добавить: `blur: 24, opacity: 0.45, color: accent.ember`)
- **Добавить** `Gradients.hotStock = [brand.cobaltDeep, brand.cobalt, accent.ember]` с `locations: [0, 0.55, 1]` — переиспользуется в `HotStockTag` и в активном чипе Фичи 3

### Компонент `Mobile/components/MiniPriceBadge.tsx` (для Фичи 4)

```typescript
interface MiniPriceBadgeProps {
  price: number;  // в рублях, целое
}
```

Не путать с `HotStockTag` — это **намеренно** более простой токен (текст + точка-диск), без gradient-pill, для плотной карусели «В наличии сейчас» (Фича 4) где полный pill был бы избыточен.

### Изменения в `Mobile/components/AutoRail.tsx`

Расширить props (backward-compatible):

```typescript
interface AutoRailProps {
  // ... существующие
  headerActionLabel?: string;              // "Смотреть все →"
  onHeaderActionPress?: () => void;
  itemBadgeRenderer?: (item) => ReactNode; // замена ♥ на mini-pill (или null)
  rotatingHeaderIcon?: boolean;            // disc вращается после заголовка (Фича 4)
}
```

Discogs-новинки продолжают работать как раньше (если новые props не переданы — fallback на текущее поведение).

### Правила «когда НЕ показывать» (Hot Stock)

Дублируем из Фичи 2.8 как чек-лист для имплементации:

1. **Карточка в коллекции пользователя** — НЕ показываем `inStock` (только `altVersion` если есть).
2. **`preorder`** — НЕ показываем в `compact`-карточках (только на детальном экране).
3. **`altVersion`** — НЕ показываем в карточках главной (только в вишлисте, на детальном экране и в маркете).
4. **`listing.last_seen_at > 7 дней`** → backend возвращает `none` (страховка от устаревших данных, уже есть в `api/offers.py`).
5. **Сетка где >20 карточек** → НЕ запускаем entry-анимацию (только статичный pill, чтобы не тормозить рендер).

---

## Что у нас уже есть готового (что переиспользуем)

| Готово | Откуда | Используется в |
|---|---|---|
| `Notification` модель + типы `wishlist_in_stock`/`wishlist_price_drop` | юзер сделал сегодня | Фича 1 |
| `notify_wishlist_in_stock` toggle у юзера | юзер сделал сегодня | Фича 1 |
| `expo-notifications` инфра + `NotificationItem.tsx` | существующее | Фича 1 |
| `RarityAura.TierLabel` — шаблон бейджа | существующее | Фича 2 |
| `RecordCard` с variant `expanded` | существующее | Фича 2 |
| Chip-фильтры в `search.tsx` (`FORMAT_OPTIONS`) | существующее | Фича 3 |
| `react-native-gesture-handler` (Swipeable) | стоит в Expo | Фича 5 |
| `Record.discogs_master_id` индекс + поле | существующее | Фичи 1, 5 |
| `OffersBlock` + `api.getRecordOffers` | Phase 0 | Фича 5 |
| `api.trackOfferClick` + click-таблица | Phase A affiliate | Все фичи |

---

## Что от тебя нужно для запуска

В порядке последовательности:

1. **Подтвердить дизайн Hot Stock pill** (Фича 2) — gradient cobalt→ember, disc-точка, outline для alt-версии, 6 состояний. Если хочешь — могу собрать визуальный мокап в Pencil.
2. **Подтвердить размещение Маркета в поиске** (Фича 4) — второй `AutoRail` ниже Discogs-новинок, кнопка «Смотреть все →» → search-grid с чипом «В продаже».
3. **Подтвердить порядок реализации** — Sprint 1 (Hot Stock pill в карточках) → 2 (уведомления) → 3 (wishlist swipe) → 4 (Маркет в поиске). Или другой порядок.
4. **Подключить 2-3 магазина** (Plastinka.com, Vinylpark, ещё один) — иначе все эти фичи будут выглядеть пусто. Без данных Hot Stock не зажжётся ни на одной карточке.
5. **Включить `SCRAPERS_ENABLED=true` на staging** после фикса `rate_limiter.py` Priority.ENRICHMENT timeout (см. SHOPS_PARSING.md).

---

## Связанные документы

- [SHOPS_PARSING.md](SHOPS_PARSING.md) — основной план (Backend инфра, парсеры, affiliate)
- [AFFILIATE_OUTREACH_TEMPLATE.md](AFFILIATE_OUTREACH_TEMPLATE.md) — шаблон для direct-партнёрок
- [DEV_SETUP_LOCAL.md](../../dev/DEV_SETUP_LOCAL.md) — как поднять локально

---

## Файлы для имплементации

**Новые:**
- `Backend/app/api/market.py` — endpoint `GET /api/market/new-arrivals` (Фича 4)
- `Backend/app/api/offers.py` — endpoint `POST /api/records/offers/summary` (Фича 2, batch для сеток)
- `Backend/app/tasks/wishlist_alerts.py` — уведомления (Фича 1)
- `Backend/alembic/versions/YYYYMMDD_record_offers_summary_view.py` — materialized view
- `Mobile/components/HotStockTag.tsx` — главный pill-компонент (Фича 2)
- `Mobile/components/MiniPriceBadge.tsx` — компактная версия для карусели маркета (Фича 4)
- `Mobile/components/WishlistRowWithOffers.tsx` — swipe wrap (Фича 5)
- `Mobile/components/OffersDrawer.tsx` — компактный drawer (Фича 5)
- `Mobile/components/OfferDetailBottomSheet.tsx` — полный список с описанием (Фича 5)

**Изменяемые:**
- `Backend/app/api/records.py` — добавить `?in_stock_only=true` параметр (Фича 3)
- `Backend/app/api/offers.py` — расширить `/records/{id}/offers` response полем `summary: RecordOffersSummary`; добавить `?include_master_versions=true` (Фича 5)
- `Backend/app/schemas/offer.py` — `RecordOffersSummary`, `MarketCarouselItem`
- `Backend/app/main.py` — регистрация market-роутера и нового cron `notify_wishlist_offers`
- `Backend/app/models/notification.py` — добавить enum `wishlist_alt_version_in_stock`
- `Mobile/lib/types.ts` — `RecordOffersSummary`, `HotStockVariant`, `MarketCarouselItem`
- `Mobile/lib/api.ts` — `getOffersSummary(discogsIds[])`, `getMarketFeed(limit)`
- `Mobile/constants/theme.ts` — убедиться что `Shadows.glowEmber` есть; добавить `Gradients.hotStock`
- `Mobile/components/RecordCard.tsx` — встроить `HotStockTag` в 3 варианта (compact/expanded/list)
- `Mobile/components/AutoRail.tsx` — props `headerActionLabel`, `onHeaderActionPress`, `itemBadgeRenderer`, `rotatingHeaderIcon` (backward-compatible)
- `Mobile/components/NotificationItem.tsx` — новые типы алертов
- `Mobile/app/(tabs)/search.tsx` — чип «В продаже» (Фича 3) + второй `AutoRail` блок «В наличии сейчас» (Фича 4) + обработка query-param `in_stock=1`
- `Mobile/app/(tabs)/collection.tsx` — вишлист с swipe-сравнением (Фича 5)
- `Mobile/app/record/[id].tsx` — заменить «Примерная стоимость» блок на двухстрочную композицию с `HotStockTag` (Фича 2.5)

**Отложено в Phase 2** (Фича 4.9 — если карусели+чипа окажется мало):
- `Mobile/app/(tabs)/market.tsx` — отдельный экран маркета
- `Mobile/app/(tabs)/_layout.tsx` — таб «Маркет»
- `Backend/app/api/market.py` — endpoint `GET /api/market/listings` (с фильтрами по магазину/цене/сортировке)
- `Mobile/components/MarketCard.tsx` — карточка с полем «магазин»
