# PLAN_QA_REVIEW_FIXES — Разбор QA-ревью «Вертушки»

> **TL;DR:** из 46 пунктов QA-ревью реально нужно чинить ~12. Остальное — фантомы (код, которого нет), уже закрытые гарды, или улучшения, которые не критичны для релиза. Документ сортирует находки по факту, привязывая каждую к конкретной строке кода.

## Context

Получено сквозное QA-ревью на 46 пунктов от 4 параллельных агентов (Backend / Mobile / Web / Infra). При спот-проверке выяснилось:

- часть номеров строк устарели (агенты работали против более раннего commit'а),
- есть как минимум один полностью галлюцинированный эндпоинт,
- часть «critical» уязвимостей нейтрализована существующими гардами выше по стеку.

Поэтому план переработан с привязкой к **актуальному коду** и реальной критичности. Цель — закрыть подтверждённые угрозы безопасности и UX-блокеры до следующего публичного релиза, не тратя время на пустышки.

---

## P0 — CRITICAL (фиксим до релиза)

### #1 Утечка Discogs API-ключа в `.env.example` ✅
- **Файл:** [Backend/.env.example](../../../Backend/.env.example) — строка 17.
- **Что:** реальный UUID-ключ закоммичен в публичный репозиторий (`github.com/bamsrf/Vertushka`).
- **Фикс:**
  1. Регенерировать ключ в личном кабинете Discogs.
  2. Заменить значение в `.env.example` на `your-discogs-api-key`.
  3. Прописать новый ключ в `.env.prod` на сервере.
  4. Удалить из git history (`git filter-repo` / BFG). Перед операцией — резервная копия `.git/`.

### #2 Нет `.gitignore` в корне репо ✅
- **Файл:** `/.gitignore` (отсутствует). Backend тоже без `.gitignore`, есть только `Mobile/.gitignore`.
- **Фикс:** создать корневой `.gitignore`:
  ```
  .env*
  *.key
  *.pem
  *.log
  __pycache__/
  .venv/
  venv/
  node_modules/
  dist/
  build/
  .DS_Store
  # EAS / Expo
  .expo/
  *.ipa
  *.apk
  *.aab
  ```

### #4 Reset-код пароля логируется в stdout ✅
- **Файл:** [Backend/app/api/auth.py:611](../../../Backend/app/api/auth.py) — `logger.info("DEV: Reset code for %s: %s", data.email, code)`.
- **Что:** код восстановления пароля летит в `docker logs`.
- **Фикс:** удалить строку. Альтернатива — обернуть в `if settings.debug:`. Маскирование смысла не имеет (любые цифры reset-кода компрометирующи).

### #6 Белый экран при истёкшем refresh-токене (Mobile) ✅
- **Файлы:** [Mobile/lib/api.ts:128-131](../../../Mobile/lib/api.ts), [Mobile/lib/store.ts:218-222](../../../Mobile/lib/store.ts).
- **Что:** в `catch` после провала `refreshToken()` вызывается `removeTokens()`, но:
  - pending `refreshSubscribers` не оповещаются → их Promise висят навсегда,
  - `useAuthStore` не обновляется → нет редиректа на `/(auth)/login`.
- **Фикс:**
  1. После `removeTokens()` пройти по `refreshSubscribers` с сигналом ошибки и обнулить массив.
  2. Дёрнуть `useAuthStore.getState().logout()` (он clear-ит state).
  3. В [Mobile/app/_layout.tsx](../../../Mobile/app/_layout.tsx) подписаться на `isAuthenticated` и пушить `(auth)/login` при `false`.

### #5 XSS в `/cancel` через token — defense-in-depth, не critical ⚠️
- **Файл:** [Backend/app/web/templates/cancel_booking.html:180](../../../Backend/app/web/templates/cancel_booking.html).
- **Нюанс:** на [Backend/app/web/routes.py:641](../../../Backend/app/web/routes.py) handler валидирует `if booking.cancel_token != token` ДО рендера. В JS-блок попадает только серверный токен из `generate_random_token(24)` (URL-safe, без кавычек/HTML). Эксплуатация невозможна.
- **Фикс (всё равно делаем, 1 строка):** `cancel_token: '{{ token|tojson }}'` + сборка URL через `URLSearchParams`.

### ❌ #3 Утечка списка бронирований по email — **ФАНТОМ, не чиним**
- Эндпоинта `GET /gifts/my-bookings/by-email` в коде **нет**. `grep -rn "by-email\|my-bookings"` по `Backend/app/` пуст.
- QA-агент либо галлюцинировал, либо ссылался на удалённую старую версию.

---

## P1 — HIGH (ближайший спринт)

### Backend

#### #7 Race condition при бронировании ✅
- **Файл:** [Backend/app/api/gifts.py:192,238](../../../Backend/app/api/gifts.py).
- **Что:** read-check `if item.gift_booking` отделён от `db.add(booking)` — между ними возможен второй insert.
- **Фикс:** новая Alembic-миграция с **partial unique index** (CANCELLED не блокирует новые попытки):
  ```sql
  CREATE UNIQUE INDEX ix_gift_bookings_active_per_item
  ON gift_bookings (wishlist_item_id)
  WHERE status IN ('PENDING', 'BOOKED');
  ```
  В коде — обработать `IntegrityError` → 409.

#### #8 Не транзакционная регистрация ⚠️ (доверифицировать)
- **Файл:** [Backend/app/api/auth.py](../../../Backend/app/api/auth.py) — функция `register`.
- **Что:** если падает создание Wishlist/Collection после User — User остаётся осиротевшим.
- **Фикс:** обернуть всё в `async with db.begin()` (если ещё нет общей транзакции). Сначала прочитать текущую логику, потом фиксить.

#### #9 IntegrityError в `get_or_create_record_by_discogs_id` ✅
- **Файл:** [Backend/app/api/records.py](../../../Backend/app/api/records.py) (поиск по имени функции).
- **Фикс:** применить тот же паттерн `try/commit/except IntegrityError → rollback + select again`, что уже есть в `profile.py:136-140`.

#### #12 N+1 в `search_users` ⚠️ (приоритет по EXPLAIN)
- **Файл:** [Backend/app/api/users.py:57-141](../../../Backend/app/api/users.py).
- **Фикс:** correlated subqueries → агрегаты + `selectinload`. Делать, если EXPLAIN или прод-метрики покажут реальную медленность.

### Mobile

#### #13 State не сбрасывается при logout ✅
- **Файл:** [Mobile/lib/store.ts:218-222](../../../Mobile/lib/store.ts) — сбрасывается только auth + searchHistory.
- **Что:** `useCollectionStore`, `useProfileStore`, `useFollowStore`, `useUserSearchStore` остаются с данными прошлого пользователя → видны под новым логином.
- **Фикс:** добавить `resetAllStores()` (общий хелпер, который вызывает `reset()` в каждом сторе) и звать его в `useAuthStore.logout()`.

#### #14 Двойные тапы на «Добавить в коллекцию» / «Забронировать» ✅
- **Файлы:** [Mobile/app/(tabs)/index.tsx](../../../Mobile/app/(tabs)/index.tsx), [Mobile/app/(tabs)/search.tsx](../../../Mobile/app/(tabs)/search.tsx), [Mobile/components/RecordCard.tsx](../../../Mobile/components/RecordCard.tsx).
- **Фикс:** локальный `inFlight: Set<recordId>`; пропс `isLoading`; дисейбл кнопки до завершения запроса.

### Infra

#### #16 Downtime: миграции после `up -d` ✅
- **Файл:** [Backend/scripts/deploy.sh:51,55](../../../Backend/scripts/deploy.sh).
- **Что:** контейнеры стартуют ДО миграций. Если миграция падает — новый код уже работает на старой схеме.
- **Фикс:**
  ```bash
  docker compose -f docker-compose.prod.yml build api
  docker compose -f docker-compose.prod.yml run --rm api alembic upgrade head
  docker compose -f docker-compose.prod.yml up -d
  # healthcheck: curl с retry
  for i in {1..30}; do
      curl -fsS https://api.vinyl-vertushka.ru/health && break
      sleep 2
  done
  ```

#### #17 Нет HSTS ✅
- **Файл:** [Backend/nginx/nginx.conf:71-73,121-123](../../../Backend/nginx/nginx.conf).
- **Фикс:** в обоих HTTPS-блоках:
  ```nginx
  add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;
  ```

#### #37 Verify бэкапов (поднимаем из P2) ✅
- **Файл:** `Backend/scripts/backup.sh`.
- **Фикс:** после `pg_dump | gzip` — `gunzip -t` тестирует целостность; загрузка в Yandex Object Storage. Бэкап без проверки = нет бэкапа.

### Что из P1 НЕ чиним

#### ⚠️ #10 Доступ к приватным вишлистам без `is_public`
- При проверке: все mutating эндпоинты требуют `current_user` и проверяют ownership; единственный публичный read `GET /share/{share_token}` уже сверяет `Wishlist.is_public == True` ([wishlists.py:309-323](../../../Backend/app/api/wishlists.py)).
- Без конкретного непокрытого пути от QA — пропускаем.

#### ⚠️ #11 CSRF на `PUT /api/gifts/{id}/cancel`
- `cancel_token` — одноразовый server-side secret для конкретной брони, **не cookie-сессия**. Атакующий не имеет токена → CSRF не применим.
- Перевод на POST + JSON body — гигиена, делается в P2 если будем трогать этот код.

#### ⚠️ #15 Toast о частичных результатах поиска
- Не баг, а UX-улучшение. P2.

#### ⚠️ #18 Rate-limit на nginx
- На `/gifts/book` уже есть лимиты на уровне приложения (`_check_rate_limits`).
- На `/auth/*` имеет смысл добавить (`5r/m`).
- На `/api` целиком — overkill для текущего трафика. **Только /auth/*.**

#### ⚠️ #19 CI
- Нужен, но не блокирует релиз. Делаем, когда доедет «бюджет на инфру».

---

## P2 — Plot to keep (плановые улучшения)

Делаем по мере касания соответствующих файлов:

- **#20 Trailing slashes** — нарушение [CLAUDE.md](../../../CLAUDE.md). `RedirectSlashes` middleware в [Backend/app/main.py](../../../Backend/app/main.py) — 5 минут работы.
- **#22 OOM при `recalculate_prices`** — `.limit(50)` или batched processing в [collections.py:56-62](../../../Backend/app/api/collections.py). Превентивно, если коллекции у пользователей растут.
- **#23 Retry на Discogs timeout** — backoff 2-3 попытки в [services/discogs.py:110-138](../../../Backend/app/services/discogs.py).
- **#24 Утечка `str(e)` Discogs наружу** — `logger.exception` + generic message клиенту в `records.py`.
- **#25 EmailStr в UserCreate** — типизация в `schemas/user.py`.
- **#26 `utcnow` → `datetime.now(timezone.utc)`** — техдолг (deprecation в Python 3.12). Одной волной grep+replace.
- **#27 Race `refresh ↔ loadMore`** — флаг `isLoadingMore` в search store.
- **#28 Дубликаты в pagination** — дедуп по `id` перед `[...results, ...new]`.
- **#29 Каскад удаления из папок** — после успеха вызывать `fetchFolders()`, а не патчить локально.
- **#30 Модалка сканера** — `setShowResults(false)` перед `router.push` в [(tabs)/index.tsx](../../../Mobile/app/(tabs)/index.tsx).
- **#31 AbortController вместо cancelled-флагов** в search.tsx.
- **#32 FlatList `getItemLayout`** в RecordGrid.
- **#33 Pull-to-refresh ↔ loadMore race** в collection.tsx.
- **#34 Двойной клик «Отменить бронь»** — guard через `dataset.loading` в cancel_booking.html.
- **#35 `cancel_token` в UI** — скрыть за «Показать ссылку отмены».
- **#36 Плавающие версии Python-пакетов** — `==` в [requirements.txt](../../../Backend/requirements.txt). Воспроизводимость билдов.

---

## P3 — техдолг и косметика

#39, #40, #41, #42, #43, #44, #45, #46 — берём по мере касания, отдельной волны не выделяем.

---

## План работ по волнам

### Волна A — Security hotfix (½ дня) 🔥
**Сотрудник:** backend + ops.
- [ ] #1 Регенерация Discogs-ключа + замена в `.env.example` + prod
- [ ] git filter-repo для очистки истории (с резервной копией `.git/`)
- [ ] #2 Корневой `.gitignore`
- [ ] #4 Удаление `logger.info` reset-кода
- [ ] #5 `tojson` для cancel_token (defense-in-depth)
- [ ] Релиз отдельным PR/деплоем

### Волна B — Mobile stability (1 день)
**Сотрудник:** mobile.
- [ ] #6 Refresh-token failure → logout + redirect
- [ ] #13 `resetAllStores()` в logout
- [ ] #14 `inFlight` Set против двойных тапов
- [ ] EAS-сборка → TestFlight

### Волна C — Data integrity (2-3 дня)
**Сотрудник:** backend.
- [ ] #7 Alembic-миграция partial unique + 409 handler (отдельный PR)
- [ ] #8 Транзакционная регистрация (после verify)
- [ ] #9 IntegrityError handling в `get_or_create_record_by_discogs_id`
- [ ] #12 EXPLAIN на `search_users`, фиксить если медленно

### Волна D — Infra (1 день)
**Сотрудник:** ops.
- [ ] #16 Порядок деплоя: build → migrate → up → healthcheck
- [ ] #17 HSTS в nginx
- [ ] #37 `gunzip -t` + загрузка бэкапов в Yandex Object Storage
- [ ] #18 (частично) rate-limit на `/auth/*`

### Волна E — Polish (по бэклогу, без дедлайна)
P2-пункты по мере касания.

---

## Что НЕ делаем

| # | Причина |
|---|---------|
| #3 | Эндпоинта в коде нет. Phantom. |
| #10 | Все эндпоинты уже под гардами; конкретного непокрытого не указано. |
| #11 | CSRF не применим к одноразовому server-side токену. |
| #18 (полный) | nginx rate-limit на весь `/api` — overkill. Только `/auth/*`. |
| #15, #19 (срочно) | Не баги, а улучшения; перенесены в P2. |

---

## Verification (только critical)

| # | Проверка |
|---|----------|
| #1 | `git log --all --full-history -- Backend/.env.example` — старого ключа нет в истории. `curl -H "Authorization: Discogs key=OLD,..." https://api.discogs.com/...` → 401. |
| #4 | После `POST /auth/forgot-password`: `docker logs api 2>&1 \| grep -i "reset code"` → пусто. |
| #5 | `https://vinyl-vertushka.ru/cancel/<id>?token=test%22+alert(1)+%22` → alert НЕ срабатывает; страница рендерит `invalid_token`. |
| #6 | Вручную инвалидировать refresh в SecureStore → следующий запрос → редирект на `(auth)/login`, без зависших спиннеров. |
| #7 | `seq 1 2 \| xargs -n1 -P2 -I{} curl -X POST ...gifts/book ... -d '{"wishlist_item_id":"<X>",...}'` → один 201, один 409. |
| #13 | Logout под user A → login под user B → коллекция/вишлист соответствуют B (не остатки A). |
| #14 | Быстрые два тапа на «Добавить в коллекцию» → один POST в Network logger Expo. |
| #16 | Симулировать падение миграции (вручную битая `alembic upgrade head` на staging) → `up -d` НЕ выполнен, прод-контейнер живёт на старой версии. |
| #17 | `curl -I https://api.vinyl-vertushka.ru/ \| grep -i strict-transport-security` → найдено. |

### Регрессионный smoke

1. Регистрация → логин → forgot-password.
2. Поиск пластинки → детали → добавить в коллекцию.
3. Создать вишлист → расшарить → забронировать с публичного профиля → отменить из email.
4. Pull-to-refresh + scroll до конца коллекции (200+ items).
