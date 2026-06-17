# User-Submitted Records (`source='user'`)

> Статус: **SHIPPED (full)** · Создан 2026-06-04 · Обновлён 2026-06-17
> (§6 clean-up + §9 мульти-формат + §10 friendly-перехват + §11 edit — done)
> Кейс: релиз, которого нет ни в Discogs (баркод/фото), ни в Маркете.
> Решение продукта: юзер добавляет вручную, запись **сразу попадает в его
> коллекцию** после дабл-чека на отсутствие в Discogs + Маркете. Enrichment из Spotify.

## Что сделано (бэкенд + фронт)

- ✅ §1 Миграция: `records.created_by_user_id / moderation_status /
  spotify_album_id / user_submitted_data` + индекс `(source,moderation_status)`;
  `users.is_staff`. Чейн `discogs_login → token_version → user_records`.
- ✅ §2 `services/user_record.py::preflight_dedup` (barcode→catalog→fuzzy→Discogs).
- ✅ §3 `services/spotify.py` (Client Credentials, no-op без кредов; креды НЕ
  настроены — enrichment молчит, ручной ввод работает).
- ✅ §4 API: `POST /records/preflight/`, `GET /records/spotify-search/`,
  `POST /records/user/`. + `cover_storage.store_user_cover`.
- ✅ §5 Guards collections/wishlists: whitelist `('discogs','user')`.
- ✅ §7 rematch расширен на approved user-records (merge → `moderation_status='merged'`).
- ✅ UI: `record/manual.tsx` визард + `ManualAddVinylToggle` (floating винил-тоггл
  на сканере, slide-to-open, рандом-цвет). PR #53 + manual-add-toggle PR — merged.
- ✅ Прод: миграция накатана, фича живая.

## ⚠️ Изменения решения (2026-06-17)

1. **Модерация выключена. Админки нет.** Владелец не сможет вручную
   модерировать все релизы. User-record **сразу общий / растёт в коллекцию** —
   без `pending`-гейта. См. §6 (revised).
2. **Мульти-формат.** Не только винил: добавляем **CD и кассеты**. См. §9 (new).

## TL;DR архитектуры

`records.source` имеет `discogs`, `store`, `user`. Дедуп/дабл-чек →
переиспользуем `services/listing_matcher.py`; авто-merge в Discogs позже →
`discogs_id_candidate` + `confirmations` + `merged_into_id`.

Новой таблицы НЕТ. User-record — это `Record` с `source='user'`,
`created_by_user_id`, `format_type` (vinyl/cd/cassette).

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

## 6. Модерация — ОТМЕНЕНА (revised 2026-06-17)

**Решение: модерации нет, админки нет.** Владелец не будет руками проверять
релизы. User-record сразу «прорастает» в коллекцию создателя и в общий пул.

Что меняем относительно текущего кода (был `pending`-гейт):
- `create_user_record` ставит `moderation_status='approved'` (не `pending`).
- Снять visibility-гейты `pending` в `get_record` и публичном профиле
  (`_is_publicly_visible` / `_PUBLIC_VISIBLE_CLAUSE`) — user-records видны всем.
- `app/api/admin.py` (лента/approve/reject) и `users.is_staff` — **больше не
  нужны** для этого флоу. Можно оставить «спящими» (вреда нет) или удалить
  в отдельном clean-up. Поле `moderation_status` оставляем (нужно для
  `merged` из rematch + на будущее, если вернём ручную модерацию).
- **rematch** по-прежнему ищет user-records в Discogs → `discogs_id_candidate`,
  при ≥2 confirmations авто-merge → `merged_into_id` + `moderation_status='merged'`.
  Фильтр меняем на `source IN ('store','user')` БЕЗ условия `approved`
  (все user-records теперь approved по умолчанию).

Анти-спам/качество без модерации (бэклог): дедуп уже отсекает дубли; при росте
мусора — лёгкие сигналы (rate-limit на создание, флаг-репорт от юзеров,
авто-скрытие при N репортах). Не сейчас.

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

1. ✅ Миграция (поля §1).
2. ✅ `services/spotify.py` + env + config.
3. ✅ `services/user_record.py::preflight_dedup`.
4. ✅ API §4 + guard §5.
5. ✅ UI визард §7 + `ManualAddVinylToggle`.
6. ✅ Модерация §6 — **отменена**. Clean-up сделан: `create_user_record` →
   `approved`, pending-гейт в `get_record` убран, data-миграция
   `20260617_approve_user_records` для старых pending-строк.
7. ✅ Расширить rematch-джоб на `source='user'`.
8. ✅ §9 мульти-формат, §10 friendly-перехват дубля, §11 редактирование.

MVP в проде. Все §6/§9/§10/§11 реализованы — осталось задеплоить + Spotify-креды.

---

## 9. Мульти-формат: выбор формата в форме (new 2026-06-17)

Поддерживаем **vinyl / CD / cassette** на уровне ДАННЫХ и ФОРМЫ. Отдельных
визуалов носителя НЕ делаем — винил остаётся единой точкой входа и бренд-объектом.

- **Точка входа** — `ManualAddVinylToggle` (винил), без изменений.
- **Визард** (`record/manual.tsx`): добавить **выбор формата** `Винил | CD | Кассета`
  (сегмент), нормализуем в `format_type` (`vinyl`/`cd`/`cassette`). Тексты убрать
  винил-центричные: не «добавить винил», а «добавить пластинку/релиз».
- **Карточка** созданной записи: формат показывается текстом (`format_type`),
  кастомного арта под CD/кассету НЕ рисуем (пока).
- **Дедуп**: `listing_matcher` уже format-aware (`_format_family`,
  `FORMAT_MISMATCH_PENALTY`). Прокинуть `format_type` из визарда в
  `preflight_dedup` (сейчас не передаётся), чтобы fuzzy не путал носители.

Объём: бэкенд — 1 параметр в preflight; фронт — сегмент формата + правка текстов.

---

## 10. Дедуп при добавлении → «уже есть, добавим к нему» (new 2026-06-17)

Сейчас preflight на `DUPLICATE`/`LIKELY_DUPLICATE`/`FOUND_IN_DISCOGS` просто
блокирует (409 / тост). Меняем на дружелюбный перехват:

- Юзер заполняет визард → submit → `preflight`.
- Если найден существующий релиз (наш `Record` или Discogs):
  «**Чел, такой релиз уже есть — вот он**» → показать карточку найденного →
  кнопка **«Добавить в коллекцию»**.
- Тап → добавляем НАЙДЕННУЮ запись в коллекцию (не создаём дубль `source='user'`).
  - наш `Record` → обычный add-to-collection по `record_id`.
  - Discogs (`FOUND_IN_DISCOGS`) → add по `discogs_id` (как из поиска).
- `LIKELY_DUPLICATE` (fuzzy) — мягко: «возможно это оно» + обе опции
  («добавить найденное» / «всё равно создать своё»).

Бэкенд готов (preflight уже возвращает `match`/`discogs_id`). Работа — на фронте:
экран-перехват в визарде + ветка add-to-collection вместо create.

---

## 11. Редактирование user-records (new 2026-06-17)

Сейчас добавленную запись нельзя отредактировать. Добавляем edit (только для
`source='user'` и только создателю — `created_by_user_id == me`).

### 11.1 Бэкенд
- `PATCH /records/user/{id}` — поля artist/title/year/label/catalog/country/
  format_type/tracklist/cover. Guard: `source=='user'` И `created_by_user_id==me`
  (иначе 403). Discogs/store записи — не редактируются.

### 11.2 Точки входа (UI)
1. **Карточка версии релиза** → меню «3 точки» → пункт **«Отредактировать»** с
   иконкой-карандашом. Виден только если запись `source=='user'` и юзер — автор.
2. **Настройки профиля** → как только добавлен ПЕРВЫЙ ручной релиз, появляется
   строка-раздел «своя коллекция вручную» (управление своими добавленными).

### 11.3 Название раздела профиля — варианты (выбрать)
- **«Мои релизы»** — ёмко, нейтрально к формату. *(рекоменд.)*
- «Добавленные вручную» — точно по смыслу, длиннее.
- «Моя картотека» — образно, бренд-нотка.
- «Свои пластинки» — но мы уходим от винил-центричности (есть CD/кассеты).

### 11.4 Иконка — варианты
- **карандаш-на-пластинке / винил + pencil** — связь «своё + правка» *(рекоменд.)*
- `square.and.pencil` (iOS-метафора «список+правка»)
- `pencil-simple` (нейтральная правка)
- винил с плюсом (вход в добавление, но это скорее про create)

Решение по названию+иконке — за продуктом; дефолт: «Мои релизы» + винил-карандаш.
