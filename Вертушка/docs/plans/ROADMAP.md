# 🎵 Вертушка — Roadmap

> Приложение для коллекционеров винила: каталог, поиск через Discogs, сканер штрихкодов и обложек, рарити-теги, рублёвые цены, публичные профили, gift-booking. Один разработчик ([@bamsrf](https://github.com/bamsrf)) + Claude Code.

| Параметр | Значение |
|---|---|
| **Репо** | [bamsrf/Vertushka](https://github.com/bamsrf/Vertushka) |
| **Прод-API** | https://api.vinyl-vertushka.ru/api |
| **TestFlight / Google Play** | _появится в M2_ |
| **Последнее обновление** | 2026-05-01 |
| **Текущий milestone** | M1 (Дизайн-система v2 + Маскот) |
| **Прогресс** | M0 ✅ · M1 ⬜ · M2 ⬜ · M3–M10 ⬜ |

---

## Содержание

1. [Принципы](#0-принципы)
2. [Snapshot — где мы сейчас](#1-snapshot)
3. [Карта планов](#2-карта-планов)
4. [Milestones](#3-milestones)
   - [M1. Дизайн-система v2 + Маскот](#m1-дизайн-система-v2--маскот)
   - [M2. Production Release (App Store + Google Play)](#m2-production-release-app-store--google-play)
   - [M3. Свои пластинки (user-submitted records)](#m3-свои-пластинки-user-submitted-records)
   - [M4. Импорт коллекций](#m4-импорт-коллекций)
   - [M5. Достижения](#m5-достижения)
   - [M6. Парсинг магазинов РФ](#m6-парсинг-магазинов-рф)
   - [M7. Магазины-партнёры (in-app purchase flow)](#m7-магазины-партнёры-in-app-purchase-flow)
   - [M8. P2P-маркетплейс](#m8-p2p-маркетплейс)
   - [M9. Персональные рекомендации](#m9-персональные-рекомендации)
   - [M10. Юнит-экономика и монетизация](#m10-юнит-экономика-и-монетизация)
5. [Changelog](#4-changelog)
6. [Backlog](#5-backlog)
7. [Как обновлять документ](#6-как-обновлять-документ)

**Легенда статусов:** ⬜ Not started · 🟨 In progress · ✅ Done · 🟥 Blocked · 🧊 Frozen

---

## 0. Принципы

Roadmap — это не «что хочется», а «что соответствует продукту». Сверяемся с этими принципами при принятии решений.

### Продукт
1. **Глубина > количество.** «100 пластинок» — слабая ачивка. «10 разных стран пресса» — сильная. Объективные сигналы (Discogs данные) > редакторские пометки.
2. **Уважение к коллекции.** Награды описывают _кто ты как коллекционер_, а не _DAU-механику_. Никаких streak-логинов, «открой 7 дней подряд», sgoраний.
3. **Лор и виниловая культура.** Тон голоса — узнаваемый коллекционерами. Не «коллекционер», а «Хранитель Сторон Б».
4. **Социальный жест престижнее накопления.** Дарить пластинку (gift-booking) — сильнее, чем просто иметь.
5. **Анти-grind.** Если фичу можно сфармить за вечер скриптом — её незачем делать. Все массовые механики требуют разнообразия.

### Технические
6. **Прод и локалка изолированы.** Реальную коллекцию строить только на проде; локальная Docker-БД может быть потеряна. См. [PRINCIPLES.md](PRINCIPLES.md#данные-пользователей-локалка-vs-прод).
7. **Discogs URL не модифицировать.** Подписанные imgproxy URL — менять параметры нельзя, подпись сломается.
8. **Дублей планов нет.** Каждый milestone ссылается на _один_ detail-spec. Если детали меняются — правится spec, а не roadmap.

### Чего **не** делаем
- Реклама в ленте, продажа данных юзеров, pay-to-win-ачивки.
- Streak-логины, push-«мы соскучились», ежедневные квесты.
- Поверхностная локализация (английский — отложить до момента, когда РФ-аудитория стабильна).

---

## 1. Snapshot

### 1.1. Стек

**Backend** — `Backend/`
- FastAPI + SQLAlchemy(asyncpg) + PostgreSQL + Redis + Alembic
- 11 API роутеров: auth, records, collections, wishlists, users, gifts, profile, export, covers, user_photos, masters
- 13 сервисов: discogs, pricing, valuation, exchange, cache, cover_storage, openai_vision, email, notifications, rate_limiter, search_cache_db, auth_oauth, и др.
- Деплой: Docker Compose на `85.198.85.12`, prod API: `https://api.vinyl-vertushka.ru/api`
- Скрипты: `recalc_collection_rub.py`, `backfill_rarity_flags.py`, `backfill_vinyl_colors.py`, `migrate_covers.py`, `deploy.sh`, `backup.sh`

**Mobile** — `Mobile/`
- Expo SDK 54, React Native 0.81.5, React 19.1, Expo Router 6
- Zustand 5 (5 сторов: auth, collection, scanner, searchHistory, onboarding) + Axios 1.13 (с retry/refresh-интерсепторами)
- 22 экрана: `(auth)/*`, `(tabs)/*`, `record/[id]`, `master/[id]/{index,versions}`, `artist/[id]`, `user/[username]`, `social/list`, `settings/*`, `folder/[id]`, `onboarding`
- 23 компонента: `RarityAura`, `RecordCard/Grid`, `VinylColorTag`, `VinylSpinner`, `GlassTabBar`, `AnimatedGradientText` и др.
- EAS configured (projectId `a603ba4b-…`), Bundle ID iOS/Android: `com.vertushka.app`

**Внешние интеграции**
- Discogs API (search, releases, masters, marketplace stats; rate limiter 0.95 req/s; кэш 7 дней)
- OpenAI Vision (распознавание обложки через камеру)
- Yandex SMTP (восстановление пароля, gift-booking уведомления)
- Apple Sign In + Google OAuth

### 1.2. Реализовано ✅

**Авторизация и аккаунты**
- Email/пароль + Apple Sign In + Google OAuth ([Backend/app/api/auth.py](../../Backend/app/api/auth.py), `(auth)/login.tsx`, `(auth)/register.tsx`)
- Восстановление пароля (коды на email) — `forgot-password.tsx`, `reset-password.tsx`
- Soft delete + 30-дневное окно восстановления

**Поиск пластинок**
- Текстовый поиск с трансслитерацией кириллицы → латиница ([services/discogs.py](../../Backend/app/services/discogs.py))
- Сканер штрихкодов и распознавание обложек через GPT-4o Vision ([services/openai_vision.py](../../Backend/app/services/openai_vision.py))
- Suggest с автодополнением, история поиска (первые 5 + «показать ещё»)
- Витрина новинок (24 релиза) на главной

**Коллекция и Вишлист**
- CRUD коллекции с condition, sleeve_condition, notes, shelf_position, фото
- Папки (folders) с drag-to-folder UI
- Вишлист с приоритетами, заметками, пометкой «куплено»
- Gift-booking: бронирование подарка незарегистрированным дарителем, cancel-token, expires_at, email-уведомления ([models/gift_booking.py](../../Backend/app/models/gift_booking.py))

**Редкость (4 тира)** — детали: [`/plans/RARITY_BADGES_PLAN.md`](RARITY_BADGES_PLAN.md)
- 🩶 **Канон** (`is_canon`) — main_release_id из Discogs, slate-графит палитра, 5s border glow
- 💚 **Коллекционка** (`is_collectible`) — комбо: цена ≥ $100 AND num_for_sale ≤ 3 AND have ≤ 200; emerald, rotating gradient
- 🟣 **Лимитка** (`is_limited`) — Test Pressing / Promo / Limited Edition / Numbered / White Label; violet pulse 4s
- 🟠 **Популярно** (`is_hot`) — have ≥ 100 AND want/have ≥ 1.5; ember 2s
- Распределение на тестовой коллекции (188 шт): canon 12%, collectible 2.7%, limited 40%, hot 8%
- Закрытый тир: «1-й пресс» — open→close после статистики (>49% коллекции = потеря смысла), детали в спеке

**Цены RUB**
- Компонентная формула: `(USD + shipping) × (1 + overhead) + customs` ([services/pricing.py](../../Backend/app/services/pricing.py))
- Параметры через env: shipping $20, overhead 30% (РФ/СССР) или 20% (ин.), customs 15% при USD > $220, format-множители (box ×1.6, 7" ×0.6, 10" ×0.8)
- Ежедневные снапшоты стоимости коллекции в RUB → дельта 30 дней ([models/collection_value_snapshot.py](../../Backend/app/models/collection_value_snapshot.py))
- Курс USD/RUB через [services/exchange.py](../../Backend/app/services/exchange.py) (кэш ЦБ)

**Социалка**
- Публичный профиль с share_token, настройки видимости (collection / wishlist / prices / year / format), highlight_record_ids, og_image ([models/profile_share.py](../../Backend/app/models/profile_share.py))
- Подписки: Follow (many-to-many), `user/[username]/index.tsx`
- Лента активности (collection_add events) — `social/list.tsx`

**UX**
- Onboarding v2: welcome-карусель + 10-шаговый интерактивный тур
- Suggest-поиск с автодополнением
- Сетка/список + фильтры формата в коллекции и вишлисте
- ErrorBoundary, OfflineBanner, retry на 503/429, token-refresh интерцептор

**Инфраструктура**
- Redis singleton с graceful fallback, connection pool (20)
- Token bucket rate limiter (60 tokens, 1/sec, capacity 55)
- Приоритетная очередь Discogs: SEARCH(1) → DETAIL(2) → SCAN(3) → ENRICHMENT(4) → BATCH(5)
- APScheduler: фоновое обновление цен (4:00) и обогащение артистов (5:00)
- search_cache (PostgreSQL + hourly cleanup), structured JSON logging, Sentry hooks

### 1.3. В процессе 🟨

| Что | Где | Статус |
|---|---|---|
| VinylSpinner / VinylColorTag | [`/VINYL_SPINNER_PLAN.md`](VINYL_SPINNER_PLAN.md) | План + бэкфилл-скрипт готовы, не интегрированы. UI-компоненты ждут merge |
| RarityAura visual polish | `Mobile/components/RarityAura.tsx` | Незакоммиченный diff: усиление opacity, collectible переведён на rotating gradient |

### 1.4. Метрики

- **PR-velocity:** 10 merged PR за 28 апр – 1 мая (≈10 PR/неделю), 0 открытых
- **Тестовая коллекция:** ~188 записей для калибровки рарити-логики
- **Аккаунты:** 1 активный разработчик, прод-аккаунт с реальной коллекцией

---

## 2. Карта планов

ROADMAP.md — это _верхнеуровневый зонтик_. Каждый milestone ссылается на конкретный детальный spec. Существующие планы остаются как они есть; новые добавляются по мере открытия milestone'ов.

| Milestone | Detail-spec | Статус spec'а |
|---|---|---|
| M1. Дизайн+Маскот | `docs/plans/PLAN_DESIGN_SYSTEM_V2.md` | 🆕 будет создан в начале M1 |
| M2. Release | [PLAN_RELEASE_v2.md](PLAN_RELEASE_v2.md) | ✅ есть, ~65% реализовано |
| M3. Свои пластинки | `docs/plans/PLAN_USER_SUBMITTED_RECORDS.md` | 🆕 |
| M4. Импорт | `docs/plans/PLAN_COLLECTION_IMPORT.md` | 🆕 |
| M5. Достижения | [`/plans/PLAN_ACHIEVEMENTS.md`](PLAN_ACHIEVEMENTS.md) | ✅ есть, 84 ачивки в 11 категориях |
| M6. Парсинг РФ | `docs/plans/PLAN_RU_SHOPS_PARSING.md` | 🆕 |
| M7. Магазины-партнёры | `docs/plans/PLAN_AFFILIATE_FLOW.md` | 🆕 |
| M8. P2P | `docs/plans/PLAN_P2P_MARKETPLACE.md` | 🆕 |
| M9. Рекомендации | `docs/plans/PLAN_RECOMMENDATIONS.md` | 🆕 |
| M10. Юнит-экономика | `docs/plans/UNIT_ECONOMICS.md` | 🆕 |

Связанные технические планы (не milestone'ы, но важные):
- [PRINCIPLES.md](PRINCIPLES.md) — техника (Discogs API, локалка vs прод, кэш)
- [BUGS.md](../BUGS.md) — реестр багов
- [`/plans/RARITY_BADGES_PLAN.md`](RARITY_BADGES_PLAN.md) — рарити-теги (готово ✅)
- [`/plans/RARITY_DESIGN_BRIEF.md`](RARITY_DESIGN_BRIEF.md) — design brief для иллюстратора
- [`/VINYL_SPINNER_PLAN.md`](VINYL_SPINNER_PLAN.md) — vinyl spinner (в процессе 🟨)

---

## 3. Milestones

---

### M1. Дизайн-система v2 + Маскот

**Статус:** ⬜ Not started
**Goal:** Маскот Вертушки на всех empty/loading/error states + единая дизайн-система без хардкода вне `theme.ts`.
**Why:** Без маскота и единого визуального языка App Store-скриншоты выглядят как «yet another Discogs клон». Маскот = узнаваемость + лицо для соцсетей (TikTok, Telegram).
**Owner:** bamsrf + иллюстратор (внешний)
**Target:** до сабмита M2
**Detail-spec:** `docs/plans/PLAN_DESIGN_SYSTEM_V2.md` — будет создан в начале M1

#### Объём

**Design (внешний иллюстратор по брифу)**
- Концепт маскота: винильный персонаж, narrative — «Хранитель полки». Тон: тёплый, ироничный, не детский. Референсы: Spotify Wrapped мини-персонажи, Mailchimp Freddie, Duolingo (но без агрессии).
- 6–8 поз/состояний:
  - `idle` — полка с пластинками
  - `scanning` — смотрит в камеру/штрих-код
  - `gift` — упаковывает пластинку (для gift-booking)
  - `achievement-unlock` — поднимает пластинку как трофей
  - `empty-state` — задумчивый/«пустая полка»
  - `error` — растерянный/иголка соскочила
  - `loading` — крутит пластинку
  - `celebrating` — для крупных ачивок и дельты стоимости коллекции вверх
- App Icon (4 размера) + Splash Screen с маскотом
- Иллюстрация для App Store / Google Play feature graphic

**Mobile**
- Унификация токенов: ревизия [Mobile/constants/theme.ts](../../Mobile/constants/theme.ts), сведение всех цветов/тени/радиусов/typography в один источник истины. Цель — `grep -rn "rgba\|#[0-9a-f]" Mobile/` не находит хардкод вне theme.ts (с эксклюзией ауры).
- Ревизия `RarityAura` палитр на согласованность с base theme.
- Применить маскот ко всем экранам:
  - Empty states: пустая коллекция, пустой вишлист, нет результатов поиска, оффлайн, нет ачивок
  - Loading states: заменить `ActivityIndicator` на `VinylSpinner`-варианты с маскотом
  - Error states: ErrorBoundary, network error, 503/429
- Обновить App Icon + Splash Screen.
- Доработать `AnimatedGradientPalette` под маскот.

**Backend**
- Не требует изменений, кроме (опц.) endpoint `GET /me/profile/og-image` для генерации OG-картинки публичного профиля с маскотом.

#### Acceptance criteria
- [ ] Бриф для иллюстратора утверждён + 6–8 поз доставлены в SVG/PNG
- [ ] App Icon обновлён, прошёл Apple HIG check (нет полупрозрачности, корректные углы)
- [ ] Splash Screen обновлён
- [ ] Все empty/loading/error states используют маскот (≥10 экранов)
- [ ] `Mobile/constants/theme.ts` — единственный источник цвета/тени/радиуса (грэп подтверждает)
- [ ] `docs/plans/PLAN_DESIGN_SYSTEM_V2.md` создан и содержит токены + маскот-гайдлайн
- [ ] Snapshot-тесты на ключевые экраны (Storybook или Detox screenshot tests — опц.)

#### Зависимости
- **Блокирует:** M2 (релиз нельзя без иконки и скриншотов)
- **Блокируется:** —

#### Связанные артефакты
- [`/plans/RARITY_DESIGN_BRIEF.md`](RARITY_DESIGN_BRIEF.md) — пример формата брифа
- `Mobile/constants/theme.ts`, `Mobile/components/AnimatedGradientText.tsx`

#### Changelog
- _нет записей_

---

### M2. Production Release (App Store + Google Play)

**Статус:** ⬜ Not started (но ~65% базы готово — см. PLAN_RELEASE_v2.md)
**Goal:** Приложение опубликовано в App Store **и** Google Play в один день. Стабильно держит 1000 DAU.
**Why:** Без публичного релиза остальные milestone'ы (P2P, парсинг, рекомендации) — работают на 1 пользователя. Пора собирать фидбек.
**Owner:** bamsrf
**Target:** через ~3 недели после M1
**Detail-spec:** [PLAN_RELEASE_v2.md](PLAN_RELEASE_v2.md) — детальный план с фазами 0–6

#### Объём

**Что уже сделано (по PLAN_RELEASE_v2.md):**
✅ Apple Sign In в `app.json`, Privacy/Terms URLs, Soft delete, JWT+bcrypt, Sentry hooks, Redis cache, request deduplication, retry 503/429, deep linking, expo-image cache.

**Что осталось (по PLAN_RELEASE_v2 и наблюдениям):**

**Mobile / Stores**
- iOS / TestFlight:
  - Заполнить в `Mobile/eas.json`: `ascAppId`, `appleTeamId`
  - App Store Connect: создать запись, заполнить метаданные (описание RU/EN, keywords, support/privacy URL, age rating, privacy manifest для camera/photos/email)
  - Скриншоты iPhone 6.7"/6.5" (5–10 шт. с маскотом из M1)
  - Build profile production-ios → upload → internal testers → external testers (после крэш-фри 99%)
  - Soak ≥2 недели в TestFlight перед App Store submit
- Android / Google Play:
  - Заполнить в `Mobile/eas.json`: `serviceAccountKeyPath`
  - Google Play Console: app, internal testing track
  - Store listing (Phone+Tablet скриншоты, feature graphic 1024×500, описание, data safety form, content rating questionnaire)
  - Build profile production-android (AAB) → internal testing → production track
- Релиз — синхронный: одна публичная дата для обеих платформ
- Review notes на русском с тестовым аккаунтом и кратким сценарием

**Backend / Инфраструктура**
- Прохождение PLAN_RELEASE_v2 фаз 0–4 (Блокеры → Наблюдаемость → Инфра → Mobile prod quality → Security hardening)
- Алармы (Sentry / Telegram bot) на падение ошибочного rate, 5xx, latency p99
- DB backup schedule + restore-drill (хотя бы один раз руками)

**Compliance**
- App Store Review Guidelines: проверить UGC moderation policy (нужна для будущего M3/M8 — лучше задокументировать сейчас, чтобы не переделывать review)
- Google Play Developer Policy: data safety form честно отражает сбор камеры/фото/email
- Условия использования + политика конфиденциальности на сайте (RU + EN)

#### Acceptance criteria
- [ ] PLAN_RELEASE_v2 фаза 0 завершена (нет блокеров)
- [ ] PLAN_RELEASE_v2 фаза 1 (Sentry активный с DSN, Telegram-алармы)
- [ ] ≥3 внешних тестера в TestFlight, ≥3 в Google Play internal testing
- [ ] Crash-free rate ≥99% за неделю soak
- [ ] App Store review пройден (≤2 итерации)
- [ ] Google Play review пройден
- [ ] Опубликовано в обеих платформах в один день
- [ ] Условия + политика на сайте (RU/EN)

#### Зависимости
- **Блокирует:** M3 (UGC), M8 (P2P) — некуда сабмитить новое до релиза
- **Блокируется:** M1 (нужны иконка + скриншоты + маскот)

#### Связанные артефакты
- [PLAN_RELEASE_v2.md](PLAN_RELEASE_v2.md), [PLAN_RELEASE.md](PLAN_RELEASE.md) (исторический), [BUGS.md](../BUGS.md)
- `Mobile/eas.json`, `Mobile/app.json`

#### Changelog
- _нет записей_

---

### M3. Свои пластинки (user-submitted records)

**Статус:** ⬜ Not started
**Goal:** Пользователь может добавить пластинку, которой нет в Discogs (самиздат, тираж <500, региональные релизы РФ/СССР), и она появится в его коллекции и в общем поиске после модерации.
**Why:** РФ/СССР-релизы и underground-самиздат плохо покрыты в Discogs. Без user-submitted мы блокируем самую интересную для коллекционеров часть рынка.
**Owner:** bamsrf
**Target:** после M2
**Detail-spec:** `docs/plans/PLAN_USER_SUBMITTED_RECORDS.md` — будет создан в начале M3

#### Объём

**Backend**
- Расширить модель `Record`: поле `source: enum('discogs', 'user') = 'discogs'` + `submitted_by_user_id: nullable FK User` + `moderation_status: enum('pending', 'approved', 'rejected') nullable`
- Новые endpoints:
  - `POST /records/user-submitted/` — создать (поля: title, artist, year, label, format, vinyl_color, описание, barcode, обложка через `cover_storage`)
  - `PATCH /records/user-submitted/{id}/` — редактирование автором до approval
  - `POST /admin/records/{id}/moderate/` — admin endpoint (approve/reject + причина)
  - `GET /me/submitted/` — список своих submitted с статусами
- Валидация: проверка дублей по barcode (если barcode совпадает с существующим Record — отказ с предложением «вы имели в виду эту?»), валидация года, размера обложки (<5MB)
- Модерация:
  - В первой версии — ручная (admin endpoint, я просматриваю)
  - Pending submissions видны только автору; в общий поиск попадают только approved
  - Auto-approve если у юзера ≥10 уже approved submissions (доверие)

**Mobile**
- Новый экран `Mobile/app/record/new.tsx`: форма с фото обложки (камера + галерея), поля title/artist/year/label/format/vinyl_color/описание/barcode
- Точка входа: на экране поиска кнопка «Не нашли? Добавьте» при пустых результатах
- Превью карточки перед отправкой
- В `record/[id].tsx` для user-submitted — бейдж «Добавлено сообществом» + ссылка на профиль автора
- В профиле — счётчик approved submissions (в M5 → ачивка `D_first_submission`)

**Юр.** — связано с M2: UGC moderation policy в App Store/Google Play. Чёткое 24-часовое SLA на модерацию.

#### Acceptance criteria
- [ ] Юзер может создать record без Discogs ID и видеть его в своей коллекции (как pending)
- [ ] После approve запись попадает в общий поиск
- [ ] Reject с причиной отображается автору
- [ ] Дубли по barcode не создаются
- [ ] Время модерации ≤24 часа (SLA в политике)
- [ ] Detail-spec написан и согласован

#### Зависимости
- **Блокирует:** M5 (некоторые ачивки опираются на user-submitted)
- **Блокируется:** M2 (UGC moderation policy в Store)

#### Связанные артефакты
- [models/record.py](../../Backend/app/models/record.py), [services/cover_storage.py](../../Backend/app/services/cover_storage.py)

#### Changelog
- _нет записей_

---

### M4. Импорт коллекций

**Статус:** ⬜ Not started
**Goal:** Юзер может импортировать коллекцию из Discogs / CSV / других винил-приложений за <2 минут на 100 записей.
**Why:** Главный барьер первого использования — «надо вручную добавлять 500 пластинок». Импорт = моментальная ценность.
**Owner:** bamsrf
**Target:** после M2 (можно параллельно M3)
**Detail-spec:** `docs/plans/PLAN_COLLECTION_IMPORT.md` — будет создан в начале M4

#### Объём

**Источники (приоритет)**
1. **Discogs collection** (CSV экспорт через Discogs settings) — самый частый случай для коллекционеров
2. **Discogs OAuth** (пуллинг через API) — следующий шаг, дороже в разработке (rate limiter)
3. **Простой CSV** (title, artist, year, [barcode], [condition], [notes]) — универсальный fallback
4. **Roon / Vinylhub / Vinyl Engine** — если будут запросы

**Backend**
- Новый endpoint `POST /collections/import/{source}` — принимает file/токен, создаёт `ImportJob (id, user_id, source, status, total, found, not_found, duplicates, started_at, finished_at)`
- Асинхронный воркер (через APScheduler / asyncio.create_task) — резолвит каждую запись через [services/discogs.py](../../Backend/app/services/discogs.py) batch-режим
- Endpoint `GET /collections/import/{job_id}/` — статус + найденные/не найденные/дубли
- Endpoint `POST /collections/import/{job_id}/confirm` — после превью пользователь подтверждает создание

**Mobile**
- Новый экран `Mobile/app/settings/import.tsx`
- Шаги: выбор источника → загрузка файла или OAuth → ожидание (прогресс-бар, polling) → превью «найдено N / не найдено M / дублей K» → подтверждение
- Обработка дубликатов: skip / update / replace — пользовательский выбор для каждой записи или batch
- Ошибки сети / частичный fallback

**Edge cases**
- 1000+ записей — chunking (по 50) + retry на rate limiter
- Discogs CSV содержит ID-колонку → fast-path без поиска (resolve по `discogs_id`)
- Записи с тем же `discogs_id` уже в коллекции — пометка «уже есть»

#### Acceptance criteria
- [ ] Импорт 100 записей из Discogs CSV за <2 минут
- [ ] Превью показывает found/not_found/duplicates с возможностью точечного ревью
- [ ] Поддержка ≥3 источников (Discogs CSV, Discogs OAuth, простой CSV)
- [ ] Прогресс-бар обновляется в реальном времени
- [ ] Detail-spec написан

#### Зависимости
- **Блокирует:** ничего (но улучшает onboarding для всех будущих юзеров)
- **Блокируется:** M2 (релиз)

#### Связанные артефакты
- [services/discogs.py](../../Backend/app/services/discogs.py) — batch-резолв
- [models/collection.py](../../Backend/app/models/collection.py)

#### Changelog
- _нет записей_

---

### M5. Достижения

**Статус:** ⬜ Not started — план готов
**Goal:** Запустить первые 14 ачивок (категории A + B), интегрировать в профиль, добавить push при анлоке.
**Why:** Достижения превращают каталог в живой ритуал коллекционера + увеличивают retention без grind-механик.
**Owner:** bamsrf
**Target:** после M2
**Detail-spec:** [`/plans/PLAN_ACHIEVEMENTS.md`](PLAN_ACHIEVEMENTS.md) — 84 ачивки в 11 категориях, философия и каталог проработаны

#### Поэтапный запуск
1. **Этап 1 (sub-milestone M5.1):** категории A (Foundation, 7 ачивок) + B (Collection size, 7 ачивок) — простые счётчики, дают мгновенную ценность
2. **Этап 2 (M5.2):** категория C (Rarity, 13 ачивок) — опирается на готовые `is_canon/is_collectible/is_limited/is_hot` флаги
3. **Этап 3 (M5.3):** категории D–K (социальные / лор / редкие) — после получения первого фидбека

#### Объём (M5.1)

**Backend**
- Новые модели:
  - `Achievement (code, name, tier, hidden, category, condition_type, condition_params, flavor_text, icon_url, unlocked_count)` — каталог
  - `UserAchievement (user_id, achievement_code, unlocked_at, progress)` — прогресс юзера
- Сервис `services/achievements.py`:
  - `recalculate_for_user(user_id)` — пересчёт всех applicable ачивок
  - `recalculate_on_event(user_id, event_type)` — точечный пересчёт по триггеру (`collection_add`, `wishlist_add`, ...)
- API:
  - `GET /me/achievements/` — список (locked/unlocked + progress)
  - `GET /achievements/` — публичный каталог
- Triggering:
  - На каждой мутации коллекции/вишлиста — async task запускает recalculate_on_event
  - Ежедневная background task — full recalc для всех активных юзеров (insurance)

**Mobile**
- Новый экран `Mobile/app/profile/achievements.tsx`:
  - Сетка с прогресс-барами (стилизованных как канавки пластинки — спираль от центра к краю)
  - Группировка по категориям, фильтр locked/unlocked
  - Tap → детальный модал с flavor text, прогресс, как разблокировать
- Toast/notification при анлоке (через expo-notifications)
- Бейдж в профиле «X из Y ачивок»

**Контент**
- Иконки 14 ачивок (черновые из M1 маскот-стиля)
- Flavor texts — есть в PLAN_ACHIEVEMENTS.md

#### Acceptance criteria
- [ ] 14 ачивок (A1–A7, B1–B7) работают на тестовом аккаунте
- [ ] Push приходит при анлоке (в момент мутации)
- [ ] Экран в профиле показывает прогресс
- [ ] Нет лагов на пересчёте при коллекции 1000+ записей
- [ ] Detail-spec обновлён с разделом Implementation

#### Зависимости
- **Блокирует:** —
- **Блокируется:** M1 (маскот для иконок), M2 (push notifications)

#### Связанные артефакты
- [`/plans/PLAN_ACHIEVEMENTS.md`](PLAN_ACHIEVEMENTS.md)

#### Changelog
- _нет записей_

---

### M6. Парсинг магазинов РФ

**Статус:** ⬜ Not started
**Goal:** Для записей в вишлистах пользователей показываются актуальные офферы из ≥3 РФ-магазинов с ценой в RUB и ссылкой.
**Why:** Самый частый запрос коллекционеров: «где купить эту пластинку в России». Без этого приложение остаётся каталогом, а не инструментом покупки.
**Owner:** bamsrf
**Target:** после M2/M3
**Detail-spec:** `docs/plans/PLAN_RU_SHOPS_PARSING.md` — будет создан в начале M6 (включая ресёрч магазинов и юр. аспект)

#### Объём

**Ресёрч (первый шаг)**
- Кандидаты: Plastinka.com, Vinylbox, Vinyl-Era, Sound-Bar, Plate, Музторг (винил-секция), Авито (винил-категория с фильтрами)
- Критерии выбора топ-3–5: размер ассортимента, читаемость HTML/JSON, наличие robots.txt-ограничений, частота обновления цен
- Юр.: не публикуем чужой контент, ссылка на оригинал, respect robots.txt + rate limit

**Backend**
- Новая папка `Backend/app/services/ru_shops/` с adapter-pattern (один файл = один магазин):
  - `base.py` — абстрактный `ShopAdapter` (поиск по barcode/title+artist, парсинг карточки)
  - `plastinka.py`, `vinylbox.py`, `sound_bar.py`, ...
  - `registry.py` — список активных адаптеров
- Модель `RuShopOffer (id, record_id, shop_slug, url, price_rub, condition, last_seen_at, is_available, raw_title)`
- Сервис `services/ru_shops_orchestrator.py`:
  - Робот раз в N часов проходит по записям из вишлистов пользователей (приоритезация: wishlist > collection > popular)
  - Для каждой записи дёргает каждый адаптер
  - Кэш + дельта (если price/availability не изменилось — TTL 24ч; иначе — обновление)
- Endpoint `GET /records/{id}/ru-offers/` — список офферов
- Background task через APScheduler

**Mobile**
- На карточке `Mobile/app/record/[id].tsx` блок «Купить в РФ» (показывается только если есть ≥1 оффер): магазин, цена RUB, condition, link → открывает webview/external browser
- В вишлисте — мини-индикатор «N магазинов имеют наличие» рядом с записью

**Ограничения и риски**
- robots.txt: respect; если магазин запретил — сразу удаляем адаптер
- IP-блокировка: использовать пользовательский IP-rotation pool или fallback на browserless (Playwright) для сложных случаев
- Спам/некорректные парсы: alert на drop > 50% офферов от магазина за день

#### Acceptance criteria
- [ ] Ресёрч-документ выбрал топ-3–5 магазинов
- [ ] ≥3 адаптера написаны и проходят integration tests
- [ ] Background scheduler работает на проде, парсит вишлисты пользователей
- [ ] На карточке показываются актуальные офферы (≤24 часа давности)
- [ ] robots.txt уважается, юр. чек пройден
- [ ] Detail-spec написан

#### Зависимости
- **Блокирует:** M7 (без офферов нет affiliate flow)
- **Блокируется:** M2 (релиз)

#### Связанные артефакты
- [services/discogs.py](../../Backend/app/services/discogs.py) — паттерн adapter + rate limiter
- [services/cache.py](../../Backend/app/services/cache.py) — Redis для кэширования

#### Changelog
- _нет записей_

---

### M7. Магазины-партнёры (in-app purchase flow)

**Статус:** ⬜ Not started
**Goal:** ≥2 партнёрства с РФ-магазинами с tracking кликов; первый rouble revenue.
**Why:** Главная гипотеза монетизации (M10). Без affiliate-flow приложение остаётся бесплатным сервисом без устойчивости.
**Owner:** bamsrf + переговоры с магазинами
**Target:** после M6
**Detail-spec:** `docs/plans/PLAN_AFFILIATE_FLOW.md` — будет создан в начале M7

#### Объём

**Партнёрства (вне кода)**
- Список целевых магазинов из M6
- Типовая модель: CPC (1₽–5₽ за клик), CPA (% от сделки 3–10%), или фиксированный месячный платёж за featured-place
- Договор + реферальная ссылка с UTM
- Health check: ежемесячная сверка кликов с магазина и наших данных

**Backend**
- Расширить `RuShopOffer`: поле `is_partner: bool`, `affiliate_template: nullable str` (URL-шаблон с подстановкой record_id или offer_id)
- Новая модель `PurchaseClick (id, user_id nullable, offer_id, shop_slug, clicked_at, user_agent, ip_hash, referrer)` — для unit-economics
- Endpoint `GET /records/{id}/buy/{offer_id}/` — редирект (302) на affiliate URL с tracking-меткой; перед редиректом пишет PurchaseClick
- Webhook от магазина (если поддерживает): `POST /webhooks/{shop}/purchase/` — обновляет PurchaseClick.completed_at + amount_rub

**Mobile**
- На карточке record/[id]: кнопка «Купить в {shop}» вместо прямой ссылки → открывает наш `/records/.../buy/...` URL → редирект → магазин открывается в webview/external
- Subtle UI-метка «Партнёр» (не агрессивная — соответствие принципу «не реклама»)

**Аналитика**
- Дашборд (простой — Grafana/Metabase или собственный admin endpoint): clicks/day, conversions, revenue, top-performing shops
- Алерт: если clicks/day упал на >50% — что-то сломалось

#### Acceptance criteria
- [ ] ≥2 партнёрских договора подписаны
- [ ] Tracking работает (PurchaseClick пишется на каждый клик)
- [ ] Первый rouble revenue зафиксирован
- [ ] Дашборд показывает основные метрики
- [ ] Detail-spec написан

#### Зависимости
- **Блокирует:** M10 (валидация unit-economics)
- **Блокируется:** M6 (нужны офферы)

#### Связанные артефакты
- M6 PLAN_RU_SHOPS_PARSING

#### Changelog
- _нет записей_

---

### M8. P2P-маркетплейс

**Статус:** ⬜ Not started
**Goal:** Юзеры могут выставлять лоты, находить лоты других юзеров, договариваться о сделке, оставлять рейтинг.
**Why:** Самая ценная функция для коллекционеров — рынок между собой (минуя магазины-перекупов). Самый рискованный milestone (UGC, anti-fraud, юр.).
**Owner:** bamsrf
**Target:** после M2 + стабильной базы (M3, M5, частично M7)
**Detail-spec:** `docs/plans/PLAN_P2P_MARKETPLACE.md` — будет создан в начале M8

#### Объём

**Backend**
- Модели:
  - `Listing (id, seller_id, record_id, condition, sleeve_condition, price_rub, photos[], status: enum, created_at, sold_at, description)`
  - `Order (id, listing_id, buyer_id, status: enum(pending, agreed, shipped, delivered, cancelled, disputed), agreed_price_rub, created_at, ...)`
  - `Message (id, order_id, sender_id, text, attachments[], created_at, read_at)`
  - `Rating (id, order_id, rater_id, rated_id, rating: 1-5, comment, created_at)` — рейтинг и продавца, и покупателя
- API:
  - `POST /marketplace/listings/` — выставить (валидация: запись должна быть в коллекции продавца — anti-fraud)
  - `GET /marketplace/listings/` — поиск с фильтрами (record, price range, condition, location)
  - `POST /marketplace/listings/{id}/order/` — открыть order
  - `WS /marketplace/orders/{id}/messages/` — чат
  - `POST /marketplace/orders/{id}/rate/` — оставить рейтинг

**Anti-fraud / Reputation**
- Продавец может выставить только запись из своей коллекции (с возможностью «удалить из коллекции после продажи» одной кнопкой)
- Рейтинг продавца виден в листинге, формула: weighted avg + штраф за отменённые сделки
- Reports: жалоба → блокировка → review

**Платежи**
- v1 (M8.1): без in-app платежей. Контакт между сторонами через чат + рейтинг по факту. Минимизирует регуляторный риск.
- v2 (M8.2 — отдельно): эскроу через ЮKassa / CloudPayments. Юр. оформление как «информационная услуга / комиссия за поиск контрагента».

**Mobile**
- Новые экраны:
  - `marketplace/index.tsx` — поиск/лента
  - `marketplace/listing/[id].tsx` — карточка лота
  - `marketplace/sell.tsx` — выставить (с автозаполнением из своей коллекции)
  - `messages/index.tsx`, `messages/[order_id].tsx` — чат
  - `profile/listings.tsx`, `profile/orders.tsx` — мои лоты, мои сделки

**Compliance**
- App Store / Google Play UGC + marketplace policies — заранее (в M2 политика согласована)
- Российское законодательство о маркетплейсах между физлицами — консультация юриста перед запуском
- Возрастное ограничение / verifiable consent

#### Acceptance criteria
- [ ] Лот выставляется, появляется в поиске
- [ ] Order открывается, чат работает (WebSocket)
- [ ] Рейтинг считается корректно
- [ ] Anti-fraud: листинг привязан к коллекции
- [ ] Юр. чек пройден
- [ ] Detail-spec написан

#### Зависимости
- **Блокирует:** —
- **Блокируется:** M2 (UGC policy), желательно после M5 (доверие через ачивки)

#### Связанные артефакты
- [models/gift_booking.py](../../Backend/app/models/gift_booking.py) — паттерн «сделки между юзерами»
- [models/follow.py](../../Backend/app/models/follow.py) — социальная база

#### Changelog
- _нет записей_

---

### M9. Персональные рекомендации

**Статус:** ⬜ Not started
**Goal:** Каждый юзер с коллекцией ≥10 записей получает 20 релевантных рекомендаций. CTR на рекомендации ≥5% (метрика после M2).
**Why:** Discovery — главная не-каталоговая ценность приложения. «Что мне послушать дальше» — постоянный вопрос коллекционера.
**Owner:** bamsrf
**Target:** после M2 + достаточная база
**Detail-spec:** `docs/plans/PLAN_RECOMMENDATIONS.md` — будет создан в начале M9

#### Поэтапно

**v1 (M9.1) — content-based**
- «Похожие на то, что у вас» по тегам Discogs:
  - Жанр (genre) + стиль (style)
  - Артист (тот же или связанные)
  - Лейбл
  - Год / десятилетие
  - Страна релиза
- Простая модель: для каждой пары (user, record) считаем score = Σ weighted overlap по тегам
- Reason-string: «Похоже на 5 записей в вашей коллекции (King Crimson, Jaki Liebezeit)»

**v2 (M9.2) — collaborative-light**
- «Юзеры с похожей коллекцией слушают»
- Cosine similarity между user-vectors из коллекции
- Hybrid: 60% content-based + 40% collaborative

**Backend**
- Модель `RecommendationFeed (user_id, record_id, score, reason, generated_at)`
- Сервис `services/recommendations.py`:
  - Daily background task → пересчёт для активных юзеров (≥10 записей в коллекции)
  - Endpoint `GET /me/recommendations/?limit=20`
- Сигналы:
  - Коллекция (вес ×1.0)
  - Вишлист (×1.5 — явный сигнал интереса)
  - Поиск с follow-up на запись (×0.3)
  - Просмотр публичного профиля артиста (×0.2)
  - Уже известные / отвергнутые рекомендации — exclude

**Mobile**
- Новая секция «Тебе может понравиться» на главной (`(tabs)/index.tsx` или новая `discover.tsx`)
- На карточке рекомендации — reason-string + actions (Add to Wishlist, Hide, View)
- В Profile — секция «Что слушают похожие коллекционеры» (после M9.2)

**Метрики**
- CTR на рекомендации, conversion → wishlist add, hide rate
- A/B тестирование вариантов формул

#### Acceptance criteria
- [ ] v1 работает: рекомендации генерируются для всех активных юзеров
- [ ] CTR ≥5% (после 2 недель сбора данных)
- [ ] Hide rate ≤30% (если выше — модель плохая)
- [ ] Detail-spec написан

#### Зависимости
- **Блокирует:** —
- **Блокируется:** M2 (нужны реальные юзеры для калибровки)

#### Связанные артефакты
- [models/collection_value_snapshot.py](../../Backend/app/models/collection_value_snapshot.py) — паттерн ежедневной background task

#### Changelog
- _нет записей_

---

### M10. Юнит-экономика и монетизация

**Статус:** ⬜ Not started (но проектируем сейчас)
**Goal:** Ясная модель монетизации с ≥1 активным каналом revenue + первое позитивное unit-economics (CAC < LTV).
**Why:** Без устойчивости приложение умрёт. Проектировать рано (сейчас) → тестировать после M2 → масштабировать после M7.
**Owner:** bamsrf
**Target:** живёт параллельно всем milestone'ам; чек-поинты после M7 и M8
**Detail-spec:** `docs/plans/UNIT_ECONOMICS.md` — будет создан до M2

#### Гипотезы источников дохода (приоритет)

1. **Affiliate с РФ-магазинами (M7)** — % с продаж от партнёрских кликов
   - Размер рынка: оценить через wishlist data (сколько рублей/мес юзеры хотят купить)
   - Ожидаемый CPA: 3–7%
2. **Premium-подписка** — 199₽/мес или 1990₽/год
   - Что входит: расширенная статистика, импорт без лимитов, приоритетный парсинг офферов, эксклюзивные ачивки/темы профиля, ранний доступ к фичам
   - Что **не** входит: ограничение коллекции (этого никогда не будет), реклама в free-версии (этого никогда не будет)
3. **P2P-комиссия (M8 v2)** — % от сделки или фиксированная плата за выставление
   - Комиссия 5–10% при эскроу через ЮKassa
4. **B2B / Data licensing** — данные о трендах рынка винила РФ для лейблов/магазинов
   - На дальнюю перспективу (≥1000 активных юзеров)

#### Что **не** будем делать
- Реклама в ленте (в т.ч. nativeАDS)
- Продажа данных юзеров
- Pay-to-win-ачивки (в т.ч. покупка прогресса)
- Платный доступ к каталогу/рекомендациям

#### Метрики

**Engagement**
- DAU/WAU/MAU (через Sentry/PostHog/собственный endpoint)
- Retention D1/D7/D30
- Сессий в день, среднее время в приложении

**Revenue**
- ARPU = revenue / MAU
- LTV = ARPU × среднее время жизни (месяцы)
- CAC = маркетинговый бюджет / новые юзеры

**Cost**
- Серверные расходы (Хетзнер/собственный сервер) — ~3000₽/мес сейчас
- Discogs API (бесплатный) + OpenAI Vision (~10₽ на 1000 распознаваний)
- Yandex SMTP, Sentry — пока бесплатные тиры

#### Каналы привлечения (гипотезы)

1. **TikTok с маскотом** (после M1) — короткие видео «5 пластинок, которые удивили меня в этой коллекции» с маскотом-комментатором
2. **Telegram-канал** — еженедельные дайджесты «топ-10 коллекций недели» (с разрешением юзеров)
3. **Форумы коллекционеров** — реддит, vk-группы, vinyl-форумы — органическое присутствие
4. **Виниловые ярмарки** — оффлайн-промо (стенд + флаеры) на московских/питерских ярмарках
5. **Партнёрство с магазинами** (M7) — взаимная реклама

#### Acceptance criteria
- [ ] `UNIT_ECONOMICS.md` написан с цифровыми гипотезами
- [ ] ≥1 канал revenue работает (M7 affiliate)
- [ ] Метрики собираются (DAU/MAU/ARPU/Retention)
- [ ] CAC < LTV (после M7+)
- [ ] Список целевых каналов привлечения с измеримыми KPI

#### Зависимости
- **Блокирует:** —
- **Блокируется:** M2 (нужны метрики), M7 (первый revenue)

#### Связанные артефакты
- M7, M8 — основные источники revenue

#### Changelog
- _нет записей_

---

## 4. Changelog

Хронологическая лента merged PR. Обновляется автоматически (см. секцию 6) — при каждом merged PR в `main` GitHub Action запускает `scripts/sync_roadmap.py`, который дописывает строку сюда и в Changelog соответствующего M-блока.

### 2026-05

- **2026-05-01** — [#10](https://github.com/bamsrf/Vertushka/pull/10) chore(pricing): фикс PYTHONPATH в обёртке recalc — _maintenance_
- **2026-05-01** — [#9](https://github.com/bamsrf/Vertushka/pull/9) feat(rarity): «Коллекционка» (комбо-сигнал) + закрыт 1-й пресс — _база для M5_

### 2026-04

- **2026-04-29** — [#8](https://github.com/bamsrf/Vertushka/pull/8) feat(rarity): новый тир «Канон» + строгий 1-й пресс — _база для M5_
- **2026-04-29** — [#7](https://github.com/bamsrf/Vertushka/pull/7) chore(pricing): одноразовый recalc CollectionItem.estimated_price_rub — _база для M9, M10_
- **2026-04-29** — [#5](https://github.com/bamsrf/Vertushka/pull/5) feat(mobile): новый онбординг — welcome-карусель + 10-шаговый интерактивный тур — _подготовка к M2_
- **2026-04-28** — [#4](https://github.com/bamsrf/Vertushka/pull/4) feat(web): фильтр формата + grid/list тоггл в Вишлисте + правка empty-state
- **2026-04-28** — [#3](https://github.com/bamsrf/Vertushka/pull/3) feat(new-releases): витрина 24 релиза вместо 12
- **2026-04-28** — [#2](https://github.com/bamsrf/Vertushka/pull/2) feat(web): фильтр по форматам + тоггл grid/list в коллекции публичного профиля
- **2026-04-28** — [#1](https://github.com/bamsrf/Vertushka/pull/1) feat(mobile/search): история — первые 5 + «Показать ещё», тап по новинкам открывает карточку

---

## 5. Backlog

Идеи, которые не дотягивают до отдельного milestone'а или ещё не дозрели. Складываем сюда; если идея набирает массу — повышаем до milestone'а.

### Discovery / UX
- Печать каталога коллекции в PDF (под виниловые встречи / страховку)
- Audio fingerprinting (Shazam-style) — распознавание играющей пластинки через микрофон
- Listening sessions tracking — «что я слушал сегодня»
- Виниловые «shelf challenges» — сезонные (например, «октябрьский darkfolk», «январский русский авангард»)
- Notifications: «появилась версия из вашего вишлиста дешевле $X»

### Платформы
- Apple Watch — быстрый просмотр цены текущей пластинки в коллекции через NFC tag
- iPad app — table view коллекции + drag-to-folder
- macOS Catalyst — десктоп-версия для каталогизации

### Локализация
- English UI (после стабилизации РФ-аудитории)
- Турецкий, немецкий — рынки с активной винил-культурой

### Контент
- Партнёрство с виниловыми ярмарками — официальный каталог ярмарки в приложении
- Лейблы — стартовая коллекция «всё от 4AD», «всё от Tape Loop»

### Технические долги
- Полная типизация Python (mypy strict)
- E2E-тесты Mobile (Detox или Maestro)
- Storybook для компонентов
- Миграция Mobile на Tamagui (если перерастём theme.ts)

---

## 6. Как обновлять документ

### Правило
**После каждого merged PR в `main`:**
1. GitHub Action `.github/workflows/sync-roadmap.yml` запускается автоматически
2. Скрипт `scripts/sync_roadmap.py` парсит conventional-commit prefix и scope (например, `feat(rarity): …` → M5) через словарь `SCOPE_TO_MILESTONE` в коде скрипта
3. Дописывает строку в:
   - Секцию 4 (Changelog) с датой и ссылкой
   - Changelog соответствующего M-блока (если scope известен)
4. Открывает sync-PR `chore(roadmap): sync changelog #N`
5. Я мержу sync-PR (или закрываю, если автоматика ошиблась)

### Ручное обновление (когда нужно)
- **При завершении milestone:** статус → ✅, дата completion в шапку, обновить Snapshot (1.2 / 1.3)
- **При смене scope/приоритета:** пересортировка milestone'ов; в коммите-объяснении — почему
- **Раз в неделю:** пробежаться по Snapshot 1.2 / 1.3 и Acceptance criteria, проставить галочки

### Как добавить новый milestone
- Если задача не вписывается в существующие — добавить как `M11.` (нумерация не пересчитывается, чтобы внешние ссылки не ломались)
- Создать detail-spec в `docs/plans/PLAN_<NAME>.md`
- Обновить таблицу в секции 2 (Карта планов)

### Как переместить idea из Backlog в milestone
- Когда становится ясно «это нужно делать» — повысить до милестоуна с порядковым номером (например, M11), создать detail-spec, удалить из Backlog

### Скрипт-помощник
- `scripts/sync_roadmap.py` — читает PR через `gh CLI` или GH Actions payload, парсит scope, обновляет ROADMAP.md
- Запуск локально: `python scripts/sync_roadmap.py --pr 9`
- Запуск из CI: автоматически на `pull_request closed && merged == true`

### История ревизий ROADMAP.md
- **2026-05-01** — initial (создание документа, M1–M10, начальный Changelog)
