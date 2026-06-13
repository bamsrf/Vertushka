# User-Submitted Records (`source='user'`)

> Статус: PLAN · Создан 2026-06-04
> Кейс: пластинка, которой нет ни в Discogs (баркод/фото), ни в Маркете.
> Решение продукта: юзер добавляет вручную, запись становится **общей** после
> дабл-чека на отсутствие в Discogs + Маркете. Enrichment из Spotify.

## TL;DR архитектуры

`records.source` уже имеет `discogs` и `store`. Добавляем **третий источник
`user`** и вешаем его на существующую store-native инфру:
- дедуп/дабл-чек → переиспользуем `services/listing_matcher.py`
- авто-merge в Discogs позже → `discogs_id_candidate` + `confirmations` + `merged_into_id`

Новой таблицы НЕ заводим. User-record — это `Record` с `source='user'`,
`created_by_user_id`, `moderation_status`.

---

## 1. Модель данных (миграция Alembic)

Добавить в `records`:

| Поле | Тип | Назначение |
|---|---|---|
| `source` | расширить convention-enum значением `'user'` | источник |
| `created_by_user_id` | `UUID FK users(id)` nullable | автор (модерация, права) |
| `moderation_status` | `String(20)` default `'pending'` | `pending` / `approved` / `rejected` / `merged` |
| `spotify_album_id` | `String(64)` nullable | связь с enrichment-источником |
| `user_submitted_data` | `JSONB` nullable | сырой ввод (аналог `discogs_data`) |

Картинки → существующие `cover_image_url` / `cover_local_path` (cover_storage).
Треклист → существующий `tracklist JSONB`. Год/лейбл/каталог/страна/формат →
существующие колонки. Форма данных не меняется.

Индекс: `(source, moderation_status)` для ленты модерации.

---

## 2. Дабл-чек (pre-flight dedup) — ядро фичи

Перед созданием `source='user'` запись проходит каскад. **Переиспользуем
`listing_matcher.py`** — там готовы `normalize_barcode/catalog/text`,
pg_trgm + rapidfuzz, пороги.

Новый сервис `services/user_record.py::preflight_dedup(payload, db)`:

```
1. barcode    → _find_by_barcode        (exact)      → DUPLICATE
2. catalog №  → _find_by_catalog        (norm)       → DUPLICATE
3. fuzzy(artist+title+year) против records (любой source) через
   _fuzzy_candidates + score ≥ threshold              → LIKELY_DUPLICATE
4. Discogs check:
   a) если дамп-индекс доступен → _lookup_in_dump_index (оффлайн, быстро)
   b) иначе live Discogs search API (services/discogs.py)  → FOUND_IN_DISCOGS
5. чисто → ALLOW_CREATE
```

Результат отдаётся на фронт:
- `DUPLICATE` / `LIKELY_DUPLICATE` → показываем найденную запись: «Кажется,
  это она — добавить в коллекцию?» (мягкий блок, юзер может настоять).
- `FOUND_IN_DISCOGS` → редиректим в обычный Discogs-флоу (не создаём user-record).
- `ALLOW_CREATE` → пускаем дальше в форму.

Порог `LIKELY_DUPLICATE` берём мягче, чем store dedup (1.6), т.к. тут human-in-loop
подтверждает. Старт: score ≥ 1.4.

---

## 3. Spotify enrichment

Новый `services/spotify.py` рядом с `discogs.py`:
- auth: **Client Credentials** (без юзер-логина), token-cache как в discogs.
- `search_album(artist, title)` → top-N кандидатов (название, год, обложка, id).
- `get_album_tracks(album_id)` → треклист → маппим в формат `tracklist`.
- `get_artist(artist_id)` → имя/жанры/фото артиста → в `user_submitted_data`.

Spotify не даёт прессинги/каталожные № — эти поля юзер вводит руками.
Обложка из Spotify = кандидат; приоритет у юзерского фото пластинки.

Env: `SPOTIFY_CLIENT_ID`, `SPOTIFY_CLIENT_SECRET` → `config.py`.

---

## 4. API (`Backend/app/api/records.py`)

```
POST /records/preflight/         body: {barcode?, catalog?, artist, title, year?}
                                 → {status, match?: RecordOut}
GET  /records/spotify-search/    ?q=...  → [SpotifyAlbumCandidate]
POST /records/user/              multipart: фото(а) + поля + spotify_album_id?
                                 → создаёт source='user', moderation_status='pending'
                                 → сразу кладёт в коллекцию создателя
```

`POST /records/user/`:
1. повторный `preflight_dedup` на бэке (фронт-чек не доверяем).
2. заливка фото через `cover_storage`.
3. enrichment-merge: Spotify-данные + ручные поля.
4. `Record(source='user', created_by_user_id=me, moderation_status='pending')`.
5. add to creator collection.

---

## 5. Guard'ы коллекций/вишлистов

Сейчас blacklist по `store` (`collections.py:425`, `wishlists.py:136`):
```python
if record.source == "store":
    raise ...
```
Переписать на **whitelist** — пускаем `discogs` и `user`, блокируем `store`:
```python
if record.source not in ("discogs", "user"):
    raise ...
```
⚠️ Менять явно и осознанно — место чувствительное, нельзя случайно открыть store.

---

## 6. Модерация + общий пул (полный скоуп)

- `moderation_status='pending'` → запись приватна (видит только создатель)
  до аппрува. В Маркете/ленте фильтр `moderation_status='approved'`.
- Лента модерации: `GET /admin/records/pending/` (переиспользуем существующую
  admin-инфру, если есть; иначе флаг `is_staff` на user).
- Аппрув → `approved`, запись становится общей.
- **rematch** (еженедельный джоб, как у store-native): ищет аппрувнутые
  user-records в Discogs → пишет `discogs_id_candidate`, при ≥2 confirmations
  авто-merge через `merged_into_id`. Код джоба уже существует для store —
  расширяем фильтр `source IN ('store','user')`.

---

## 7. UI — экран скана (`Mobile/app/(tabs)/index.tsx`, `ScannerScreen`)

1. После неудачного скана (barcode+фото пусто) — кнопка снизу
   **«Добавить вручную»**.
2. Визард (новый экран `Mobile/app/record/manual.tsx`):
   - шаг 1: фото обложки (обяз.) + спайн/задник (опц.)
   - шаг 2: ввод «артист — альбом» → `spotify-search` → выбор кандидата →
     автозаполнение треклиста/года/артиста
   - шаг 3: ручные поля (label, catalog №, country, format)
   - submit → `preflight` → при чистом результате `POST /records/user/`
3. При `DUPLICATE`/`FOUND_IN_DISCOGS` — показываем найденную, предлагаем её.

Store: расширить `useScannerStore` методами `preflight`, `spotifySearch`,
`createUserRecord`. Типы: `ScanMode` уже есть; добавить `UserRecordDraft`,
`SpotifyAlbumCandidate` в `lib/types.ts`.

---

## 8. Порядок работ

1. Миграция (поля §1).
2. `services/spotify.py` + env + config.
3. `services/user_record.py::preflight_dedup` (обёртка над listing_matcher).
4. API §4 + guard §5.
5. UI визард §7.
6. Модерация §6 (admin-лента + фильтры видимости).
7. Расширить rematch-джоб на `source='user'`.

Шаги 1–5 = MVP в прод. 6–7 = полный скоуп (общий пул).
