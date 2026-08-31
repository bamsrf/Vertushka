# Plan v2: Релиз Вертушки на 1000+ DAU

> **Цель**: Подготовить приложение к публичному релизу в App Store и Google Play с расчётом на 1000 DAU.
> **Дата ревью**: 10 апреля 2026
> **Источники**: PLAN_DISCOGS_SCALING.md, PLAN_RELEASE.md, полное ревью Backend + Mobile (апрель 2026)

---

## Что уже реализовано (не нужно делать)

Из предыдущих планов закрыто ~65%. Это не требует работы:

| Компонент | Статус | Детали |
|-----------|--------|--------|
| Redis кэш (Discogs) | ✅ | Singleton, connection pool (20), graceful fallback, TTL по типам данных |
| Redis в Docker | ✅ | Redis 7 в docker-compose.prod.yml |
| Кэш поисковых запросов | ✅ | `search:{type}:{md5(params)}`, TTL 10 мин |
| Token bucket rate limiter | ✅ | 60 tokens, 1/sec refill, capacity 55 |
| Приоритетная очередь Discogs | ✅ | SEARCH(1) → DETAIL(2) → SCAN(3) → ENRICHMENT(4) → BATCH(5) |
| search_cache таблица | ✅ | PostgreSQL + hourly cleanup cron |
| Фоновое обновление цен | ✅ | APScheduler daily 4:00 |
| Фоновое обогащение артистов | ✅ | APScheduler daily 5:00 |
| recalculate-prices лимит | ✅ | Ограничен 50 записями |
| CORS | ✅ | Только `https://vinyl-vertushka.ru` |
| Rate limiting auth | ✅ | register 3/мин, login 5/мин, password 3/мин |
| JWT + bcrypt | ✅ | Tokens с типизацией (access, refresh, reset, restore) |
| Global exception handler | ✅ | Не утекают стектрейсы |
| Structured JSON logging | ✅ | pythonjsonlogger |
| Health check (DB + Redis) | ✅ | `/health` endpoint |
| Sentry (Backend) | ✅ | Подключен, нужен только DSN в .env |
| Apple Sign In (app.json) | ✅ | `usesAppleSignIn: true` |
| Privacy/Terms URLs | ✅ | В app.json |
| Soft delete + восстановление | ✅ | 30-дневное окно |
| Mobile: request deduplication | ✅ | Map для GET-запросов в api.ts |
| Mobile: Zustand кэш | ✅ | useCacheStore с TTL: search 5м, artist/release 30м, LRU |
| Mobile: expo-image | ✅ | disk cache policy |
| Mobile: retry 503/429 | ✅ | Exponential backoff |
| Mobile: token refresh | ✅ | Interceptor с очередью на 401 |
| Mobile: deep linking | ✅ | Настроен в app.json |

---

## Фаза 0 — Блокеры (без этого приложение будет падать)

> Срок: 2-3 дня. Без этих исправлений невозможно стабильно обслуживать 1000 DAU.

### 0.1 🔴 Убрать хардкод dev IP из Mobile

**Проблема:** В `Mobile/lib/api.ts` захардкожен `http://192.168.1.78:8000/api`. Прод-билд через EAS Build пойдёт на локальный IP → приложение не будет работать.

**Решение:**
- Использовать `expo-constants` + `app.json` extra для переключения dev/prod
- Dev: определять IP динамически через Expo manifest
- Prod: `https://api.vinyl-vertushka.ru/api`

**Файлы:** `Mobile/lib/api.ts`, `Mobile/app.json`
**Оценка:** 1 час

### 0.2 🔴 Пагинация коллекций в Mobile

**Проблема:** `getCollectionItems()` загружает ВСЕ записи коллекции за один запрос. При 500+ записях — зависание UI, при 1000+ — crash (Out of Memory).

**Решение:**
- Backend endpoint уже поддерживает `page` и `per_page`
- Mobile: добавить `onEndReached` пагинацию в `collection.tsx` и `folder/[id].tsx`
- Первая загрузка: 20 записей, подгрузка по скроллу

**Файлы:** `Mobile/app/(tabs)/collection.tsx`, `Mobile/app/folder/[id].tsx`, `Mobile/lib/store.ts`
**Оценка:** 3-4 часа

### 0.3 🔴 Инвалидация кэша при мутациях

**Проблема:** После добавления записи в коллекцию кнопка «Добавить» не меняется на «В коллекции» — useCacheStore не знает о мутации.

**Решение:**
- При `addToCollection` / `removeFromCollection` / `addToWishlist` — инвалидировать соответствующие записи в useCacheStore
- Вызвать `invalidate()` по ключу релиза/мастера

**Файлы:** `Mobile/lib/store.ts` (useCollectionStore, useCacheStore)
**Оценка:** 1-2 часа

### 0.4 🔴 Увеличить DB connection pool

**Проблема:** `pool_size=10, max_overflow=20`. При 4 воркерах uvicorn (Фаза 2) — 4×10=40 базовых соединений, при пиковой нагрузке — до 4×30=120. PostgreSQL default `max_connections=100` → connection refused.

**Решение:**
- Установить `pool_size=5, max_overflow=10` на один воркер (× 4 = 20 базовых, 60 макс)
- Или добавить PgBouncer перед PostgreSQL (рекомендуется для горизонтального масштабирования)
- В PostgreSQL: `max_connections=200`

**Файлы:** `Backend/app/database.py`, `docker-compose.prod.yml` (postgresql.conf)
**Оценка:** 1-2 часа

### 0.5 🔴 Request timeouts

**Проблема:** Нет таймаутов на запросы к внешним сервисам. Зависший запрос к Discogs блокирует воркер навсегда.

**Решение:**
- Общий middleware: 30 сек таймаут на каждый запрос
- Discogs HTTP client: уже есть `timeout=10` на httpx — проверить что работает
- APScheduler задачи: добавить таймауты

**Файлы:** `Backend/app/main.py`, `Backend/app/services/discogs.py`
**Оценка:** 1-2 часа

---

## Фаза 1 — Наблюдаемость (иначе будем слепы в проде)

> Срок: 2-3 дня. Без этого не узнаем что сломалось у юзеров.

### 1.1 🔴 Sentry на Mobile

**Проблема:** Backend подключен к Sentry, Mobile — нет. Крашнулось у юзера → не узнаем.

**Решение:**
- `npx expo install @sentry/react-native`
- Плагин `@sentry/react-native/expo` в app.json
- `Sentry.init()` в `_layout.tsx`
- Source maps через EAS Build (автоматически)

**Файлы:** `Mobile/package.json`, `Mobile/app.json`, `Mobile/app/_layout.tsx`
**Оценка:** 2-3 часа

### 1.2 🟡 Sentry DSN на Backend

**Проблема:** Код Sentry есть, но DSN нужно прописать в `.env` на сервере.

**Решение:** Создать проекты в Sentry (backend-python, mobile-react-native), прописать DSN.

**Оценка:** 30 минут

### 1.3 🟡 Аналитика

**Проблема:** Не знаем: сколько юзеров сканирует, сколько добавляет в коллекцию, где отваливаются.

**Решение:** Expo Analytics (или PostHog / Amplitude). Ключевые события:
- `scan_barcode`, `scan_cover`, `add_to_collection`, `add_to_wishlist`
- `search`, `view_record`, `view_artist`
- `register`, `login`, `follow_user`, `book_gift`

**Файлы:** `Mobile/lib/analytics.ts` (новый), все экраны (добавить track-вызовы)
**Оценка:** 4-6 часов

### 1.4 🟡 Request ID tracing

**Проблема:** При расследовании инцидента невозможно связать запрос юзера с логами сервера.

**Решение:**
- Middleware: генерировать `X-Request-ID` (uuid4) на каждый запрос
- Добавлять в JSON-логи
- Возвращать в response header
- Mobile: логировать request_id при ошибках в Sentry

**Файлы:** `Backend/app/main.py`
**Оценка:** 1-2 часа

---

## Фаза 2 — Инфраструктура (масштабирование под нагрузку)

> Срок: 2-3 дня. Критично для стабильности при 1000 DAU.

### 2.1 🔴 Multi-worker uvicorn

**Проблема:** 1 процесс = 1 ядро CPU. Один тяжёлый запрос блокирует всех.

**Решение:**
```yaml
# docker-compose.prod.yml
backend:
  command: uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 4
```

**Зависимость:** 0.4 (pool size) должен быть сделан ДО этого.

**Файлы:** `docker-compose.prod.yml`
**Оценка:** 30 минут + тестирование

### 2.2 🔴 APScheduler → единственный воркер

**Проблема:** При 4 воркерах APScheduler запустится в каждом → задачи выполнятся 4 раза (4 письма, 4 обновления цен).

**Решение (выбрать одно):**
- **A)** Переменная окружения: один воркер помечен как scheduler (`IS_SCHEDULER=true`)
- **B)** Lock в Redis: `SET scheduler_lock NX EX 60` — только один воркер берёт задачи
- **C)** Вынести scheduler в отдельный контейнер (рекомендуется)

**Файлы:** `Backend/app/main.py`, `docker-compose.prod.yml`
**Оценка:** 2-3 часа

### 2.3 🟡 Circuit breaker для Discogs

**Проблема:** Если Discogs лежит — все воркеры висят в очереди rate limiter. Нет fast-fail.

**Решение:**
- Считать ошибки: 5 подряд 5xx → circuit OPEN (отдаём из кэша/БД, не ходим в Discogs)
- Через 60 сек → HALF-OPEN (пробуем один запрос)
- Успех → CLOSED (нормальная работа)

**Файлы:** `Backend/app/services/discogs.py`
**Оценка:** 2-3 часа

### 2.4 🟡 Nginx proxy cache

**Проблема:** 3 уровня кэша запланированы (Nginx → Redis → Discogs), но Nginx-кэш не настроен.

**Решение:**
```nginx
proxy_cache_path /var/cache/nginx levels=1:2 keys_zone=api_cache:10m max_size=1g inactive=10m;

location /api/records/search { proxy_cache api_cache; proxy_cache_valid 200 5m; }
location /api/records/masters/ { proxy_cache api_cache; proxy_cache_valid 200 1h; }
location /api/records/artists/ { proxy_cache api_cache; proxy_cache_valid 200 30m; }
```

**Файлы:** nginx.conf
**Оценка:** 1-2 часа

### 2.5 🟡 HTTP Cache-Control заголовки

**Проблема:** Эндпоинты не отдают Cache-Control — каждый запрос идёт до бэкенда.

**Решение:**
- `GET /records/search`: `Cache-Control: public, max-age=300`
- `GET /records/discogs/{id}`: `Cache-Control: public, max-age=3600`
- `GET /artists/{id}`: `Cache-Control: public, max-age=1800`

**Файлы:** `Backend/app/api/records.py`
**Оценка:** 1 час

---

## Фаза 3 — Mobile production quality

> Срок: 3-4 дня. UX-качество и стабильность.

### 3.1 🟡 React.memo на тяжёлых компонентах

**Проблема:** RecordCard ре-рендерится при каждом обновлении родителя. В списке из 200 карточек — 200 лишних ре-рендеров.

**Решение:**
```typescript
export const RecordCard = memo(RecordCardComponent);
export const RecordGrid = memo(RecordGridComponent);
export const ArtistCard = memo(ArtistCardComponent);
```

**Файлы:** `Mobile/components/RecordCard.tsx`, `Mobile/components/RecordGrid.tsx`, `Mobile/components/ArtistCard.tsx`
**Оценка:** 1 час

### 3.2 🟡 Push-уведомления (listener)

**Проблема:** `savePushToken` вызывается, токен хранится на сервере, но `expo-notifications` listener не добавлен — уведомления не показываются.

**Решение:**
- Регистрация listener в `_layout.tsx`
- Обработка foreground / background / killed state
- Deep link при тапе на уведомление

**Файлы:** `Mobile/app/_layout.tsx`
**Оценка:** 3-4 часа

### 3.3 🟡 Тосты вместо Alert.alert

**Проблема:** `Alert.alert()` блокирует UI. «Добавлено в коллекцию» не должно требовать нажатия «ОК».

**Решение:**
- Установить `react-native-toast-message` или `burnt` (нативные тосты)
- Заменить Alert.alert на тосты для success/info операций
- Оставить Alert.alert только для деструктивных действий (удалить аккаунт)

**Файлы:** `Mobile/package.json`, все экраны с Alert.alert
**Оценка:** 2-3 часа

### 3.4 🟡 Error boundaries

**Проблема:** Ошибка в одном компоненте крашит всё приложение.

**Решение:**
- Обернуть каждый Tab-экран в `ErrorBoundary`
- Показывать fallback UI с кнопкой «Попробовать снова»

**Файлы:** `Mobile/components/ErrorBoundary.tsx` (новый), `Mobile/app/(tabs)/_layout.tsx`
**Оценка:** 1-2 часа

### 3.5 🟡 Offline-индикатор

**Проблема:** При потере сети — молчаливые ошибки. Юзер не понимает что происходит.

**Решение:**
- `@react-native-community/netinfo`
- Баннер вверху экрана: «Нет подключения к интернету»
- Блокировать мутации (add/remove), показывать кэшированные данные

**Файлы:** `Mobile/package.json`, `Mobile/app/_layout.tsx`, `Mobile/components/OfflineBanner.tsx` (новый)
**Оценка:** 2-3 часа

---

## Фаза 4 — Безопасность и hardening

> Срок: 1-2 дня.

### 4.1 🔴 TTL access-токена

**Проблема:** Access token живёт 30 дней — при утечке токена злоумышленник имеет полный доступ на месяц.

**Решение:** Access token → 30 минут, refresh token → 30 дней. Mobile уже умеет рефрешить.

**Файлы:** `Backend/app/config.py`
**Оценка:** 15 минут + тестирование refresh flow

### 4.2 🟡 Валидация avatar upload

**Проблема:** Сервер проверяет расширение файла (JPEG/PNG), но не содержимое. Можно загрузить .exe переименованный в .jpg.

**Решение:** Проверять magic bytes файла (первые 8 байт):
- JPEG: `FF D8 FF`
- PNG: `89 50 4E 47`
- Ограничить размер: max 5MB

**Файлы:** `Backend/app/api/users.py`
**Оценка:** 1 час

### 4.3 🟡 Google Sign In

**Проблема:** Эндпоинт возвращает 501 Not Implemented. Если кнопка видна в UI — юзер нажмёт и получит ошибку.

**Решение (выбрать одно):**
- **A)** Реализовать Google Sign In (google-auth библиотека, проверка id_token)
- **B)** Убрать кнопку Google из UI, если не планируем сейчас

**Файлы:** `Backend/app/api/auth.py`, `Mobile/app/(auth)/login.tsx`
**Оценка:** A — 4-6 часов, B — 15 минут

### 4.4 🟡 Audit logging

**Проблема:** Нет логов: кто удалил аккаунт, кто сбросил пароль, кто забронировал подарок.

**Решение:** Логировать в JSON-лог (уже есть pythonjsonlogger):
```python
logger.info("account_deleted", extra={"user_id": str(user.id), "email": user.email})
logger.info("password_reset", extra={"user_id": str(user.id)})
logger.info("gift_booked", extra={"booking_id": str(booking.id), "gifter_email": email})
```

**Файлы:** `Backend/app/api/auth.py`, `Backend/app/api/users.py`, `Backend/app/api/gifts.py`
**Оценка:** 1-2 часа

---

## Фаза 5 — App Store / Google Play

> Срок: 3-5 дней. Параллельно с разработкой.

### 5.1 EAS Build (eas.json)

**Проблема:** Без eas.json нельзя собрать production-билды.

**Решение:** Создать `eas.json` с профилями:
- `development` — dev client для тестирования
- `preview` — TestFlight / Internal Testing
- `production` — финальный билд для стора

**Файлы:** `Mobile/eas.json` (новый)
**Оценка:** 1-2 часа

### 5.2 TestFlight / Internal Testing

- Собрать preview-билд через EAS
- 3-5 бета-тестеров на реальных устройствах
- Минимум 1 неделя тестирования

### 5.3 App Store метаданные

- Скриншоты: 5 штук на каждый размер (6.7", 6.5", 5.5" для iOS; phone + tablet для Android)
- Описание: RU + EN
- Категория: Lifestyle / Music
- Возрастной рейтинг: 4+
- Иконка 1024×1024

### 5.4 Compliance

- Apple: если есть OAuth — **обязателен** Apple Sign In ✅ (уже есть)
- App Tracking Transparency (ATT): если есть аналитика — нужен ATT prompt
- Privacy Nutrition Labels: заполнить в App Store Connect
- Google: Data Safety section в Play Console

---

## Фаза 6 — После релиза (backlog)

> Не блокирует релиз, делать по мере необходимости.

| # | Задача | Приоритет | Оценка |
|---|--------|-----------|--------|
| 6.1 | Тесты (pytest backend, jest mobile) — хотя бы auth + collection CRUD | 🟡 | 2-3 дня |
| 6.2 | CI/CD (GitHub Actions: lint + test + EAS build) | 🟡 | 1 день |
| 6.3 | Ротация Discogs токенов (если упираемся в лимит) | 🟡 | 1 день |
| 6.4 | Админ-панель (статистика юзеров, коллекций, подарков) | 🟡 | 3-5 дней |
| 6.5 | Accessibility (a11y labels) — Apple может отклонить без базового a11y | 🟡 | 1-2 дня |
| 6.6 | Dark mode | ⚪ | 2-3 дня |
| 6.7 | Локализация (EN) | ⚪ | 2-3 дня |
| 6.8 | OAuth per-user Discogs (максимальное масштабирование) | ⚪ | 5+ дней |
| 6.9 | CDN для изображений (проксирование i.discogs.com) | ⚪ | 1-2 дня |
| 6.10 | PgBouncer для connection pooling | ⚪ | 1 день |

---

## Сводная таблица

| Фаза | Задач | Критичных 🔴 | Срок | Зависимости |
|------|-------|-------------|------|-------------|
| **Фаза 0** — Блокеры | 5 | 5 | 2-3 дня | — |
| **Фаза 1** — Наблюдаемость | 4 | 1 | 2-3 дня | — |
| **Фаза 2** — Инфраструктура | 5 | 2 | 2-3 дня | Фаза 0.4 |
| **Фаза 3** — Mobile quality | 5 | 0 | 3-4 дня | — |
| **Фаза 4** — Безопасность | 4 | 1 | 1-2 дня | — |
| **Фаза 5** — App Store | 4 | 0 | 3-5 дней | Фазы 0-4 |
| **Итого** | **27** | **9** | **~14-20 дней** | |

---

## Рекомендуемый порядок

```
Неделя 1:  Фаза 0 (блокеры) + Фаза 4.1 (TTL токена)
           ├── 0.1 Dev IP → env config
           ├── 0.2 Пагинация коллекций
           ├── 0.3 Инвалидация кэша
           ├── 0.4 DB pool size
           ├── 0.5 Request timeouts
           └── 4.1 TTL access-токена

Неделя 2:  Фаза 1 (наблюдаемость) + Фаза 2 (инфраструктура)
           ├── 1.1 Sentry Mobile
           ├── 1.2 Sentry DSN Backend
           ├── 2.1 Multi-worker uvicorn
           ├── 2.2 APScheduler → single worker
           ├── 2.3 Circuit breaker
           └── 2.4 Nginx cache

Неделя 3:  Фаза 3 (Mobile quality) + Фаза 4 (безопасность)
           ├── 3.1 React.memo
           ├── 3.2 Push notifications listener
           ├── 3.3 Тосты вместо Alert
           ├── 3.4 Error boundaries
           ├── 3.5 Offline indicator
           ├── 4.2 Avatar validation
           ├── 4.3 Google Sign In (решить: реализовать или убрать)
           └── 4.4 Audit logging

Неделя 4:  Фаза 5 (App Store) + финальное тестирование
           ├── 5.1 eas.json
           ├── 5.2 TestFlight / Internal Testing
           ├── 5.3 Скриншоты, описание, метаданные
           ├── 5.4 Compliance check
           └── 1.3 Аналитика (базовые события)
```

---

## Ожидаемый результат после всех фаз

| Метрика | Сейчас | После |
|---------|--------|-------|
| Запросов к Discogs/мин (пик) | ~160 (с Redis) | ~15-30 (+ Nginx cache + circuit breaker) |
| Crash visibility | 0% (слепы) | 100% (Sentry backend + mobile) |
| Среднее время ответа поиска | 50-100ms (Redis) | 5-20ms (Nginx cache) |
| Устойчивость к Discogs downtime | Очередь растёт, таймауты | Fast-fail, отдаём из кэша/БД |
| Горизонтальное масштабирование | 1 процесс | 4 воркера, shared Redis, правильный pool |
| Большие коллекции (500+) | Crash | Пагинация, плавный скролл |
| Потеря сети | Молчаливые ошибки | Баннер + кэшированные данные |
| UX-обратная связь | Alert.alert (блокирует) | Нативные тосты |
| Безопасность токена | 30 дней | 30 минут + auto-refresh |

---

## Чеклист перед сабмитом в стор

- [ ] API URL = `https://api.vinyl-vertushka.ru/api` (не localhost)
- [ ] Sentry DSN прописан (backend + mobile)
- [ ] Access token TTL = 30 минут
- [ ] `eas build --profile production` — билды собираются
- [ ] TestFlight / Internal Testing — протестировано 3+ людьми
- [ ] Скриншоты загружены в App Store Connect / Play Console
- [ ] Privacy policy доступна по URL
- [ ] Apple Sign In работает
- [ ] Google Sign In работает ИЛИ кнопка скрыта
- [ ] Push notifications работают (iOS + Android)
- [ ] Коллекция 500+ записей — не крашится
- [ ] Offline → показывает баннер, не крашится
- [ ] `curl https://api.vinyl-vertushka.ru/health` → 200 OK
