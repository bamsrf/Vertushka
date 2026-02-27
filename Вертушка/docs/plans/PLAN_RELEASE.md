# Что нужно для первого релиза (iOS + Android)

## Контекст

Приложение "Вертушка" — сканер и коллекционер виниловых пластинок. Backend (FastAPI) задеплоен на VPS, Mobile (Expo/React Native) работает в dev-режиме. Цель — первый публичный релиз в App Store и Google Play.

Текущая готовность: **Mobile ~70%, Backend ~65%**

---

## БЛОК 1 — КРИТИЧНОЕ (без этого не релизнуться)

### 1.1 Redis-кэш для Discogs API

**Проблема:** Каждый запрос страницы артиста = 20-30 запросов к Discogs (rate limit 60/мин). При 1000 юзеров — постоянные таймауты.
**Решение:** Redis-кэш для `_get_master_info`, `get_release`, `get_artist_releases` (TTL 24ч). Мастер-релизы не меняются.
**Файлы:** `Backend/app/services/discogs.py`, новый `Backend/app/services/cache.py`, `docker-compose.prod.yml` (добавить Redis)

### 1.2 EAS Build (eas.json)

**Проблема:** Без eas.json нельзя собрать production-билды для App Store / Google Play.
**Решение:** Создать `eas.json` с профилями development, preview, production. Настроить signing credentials.
**Файлы:** `Mobile/eas.json` (новый)

### 1.3 Политика конфиденциальности + Terms of Service

**Проблема:** App Store и Google Play **отклонят** приложение без privacy policy.
**Решение:** Написать privacy policy и terms of service, захостить на `vinyl-vertushka.ru`, добавить URL в app.json.
**Файлы:** `Backend/templates/privacy.html`, `Backend/templates/terms.html`, `Mobile/app.json`

### 1.4 Сократить TTL access-токена

**Проблема:** Сейчас access token живёт **30 дней** — огромная дыра в безопасности.
**Решение:** Access token → 30 минут, refresh token → 30 дней. Mobile уже умеет рефрешить.
**Файлы:** `Backend/app/config.py`

### 1.5 Ограничить CORS

**Проблема:** `allow_origins=["*"]` — открыто для всех.
**Решение:** Для мобильного приложения CORS не нужен (не браузер), но на всякий случай ограничить до `["https://vinyl-vertushka.ru"]`.
**Файлы:** `Backend/app/main.py`

### 1.6 Rate limiting на auth-эндпоинтах

**Проблема:** `/auth/login` и `/auth/register` можно брутфорсить без ограничений.
**Решение:** `slowapi` — 5 попыток/минуту на login, 3/минуту на register.
**Файлы:** `Backend/app/api/auth.py`, `Backend/requirements.txt`

### 1.7 APScheduler в requirements.txt

**Проблема:** APScheduler используется для фоновых задач (напоминания, автопродление), но **не указан в зависимостях**. На проде задачи молча не работают.
**Решение:** Добавить `apscheduler==3.10.4` в requirements.txt.
**Файлы:** `Backend/requirements.txt`

### 1.8 Глобальный exception handler

**Проблема:** Необработанные ошибки возвращают 500 со стектрейсом клиенту.
**Решение:** `@app.exception_handler(Exception)` — логировать, возвращать `{"detail": "Internal server error"}`.
**Файлы:** `Backend/app/main.py`

---

## БЛОК 2 — ВЫСОКИЙ ПРИОРИТЕТ (нужно для нормального UX)

### 2.1 Sentry (error tracking)

**Проблема:** Без мониторинга крашей невозможно узнать, что сломалось у юзера.
**Решение:** `sentry-sdk[fastapi]` на бэкенде, `@sentry/react-native` на мобильном.
**Файлы:** `Backend/app/main.py`, `Backend/requirements.txt`, `Mobile/app/_layout.tsx`, `Mobile/package.json`

### 2.2 Push-уведомления

**Проблема:** Нет способа уведомить юзера о забронированном подарке, новом подписчике и т.д.
**Решение:** `expo-notifications` + Expo Push API. На бэке — сохранение push-токенов и отправка через Expo.
**Файлы:** `Mobile/app/_layout.tsx`, новый `Backend/app/services/push.py`, `Backend/app/models/user.py` (push_token поле)

### 2.3 Apple Sign In в app.json

**Проблема:** Бэкенд поддерживает Apple Sign In, но в app.json не настроены entitlements.
**Решение:** Добавить `"ios": { "usesAppleSignIn": true }` и associated domains.
**Файлы:** `Mobile/app.json`

### 2.4 Health check с проверкой БД

**Проблема:** `/health` возвращает 200 даже если БД упала.
**Решение:** Добавить `SELECT 1` в health check.
**Файлы:** `Backend/app/main.py`

### 2.5 Structured logging (JSON)

**Проблема:** Логи — plain text, невозможно парсить и фильтровать на проде.
**Решение:** `structlog` или `python-json-logger`, JSON-формат, correlation ID.
**Файлы:** `Backend/app/main.py`, `Backend/requirements.txt`

---

## БЛОК 3 — СРЕДНИЙ ПРИОРИТЕТ (можно после первого релиза)

### 3.1 Firebase Analytics

Отслеживание пользовательского поведения: какие экраны смотрят, где отваливаются.

### 3.2 Accessibility (a11y)

`accessibilityLabel` на кнопках, `accessibilityHint` на интерактивных элементах. Apple может отклонить без базового a11y.

### 3.3 Deep linking (universal links)

Чтобы ссылки `vertushka://record/123` и `https://vinyl-vertushka.ru/record/123` открывали приложение.

### 3.4 Тесты (хотя бы интеграционные)

pytest для критичных эндпоинтов: auth, collection CRUD, gifts.

### 3.5 CI/CD (GitHub Actions)

Автоматический lint + тесты при push, деплой при merge в main.

### 3.6 Офлайн-режим

Кэширование коллекции локально, очередь запросов при потере сети.

### 3.7 Админ-панель (статистика и управление)

**Проблема:** Нет способа следить за состоянием приложения — сколько юзеров, какие пластинки популярны, сколько подарков забронировано, есть ли ошибки.
**Решение:** Веб-админка на FastAPI + Jinja2 (уже есть templates), защищённая паролем. Дашборд с метриками:

- **Юзеры:** всего, новых за день/неделю, активных (last_login_at), по провайдеру (email/Apple)
- **Коллекции:** общее кол-во пластинок, средний размер коллекции, топ-артисты
- **Подарки:** активных бронирований, завершённых, отменённых
- **API:** кол-во запросов к Discogs за день (из логов), ошибки
- **Управление:** блокировка юзеров, просмотр профилей, ручное продление бронирований
**Файлы:** новый `Backend/app/api/admin.py`, `Backend/templates/admin/` (dashboard.html, users.html, stats.html)

### 3.8 Redis-кэш для Discogs API

**Проблема:** Сейчас используется in-memory кэш (`cachetools`), который сбрасывается при рестарте сервера и не шарится между воркерами.
**Решение:** Заменить `cachetools.TTLCache` на Redis. Поднять Redis в Docker на VPS, использовать `redis.asyncio` в Python. TTL 24ч для мастер-релизов.
**Файлы:** `Backend/app/services/discogs.py`, новый `Backend/app/services/cache.py`, `docker-compose.prod.yml` (добавить Redis), `Backend/requirements.txt` (добавить `redis`)

---

## БЛОК 4 — ПЕРЕД САБМИТОМ В СТОР

### 4.1 App Store / Google Play метаданные

- Скриншоты (5 штук на каждый размер экрана)
- Описание приложения (RU + EN)
- Категория, возрастной рейтинг
- Иконка 1024x1024

### 4.2 TestFlight / Internal Testing

- Собрать preview-билд через EAS
- Тестирование на реальных устройствах (iPhone + Android)
- Минимум 3-5 бета-тестеров

### 4.3 App Store Review Guidelines

- Проверить compliance с Apple/Google guidelines
- Убедиться что Apple Sign In работает (Apple **требует** его если есть другие OAuth)

---

## ПЕРЕД ДЕПЛОЕМ — не забыть вернуть

> Эти вещи были отключены/убраны для работы через Expo Go на локалке. Вернуть перед production-сборкой!

- [ ] **Sentry на мобилке** — добавить `@sentry/react-native` в package.json, плагин `@sentry/react-native/expo` в app.json plugins, инициализацию `Sentry.init()` в `Mobile/app/_layout.tsx`. Вставить реальный DSN.
- [ ] **Sentry DSN на бэкенде** — добавить `SENTRY_DSN=...` в `.env` на сервере (бэкенд уже готов, нужен только DSN)
- [ ] **TTL access-токена (1.4)** — сменить `access_token_expire_minutes` с 43200 (30 дней) на 30 минут в `Backend/app/config.py`
- [ ] **API URL на мобилке** — убедиться что в `Mobile/lib/api.ts` dev-режим указывает на локальный IP, а prod — на `https://api.vinyl-vertushka.ru/api`

---

## Порядок реализации (рекомендуемый)

**Неделя 1:** 1.2 (eas.json), 1.4 (TTL), 1.5 (CORS), 1.6 (rate limit), 1.7 (APScheduler), 1.8 (exception handler)
**Неделя 2:** 1.1 (Redis-кэш), 2.1 (Sentry), 2.3 (Apple Sign In config), 2.4 (health check)
**Неделя 3:** 1.3 (privacy policy), 2.2 (push notifications), 2.5 (structured logging)
**Неделя 4:** 3.7 (админ-панель), 4.1 (метаданные), 4.2 (TestFlight), 3.2 (a11y)
**Неделя 5:** финальное тестирование, 4.3 (review guidelines), сабмит в App Store + Google Play

## Верификация

- Backend: `cd Вертушка/Backend && uvicorn app.main:app --reload` — проверить что все эндпоинты работают
- Mobile: `cd Вертушка/Mobile && npx expo start` — проверить все экраны
- Production: `curl https://api.vinyl-vertushka.ru/health` — должен вернуть DB status
- EAS: `eas build --profile preview --platform all` — билды собираются

