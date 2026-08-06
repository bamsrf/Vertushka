# Discogs Data Dumps — план для независимости от API

> Обзор операционки парсинга — в [PARSING.md](PARSING.md).
> План верхнего уровня (магазины, аффилиаты) — в [SHOPS_PARSING.md](SHOPS_PARSING.md).

## Context — зачем

Сейчас наш matcher для создания новой `records` (когда юзер кликает на пластинку, или когда парсер магазина приносит новый листинг с barcode которого ещё нет в нашей БД) **дёргает Discogs API** через `_try_discogs_fetch` / `_try_discogs_fetch_by_text`. Это создаёт **два бутылочных горлышка**:

1. **Rate limit Discogs API**: 60 req/min на токен. Жёсткий лимит, заплатить за повышение нельзя — Discogs не продаёт premium tier.
2. **Latency**: ~300-500 мс на запрос. При активном backfill 10к листингов один matcher batch занимает часы.

В стационаре после первоначального импорта (когда у нас в магазинах ~100к листингов, и большинство уже сматчены) проблема снижается. Но **на каждом новом магазине** или при перепарсинге у нас всплеск Discogs-запросов.

**Решение**: Discogs официально публикует **полные дампы базы данных** на S3. Если их распарсить и держать **local mirror** таблицы `records` — matcher работает **полностью локально**, без сети, без лимитов. На каждое обновление магазина (10к-100к листингов) — мгновенный матчинг через INDEX lookup по barcode.

---

## 1. Что есть в дампах

Discogs выкладывает 4 типа дампов **каждый месяц 1-го числа** на публичный S3:

```
https://data.discogs.com/?prefix=data/{YEAR}/
```

> ⚠️ **Прямой S3-бакет мёртв (проверено 2026-08-06).**
> `discogs-data-dumps.s3.us-west-2.amazonaws.com` отдаёт `403 AccessDenied` на
> всё, включая `index.html` и старые файлы. Единственная рабочая точка входа —
> `data.discogs.com`, ссылка на файл выглядит так:
> `https://data.discogs.com/?download=data%2F2026%2Fdiscogs_20260801_releases.xml.gz`
>
> **Качать с прода нельзя.** Cloudflare встречает IP дата-центра
> JS-челленджем: `curl` получает 403 и HTML. Дамп качается на машине с
> «обычным» IP, на прод уезжает только CSV.gz — см.
> `scripts/refresh_discogs_dump.sh`.
>
> **Докачки нет.** На `Range: bytes=1000000-1000999` сервер отвечает `200` с
> `content-length: 11200898615` и начинает лить файл сначала — `curl -C -`
> бесполезен, обрыв означает старт заново.
>
> **Обрывы — норма.** 11.2 ГБ одним потоком: наблюдались `rc=92` (HTTP/2 stream
> INTERNAL_ERROR у Cloudflare на ~5 ГБ), `rc=28` (просадка скорости), `rc=56`
> сразу после оборванной попытки (похоже на троттлинг). Лечится `--http1.1`,
> мягким `--speed-time 300` и паузой между заходами — всё это уже в
> `refresh_discogs_dump.sh`.
>
> **Проверять sha256 обязательно.** `HEAD` не отдаёт `Content-Length` (только
> `GET`), и при обрыве curl раньше завершался с кодом 0: первая загрузка дала
> 7.29 ГБ вместо 11.2, «успешно». Эталон — `discogs_YYYYMMDD_CHECKSUM.txt`
> рядом с дампом.

| Файл | Содержит | Размер сжатый | Разжатый |
|---|---|---|---|
| `discogs_YYYYMMDD_releases.xml.gz` | Все releases (пресс/издание) — главное что нам нужно | ~10.4 ГБ | ~50 ГБ |
| `discogs_YYYYMMDD_masters.xml.gz` | Master-releases (объединяют все версии одного альбома) | ~593 МБ | ~3 ГБ |
| `discogs_YYYYMMDD_artists.xml.gz` | Артисты | ~472 МБ | ~1.5 ГБ |
| `discogs_YYYYMMDD_labels.xml.gz` | Лейблы | ~86 МБ | ~250 МБ |

Формат: **XML** (один большой файл на 17-18 млн элементов). Поддерживает stream-парсинг через `lxml.etree.iterparse` — без загрузки всего в память.

### Что мы берём из releases

Каждый `<release>` содержит:
- `@id` → `discogs_id`
- `master_id` → `discogs_master_id`
- `<title>` → название альбома
- `<artists>/<artist>/<name>` → артист
- `<released>` (YYYY-MM-DD) → год
- `<country>` → страна издания
- `<labels>/<label>/@catno` → каталожный номер ⭐ важно для матчинга
- `<identifiers>/<identifier @type="Barcode">` → EAN-13/UPC ⭐ важно для матчинга
- `<formats>/<format @name="Vinyl|CD|Cassette|Box Set">` → формат
- `<images>/<image @type="primary" @uri>` → URL обложки
- `<genres>/<genre>`, `<styles>/<style>` → жанры/стили

**Чего НЕ берём** (раздуло бы БД на ×3-5):
- `<tracklist>` — мы тянем по требованию из API когда юзер открывает запись
- `<videos>`, `<companies>`, `<extraartists>` — не нужно для матчинга/карусели

---

## 2. Покрытие форматов — ВСЕ носители, не только vinyl

Магазины торгуют разными носителями (LP, CD, кассеты, бокс-сеты, картриджи). Нам нужно матчить все, чтобы:
- Карусель «В наличии сейчас» показывала **то что юзер хочет** (винил или CD-коллекционер)
- Поиск по сканер штрихкода работал для любого носителя

Поэтому при импорте dump **фильтруем не по формату**, а **по существованию `<format>`** (исключаем `release` без формата — это битые данные).

| `<format @name>` (Discogs) | Наш `format_type` | Парсить |
|---|---|---|
| `Vinyl` | `LP` или `7"` (по `<format @qty>` и `<format/descriptions>`) | ✅ |
| `CD` | `CD` | ✅ |
| `Cassette` | `Cassette` | ✅ |
| `Box Set` (как контейнер) | `Box Set` | ✅ |
| `File` (digital) | `File` | ✅ (для completeness, но скорее всего не появится в магазинах) |
| `Hybrid` | `Hybrid` (SACD/CD) | ✅ |
| `Reel-To-Reel`, `8-Track`, `DAT`, `MiniDisc` | как есть | ✅ (на случай редких releases) |

**Расчёт**: на 18 млн releases в полной базе разбивка примерно:
- Vinyl: ~5-7 млн
- CD: ~7-8 млн
- Cassette: ~1.5-2 млн
- Box Set / прочее: ~1 млн

Итого **~15-17 млн нужных записей**. Если фильтровать только Vinyl — теряем ~60% полезных данных для магазинов где есть CD/Cassette.

---

## 3. Архитектура импорта

```
            ┌──────────────────────────┐
            │  Discogs S3 dump (XML.gz)│  ~5 ГБ download раз в месяц
            └──────────┬───────────────┘
                       │ stream download
                       ▼
            ┌──────────────────────────┐
            │  lxml.etree.iterparse    │  stream parse XML (no full load)
            │  + tag='release'         │
            └──────────┬───────────────┘
                       │ для каждого release:
                       ▼
            ┌──────────────────────────┐
            │  to_record(release)      │  extract нужные поля
            └──────────┬───────────────┘
                       │ batch 1000
                       ▼
            ┌──────────────────────────┐
            │  PG COPY FROM STDIN      │  bulk insert ON CONFLICT
            │  ON CONFLICT(discogs_id) │  DO UPDATE для месячных дельт
            │  DO UPDATE               │
            └──────────────────────────┘
```

**Поэтапно**:

### Phase 0 — Foundation (1 день)

1. CLI `python -m app.scripts.import_discogs_dump --type=releases --file=...`
2. Скачивание: `aria2c` или `httpx.stream()` с прогресс-баром
3. Декомпрессия: `gzip.open(stream)` — не разжимать на диск
4. Парсер: `lxml.etree.iterparse(stream, events=('end',), tag='release')` + `elem.clear()` после обработки (память константа ~200 МБ)
5. Маппинг XML → dict (`to_record_dict()`)
6. Batch UPSERT в `records` через `INSERT ... ON CONFLICT (discogs_id) DO UPDATE`

### Phase 1 — Первый full import (1 день)

1. Скачать последний дамп `releases` (~5 ГБ)
2. Запустить import — пишет в БД через batch 1000
3. **Время**: ~3-6 часов на 18 млн записей (зависит от disk I/O)
4. **Результат**: ~3-5 ГБ в таблице `records` (только нужные поля)

### Phase 2 — Monthly refresh (cron)

1. Cron 1-го числа в 04:00: cкачать новый dump
2. Сравнить с предыдущим (по дате в filename) — обработать **только новые** records (Discogs выпускает delta-сравнение)
3. На месяц ~50-100к новых releases → импорт ~30-60 мин
4. Идемпотентность: `ON CONFLICT DO UPDATE` на случай если запись изменилась

### Phase 3 — Снос зависимости от on-demand API

После Phase 1+2:
- `listing_matcher._try_discogs_fetch` (шаг 5 каскада) → **отключить** (или оставить как ultimate fallback на случай новейших releases которые ещё не в dump)
- `_try_discogs_fetch_by_text` (шаг 5b) → можно оставить как fallback, но в большинстве случаев barcode/catalog в dump уже есть
- `DISCOGS_FETCH_HOURLY_LIMIT` опустить до 50 (только для live-поиска юзера)

---

## 4. Storage — что в БД

```sql
-- Schema records уже есть (см. Backend/app/models/record.py).
-- Импорт не требует миграций, только добавление строк.

ALTER TABLE records
    ADD COLUMN IF NOT EXISTS imported_from_dump_date date;
-- Полезно для дебага: знать что эта запись из импорта vs от юзера/API

CREATE INDEX IF NOT EXISTS ix_records_barcode_when_set ON records (barcode)
    WHERE barcode IS NOT NULL;
-- Частичный индекс — для быстрого поиска при матчинге (только записи с barcode)
```

| Что | Размер |
|---|---|
| `records` после full import | ~15 млн строк × ~200 байт = **~3 ГБ** |
| Индексы (`discogs_id` unique, `barcode` partial, `master_id`, `title` pg_trgm) | ~1.5 ГБ |
| **Итого + текущая БД (~30 МБ)** | **~5 ГБ** |

Сервер `85.198.85.12` сейчас имеет PG 16 на отдельном volume. Запас на десятки ГБ. Стоит проверить `df -h` на проде перед импортом.

---

## 5. Риски и сложности

### A. Размер дампа (5 ГБ download → 25 ГБ XML)

- **Риск**: исчерпание места на сервере. PG datafiles + temp files на парсинге.
- **Митигация**:
  - Не разжимать на диск — стримить из gzip напрямую в iterparse
  - Удалять старые дампы после обработки
  - Перед запуском: `df -h /var/lib/postgresql` → нужно ≥10 ГБ свободного

### B. Производительность импорта

- **Риск**: 18 млн INSERT'ов = часы. Если делать построчно — дни.
- **Митигация**:
  - Batch 1000 через `INSERT ... VALUES (...), (...), ...` или `COPY FROM STDIN` (быстрее в 10×)
  - Отключить триггеры на время импорта (`SET session_replication_role = replica`)
  - Drop+recreate индексы после массового импорта (быстрее чем поддерживать на insert)
  - Использовать `UNLOGGED` table → потом `ALTER TABLE SET LOGGED` (рискованно при crash, но дешевле)

### C. Совместимость схемы

- **Риск**: наша `records` таблица сейчас допускает `discogs_id NULL` (для записей которые юзер создал вручную). Импорт всегда даёт `discogs_id NOT NULL`. UNIQUE INDEX на `discogs_id` есть — конфликты по UPSERT отработают.
- **Митигация**: проверить тип всех полей (string vs int), nullable, длина (varchar limits).

### D. Изменение схемы XML между месяцами

- **Риск**: Discogs обновляет формат XML (редко, но было в 2019, 2022). Поломает парсер.
- **Митигация**:
  - Schema-version regex в filename
  - Smoke-test: после импорта проверить случайные 10 записей через API — совпадают ли поля
  - Fallback: оставить on-demand fetch для тех записей где импорт упал

### E. Свежесть данных (delay месяц)

- **Риск**: Discogs dump — snapshot 1-го числа. Если 15-го числа на Discogs появилась новая запись (юзер создал) — мы её не увидим до следующего dump через 2 недели.
- **Митигация**: оставить on-demand fetch (`_try_discogs_fetch`) **как fallback** — если record по `discogs_id` не нашёлся → пробуем API. Это редкий путь после Phase 1.

### F. Покрытие форматов — Vinyl vs CD vs Cassette

- **Риск**: если случайно фильтрнём `format='Vinyl'` при импорте — потеряем 60% полезных данных. У магазинов есть CD, кассеты, боксы.
- **Митигация**:
  - Импортировать **все форматы** (без фильтра по `<format>`)
  - Хранить `format_type` как пришло из dump (например, «LP», «12"», «CD», «Cassette», «Box Set»)
  - В matcher не фильтровать по формату при поиске barcode (один barcode = один конкретный formate, и так совпадёт)
  - **Исключение**: можно отбросить очень редкие как `8-Track`, `DAT` если совсем хочется экономить место (~100к записей)

### G. Лицензия и юр.риск

- **Информация**: Discogs Data Dumps под лицензией [CC0 Public Domain](https://www.discogs.com/developers/#page:database-download). Можно использовать в любых целях коммерчески.
- **Атрибуция**: не требуется, но **рекомендуется** добавить «Powered by Discogs» в Mobile UI (мы и так это собираемся показывать в `OffersBlock`).

### H. Обновление = пересчёт matcher на старых unmatched

- **Риск**: после Phase 1 у нас в БД могут быть unmatched листинги которые **до** импорта матчер не нашёл. После импорта records гораздо больше — нужно перепрогнать matcher на всё.
- **Митигация**:
  - Один раз после Phase 1: `python -m app.scripts.scrape_all --match-only --batch=10000`
  - 10к листингов × ~50мс на матч = ~10 минут (in-memory lookup быстрее API)

### I. Memory pressure при парсинге

- **Риск**: `lxml.etree.iterparse` может накапливать память если не звать `elem.clear()` и не удалять предков.
- **Митигация**: классический паттерн:
  ```python
  for event, elem in iterparse(stream, events=('end',), tag='release'):
      yield to_record_dict(elem)
      elem.clear()
      while elem.getprevious() is not None:
          del elem.getparent()[0]
  ```
- Контролируем через `psutil.Process().memory_info().rss` — должно быть стабильно ~200 МБ.

---

## 6. Поэтапный план реализации

| Phase | Что | Время |
|---|---|---|
| **Phase 0 — Foundation** | CLI скелет, скачивание, stream-парсер, dry-run на 100 records | 1 день |
| **Phase 1 — First import** | Полный импорт actual dump (~18 млн records). Verify counts | 6-8 часов (включая monitoring) |
| **Phase 2 — Cron monthly** | Cron 1-го числа: download → diff → batch update | 1 день |
| **Phase 3 — Snose on-demand** | Удалить/ослабить `_try_discogs_fetch` пути в matcher | 1 час |
| **Phase 4 (опц)** — Master & Artist import | Дамп `masters.xml` (для alt-version detection) + `artists.xml` (для thumbs) | 2 дня |

**Суммарно**: ~1 неделя инженерной работы. Окупаемость: навсегда отвязаны от Discogs API на массовом матчинге.

---

## 7. Файлы (плановые)

```
Backend/
├── app/
│   ├── scripts/
│   │   └── import_discogs_dump.py        ← новый CLI
│   ├── services/
│   │   └── discogs_dump/                  ← новый модуль
│   │       ├── __init__.py
│   │       ├── downloader.py              ← S3 download + gzip stream
│   │       ├── parser.py                  ← lxml iterparse → dict generator
│   │       ├── importer.py                ← batch UPSERT в records
│   │       └── refresh.py                 ← month delta-обновление
│   ├── tasks/
│   │   └── discogs_dump_tasks.py          ← cron: monthly_dump_refresh
│   └── alembic/versions/
│       └── YYYY_add_records_imported_from.py  ← добавление imported_from_dump_date
└── tests/
    └── discogs_dump/
        ├── fixtures/
        │   └── sample_release.xml         ← один реальный <release> для unit-теста
        └── test_parser.py
```

---

## 8. Verification

После Phase 1:

1. **Count check**: `SELECT count(*) FROM records WHERE imported_from_dump_date IS NOT NULL` — должно быть ~15-18 млн
2. **Barcode coverage**: `SELECT count(*) FROM records WHERE barcode IS NOT NULL` — обычно ~70% records имеют barcode
3. **Format распределение**: `SELECT format_type, count(*) FROM records GROUP BY format_type ORDER BY 2 DESC LIMIT 20` — должны быть LP/CD/Cassette/Box Set в топе
4. **Live matcher test**: перепрогнать `--match-only --batch=10000` на текущих unmatched. Coverage **должен подскочить с ~5% до 70-90%**.
5. **Sample queries**:
   - Поиск «Khruangbin Mordechai» через `/api/records/search` — должны быть все 5+ пресов
   - Поиск по barcode `0656605149318` (например, Khruangbin Mordechai пресс 2020) — должна найтись запись с правильным master_id

После Phase 3:

- Mobile-карусель «В наличии сейчас» имеет ≥100 листингов
- Запросы в Discogs API через `_try_discogs_fetch` идут **только при поиске юзером** (нечасто)
- Cron `hourly_match_unmatched` отрабатывает за **секунды** (lookup из local records, без сети)

---

## 9. Альтернатива — гибридный режим (если не хотим импортить всё)

Можно держать **только subset** dump: только записи **с barcode** (~70% от 18 млн = ~12 млн). Это снизит storage с 5 ГБ до ~3.5 ГБ и сохранит 90% полезности (matcher идёт по barcode в первую очередь).

Или: **only popular** — фильтровать по `have_count > N` (популярность). На записях которые никто не имеет вряд ли будут листинги в наших магазинах. Так можно ужать до 5-7 млн самых ходовых записей (~1.5 ГБ).

---

## 10. Обновление индекса — раз в 2 месяца

`scripts/refresh_discogs_dump.sh` — полный цикл одной командой. **Запускать на
своей машине, не на проде** (Cloudflare, см. предупреждение в §2).

```bash
scripts/refresh_discogs_dump.sh          # найдёт свежий дамп, скачает, зальёт
KEEP_DUMP=1 scripts/refresh_discogs_dump.sh   # не удалять 10 ГБ после прогона
DUMP_DATE=20260701 scripts/refresh_discogs_dump.sh
```

Что происходит:

| Шаг | Скрипт | Время |
|---|---|---|
| Скачать releases-дамп | `curl` | ~40 мин |
| Извлечь полные описания формата + новинки | `app.scripts.extract_release_formats` | ~15 мин |
| Залить описания в `discogs_release_formats` | `app.scripts.load_release_formats` | ~10 мин |
| Вставить новые релизы в индекс | `app.scripts.load_new_releases` | ~2 мин |
| Сбросить `artist_masters:*` в Redis | — | сек |

**Почему раз в 2 месяца:** дамп выходит ~1-го числа, дельта за месяц мелкая, а
каждый прогон — 10 ГБ трафика и час времени. Реже — новинки заметно отстают.

> ⚠️ **Репозиторий обязан лежать вне `Desktop`, `Documents` и `Downloads`.**
> macOS TCC запрещает фоновым процессам читать эти папки. Проверено 2026-08-06:
> у задачи launchd `stat` каталога проходит, а листинг, чтение файла и запуск
> скрипта — отказ, причём даже когда сам скрипт лежит в `~/`, то есть тонкой
> обёрткой не обойтись. Поэтому репо переехало `~/Desktop/Cursor` → `~/Cursor`,
> а на рабочем столе оставлен симлинк — внешне ничего не изменилось.
> Альтернатива — выдать Full Disk Access для `/bin/bash`, но это открывает
> Desktop любому фоновому скрипту на машине.

Автозапуск — `scripts/ru.vertushka.discogs-refresh.plist` (launchd, нечётные
месяцы, 5-е число, 03:20; если Mac спит — отработает при пробуждении):

```bash
cp scripts/ru.vertushka.discogs-refresh.plist ~/Library/LaunchAgents/
sed -i '' "s|__REPO__|$PWD|g" ~/Library/LaunchAgents/ru.vertushka.discogs-refresh.plist
launchctl load ~/Library/LaunchAgents/ru.vertushka.discogs-refresh.plist
```

Лог — `/tmp/vertushka-discogs-refresh.log`. Ручной прогон:
`launchctl start ru.vertushka.discogs-refresh`.

**Почему две таблицы, а не UPDATE.** `discogs_releases_index` — 13.1M строк,
heap 2.95 ГБ; UPDATE переписал бы весь heap и до VACUUM удвоил его, а на проде
свободно ~4 ГБ. Полные описания живут в отдельной `discogs_release_formats`
(только релизы с ≥2 описаниями, ~60% дампа), запрос дискографии берёт
`COALESCE(f.format_full, i.format_type)`.

**Новинки определяются по `discogs_id > max(id в индексе)`** — id Discogs
инкрементальны. Строки везут `artist_ids` и `is_unofficial` в той же CSV: без
первого релиз не виден на экране артиста (фильтр по GIN `artist_ids`), без
второго дискография тонет в бутлегах.

---

## 11. ⚠️ Индекс покрывает только 2/3 дампа

Замерено 2026-08-06: в `discogs_releases_index` **13.12M** строк, в дампе
2026-08-01 — **19.34M** релизов. Выборка каждого 1000-го id из дампа: в индексе
нашлось **66.8%**. Не хватает ~6.4M релизов, и пропуски размазаны по всему
диапазону id, а не отрезаны хвостом.

**Вероятная причина** — баг в `ingest_discogs_dump._copy_batch` под флагом
`--skip-existing`: staging-таблица создавалась с `ON COMMIT DELETE ROWS`, а
asyncpg работает в автокоммите, поэтому COPY коммитился сам и чистил staging
ДО того, как отработает `INSERT ... SELECT`. Ветка молча вставляла ноль строк и
рапортовала об успехе. Если первичный ingest прерывали и возобновляли с этим
флагом — всё после точки возобновления не записалось. Баг исправлен
2026-08-06 (явный `TRUNCATE _stage` вместо `ON COMMIT`), но данные сами собой
не появятся.

**Что это ломает:** matcher не найдёт локально треть релизов и уйдёт в Discogs
API; дискография артиста неполна; поиск не видит эти релизы.

**Чего НЕ чинит дельта-обновление:** `--since-id` берёт только id выше
максимума в индексе — это новинки, а не пропуски в середине. Закрыть разрыв
можно только анти-джойном всего дампа против индекса.

**Почему не сделано сразу:** +6.4M строк это ~2 ГБ вместе с семью индексами
таблицы, а на проде свободно 2.7 ГБ (91% занято). Сначала нужно место.

---

## 12. Связанные документы

- [PARSING.md](PARSING.md) — текущая операционка
- [SHOPS_PARSING.md](SHOPS_PARSING.md) — план магазинов
- [OFFERS_UX.md](OFFERS_UX.md) — UI карусели/Hot Stock
- [artist_page_and_filters.md](artist_page_and_filters.md) — классификация типа релиза, ради которой нужны полные описания
- Discogs Developers: https://www.discogs.com/developers/#page:database-download
- Discogs Data Dumps: https://data.discogs.com/
