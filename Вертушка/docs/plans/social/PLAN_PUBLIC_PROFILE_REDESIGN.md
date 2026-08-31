# План: Production-ready публичный профиль Вертушка

## Context

Цель — довести публичный профиль (`vinyl-vertushka.ru/@username` + mobile-экран чужого профиля) до прод-готовности по дизайн-файлам в [Vertuska_publicPRofile/](../../../Design/Vertuska_publicPRofile/). Меняем визуальный язык с тёмной темы (`#0f0f0f`/`#e85d04`) на light premium (`#F4EEE6` ivory + `#3A4BE0` cobalt), добавляем рейлы «Недавно добавленные» и «Новинки», блок-объяснение бронирования, метрику прироста стоимости за месяц. Параллельно чиним 3 бага в текущей логике брони.

Аудит выявил критические пробелы инфраструктуры:
- Снапшотов стоимости коллекции **нет** — нужна новая модель + ежедневный cron.
- Cron `auto_extend_expired_bookings` **продлевает** бронь на 30 дней, хотя по продукту должен **освобождать** её.
- В `Backend/app/api/gifts.py:357` endpoint `/me/received` отдаёт `gifter_name` владельцу — нарушает анонимность.
- Текст шаблона напоминания в `Backend/app/services/notifications.py:88` обещает «бронь продлится автоматически» — нужно «истечёт».

Решения:
- **Прирост за месяц**: блок скрывается, если истории снапшотов < 30 дней.
- **Новинки**: `year >= current_year - 1`, сортировка по числу появлений в `WishlistItem.record_id`, лимит 12.
- **Рейлы**: и Web, и Mobile.
- **Mobile экран**: полный rewrite под дизайн.

---

## 1. Backend — данные и логика

### 1.1 Новая модель снапшотов
Файл: `Backend/app/models/collection_value_snapshot.py` (создать)

```python
class CollectionValueSnapshot(Base):
    id: UUID
    user_id: UUID  # FK → users.id, ondelete=CASCADE, indexed
    snapshot_date: date  # уникальный составной (user_id, snapshot_date)
    total_value_rub: Decimal  # сумма estimated_price_median * курс на момент
    items_count: int
    created_at: datetime
```
- Один индекс `(user_id, snapshot_date DESC)` для быстрых выборок.
- Миграция: новый файл в `Backend/alembic/versions/` с шаблоном дат как у `20260417_add_user_record_photos.py`.

### 1.2 Cron ежедневного снапшота
Файл: `Backend/app/tasks/valuation_tasks.py` (создать)

- `record_daily_snapshots()`: один INSERT-from-SELECT, считающий сумму `estimated_price_median` через те же join'ы, что в `profile.py:206-213`. Конвертация USD→RUB переиспользуется существующая, если есть, иначе храним в USD и конвертим на чтении.
- Регистрация в `main.py:93-114`: cron `05:00` ежедневно (после `update_prices_batch` в `04:00` — снапшот возьмёт уже обновлённые цены).

### 1.3 Helper расчёта дельты
Файл: `Backend/app/services/valuation.py` (создать)

```python
async def get_monthly_delta(user_id: UUID, db) -> Decimal | None:
    # Возвращает None, если самый старый снапшот юзера < 30 дней назад.
    # Иначе: today_value - value_30_days_ago.
```
Используется в `/api/profile/public/{username}` и в `web/routes.py`.

### 1.4 Endpoints для рейлов
Файл: `Backend/app/api/profile.py` (расширить)

- `GET /api/profile/public/{username}/recent-additions?limit=10` — последние `CollectionItem` юзера по `added_at DESC`, маппим в `PublicProfileRecord`.
- `GET /api/profile/public/new-releases?limit=12` — глобальный (не юзер-зависимый) запрос:
  ```sql
  SELECT records.*, COUNT(wishlist_items.id) AS demand
  FROM records
  LEFT JOIN wishlist_items ON wishlist_items.record_id = records.id
  WHERE records.year >= EXTRACT(YEAR FROM NOW()) - 1
  GROUP BY records.id
  ORDER BY demand DESC, records.year DESC
  LIMIT 12
  ```
  Кэшируем результат in-memory на 1 час (рейл общий для всех юзеров).

### 1.5 Расширить `PublicProfileResponse`
Файл: `Backend/app/schemas/profile.py`

Добавить поля:
```python
monthly_value_delta_rub: float | None  # None если < 30 дней снапшотов
recent_additions: list[PublicProfileRecord]
new_releases: list[PublicProfileRecord]
```
Вшить `recent_additions` (8 шт) и `new_releases` (12 шт) в основной JSON — публичная страница рендерится одним запросом.

### 1.6 Фиксы анонимности и логики брони (3 бага)
1. `gifts.py:357` — в `/me/received` всегда возвращать `gifter_name=""`, `gifter_email=""`. Выровнять по образцу строки 179.
2. `booking_tasks.py:57-86` — переименовать `auto_extend_expired_bookings` → `auto_release_expired_bookings`. Логика: для броней `BOOKED` с `expires_at < now()` ставим `status=CANCELLED`, `cancellation_reason='expired'` (новое необязательное поле), очищаем связь с `wishlist_item` (nullable FK).
3. `notifications.py:88` — заменить «бронь продлится автоматически» на «по истечении срока бронь будет автоматически освобождена».

### 1.7 Web-роут — обновить контекст
Файл: `Backend/app/web/routes.py:44-163`

Передавать в шаблон: `monthly_delta`, `recent_additions`, `new_releases`. Вынести логику в общий helper `get_public_profile_payload(user, db)` — переиспользуется в API endpoint и web-роуте.

---

## 2. Web — полный rewrite шаблона

Файл: `Backend/app/web/templates/public_profile.html` (переписать с нуля, 781 → ~600 строк)

### Структура (по vertushka-screen.jsx + vertushka-desktop.jsx)

```
<header> ВЕРТУШКА · ПРОФИЛЬ + share icon
<hero>
  ├─ Spinning Vinyl SVG (170px, 14s linear)
  ├─ @username + bio + custom_title
  └─ Stats row: collection_count · collection_value_rub · monthly_delta (если не None)
<segmented> Коллекция / Вишлист (animated pill, ~420ms cubic-bezier)
<rails-area> (crossfade ~2.5s между табами)
  ├─ Collection state: RecentlyAddedRail (recent_additions)
  └─ Wishlist state:
       ├─ BookingExplainer (4 шага: 🔒 анонимно · 🎁 60 дней · ⏰ напоминание за 7 · 📅 авто-release)
       └─ НовинкиRail (new_releases)
<grid> 3-колоночный (desktop) / 2-колоночный (≤768px) RecordCardGrid
  └─ ReservedBadge на забронированных (только в wishlist)
<footer> CTA «Создать свой профиль»
```

### Палитра (CSS-переменные)
```css
--ivory: #F4EEE6;
--pearl: #F7F4EE;
--cobalt: #3A4BE0;
--periwinkle: #9AA8FF;
--lavender: #C9B8FF;
--blush: #F6C7D0;
--ink: #1B1D26;
--slate: #6B7080;
--mute: #9096A6;
--hairline: rgba(27,29,38,0.08);
```
Фон: радиальные градиенты как в `vertushka-system.jsx:22-26`.

### Motion (vanilla CSS/JS)
- Vinyl: `@keyframes spin 14s linear infinite`
- Value counter: одноразовая `1.6s` анимация `cubic-bezier(.22,.7,.18,1)` от 0 до целевого значения
- Segmented pill: `transform: translateX(...)` 420ms
- Crossfade рейлов: opacity 2.5s при смене таба
- CTA sweep: ~3.8s `linear-gradient` glint

### Booking-модалка (обновить копию)
Сохранить существующие поля формы (`gifter_name`, `gifter_email`, `gifter_message`), endpoint `POST /api/gifts/book` без изменений. Текст:
> Бронь анонимная — владелец увидит только статус «забронировано». Срок 60 дней. За 7 дней до истечения вы получите напоминание на email. Если подарок не вручён — бронь освободится автоматически.

### Desktop breakpoints
- ≥1024px: 3-колоночный grid, hero в 2 колонки (vinyl + текст)
- 768–1023px: 2-колоночный grid, hero в 1 колонку
- <768px: 2-колоночный grid, рейлы свайпаются

**Не используем** ios-frame mockup как desktop preview — desktop рендерит реальный контент.

---

## 3. Mobile — полный rewrite экрана

Файл: `Mobile/app/user/[username]/index.tsx` (698 → ~550 строк, переписать)

### Маппинг дизайн → RN компоненты

| Design | RN компонент | Файл |
|--------|-------------|------|
| Spinning Vinyl | `<Vinyl/>` | `components/profile/Vinyl.tsx` |
| Segmented с pill | `<ProfileSegmented/>` | `components/profile/ProfileSegmented.tsx` (Reanimated) |
| RecentlyAddedRail | `<RecentlyAddedRail/>` | `components/profile/RecentlyAddedRail.tsx` |
| НовинкиRail | `<NewReleasesRail/>` | `components/profile/NewReleasesRail.tsx` |
| BookingExplainer | `<BookingExplainer/>` | `components/profile/BookingExplainer.tsx` |
| ReservedBadge | `<ReservedBadge/>` | `components/profile/ReservedBadge.tsx` (lilac pulse) |
| DetailOverlay | `<RecordDetailSheet/>` | `components/profile/RecordDetailSheet.tsx` |

### Палитра
Добавить namespace `theme.publicProfile` в `Mobile/constants/theme.ts` с точными токенами из дизайна. Глобальную тему не трогаем — остальные экраны не ломаются.

### State (Zustand)
В `store.ts`, `useProfileStore`: добавить `recentAdditions`, `newReleases`, метод `loadPublicProfile(username)` — дёргает `getPublicProfile`, который после §1.5 возвращает всё одним JSON.

### Booking flow
Существующая модалка (строки 386-461) переезжает в `components/profile/BookingSheet.tsx` с новой копией текста. Endpoint и валидация без изменений.

### Анимации
- Background hue transition при смене таба: `Animated.timing` 2500ms, два слоя `LinearGradient` с `interpolate`
- Auto-scroll рейла: `Animated.loop(Animated.timing(scrollX, ...))` 30s
- Vinyl spin: `Animated.loop(Animated.timing(rotate, { toValue: 1, duration: 14000, easing: Easing.linear }))`

---

## 4. OG-image (опционально, не блокер)

Файл: `Backend/app/services/og_image.py`

Перерисовать под новую палитру: ivory фон, cobalt акценты, коллаж 4 highlight-обложек слева, имя/статы справа. Pillow генерация, кэш по `user_id+updated_at` хэшу.

---

## 5. Критические файлы

| Файл | Действие |
|------|----------|
| `Backend/app/models/collection_value_snapshot.py` | создать |
| `Backend/alembic/versions/20260427_*.py` | миграция: snapshot table + `gift_booking.cancellation_reason` |
| `Backend/app/services/valuation.py` | создать |
| `Backend/app/tasks/valuation_tasks.py` | создать |
| `Backend/app/tasks/booking_tasks.py` | release вместо extend |
| `Backend/app/services/notifications.py` | обновить текст напоминания |
| `Backend/app/api/profile.py` | расширить + новые endpoints |
| `Backend/app/api/gifts.py` | замаскировать `gifter_name` в `/me/received` |
| `Backend/app/schemas/profile.py` | новые поля ответа |
| `Backend/app/main.py` | регистрация cron |
| `Backend/app/web/routes.py` | новые поля в контекст шаблона |
| `Backend/app/web/templates/public_profile.html` | rewrite |
| `Mobile/app/user/[username]/index.tsx` | rewrite |
| `Mobile/components/profile/*.tsx` | 7 новых компонентов |
| `Mobile/components/RecordCard.tsx` | стили под новую палитру |
| `Mobile/constants/theme.ts` | `theme.publicProfile` namespace |
| `Mobile/lib/types.ts` | расширить `PublicProfile` |
| `Mobile/lib/store.ts` | расширить `useProfileStore` |

---

## 6. Порядок реализации (4 PR)

1. **PR-1: Backend данные + фиксы багов** — модель снапшотов, миграция, cron, valuation helper, расширение `PublicProfileResponse`, фиксы анонимности и release-логики, текст письма.
2. **PR-2: Web rewrite** — новый `public_profile.html` под light-палитру, рейлы, BookingExplainer, обновлённая модалка.
3. **PR-3: Mobile rewrite** — новые компоненты, переписанный экран, Reanimated-анимации.
4. **PR-4 (опц.)**: OG-image под новую палитру.

---

## 7. Верификация

**PR-1:**
- `curl https://api.vinyl-vertushka.ru/api/profile/public/testuser` → JSON содержит `recent_additions`, `new_releases`, `monthly_value_delta_rub`
- Снапшот 31+ день назад → дельта возвращается; < 30 дней → `null`
- Бронь с `expires_at = NOW() - 1 day` → после cron `status=CANCELLED`, `cancellation_reason='expired'`
- `/me/received` → `gifter_name == ""`

**PR-2:**
- `vinyl-vertushka.ru/@testuser` в Chrome desktop и Safari iPhone — layout по дизайн-файлам
- Переключение Коллекция/Вишлист — плавный фон 2-3s, рейлы crossfade корректно
- Booking-модалка → текст про 60 дней + анонимность → отправить → owner получает push без имени
- Поделиться в Telegram → OG превью с новой палитрой

**PR-3:**
- iOS sim + Android sim: vinyl крутится 14s, рейлы скроллятся
- Booking flow проходит до конца
- Остальные экраны не сломались (используем только `theme.publicProfile`)
- `is_booked` бейдж lilac, не оранжевый

**Deploy:** `git push && ssh deploy@85.198.85.12 'cd ~/vertushka && bash Вертушка/Backend/scripts/deploy.sh'` после PR-1 и PR-2.

---

## 8. Доработки после первого релиза (post-review fixes)

После первой реализации владелец вернул список регрессий и недостающего поведения. Делаем поэтапно, в одном PR-5.

### Mobile (`Mobile/app/user/[username]/index.tsx` + компоненты)

| # | Проблема | Решение |
|---|----------|---------|
| M1 | Винил «уехал», нет анимации, нет типографической маркировки на диске | Вернуть spin (`Animated.loop`, 14s, `useNativeDriver: true`), вписать в hero по центру, добавить криволинейный лейбл «ВЕРТУШКА · ПРОФИЛЬ» вокруг шпинделя (SVG `<TextPath>` или 8 повёрнутых `Text` по окружности) |
| M2 | Фон не переключается между коллекцией и вишлистом | Починить `bgAnim` — два `LinearGradient` слоя, opacity interpolate `[0,1]→[1,0]` и `[0,1]→[0,1]`, оба `pointerEvents="none"`, `useNativeDriver: true` для opacity |
| M3 | Сегмент-контрол не по центру | `alignSelf: 'center'` на `<Segmented/>` + контейнер `alignItems: 'center'` |
| M4 | Дубли пластинок в гриде коллекции | Грид коллекции должен брать **полную** коллекцию (не `recent_additions`). Добавить endpoint `GET /api/profile/public/{username}/collection?limit=200` или включить `collection: PublicProfileRecord[]` в основной payload. Дедуп по `record.id` на бэке |
| M5 | В вишлисте лишний BookingExplainer | Заменить на 1-строчный hint: «Бронь анонимна · 60 дней · напоминание за 7». Большой блок убрать |
| M6 | Обложки в вишлисте «поплыли» | Унифицировать: тот же `RecordCardLight` что и в коллекции, та же сетка |
| M7 | Сверху в коллекции лишняя статистика 16/5/0 | Удалить блок `statsRow` (lines 683-698) |
| M8 | Нет переключения плитка/список и фильтра по форматам | Добавить `<ViewToggle/>` (grid/list) и `<FormatFilter/>` (LP/EP/7"/Все) над гридом. List = одна колонка с горизонтальной карточкой |
| M9 | «Недавно добавленные» не движутся | `Animated.loop(Animated.timing(scrollX, …, 30000))` на горизонтальном `Animated.ScrollView`, бесконечная прокрутка через дублирование массива ×2 |
| M10 | Карточки в коллекции слишком большие | 3 колонки, размер обложки = размер обложки в рейле (~108-110px) для визуальной когерентности |
| M11 | Не показывается стоимость | Добавить `estimated_price_median` в `PublicProfileRecord` (бэк) и рендерить под названием маленькой строкой `~₽{price}` |
| M12 | CTA внизу не читается как sticky overlay | `position: absolute, bottom: 0` с `LinearGradient` фейдом сверху-вниз (от прозрачного к ivory), кнопка cobalt с лёгкой тенью, `safeAreaInset.bottom` |

### Web (`Backend/app/web/templates/public_profile.html`)

| # | Проблема | Решение |
|---|----------|---------|
| W1 | Hero не отцентрирован | `.hero { justify-content: center; align-items: center; text-align: center; grid-template-columns: auto; }` для ≥1024px — vinyl сверху, текст под ним по центру (как в моб. дизайне) |
| W2 | Винил не крутится | Проверить, что `.vinyl` не перекрыт `prefers-reduced-motion: reduce` (либо обернуть keyframes в `@media (prefers-reduced-motion: no-preference)`), убедиться что не теряется `animation` при ре-рендере. Принудительный `will-change: transform` |
| W3 | Цена не подтягивается | В `Backend/app/schemas/profile.py` `PublicProfileRecord` уже должен иметь `estimated_price_median`. Проверить, что web-route передаёт и в `card-price` `<span>` всегда выводится цена при наличии (без флага `show_record_prices` на публичном профиле — это публичная цена рынка, не личная) |

### Backend изменения

- `Backend/app/schemas/profile.py` — добавить `estimated_price_median: float | None` в `PublicProfileRecord`, добавить `collection: list[PublicProfileRecord]` (полная коллекция, дедуп по record_id) в `PublicProfileResponse`
- `Backend/app/api/profile.py` — extend `_build_public_profile_payload` чтобы включать цену и полную коллекцию
- `Backend/app/web/routes.py` — пробросить `collection` и цены в шаблон

### Порядок исполнения

1. Backend: schema + endpoint (M4, M11, W3)
2. Mobile мелочи: M3, M5, M7 (убрать/центрировать)
3. Mobile грид: M4, M6, M10 (использовать `collection`, 3 колонки в рейл-размер)
4. Mobile vinyl: M1 (spin + лейбл)
5. Mobile background: M2
6. Mobile rail auto-scroll: M9
7. Mobile toggle/filter: M8
8. Mobile sticky CTA: M12
9. Mobile цена в карточке: M11
10. Web: W1 (центрирование), W2 (spin), W3 (цена)
