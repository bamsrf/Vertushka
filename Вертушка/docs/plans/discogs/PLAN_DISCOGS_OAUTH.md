# План: Discogs OAuth — per-user токены

> Статус: ⬜ Not started · Owner: bamsrf · Связан с [ROADMAP M4](../../../ROADMAP.md)

## Зачем

Сейчас весь трафик к Discogs идёт через **один общий app-токен** (`DISCOGS_TOKEN` / `key+secret` в [config.py](../../../Backend/app/config.py)). Лимит Discogs — **60 req/min на токен**, повысить нельзя. При росте юзеров общий пул ([rate_limiter.py](../../../Backend/app/services/rate_limiter.py), capacity=55, refill≈0.95/s) станет бутылочным горлышком: один активный юзер с массовым поиском тормозит всех.

**Цель:** дать каждому юзеру возможность подключить свой Discogs-аккаунт. Тогда его поиск/детали идут через **его** токен → его личные 60 req/min, общий пул разгружается.

**Решения (согласовано):**
- Подключение Discogs — **опционально**. Без него всё работает на общем app-токене, как сейчас (онбординг не меняется).
- Первичная цель — **снять общий rate-limit**. Импорт коллекции (M4) и запись в Discogs — следующие шаги, на этой же инфраструктуре.

## Протокол

Discogs использует **OAuth 1.0a (3-legged)**, не OAuth2. Подпись каждого запроса — HMAC-SHA1. Добавляем зависимость `authlib` (умеет OAuth1 поверх httpx). App-уровневые `consumer_key`/`consumer_secret` = текущие `DISCOGS_API_KEY`/`DISCOGS_API_SECRET`.

Flow:
1. `request_token` — `GET https://api.discogs.com/oauth/request_token` (подпись consumer key/secret) → `oauth_token`, `oauth_token_secret`.
2. Redirect юзера → `https://www.discogs.com/oauth/authorize?oauth_token=...`.
3. Discogs → callback с `oauth_verifier`.
4. `access_token` — `POST https://api.discogs.com/oauth/access_token` → постоянные `oauth_token` + `oauth_token_secret` юзера.
5. `GET /oauth/identity` → `username` юзера (для отображения + импорта коллекции).

## Backend

### Модель / миграция
[models/user.py](../../../Backend/app/models/user.py) — новые поля:
- `discogs_username: str | None`
- `discogs_oauth_token: str | None`
- `discogs_oauth_token_secret: str | None` — **шифровать at rest** (Fernet, ключ в env), а не plaintext.
- `discogs_connected_at: datetime | None`

Alembic-миграция на эти поля. Временные request-token secret'ы (между шагом 1 и 4) держать в коротком кэше/таблице, не в User.

### Сервис подписи
Новый `services/discogs_oauth.py`:
- `build_authorize_url(callback_url) -> (url, request_token_secret)`
- `exchange(oauth_token, oauth_verifier, request_token_secret) -> (token, secret, username)`
- `sign_headers(user_token, user_secret) -> dict` — возвращает `Authorization` для OAuth1.

### discogs.py
`_get` уже принимает `headers` — это точка интеграции. Добавить опциональный параметр `creds` (user token/secret) в user-инициируемые методы (search, get_release, scan). Если `creds` есть → `_get_headers` отдаёт OAuth1-подпись вместо `key=,secret=`. Fallback на app-токен, если не подключён или подпись протухла (401 → пометить отключённым, не падать).

### Rate limiter
Сейчас singleton `discogs_limiter` — один bucket на всё приложение. Рефактор в **реестр bucket'ов по ключу токена**:
- `get_limiter(token_key)` → bucket (app-токен = ключ `"app"`, юзер = его token).
- Каждый bucket: capacity 55, refill 0.95/s.
- `acquire` вызывается на bucket'е, соответствующем используемому токену.
- Метрики stats() агрегируют по bucket'ам.

### Endpoints (`api/auth.py` или новый `api/discogs.py`)
- `POST /auth/discogs/connect` → `{ authorize_url }` (шаг 1–2).
- `GET /auth/discogs/callback?oauth_token&oauth_verifier` → обмен, сохранение, редирект обратно в апп (deep-link).
- `DELETE /auth/discogs` → отключить (очистить поля).
- `GET /auth/discogs/status` → `{ connected, username }`.

## Mobile

- `Mobile/app/settings/` — экран/секция «Discogs»: статус (подключён как `username` / не подключён), кнопки Подключить / Отключить.
- Flow: `connect` → открыть `authorize_url` через `expo-web-browser` (`openAuthSessionAsync`) → callback deep-link (`vertushka://discogs-callback`) → закрыть, обновить статус.
- [lib/api.ts](../../../Mobile/lib/api.ts): `connectDiscogs()`, `getDiscogsStatus()`, `disconnectDiscogs()`.
- [lib/store.ts](../../../Mobile/lib/store.ts): поле `discogs: { connected, username }`.
- Backend сам решает, чей токен использовать (по аутентифицированному юзеру) — мобилке не нужно ничего прокидывать в search/detail.

## Edge cases / безопасность
- Secret'ы шифровать (Fernet). Не логировать токены.
- 401 от Discogs по user-токену → авто-disconnect + fallback на app-токен, уведомить юзера переподключиться.
- Callback CSRF — проверять `oauth_token` против сохранённого request-token.
- Юзер сменил пароль/отозвал доступ на Discogs — обрабатывать 401 как выше.
- Per-user bucket для неактивных юзеров — лениво создавать, чистить по TTL чтобы не течь памятью.

## Фазы
1. **Backend OAuth flow** — модель+миграция, `discogs_oauth.py`, endpoints, шифрование. Тест: подключить аккаунт, токен в БД.
2. **Per-token rate limiter** — рефактор реестра bucket'ов.
3. **discogs.py интеграция** — прокинуть creds в user-методы, fallback на 401.
4. **Mobile** — экран настроек + web-browser flow + deep-link callback.
5. **(M4) Импорт коллекции** — поверх готового OAuth, отдельный spec [PLAN_COLLECTION_IMPORT.md].

## Acceptance
- [ ] Юзер подключает Discogs из настроек за <30с.
- [ ] После подключения его search/detail идут через его токен (проверить по логам bucket-ключа).
- [ ] Без подключения — работает на app-токене, без регрессий.
- [ ] 401 по user-токену → graceful fallback + disconnect, не 500.
- [ ] Secret'ы зашифрованы в БД.
