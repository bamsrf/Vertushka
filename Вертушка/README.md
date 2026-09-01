# Вертушка 🎵

Мобильное приложение для коллекционеров винила: каталог пластинок, поиск через Discogs, рарити-теги, рублёвые цены, маркет РФ-магазинов, личные сообщения, достижения, публичные профили и gift-booking.

> Главный living document — [ROADMAP.md](ROADMAP.md) (Snapshot, Milestones M1–M10, Changelog). Прод-API: `https://api.vinyl-vertushka.ru/api`.

---

## Что умеет приложение

### Коллекция
- Ищите и добавляйте пластинки через Discogs (15+ млн релизов), сканируйте штрихкод или просто сфотографируйте обложку — приложение само распознает релиз и покажет все его издания.
- Раскладывайте коллекцию по папкам, добавляйте заметки и свои фото.
- Приложение считает стоимость каждой пластинки в рублях с учётом доставки и пошлин, рисует график изменения цены и показывает, как выросла стоимость всей коллекции за месяц.

### Редкость
Каждая пластинка автоматически получает метку редкости: 🩶 Канон (главное издание), 💚 Коллекционка (дорогая и редкая на рынке), 🟣 Лимитка (промо, нумерованные и ограниченные тиражи), 🟠 Популярно (все хотят). Редкие пластинки красиво подсвечиваются в коллекции.

### Поиск
- Понимает кириллицу, подсказывает по мере ввода, помнит историю.
- Работает поверх локальной копии базы Discogs, поэтому не зависит от лимитов их API: обложки, штрихкоды и списки изданий находятся мгновенно.
- Есть витрина новинок, страницы артистов и релизов со всеми изданиями, а у пластинок показывается настоящий цвет винила.

### Маркет
Приложение само обходит каталоги российских магазинов винила — свыше 30 000 релизов в продаже — и показывает, что сейчас есть в наличии и почём. Каждый товар привязывается к конкретному изданию, так что цены из магазинов видны прямо в вишлисте и на публичном профиле. Есть даже релизы, которых нет на Discogs — русский инди и малые лейблы.

### Радар цен
Повесьте колокольчик на пластинку из вишлиста — и получите пуш, когда она появится в продаже или подешевеет до нужной вам цены. Если точного издания нет, радар предложит аналог — другое издание того же альбома.

### Вишлист и подарки
Вишлистом можно поделиться ссылкой: друг забронирует пластинку в подарок даже без регистрации и получит подтверждение на почту — а вы не купите её сами и не получите два одинаковых подарка. От злоупотреблений защищают верификация почты и лимиты на брони.

### Общение
Личные сообщения с мгновенной доставкой: статусы «печатает» и «в сети», ответы, пересылка, реакции, закрепы и «поделиться пластинкой». Плюс подписки на других коллекционеров, лента активности и публичный профиль с настройками приватности — его видно и в вебе.

### Достижения
Система достижений «Физика звука»: авторские пины за рост коллекции, редкости, общение и покупки, плюс спрятанные пасхалки. Каждая ачивка помнит, за какую музыку выдана. С уровнем растёт ваша «ступень» — она красит профиль, папки и уведомления.

### Свои пластинки
Если релиза нет на Discogs — добавьте его сами через пошаговый визард. После модерации пластинка появится в общем поиске.

### Вход и прочее
Вход по почте, через Apple или через Discogs (с импортом коллекции оттуда в один клик). Интерактивный онбординг-тур, экспорт коллекции в CSV, пуш-уведомления с тихими часами и недельным дайджестом.

---

## Стек

### Mobile (`Mobile/`)
- **Expo SDK 54**, **React Native 0.81.5**, **React 19.1**, **Expo Router 6**, TypeScript.
- **Zustand 5** — 16 сторов: auth, collection, scanner, search, suggest, searchHistory, sections, market, messages, notifications, follow, gift, profile, userSearch, cache, onboarding.
- **Axios 1.13** с retry и token-refresh интерцепторами; глобальный clamp font-scale до 1.15 + `ms()` на reading-text.
- `expo-image` (disk cache), `expo-camera`, `expo-barcode-scanner`, `expo-notifications` (push), `react-native-reanimated 4`, WebSocket для realtime-чата, `phosphor-react-native`, `react-native-svg`.
- `expo-apple-authentication`, Discogs OAuth, `@amplitude/analytics-react-native`.
- EAS configured, bundle id `com.vertushka.app`.

### Backend (`Backend/`)
- **FastAPI 0.109** + **SQLAlchemy 2 (asyncpg)** + **PostgreSQL** + **Redis** + **Alembic**.
- **19 роутеров** (auth, records, collections, wishlists, users, gifts, profile, export, covers, user_photos, waitlist, market, offers, messages, notifications, achievements, discogs_oauth, admin).
- **WebSocket-хаб** для realtime-сообщений (`messages_ws_hub`), Expo push (`push`), distributed rate-limiter Discogs.
- **APScheduler** — обновление цен 04:00, обогащение артистов 05:00, ночной crawl магазинов, stock-refresh 6ч, matcher batch, weekly re-match store-native, monthly new-releases refresh, очистка booking-токенов, search_cache cleanup, weekly digest.
- **Локальный slim Discogs-дамп** (`discogs_index`) — обложки, suggest, barcode, master-versions без обращения к API.
- **httpx / aiohttp / BeautifulSoup** (scraping), **Pillow** + CLIP ONNX (визуальный re-rank обложек при скане), **Jinja2** (веб-страницы), **bcrypt + jose**, **aiosmtplib** (Yandex SMTP) + Resend fallback.
- Token-bucket rate-limiter Discogs + приоритетная очередь SEARCH→DETAIL→SCAN→ENRICHMENT→BATCH + circuit breaker.
- Docker Compose, Nginx, **self-hosted GlitchTip** (sentry.vinyl-vertushka.ru) для крэш-репортинга, structured JSON logging, Supabase mirror для аналитики.

### Внешние интеграции
- **Discogs API** (search / releases / masters / marketplace stats, кэш 7 дней) + **локальный slim-дамп** (local-first).
- **OpenAI Vision** (GPT-4o, распознавание обложек) + CLIP ONNX визуальный re-rank.
- **Spotify** (через `SPOTIFY_PROXY_URL` для обхода RU geo-block).
- **ЦБ РФ** (курс USD/RUB, кэш).
- **Yandex SMTP** + **Resend** fallback (восстановление пароля, gift-booking, уведомления).

---

## Структура

```
Вертушка/                  # git root, github.com/bamsrf/Vertushka
├── Backend/               # FastAPI
│   ├── app/
│   │   ├── api/           # 19 роутеров: auth, records, collections, wishlists,
│   │   │                  # users, gifts, profile, export, covers, user_photos,
│   │   │                  # waitlist, market, offers, messages, notifications,
│   │   │                  # achievements, discogs_oauth, admin
│   │   ├── models/        # 23 модели: user, record, collection, wishlist,
│   │   │                  # gift_booking, blocked_contact, follow, follow_request,
│   │   │                  # profile_share, collection_value_snapshot, user_photo,
│   │   │                  # waitlist, search_cache, store, store_listing,
│   │   │                  # conversation, message_reaction, message_hidden,
│   │   │                  # notification, offer_click, user_achievement, user_block
│   │   ├── services/      # 30+ сервисов: discogs, discogs_index (local dump),
│   │   │                  # pricing, valuation, marketplace_pricing, exchange,
│   │   │                  # cache, cover_storage/_fallback/_matcher/_warm,
│   │   │                  # openai_vision, listing_matcher, messaging,
│   │   │                  # messages_ws_hub, notification_service, push, feed,
│   │   │                  # affiliate, spotify, user_record, vinyl_color, …
│   │   ├── services/scrapers/  # base, registry, sitemap, robots, http_client,
│   │   │                  # browser + shops/ (korobkavinyla, plastinka_com,
│   │   │                  # vinyl_ru, stoprobotvinyl, found, doctorhead)
│   │   ├── tasks/         # booking_tasks, discogs_tasks, valuation_tasks
│   │   ├── web/           # routes.py + Jinja-шаблоны (публичный профиль, /cancel)
│   │   └── scripts/       # recalc_collection_rub, backfill_rarity_flags,
│   │                      # backfill_vinyl_colors, mirror_to_supabase,
│   │                      # bulk_rematch, build_discogs_index, …
│   ├── nginx/, scripts/deploy.sh, scripts/backup.sh
│   └── docker-compose.prod.yml
│
├── Mobile/                # Expo / React Native
│   ├── app/               # Expo Router (~43 экрана)
│   │   ├── (auth)/        # login, register, forgot/reset-password, verify-code
│   │   ├── (tabs)/        # index, collection, search
│   │   ├── record/[id], record/manual, records/mine  # детали + ручное добавление
│   │   ├── master/[id]/   # мастер-релиз + версии
│   │   ├── artist/[id]    # дискография
│   │   ├── market/        # index + store/[slug]
│   │   ├── messages/      # index, [conversationId], new, share-record
│   │   ├── notifications.tsx, achievements.tsx
│   │   ├── user/[username]# публичный профиль + achievements
│   │   ├── gift/[id], social/list, social/follow-requests
│   │   ├── collection/value, folder/[id], wishlist-folder/[id]
│   │   ├── settings/      # discogs, edit-profile, notifications, share-profile,
│   │   │                  # wishlists
│   │   └── onboarding.tsx, profile.tsx
│   ├── components/        # RarityAura, RecordCard/Grid, VinylColorTag,
│   │                      # VinylSpinner, GlassTabBar, AnimatedGradientText,
│   │                      # AutoRail, AchievementPin, StoreCarousel, MarketSection,
│   │                      # HotStockTag, OffersBlock, OnboardingOverlay, …
│   ├── components/ui/     # design-system v2 (Icon)
│   └── lib/               # api, store, types, analytics, toast, vinylColor
│
├── Design/                # дизайн-ассеты
├── docs/
│   ├── BUGS.md
│   └── plans/             # ROADMAP детализация (RARITY, RELEASE_v2, …)
├── ROADMAP.md             # главный living document
└── scripts/               # repo-wide tooling (sync_roadmap.py)
```

---

## Принципы работы с Discogs API

Discogs hard-cap: **60 req/min** для аутентифицированных запросов. Чтобы UI не упирался в этот потолок, придерживаемся следующих правил:

1. **Никогда не делать N+1 запросов в синхронной части эндпоинта.** Если экран показывает список из N релизов, эндпоинт обязан укладываться в O(1)–O(2) Discogs-запросов. Всё, что требует обращения к `/releases/{id}` per-item, уезжает в `BackgroundTasks`.
2. **Использовать всё, что Discogs уже отдаёт в ответе.** В `/masters/{id}/versions` лежат `stats.community.in_collection / in_wantlist` и `major_formats` — этого хватает на `is_hot` и `is_limited` без доп. запросов.
3. **Дешёвые флаги — сразу, дорогие — фоном.** `is_canon` из `master.main_release_id`, `is_limited` из format-токенов, `is_hot` из `stats.community` отдаются юзеру за < 3 сек. `is_collectible` (требует marketplace `price_stats`) досчитывается в фоне и пишется в `master_versions_enriched` Redis-кэш.
4. **Single-flight на фоновое обогащение.** Redis `set_nx`-lock не даёт двум запросам на один и тот же мастер запустить enrichment параллельно — иначе сжигаем rate-limit вдвое быстрее без пользы.
5. **Watchdog везде.** `asyncio.wait_for(timeout=25)` на синхронной части (быстрый 503 вместо 60s axios timeout) и `timeout=120` на фоновом обогащении (не висим вечно при медленном Discogs).
6. **Многослойный кэш.** Сырые ответы Discogs (`release` 7д, `master` 7д, `master_versions` 3д) + enriched-ответы по эндпоинтам (`master_versions_enriched` 3д). Локальная БД `Record` — самый быстрый источник для виденных релизов.
7. **Token-bucket с приоритетами.** `SEARCH > DETAIL > SCAN > ENRICHMENT > BATCH` — пользователь, ждущий поиска прямо сейчас, не стоит за фоновым backfill'ом.

Подробности: [`Backend/app/services/rate_limiter.py`](Backend/app/services/rate_limiter.py), [`Backend/app/services/cache.py`](Backend/app/services/cache.py), [`Backend/app/api/records.py`](Backend/app/api/records.py).

---

## Парсинг магазинов винила («Где купить»)

Помимо Discogs, у нас своя scraping-инфра — обходит каталоги российских магазинов (Коробка Винила, Plastinka.com и т.д.), сохраняет листинги в `store_listings`, матчит на наши `records`, отдаёт в Mobile карусель «В наличии сейчас» на экране Поиск.

**Покрытие форматов**: парсим **все носители** что в каталогах — LP, CD, кассеты, бокс-сеты. Не только винил.

**Архитектура**: per-shop парсер (наследник `BaseStoreParser`) → sitemap discovery → `httpx` с per-domain rate-limit (0.5 req/s) и Cloudflare-detect → BeautifulSoup/Schema.org/Tilda JSON → `ListingDTO` → UPSERT в `store_listings` → отдельный matcher привязывает листинг к нашему `records.id`, чтобы цена из магазина появилась в Маркете.

**Как происходит матчинг листинга** ([Backend/app/services/listing_matcher.py](Backend/app/services/listing_matcher.py)) — каскад из 5 шагов, каждый со своим `match_confidence`:

1. **Discogs URL из карточки магазина** → `Record.discogs_id` (1.00) — самый надёжный, многие магазины сами линкуют release.
2. **Barcode (EAN-13)** → `Record.barcode` (1.00).
3. **Catalog number** (нормализованный, без пробелов и дефисов) → `Record.catalog_number` (0.90).
4. **Fuzzy artist + title + year** через `pg_trgm` + `rapidfuzz.token_sort_ratio`, порог 0.85 (variable confidence).
5. **On-demand Discogs API** — если в локальной БД нет, дёргаем Discogs search (по barcode/catalog или artist+title) и создаём `Record` из ответа (0.85–0.95). Соблюдает hourly-лимит `DISCOGS_FETCH_HOURLY_LIMIT=500`, чтобы matcher batch не вычерпал квоту перед live-поиском.

Аксессуары (пины, постеры, футболки) отсекаются регулярным выражением до Discogs-фолбэка — не сжигать квоту на товары, которых на Discogs не бывает в принципе.

**Store-native записи** — что делаем с релизами, которых нет на Discogs (русский инди, малые лейблы типа Coastal Pirates). Если все 5 шагов матчера не нашли запись, создаём `Record(source='store', discogs_id=NULL)` прямо из данных листинга (artist, title, year, cover, label). Маркет автоматически их подхватывает (`source` прозрачен для INNER JOIN), но **в коллекцию/wishlist их добавить нельзя** до появления merge-tool (защита от CASCADE-потери юзер-данных при будущем мердже на Discogs). Anti-noise gate: создаём только если листинг увиден ≥7 дней назад ИЛИ его продаёт ≥2 магазина — отсекает опечатки парсера. Раз в неделю cron повторно пробует найти запись на Discogs (вдруг релиз там появился). План: [docs/plans/market/STORE_NATIVE_RECORDS.md](docs/plans/market/STORE_NATIVE_RECORDS.md).

**Cron-задачи**: incremental crawl каждую ночь (~10 мин на магазин), full re-crawl раз в неделю, stock-refresh каждые 6 часов (для активных листингов в карусели), matcher batch каждый час, re-match store-native — раз в неделю.

**Ресурсы для 10 магазинов** (после initial backfill): ~150 МБ постоянной RAM, 3-5% CPU в среднем, ~55 ГБ трафика/мес, ~1 ГБ БД через год.

**Бутылочное горлышко** — не наш сервер, а Discogs API rate-limit (60 req/min). **Решено**: импортирован slim [Discogs Data Dump](docs/plans/discogs/DISCOGS_DATA_DUMPS.md) в локальный индекс (`services/discogs_index.py`) — обложки, suggest, barcode-lookup и master-versions резолвятся локально, к API уходим только на промах.

📖 **Детальная операционка**: [docs/plans/market/PARSING.md](docs/plans/market/PARSING.md) — архитектура, cron, лимиты, ресурсы, HOWTO добавить новый магазин, troubleshooting.
📋 **План локального mirror Discogs**: [docs/plans/discogs/DISCOGS_DATA_DUMPS.md](docs/plans/discogs/DISCOGS_DATA_DUMPS.md).
📦 **Стратегия магазинов**: [docs/plans/market/SHOPS_PARSING.md](docs/plans/market/SHOPS_PARSING.md).
🎨 **UX офферов в Mobile**: [docs/plans/market/OFFERS_UX.md](docs/plans/market/OFFERS_UX.md).

---

## Запуск локально

### Backend

```bash
cd Backend
cp .env.example .env
docker-compose up -d                # рекомендуется
# или: pip install -r requirements.txt && uvicorn app.main:app --reload
```

API: `http://localhost:8000`.

**Smoke-тесты** (чистые функции, без БД/Redis):
```bash
cd Backend && source venv/bin/activate && python -m pytest -q
# pricing-формула, транслитерация, нормализация, accessory/format-гейты matcher'а
```

### Mobile

```bash
cd Mobile
npm install
npm start
```

Откройте в Expo Go или симуляторе. Для локального бэкенда укажите свой IP в [Mobile/lib/api.ts](Mobile/lib/api.ts).

---

## Продакшен

- **API**: https://api.vinyl-vertushka.ru/api
- **Хост**: Beget VPS Ubuntu 24.04 (`85.198.85.12`, 8.7 ГБ диск, 10 ГБ тариф)
- **Стек**: Docker Compose (`docker-compose.prod.yml`) + Nginx + 5 контейнеров: api, scheduler, db (Postgres 16), redis, nginx. Metabase убран с прода 2026-05-09 — поднимается локально по требованию.

### Деплой

**Стандартный путь — одна команда:**
```bash
git push origin main
ssh deploy@85.198.85.12 'bash ~/vertushka/Вертушка/Backend/scripts/deploy.sh'
```

`deploy.sh` ([Backend/scripts/deploy.sh](Backend/scripts/deploy.sh)) делает: git pull → pre-flight check свободного места (нужно >1 ГБ, иначе сам почистит) → build api+scheduler из общего Dockerfile → миграции → up -d с **`--force-recreate --no-deps api scheduler`** → healthcheck `/health` 60 сек → `image prune` + `builder prune --reserved-space 500MB`.

### Бэкап БД

Перед любой потенциально опасной операцией (миграция новой схемы, чистка volume, сомнительный SQL):
```bash
ssh deploy@85.198.85.12 'bash ~/vertushka/Вертушка/Backend/scripts/backup.sh'
# дамп → ~/backups/vertushka_YYYYMMDD_HHMMSS.sql.gz, хранится 7 дней
```

**Off-site (от SPOF).** Локальный бэкап лежит на том же VPS — если умрёт диск, улетят и БД, и бэкапы. `backup.sh` умеет грузить в S3-совместимое хранилище (Yandex Object Storage) — включается env-переменными перед запуском/в cron:
```bash
export S3_BUCKET=vertushka-backups S3_ENDPOINT=https://storage.yandexcloud.net
export AWS_ACCESS_KEY_ID=... AWS_SECRET_ACCESS_KEY=...
bash backup.sh   # после verify зальёт дамп в s3://$S3_BUCKET/
```

**Restore-drill (бэкап без проверки = нет бэкапа).** Разворачивает последний дамп в одноразовый Postgres-контейнер, гоняет sanity-проверки (таблицы + строки в users/records/collections/wishlists) и сносит контейнер — прод не трогает:
```bash
ssh deploy@85.198.85.12 'bash ~/vertushka/Вертушка/Backend/scripts/restore_drill.sh'
# опц.: restore_drill.sh /path/to/конкретный_дамп.sql.gz
```

### Откат

Если деплой испортил api:
```bash
# 1. вернуть код:
ssh deploy@85.198.85.12 'cd ~/vertushka && git reset --hard <предыдущий-commit-sha>'
# 2. пересобрать:
ssh deploy@85.198.85.12 'bash ~/vertushka/Вертушка/Backend/scripts/deploy.sh'
```
Если миграция испортила БД — восстановить из дампа:
```bash
ssh deploy@85.198.85.12 'gunzip -c ~/backups/vertushka_<timestamp>.sql.gz | docker exec -i vertushka_db psql -U <user> -d vertushka'
```

### Disk hygiene (защита от разрастания)

Активна автоматически — ничего регулярно не делать:
- **Лимит логов всех контейнеров** — 30 МБ rolling buffer (`/etc/docker/daemon.json`).
- **journald** — `SystemMaxUse=200M` (`/etc/systemd/journald.conf`).
- **Weekly auto-prune** — воскресенье 04:00 UTC (`/etc/cron.d/vertushka-disk-cleanup`): `docker system prune -af --filter until=336h` + `apt-get clean`.
- **Disk-alert** — каждые 30 мин, лог `/var/log/disk-alert.log` если `/` >80%.
- **Cover cache cap** — `COVERS_MAX_CACHE_MB=500` в `.env.prod`, LRU-cleanup ежедневно в 03:00.

Проверить состояние диска:
```bash
ssh deploy@85.198.85.12 'df -h / && docker system df && tail -5 /var/log/disk-alert.log'
```

### Локальный Metabase для аналитики

```bash
cd Backend && docker compose up -d metabase
# http://localhost:3000
docker compose stop metabase  # когда закончил
```

### Правила работы с продом

✅ **Можно**:
- Запускать `bash deploy.sh` — он сам проверяет место, бэкапит, делает healthcheck.
- `docker image prune -f`, `docker container prune -f`, `docker builder prune -af` — чистят только мусор.
- Любые правки в `docker-compose.prod.yml` — сервис, env, healthcheck, ports.

❌ **Нельзя без явного намерения** (data loss):
- `docker system prune` **с флагом `--volumes`** — удалит всю БД, обложки, redis-кэш.
- `docker compose down -v` — то же самое (флаг `-v` удаляет volume).
- `docker volume rm backend_postgres_data | backend_uploads_data` — без бэкапа.
- `git reset --hard` без предварительного `git stash` локальных правок на сервере.

⚠️ **Если что-то добавляешь в стек**:
- Новый сервис → правь **И** `docker-compose.prod.yml`, **И** dev `docker-compose.yml`.
- Если сервис должен светиться через nginx — добавь server-блок в [Backend/nginx/nginx.conf](Backend/nginx/nginx.conf), подними SSL через certbot.
- Если сервис собирается из своего Dockerfile — добавь его в `build` секцию `deploy.sh` (сейчас билдятся `api scheduler`).
- Если сервис должен пересоздаваться при деплое — добавь его в `--force-recreate --no-deps` в `deploy.sh`.

---

## Ключевые изменения (май–июнь 2026)

Хайлайты по веткам — полный список см. в [ROADMAP.md → Changelog](ROADMAP.md).

**Маркет РФ-магазинов (новый раздел продукта)**
- Scraping-стек на 5 магазинов, листинги → matcher → `store_listings`, store-native записи для не-Discogs релизов.
- Маркет в Поиске (карусель «В наличии сейчас»), экран `/market` + `/market/store/[slug]`, Hot Stock pill, swipe-сравнение цен.
- Распределённый rate-limiter, parallel crawl, targeted stock-refresh, smoke-checks ингеста.

**Личные сообщения (новая фича)**
- TG-style чат: WebSocket realtime, typing, presence, read-receipts, reply/forward/edit/реакции/pin, media, «поделиться пластинкой».
- Лента уведомлений «Ты»/«Подписки», Expo push, v2 (dedup, snooze, weekly digest, quiet hours, badge).

**Достижения (зашиты в Mobile)**
- Архетипы «Физика звука» (XP-ladder), PNG/SVG-пины, серии Foundation/Collection/Rarity/Сообщество/Market/Пасхалки, share-карточка.

**Свои пластинки + импорт**
- User-submitted records (`source='user'`), Discogs-first ручной визард, auto-approve по доверию, dedup-intercept.
- Login via Discogs + one-time импорт коллекции; стабильная пагинация и hydration цен.

**Local-first Discogs**
- Slim-дамп в локальный индекс: обложки/suggest/barcode/master-versions резолвятся локально, к API — только на промах.
- Self-healing обложки версий (user-bucket + CAA), bound cover fan-out (нет 60s-зависаний на артистах).

**Цены и редкость**
- Маркетплейс-цены для RU/USSR, value коллекции через `estimate_rub` fallback, foldered-записи исключены из valuation.
- 3 тира редкости (Коллекционка / Лимитка / Популярно), `RarityAura`, VinylColorTag + VinylSpinner.

**Инфра и релиз-преп**
- Self-hosted GlitchTip (sentry.vinyl-vertushka.ru), TestFlight build prep, user-context в Sentry-scope.
- Security: trusted client IP, Google email_verified gate, token-revocation, broaden `.gitignore`.
- iOS-билд: modular headers для Google transitive pods; Spotify через прокси (обход RU geo-block).
- CLIP ONNX визуальный re-rank обложек при скане; font-scale clamp 1.15.

---

## Автор

Один разработчик ([@bamsrf](https://github.com/bamsrf)) + Claude Code. Сделано с любовью к виниловым пластинкам 🎶
