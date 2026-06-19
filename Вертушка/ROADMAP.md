# 🎵 Вертушка — Roadmap

> Приложение для коллекционеров винила: каталог, поиск через Discogs, сканер штрихкодов и обложек, рарити-теги, рублёвые цены, публичные профили, gift-booking. Один разработчик ([@bamsrf](https://github.com/bamsrf)) + Claude Code.

| Параметр | Значение |
|---|---|
| **Репо** | [bamsrf/Vertushka](https://github.com/bamsrf/Vertushka) |
| **Прод-API** | https://api.vinyl-vertushka.ru/api |
| **TestFlight / Google Play** | TestFlight build prep ✅, soak в процессе (M2) |
| **Последнее обновление** | 2026-06-19 |
| **Текущий milestone** | M2 (Release prep) параллельно M5/M6 (зашиты в продукт) |
| **Прогресс** | M0 ✅ · M1 🟨 · M2 🟨 · M3 🟨 · M4 🟨 · M5 🟨 · M6 🟨 · M7 🟨 · M8 ⬜ · M9 ⬜ · M10 🟨 |

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
6. **Прод и локалка изолированы.** Реальную коллекцию строить только на проде; локальная Docker-БД может быть потеряна. См. [PRINCIPLES.md](docs/plans/PRINCIPLES.md#данные-пользователей-локалка-vs-прод).
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
- FastAPI + SQLAlchemy(asyncpg) + PostgreSQL + Redis + Alembic + WebSocket
- 19 API роутеров: auth, records, collections, wishlists, users, gifts, profile, export, covers, user_photos, waitlist, market, offers, messages, notifications, achievements, discogs_oauth, admin
- 30+ сервисов: discogs, discogs_index (local dump), pricing, valuation, marketplace_pricing, exchange, cache, cover_storage/_fallback/_matcher/_warm, openai_vision, listing_matcher, messaging, messages_ws_hub, notification_service, push, feed, affiliate, spotify, user_record, vinyl_color, scrapers/* и др.
- Scraping-стек: `scrapers/shops/` — korobkavinyla, plastinka_com, vinyl_ru, stoprobotvinyl, found
- Локальный slim Discogs-дамп (`discogs_index`) — local-first обложки/suggest/barcode/versions
- Деплой: Docker Compose на `85.198.85.12`, prod API: `https://api.vinyl-vertushka.ru/api`, self-hosted GlitchTip (sentry.vinyl-vertushka.ru)

**Mobile** — `Mobile/`
- Expo SDK 54, React Native 0.81.5, React 19.1, Expo Router 6
- Zustand 5 (16 сторов: auth, collection, scanner, search, suggest, searchHistory, sections, market, messages, notifications, follow, gift, profile, userSearch, cache, onboarding) + Axios 1.13
- ~43 экрана: `(auth)/*`, `(tabs)/*`, `record/[id]`, `record/manual`, `records/mine`, `master/[id]/{index,versions}`, `artist/[id]`, `market/{index,store/[slug]}`, `messages/*`, `notifications`, `achievements`, `user/[username]/*`, `gift/[id]`, `social/*`, `collection/value`, `folder/[id]`, `wishlist-folder/[id]`, `settings/*`, `onboarding`
- Компоненты: `RarityAura`, `RecordCard/Grid`, `VinylColorTag`, `VinylSpinner`, `AchievementPin`, `StoreCarousel`, `MarketSection`, `HotStockTag`, `OffersBlock`, `GlassTabBar` и др.
- expo-notifications (push), WebSocket realtime-чат
- EAS configured (projectId `a603ba4b-…`), Bundle ID iOS/Android: `com.vertushka.app`

**Внешние интеграции**
- Discogs API (search, releases, masters, marketplace stats) + локальный slim-дамп (local-first)
- OpenAI Vision (GPT-4o) + CLIP ONNX визуальный re-rank обложек
- Spotify (через `SPOTIFY_PROXY_URL`, обход RU geo-block)
- Yandex SMTP + Resend fallback (восстановление пароля, gift-booking, уведомления)
- Apple Sign In + Login via Discogs (OAuth + импорт коллекции); Google OAuth (кнопка скрыта)

### 1.2. Реализовано ✅

**Авторизация и аккаунты**
- Email/пароль + Apple Sign In + Google OAuth ([Backend/app/api/auth.py](Backend/app/api/auth.py), `(auth)/login.tsx`, `(auth)/register.tsx`)
- Восстановление пароля (коды на email) — `forgot-password.tsx`, `reset-password.tsx`
- Soft delete + 30-дневное окно восстановления

**Поиск пластинок**
- Текстовый поиск с трансслитерацией кириллицы → латиница ([services/discogs.py](Backend/app/services/discogs.py))
- **Local-first**: suggest, barcode, обложки, master-versions сначала бьют по локальному slim Discogs-дампу ([services/discogs_index.py](Backend/app/services/discogs_index.py)), к API — только на промах
- Сканер штрихкодов + GPT-4o Vision ([services/openai_vision.py](Backend/app/services/openai_vision.py)) + CLIP ONNX визуальный re-rank
- Suggest с автодополнением, история поиска (первые 5 + «показать ещё»)
- Гибридная витрина новинок (top-10, recency × want, ежемесячный refresh-job)

**Маркет РФ-магазинов** — детали: [PARSING.md](docs/plans/PARSING.md), [SHOPS_PARSING.md](docs/plans/SHOPS_PARSING.md)
- 5 парсеров: Коробка Винила, Plastinka.com, Vinyl.ru, StopRobotVinyl, Found ([scrapers/shops/](Backend/app/services/scrapers/shops/))
- 5-шаговый matcher листинг→record ([services/listing_matcher.py](Backend/app/services/listing_matcher.py)), store-native записи (`source='store'`)
- Маркет в Поиске (карусель «В наличии сейчас»), `/market`, `/market/store/[slug]`, Hot Stock pill, swipe-сравнение цен
- Distributed rate-limiter, parallel crawl, stock-refresh 6ч, smoke-checks ингеста

**Личные сообщения** — TG-style
- WebSocket realtime ([services/messages_ws_hub.py](Backend/app/services/messages_ws_hub.py)), typing, presence, read-receipts
- Reply / forward / edit / реакции / pin / mute / media / «поделиться пластинкой», message requests, block

**Уведомления**
- Лента «Ты» / «Подписки», Expo push ([services/push.py](Backend/app/services/push.py))
- v2: dedup-ключи (bump-or-create), snooze, weekly digest, quiet hours, badge, swipe-to-delete

**Достижения** — детали: [PLAN_ACHIEVEMENTS.md](docs/plans/PLAN_ACHIEVEMENTS.md)
- Архетипы «Физика звука» (XP-ladder), PNG/SVG-пины, серии Foundation/Collection/Rarity/Сообщество/Market/Пасхалки
- Per-achievement описания, share-карточка, push при анлоке, locked-плейсхолдеры

**Свои пластинки (user-submitted)**
- `source='user'` ([services/user_record.py](Backend/app/services/user_record.py)), Discogs-first ручной визард, self-enriching индекс
- Auto-approve по доверию, multi-format, dedup-intercept, правка автором; Login via Discogs + one-time импорт коллекции

**Коллекция и Вишлист**
- CRUD коллекции с condition, sleeve_condition, notes, shelf_position, фото
- Папки (folders) с drag-to-folder UI
- Вишлист с приоритетами, заметками, пометкой «куплено»
- Gift-booking: бронирование подарка незарегистрированным дарителем, cancel-token, expires_at, email-уведомления ([models/gift_booking.py](Backend/app/models/gift_booking.py))

**Редкость (4 тира)** — детали: [`/plans/RARITY_BADGES_PLAN.md`](docs/plans/RARITY_BADGES_PLAN.md)
- 🩶 **Канон** (`is_canon`) — main_release_id из Discogs, slate-графит палитра, 5s border glow
- 💚 **Коллекционка** (`is_collectible`) — комбо: цена ≥ $100 AND num_for_sale ≤ 3 AND have ≤ 200; emerald, rotating gradient
- 🟣 **Лимитка** (`is_limited`) — Test Pressing / Promo / Limited Edition / Numbered / White Label; violet pulse 4s
- 🟠 **Популярно** (`is_hot`) — have ≥ 100 AND want/have ≥ 1.5; ember 2s
- Распределение на тестовой коллекции (188 шт): canon 12%, collectible 2.7%, limited 40%, hot 8%
- Закрытый тир: «1-й пресс» — open→close после статистики (>49% коллекции = потеря смысла), детали в спеке

**Цены RUB**
- Компонентная формула: `(USD + shipping) × (1 + overhead) + customs` ([services/pricing.py](Backend/app/services/pricing.py))
- Параметры через env: shipping $20, overhead 30% (РФ/СССР) или 20% (ин.), customs 15% при USD > $220, format-множители (box ×1.6, 7" ×0.6, 10" ×0.8)
- Ежедневные снапшоты стоимости коллекции в RUB → дельта 30 дней ([models/collection_value_snapshot.py](Backend/app/models/collection_value_snapshot.py))
- Курс USD/RUB через [services/exchange.py](Backend/app/services/exchange.py) (кэш ЦБ)

**Социалка**
- Публичный профиль с share_token, настройки видимости (collection / wishlist / prices / year / format), highlight_record_ids, og_image ([models/profile_share.py](Backend/app/models/profile_share.py))
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
| M2 Release prep | [PLAN_RELEASE_v2.md](docs/plans/PLAN_RELEASE_v2.md) | TestFlight build prep ✅, GlitchTip live; ждёт soak + store-метаданные (после M1-маскота) |
| M1 Дизайн-система v2 + Маскот | `Mobile/constants/theme.ts` | Icon v2 мигрирован; маскот ещё не нарисован |
| Достижения серии D–K | [PLAN_ACHIEVEMENTS.md](docs/plans/PLAN_ACHIEVEMENTS.md) | A/B/C/Market/Сообщество/Пасхалки зашиты; социальные/лор-серии добиваются |

### 1.4. Метрики

- **Темп:** ~200 коммитов за 12 мая – 19 июня (Маркет, DM, уведомления, достижения, local-dump, user-records)
- **Тестовая коллекция:** ~188 записей для калибровки рарити-логики
- **Магазины:** 5 парсеров в проде, store-native записи + weekly re-match
- **Аккаунты:** 1 активный разработчик, прод-аккаунт с реальной коллекцией

---

## 2. Карта планов

ROADMAP.md — это _верхнеуровневый зонтик_. Каждый milestone ссылается на конкретный детальный spec. Существующие планы остаются как они есть; новые добавляются по мере открытия milestone'ов.

| Milestone | Detail-spec | Статус spec'а |
|---|---|---|
| M1. Дизайн+Маскот | `docs/plans/PLAN_DESIGN_SYSTEM_V2.md` | 🆕 будет создан в начале M1 |
| M2. Release | [PLAN_RELEASE_v2.md](docs/plans/PLAN_RELEASE_v2.md) | ✅ есть, ~65% реализовано |
| M3. Свои пластинки | [PLAN_USER_SUBMITTED_RECORDS.md](docs/plans/USER_SUBMITTED_RECORDS.md) | ✅ есть, ядро в проде |
| M4. Импорт | `docs/plans/PLAN_COLLECTION_IMPORT.md` | 🆕 (Discogs OAuth-импорт уже в проде) |
| M5. Достижения | [`/plans/PLAN_ACHIEVEMENTS.md`](docs/plans/PLAN_ACHIEVEMENTS.md) | ✅ есть, зашиты в продукт |
| M6. Парсинг РФ | [PARSING.md](docs/plans/PARSING.md) + [SHOPS_PARSING.md](docs/plans/SHOPS_PARSING.md) | ✅ есть, 5 парсеров в проде |
| M7. Магазины-партнёры | `docs/plans/PLAN_AFFILIATE_FLOW.md` | 🆕 будет в начале M7 (общая стратегия — в [PLAN_MONETIZATION.md](docs/plans/PLAN_MONETIZATION.md)) |
| M8. P2P | [PLAN_P2P_MARKETPLACE.md](docs/plans/PLAN_P2P_MARKETPLACE.md) | ✅ спек готов (2026-05-12) |
| M9. Рекомендации | `docs/plans/PLAN_RECOMMENDATIONS.md` | 🆕 |
| M10. Юнит-экономика | [PLAN_MONETIZATION.md](docs/plans/PLAN_MONETIZATION.md) (зонтик A→B→C) + `UNIT_ECONOMICS.md` (цифры) | ✅ стратегия готова (2026-05-12); цифровая модель — позже |

Связанные технические планы (не milestone'ы, но важные):
- [PRINCIPLES.md](docs/plans/PRINCIPLES.md) — техника (Discogs API, локалка vs прод, кэш)
- [BUGS.md](docs/BUGS.md) — реестр багов
- [PLAN_MONETIZATION.md](docs/plans/PLAN_MONETIZATION.md) — зонтик над M7+M8+M10 (стратегия трёх потоков A→B→C, последовательность запуска, юр.обвязка, юнит-эконом)
- [`/plans/RARITY_BADGES_PLAN.md`](docs/plans/RARITY_BADGES_PLAN.md) — рарити-теги (готово ✅)
- [`/plans/RARITY_DESIGN_BRIEF.md`](docs/plans/RARITY_DESIGN_BRIEF.md) — design brief для иллюстратора
- [`/VINYL_SPINNER_PLAN.md`](docs/plans/VINYL_SPINNER_PLAN.md) — vinyl spinner (в процессе 🟨)

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
- Унификация токенов: ревизия [Mobile/constants/theme.ts](Mobile/constants/theme.ts), сведение всех цветов/тени/радиусов/typography в один источник истины. Цель — `grep -rn "rgba\|#[0-9a-f]" Mobile/` не находит хардкод вне theme.ts (с эксклюзией ауры).
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
- [`/plans/RARITY_DESIGN_BRIEF.md`](docs/plans/RARITY_DESIGN_BRIEF.md) — пример формата брифа
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
**Detail-spec:** [PLAN_RELEASE_v2.md](docs/plans/PLAN_RELEASE_v2.md) — детальный план с фазами 0–6

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

**Pre-launch риски (выявлено вне исходного плана, 2026-06-19)**
- 🟥 **UGC-compliance — блокер App Store (Guideline 1.2).** DM и user-submitted records = user-gen контент. В коде есть block, но **нет report-content / report-user и нет rate-limit на сообщения**. Apple требует фильтр + репорт + блок + реакцию ≤24ч. Без этого — реджект. Добавить report-эндпоинт + EULA no-tolerance + rate-limit DM до сабмита.
- ⚠️ **Legal: ToS scraping + Discogs dump.** Публично показываем scraped-данные магазинов + локальный Discogs-дамп. Проверить Discogs API ToS (массовый дамп + редистрибуция) и per-shop robots/ToS **до** публичного релиза — cease-and-desist прилетает после роста, а не на старте.
- 💡 **Activation-метрика.** DAU=1, тюнить нечего. Зашить одну activation-метрику (первый added record / первый импорт) в Amplitude и вывести Discogs-импорт (M4, уже в проде) прямо в онбординг.
- ✅ **Off-site backup + restore-drill — закрыто** (см. Changelog ниже, 2026-06-19).

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
- [PLAN_RELEASE_v2.md](docs/plans/PLAN_RELEASE_v2.md), [PLAN_RELEASE.md](docs/plans/PLAN_RELEASE.md) (исторический), [BUGS.md](docs/BUGS.md)
- `Mobile/eas.json`, `Mobile/app.json`, `Backend/scripts/restore_drill.sh`, `Backend/tests/`

#### Changelog
- **2026-06-19** — data-safety: restore-drill ([scripts/restore_drill.sh](Backend/scripts/restore_drill.sh)) — одноразовый контейнер + sanity; off-site backup в S3/Yandex активирован env в `backup.sh`. Закрыта галка «restore-drill хотя бы раз руками».
- **2026-06-19** — quality net: первые smoke-тесты ([Backend/tests/](Backend/tests/), 27 шт) на pricing-формулу, транслитерацию, нормализацию и accessory/format-гейты matcher'а
- **2026-05-31** — TestFlight build prep; self-hosted GlitchTip (sentry.vinyl-vertushka.ru)

---

### M3. Свои пластинки (user-submitted records)

**Статус:** 🟨 In progress — ядро в проде (`source='user'`, Discogs-first визард, auto-approve, dedup-intercept, правка). Осталось: формальное UGC-moderation SLA под M2-стор.
**Goal:** Пользователь может добавить пластинку, которой нет в Discogs (самиздат, тираж <500, региональные релизы РФ/СССР), и она появится в его коллекции и в общем поиске после модерации.
**Why:** РФ/СССР-релизы и underground-самиздат плохо покрыты в Discogs. Без user-submitted мы блокируем самую интересную для коллекционеров часть рынка.
**Owner:** bamsrf
**Target:** после M2
**Detail-spec:** [PLAN_USER_SUBMITTED_RECORDS.md](docs/plans/USER_SUBMITTED_RECORDS.md) ✅

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
- [models/record.py](Backend/app/models/record.py), [services/cover_storage.py](Backend/app/services/cover_storage.py), [services/user_record.py](Backend/app/services/user_record.py)

#### Changelog
- **2026-06-18** — Discogs-first manual add + self-enriching search index
- **2026-06-17** — auto-approve, multi-format, dedup intercept, edit (§6/§9/§10/§11)
- **2026-06-13** — [#52/#53](https://github.com/bamsrf/Vertushka/pull/53) user-submitted records (`source='user'`), pending исключены из public aggregates

---

### M4. Импорт коллекций

**Статус:** 🟨 In progress — Login via Discogs + one-time импорт коллекции через OAuth в проде ([discogs_oauth.py](Backend/app/api/discogs_oauth.py), `settings/discogs.tsx`). Осталось: CSV-импорт, превью found/not_found/duplicates, прогресс-бар.
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
- Асинхронный воркер (через APScheduler / asyncio.create_task) — резолвит каждую запись через [services/discogs.py](Backend/app/services/discogs.py) batch-режим
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
- [services/discogs.py](Backend/app/services/discogs.py) — batch-резолв
- [models/collection.py](Backend/app/models/collection.py), [api/discogs_oauth.py](Backend/app/api/discogs_oauth.py)

#### Changelog
- **2026-06-02** — login via Discogs + one-time collection import; стабильная пагинация, price hydration

---

### M5. Достижения

**Статус:** 🟨 In progress — зашиты в продукт. Архетипы «Физика звука», серии A/B/C/Market/Сообщество/Пасхалки + формат-серии (кассета/CD/бокс-сет), PNG/SVG-пины, экран профиля, share-карточка, push при анлоке. Осталось: социальные/лор-серии D–K.
**Goal:** Запустить первые 14 ачивок (категории A + B), интегрировать в профиль, добавить push при анлоке.
**Why:** Достижения превращают каталог в живой ритуал коллекционера + увеличивают retention без grind-механик.
**Owner:** bamsrf
**Target:** после M2
**Detail-spec:** [`/plans/PLAN_ACHIEVEMENTS.md`](docs/plans/PLAN_ACHIEVEMENTS.md) — 84 ачивки в 11 категориях, философия и каталог проработаны

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
- [`/plans/PLAN_ACHIEVEMENTS.md`](docs/plans/PLAN_ACHIEVEMENTS.md), `Mobile/app/achievements.tsx`, `Mobile/components/AchievementPin.tsx`

#### Changelog
- **2026-06-19** — rework серии «Сообщество» (v2.1)
- **2026-06-06** — per-achievement descriptions, new pin designs (C2/C5/C6/meta_scale), past-tense done text
- **2026-06-02** — finished PNG pin designs для unlocked-бейджей
- **2026-05-27** — архетипы V3 «Физика звука» (XP-ladder), SVG-пины + официальные пины, «Сюрпризы» → «Пасхалки»
- **2026-05-13** — [#44](https://github.com/bamsrf/Vertushka/pull/44) каркас серий C/D/E/F/INV/H + Phase 2-5 AC

---

### M6. Парсинг магазинов РФ

**Статус:** 🟨 In progress — по сути в проде. 5 парсеров (Коробка Винила, Plastinka.com, Vinyl.ru, StopRobotVinyl, Found), matcher, store-native записи, Маркет-UI (карусель, `/market`, Hot Stock pill, swipe-цены). Реализовано шире исходного плана (свой `scrapers/`-фреймворк вместо `ru_shops/`). Осталось: добор магазинов, юр-чек robots.txt по каждому.
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
- [services/scrapers/](Backend/app/services/scrapers/) — фреймворк парсинга + shops/
- [services/listing_matcher.py](Backend/app/services/listing_matcher.py), [PARSING.md](docs/plans/PARSING.md), [SHOPS_PARSING.md](docs/plans/SHOPS_PARSING.md)

#### Changelog
- **2026-06-13** — [#51/#52](https://github.com/bamsrf/Vertushka/pull/52) Found parser (Tilda store-API) + reliable ingest (parallel crawl, stock-refresh, smoke-checks)
- **2026-06-12** — distributed rate limiter, local-first suggest/barcode, cover warm-up
- **2026-05-29** — vinyl.ru parser (64k товаров), WS3 matcher (dedup, trusted-store gate, barcode/catalog rematch)
- **2026-05-19** — Маркет Phase 1–7.5 (Hot Stock pill, MarketSection, `/market/store/[slug]`, swipe-сравнение цен)
- **2026-05-12** — инфраструктура парсинга РФ-магазинов + пилот korobkavinyla

---

### M7. Магазины-партнёры (in-app purchase flow)

**Статус:** 🟨 In progress (фаза A) — клик-трекинг + UTM + каркас под Admitad в коде ([services/affiliate.py](Backend/app/services/affiliate.py), [models/offer_click.py](Backend/app/models/offer_click.py)). Осталось: подписать партнёрские договоры, дашборд revenue.
**Goal:** ≥2 партнёрства с РФ-магазинами с tracking кликов; первый rouble revenue.
**Why:** **Поток A** из трёх-потоковой монетизации — самое короткое time-to-revenue, доказывает партнёрам трафик, фундамент для M8 (P2P) и M10.
**Owner:** bamsrf + переговоры с магазинами
**Target:** после M6 (мес 4–6 после M2)
**Detail-spec:**
- Стратегия и юнит-экономика — [PLAN_MONETIZATION.md §Поток A](docs/plans/PLAN_MONETIZATION.md)
- Технический спек — `docs/plans/PLAN_AFFILIATE_FLOW.md` (будет создан в начале M7)

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
- [services/affiliate.py](Backend/app/services/affiliate.py), [models/offer_click.py](Backend/app/models/offer_click.py)

#### Changelog
- **2026-05-17** — фаза A: клик-трекинг + UTM + каркас под Admitad; гибридная стратегия direct + CPA

---

### M8. P2P-маркетплейс

**Статус:** ⬜ Not started — детальный спек готов
**Goal:** Юзеры могут выставлять лоты, находить лоты других юзеров, безопасно покупать через эскроу с защитой 14 дней, оставлять рейтинг.
**Why:** **Поток B** из трёх-потоковой монетизации. Стратегический lock-in аудитории через рейтинг и эскроу. Запускается **после M7** (после доказательства трафика партнёрам).
**Owner:** bamsrf
**Target:** мес 6–14 после M2; 16–21 человеко-неделя чистого dev, 7 под-фаз (2.0 Подготовка → 2.6 Scale)
**Detail-spec:** [PLAN_P2P_MARKETPLACE.md](docs/plans/PLAN_P2P_MARKETPLACE.md) — полный спек с state machine, моделями, антифрод-стеком, винильной спецификой, эскроу ЮKassa, phased rollout. Стратегический контекст — [PLAN_MONETIZATION.md §Поток B](docs/plans/PLAN_MONETIZATION.md).

#### Краткая сводка (детали — в спеке)

**Несущая конструкция:**
- ИП-«Вертушка» = агент по ст. 1005 ГК; продавец = принципал; покупатель = заказчик услуги
- ЮKassa «Безопасная сделка» (~5.5% эфф.комиссия с 2026) держит эскроу
- Доставка: CDEK / Boxberry с PVZ-приёмкой и видео распаковки
- Cloud-касса (АТОЛ через ЮKassa) для агентских чеков

**Эталонные кейсы:** Авито Доставка (flow + видео в ПВЗ), Discogs Marketplace (Goldmine grading, dead-wax), Vinted (UX, blind reviews), Reverb (trust badges).

**Винильная специфика:**
- Goldmine grading **раздельно** для пластинки и конверта (M / NM / VG+ / VG / G / F-P)
- Pressing variant обязателен (страна + год + лейбл + dead-wax матрица)
- 6 обязательных фото (cover_front/back, record_side_a/b, label_close, dead_wax_close)
- Привязка к Discogs release_id (упрощает верификацию контрафакта)

**Модель комиссии:** 7% с продавца + 1.5% сервис-фи с покупателя. Take rate ≈ 8.5% GMV, чистая маржа ~2.5%.

**Anti-disintermediation (КРИТИЧНО для маржи — обычно тут теряют 30–50% сделок в Telegram):**
- Контакты скрыты до Reserved
- Чат-фильтр маскирует телефоны/`@`/Telegram-ссылки
- 3-страйковая система (3 страйка = бан)
- Эскроу как value-add (плашка «Защита 14 дней»)
- Рейтинг привязан **только** к завершённым в платформе сделкам

**Phased rollout:**
- 2.0 Подготовка (юр. + ЮKassa setup) — 4–5 нед
- 2.1 Closed beta v1 без оплаты (50 инвайтов) — 2 нед
- 2.2 Open v1 без оплаты — 1–2 нед
- 2.3 Эскроу пилот на 10% юзеров — 3–4 нед
- 2.4 Full rollout эскроу — 1–2 нед
- 2.5 KYC mid-tier (ЮKassa Identity + Verified Seller badges) — 2 нед
- 2.6 Scale features (saved searches, smart pricing) — 3–4 нед

#### Acceptance criteria (укрупнённо — детальные go-criteria для каждой sub-phase в спеке)
- [ ] Phase 2.0 завершена: 6 юр-документов опубликованы, ЮKassa Safe Deal подключена, оператор ПДн зарегистрирован, webhooks тестово ходят
- [ ] Phase 2.2: ≥300 листингов, ≥50 завершённых сделок, dispute rate <5%
- [ ] Phase 2.4: GMV растёт MoM, in-platform completion ≥80%, take rate ≥8%
- [ ] Phase 2.5: ≥20% продавцов на mid-KYC+
- [ ] Detail-spec обновляется при изменениях

#### Зависимости
- **Блокирует:** —
- **Блокируется:** M2 (UGC moderation policy), M7 (валидация Affiliate как первого потока), желательно M5 (доверие через ачивки)

#### Связанные артефакты
- [PLAN_P2P_MARKETPLACE.md](docs/plans/PLAN_P2P_MARKETPLACE.md), [PLAN_MONETIZATION.md](docs/plans/PLAN_MONETIZATION.md)
- [models/gift_booking.py](Backend/app/models/gift_booking.py) — паттерн «сделки между юзерами»
- [models/blocked_contact.py](Backend/app/models/blocked_contact.py) — расширяется для антифрода (phone/device_id/card_hash)
- [models/follow.py](Backend/app/models/follow.py) — социальная база

#### Changelog
- **2026-05-12** — создан детальный spec [PLAN_P2P_MARKETPLACE.md](docs/plans/PLAN_P2P_MARKETPLACE.md) с полной архитектурой, антифрод-стеком, phased rollout

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
- [models/collection_value_snapshot.py](Backend/app/models/collection_value_snapshot.py) — паттерн ежедневной background task

#### Changelog
- _нет записей_

---

### M10. Юнит-экономика и монетизация

**Статус:** 🟨 In progress — стратегия утверждена 2026-05-12, цифровая модель пишется параллельно
**Goal:** Ясная модель монетизации с ≥1 активным каналом revenue + первое позитивное unit-economics (CAC < LTV).
**Why:** Без устойчивости приложение умрёт. Проектировать рано (сейчас) → тестировать после M2 → масштабировать после M7.
**Owner:** bamsrf
**Target:** живёт параллельно всем milestone'ам; чек-поинты после M7 и M8
**Detail-spec:**
- Стратегия и phased rollout — [PLAN_MONETIZATION.md](docs/plans/PLAN_MONETIZATION.md) ✅
- Детальный P2P — [PLAN_P2P_MARKETPLACE.md](docs/plans/PLAN_P2P_MARKETPLACE.md) ✅
- Цифровая фин-модель — `docs/plans/UNIT_ECONOMICS.md` (будет создан до M2)

#### Стратегия одной строкой

**A → B(v1) → B(v2) → C.** Строго последовательно, не параллельно. Affiliate первый (короткое time-to-revenue, доказывает трафик магазинам). P2P второй (lock-in аудитории через рейтинг). Premium третий (требует существующих core-features для конверсии). Подробное обоснование — в [PLAN_MONETIZATION.md](docs/plans/PLAN_MONETIZATION.md).

#### Три потока (детально в PLAN_MONETIZATION.md)

1. **Поток A — Affiliate с РФ-магазинами (M7)** — % с продаж от партнёрских кликов. CPA 5% от чека. Phase 1, мес 1–6 после M2. Юнит-экономика к мес 6: ~30к₽/мес комиссии.
2. **Поток B — P2P-маркетплейс (M8)** — 7% с продавца + 1.5% сервис-фи. Phase 2, мес 6–14. Юнит-экономика к мес 14: 1М₽ GMV/мес → 70к₽ комиссии. Детально — [PLAN_P2P_MARKETPLACE.md](docs/plans/PLAN_P2P_MARKETPLACE.md).
3. **Поток C — Premium-подписка** — 199₽/мес или 1990₽/год через External Link Entitlement (Apple) → ЮKassa СБП / Paddle (по гео). Phase 3, мес 9–18. Юнит-экономика к мес 18: 500 платных → 100к₽/мес.

**Целевая структура revenue mix к 24 мес:** Affiliate 40%, P2P 45%, Premium 15%. Совокупно ~600к₽/мес = ~7.2М₽/год.

#### Что **не** будем делать (твёрдая граница)
- Реклама в ленте (в т.ч. native ADS)
- Продажа данных юзеров
- Pay-to-win-ачивки (в т.ч. покупка прогресса)
- Платный доступ к каталогу/рекомендациям
- Ограничение размера коллекции в free-версии
- Блокировка обычных функций при истечении Premium (деактивируются только premium-фичи)

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
- **2026-05-12** — утверждена стратегия трёх потоков A→B→C; созданы [PLAN_MONETIZATION.md](docs/plans/PLAN_MONETIZATION.md) и [PLAN_P2P_MARKETPLACE.md](docs/plans/PLAN_P2P_MARKETPLACE.md)
- **2026-05-07** — [#35](https://github.com/bamsrf/Vertushka/pull/35) feat(analytics): скрипт зеркалирования БД в Supabase — _M10 relevant_

---

## 4. Changelog

Хронологическая лента merged PR. Обновляется автоматически (см. секцию 6) — при каждом merged PR в `main` GitHub Action запускает `scripts/sync_roadmap.py`, который дописывает строку сюда и в Changelog соответствующего M-блока.

### 2026-06

- **2026-06-19** — chore(data-safety): restore-drill скрипт + off-site backup (S3/Yandex); test: первые 27 smoke-тестов бэкенда (pricing/translit/normalize/matcher-гейты) — _M2_
- **2026-06-19** — fix(search): constant rail scroll speed; fix(valuation): value через estimate_rub fallback; feat(discogs): hybrid new-releases rail (recency × want); feat(achievements): rework серии «Сообщество» v2.1 — _M5/M6_
- **2026-06-18** — feat(discogs): Discogs-first manual add + self-enriching index; fix(spotify): `SPOTIFY_PROXY_URL` обход RU geo-block; fix(ios-build): modular headers для Google pods — _M3_
- **2026-06-17** — feat(user-records): auto-approve, multi-format, dedup intercept, edit; fix(versions): self-healing straggler covers — _M3_
- **2026-06-15** — feat(matcher): exact dump barcode/catalog перед fuzzy, vinyl-color penalty, SKU-padded barcode fix; feat(market): pressing-trust тиры офферов — _M6_
- **2026-06-13** — [#51/#52/#53](https://github.com/bamsrf/Vertushka/pull/53) feat(records): user-submitted (`source='user'`); feat(market): Found parser + reliable ingest; fix(security): trusted client IP, email_verified gate, token revocation — _M3/M6_
- **2026-06-12** — feat(discogs): distributed rate limiter, local-first suggest/barcode, cover warm-up — _M6_
- **2026-06-09** — feat(achievements): per-series locked placeholders; feat(auth): скрыть кнопку Google Sign In — _M5_
- **2026-06-06** — feat(achievements): per-achievement descriptions + new pin designs (C2/C5/C6) — _M5_
- **2026-06-05** — [#48](https://github.com/bamsrf/Vertushka/pull/48) feat(notifications): seen=read, weekly digest, grouping, deep-links, swipe polish
- **2026-06-02** — feat(discogs): login via Discogs + one-time collection import; feat(observability): user-context в Sentry/GlitchTip scope — _M4_

### 2026-05

- **2026-05-31** — chore(release): TestFlight build prep; mobile: self-hosted GlitchTip DSN; nginx: sentry.vinyl-vertushka.ru reverse proxy — _M2_
- **2026-05-29** — feat(scan): CLIP ONNX визуальный re-rank обложек; perf(scan): vision → gpt-4o; feat(scrapers): vinyl.ru (64k товаров) — _M6_
- **2026-05-26** — feat(matcher): slim Discogs Releases Dump — локальный индекс + lookup (local-first) — _M6_
- **2026-05-19** — feat(market): Phase 1–7.5 (Hot Stock, MarketSection, store/[slug]); feat(messages): TG-style чат Phase 1–8; feat(claude): context layer V1 (FTS5)
- **2026-05-17** — feat(messages): M1 DM router + mobile screens, WebSocket realtime; feat(notifications): лента + Expo push; feat(affiliate): фаза A клик-трекинг + UTM — _M7_
- **2026-05-13** — [#44/#45](https://github.com/bamsrf/Vertushka/pull/45) feat(achievements): каркас серий C/D/E/F; feat(profile): редизайн чужого профиля + follow-requests — _M5_
- **2026-05-12** — docs(monetization): утверждена стратегия монетизации A→B→C; добавлены [PLAN_MONETIZATION.md](docs/plans/PLAN_MONETIZATION.md) и [PLAN_P2P_MARKETPLACE.md](docs/plans/PLAN_P2P_MARKETPLACE.md) — _M7/M8/M10_
- **2026-05-09** — [#39](https://github.com/bamsrf/Vertushka/pull/39) feat(email): отправка через Resend + SMTP fallback
- **2026-05-07** — [#35](https://github.com/bamsrf/Vertushka/pull/35) feat(analytics): скрипт зеркалирования БД в Supabase — _M10 relevant_
- **2026-05-07** — [#32](https://github.com/bamsrf/Vertushka/pull/32) feat(design-system): миграция Mobile на Icon v2 (b2v2-icons + Phosphor halo wrapper)
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
- Smoke-тесты бэкенда забутстраплены (`Backend/tests/`, pytest) — расширить до integration (matcher на фикстурах БД, auth-refresh, endpoint-контракты)
- E2E-тесты Mobile (Detox или Maestro)
- CI: гонять `pytest` на каждый PR (сейчас локально)
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
