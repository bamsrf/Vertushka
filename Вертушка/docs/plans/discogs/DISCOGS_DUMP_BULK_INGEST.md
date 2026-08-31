# Discogs Data Dump — Bulk Ingest для матчера

> **Цель:** один раз загрузить дамп Discogs Releases (~30M записей) в локальный
> поисковый индекс, чтобы matcher магазинных листингов работал **без обращения
> к Discogs API** для подавляющего большинства релизов. Это поднимет покрытие
> матчинга с текущих **27.6%** до **80-90%+** без упирания в Discogs rate-limit.

**Owner:** backend
**Estimate:** 1-2 дня кода + 4-8 часов разового ingest'а на проде
**Зависимости:** PostgreSQL ≥14, `lxml`, ~40 GB свободного места на сервере (временно)

---

## 1. Контекст и проблема

### Что сейчас (state 2026-05-20)

| Магазин | In-stock listings | Матчено | Покрытие |
|---|---|---|---|
| Korobka Vinyla | 650 | 545 | **84%** ✓ |
| Vinyl.ru | 996 | 9 | **0.9%** ❌ |
| Stoprobot Vinyl | 606 | 66 | **11%** ⚠️ |
| Plastinka.com | 3 | 2 | 67% |
| **ИТОГО** | **2 255** | **622** | **27.6%** |

**Почему Korobka хорошо матчится:** их парсер достаёт `discogs_id` прямо
со страницы товара (магазин ссылается на Discogs). Match instant + 100%.

**Почему остальные плохо:** у них на странице нет `discogs_id` — только
`barcode`, `catalog_number`, `artist+title`. Текущий `listing_matcher.py`
ищет в нашей БД по этим ключам, но т.к. БД заполняется только теми
записями, что юзеры открывали, **большинство barcode'ов из новых
магазинов не находят соответствия локально**. Падают на **on-demand
Discogs search** (`/database/search?barcode=...`) который limited
60 req/min — за batch 500 листингов матчится 5-15 штук.

### Discogs API лимиты (текущие узкие места)

- **60 запросов/минуту** общий лимит на authenticated client
- При burst → 429 + `Retry-After: 2s`, на практике matcher простаивает 80%+ времени
- Hourly cap matcher'а 500 req — мы упираемся за 8-10 минут active'а
- За batch 500 unmatched ≈ 7 минут работы → 7-15 матчей. Чтобы домотать
  vinyl_ru (987 unmatched), нужно ~70 batch'ей = **дни активной работы**

### Решение

Скачать **Discogs Data Dump** один раз → положить в локальную таблицу
с индексами по barcode/catalog/artist+title. Matcher проверяет локальный
индекс ПЕРЕД походом в Discogs API. Discogs API остаётся как fallback
для релизов, вышедших после даты дампа.

---

## 2. Что такое Discogs Data Dumps

- **Источник:** [discogs.com/data](https://www.discogs.com/data/)
- **Bucket:** `s3://discogs-data-dumps/data/{YEAR}/discogs_{YYYYMMDD}_releases.xml.gz`
- **Лицензия:** Creative Commons Zero — можно использовать
  коммерчески, требует только указать источник
- **Релиз-каденс:** обычно ~1 числа каждого месяца
- **Размер:** releases-дамп ~7-8 GB сжатый, ~30-35 GB развёрнутый
- **Содержит:** все releases (конкретные прессинги). НЕ masters, НЕ artists,
  НЕ labels — это отдельные дампы, нам они не нужны
- **Формат:** XML с примерно такой структурой:

```xml
<releases>
  <release id="12345" status="Accepted">
    <master_id is_main_release="true">789</master_id>
    <artists>
      <artist>
        <id>456</id>
        <name>Twenty One Pilots</name>
      </artist>
    </artists>
    <title>Blurryface Live</title>
    <country>US</country>
    <released>2022</released>
    <labels>
      <label name="Fueled By Ramen" catno="FBR-XXX" />
    </labels>
    <formats>
      <format name="Vinyl" qty="2" text="">
        <descriptions>
          <description>LP</description>
        </descriptions>
      </format>
    </formats>
    <identifiers>
      <identifier type="Barcode" value="075678657238" />
    </identifiers>
    <images>
      <image type="primary" uri150="https://..." uri="https://..." />
    </images>
    <tracklist>
      <track><position>A1</position><title>Heavydirtysoul</title><duration>4:09</duration></track>
      <!-- ... -->
    </tracklist>
  </release>
  <!-- ~30M записей -->
</releases>
```

---

## 3. Архитектура решения

### 3.1 Новая таблица `discogs_releases_index`

**Отдельная** от `records`! Это **поисковый индекс**, не каталог пользовательский.
`records` остаётся «обогащённой» таблицей с tracklist, ценами, artist-thumb'ами,
заполняется по запросу при первом visit'е.

```sql
CREATE TABLE discogs_releases_index (
    discogs_id        BIGINT      PRIMARY KEY,
    master_id         BIGINT,

    artist            TEXT        NOT NULL,
    title             TEXT        NOT NULL,
    year              SMALLINT,
    country           TEXT,
    format_type       TEXT,       -- "Vinyl, LP" / "CD" / "Cassette" — derived
    label             TEXT,        -- первый label из дампа

    -- normalized для матчинга
    barcode_norm      TEXT,        -- digits only, lowercase
    catalog_norm      TEXT,        -- uppercase, no spaces/dashes

    -- для UI fallback (если Record не enriched ещё)
    cover_image_url   TEXT,        -- uri из <images type=primary>

    -- минимальный raw для быстрого create-record без Discogs API
    -- содержит tracklist, vinyl_color_raw, всё ценное
    raw_payload       JSONB
);

-- Индексы для матчинга
CREATE INDEX ix_dri_barcode
    ON discogs_releases_index(barcode_norm)
    WHERE barcode_norm IS NOT NULL;

CREATE INDEX ix_dri_catalog
    ON discogs_releases_index(catalog_norm)
    WHERE catalog_norm IS NOT NULL;

-- Fuzzy artist+title через pg_trgm (уже включен в проекте для других вещей)
CREATE INDEX ix_dri_artist_trgm
    ON discogs_releases_index USING GIN (artist gin_trgm_ops);
CREATE INDEX ix_dri_title_trgm
    ON discogs_releases_index USING GIN (title gin_trgm_ops);

-- Для alt-version поиска
CREATE INDEX ix_dri_master_id
    ON discogs_releases_index(master_id)
    WHERE master_id IS NOT NULL;
```

**Оценка размера:**
- 30M строк × ~400 байт avg = ~12 GB heap
- +5 GB на индексы (trigram'ы тяжёлые)
- = **~17-20 GB на диске Postgres**

### 3.2 Ingest-скрипт `Backend/app/scripts/ingest_discogs_dump.py`

**Стратегия parsing'а:**

- `lxml.etree.iterparse` — streaming-парсер, не грузит весь XML в память
- На каждый `</release>` event:
  - извлечь поля через XPath (`.//identifiers/identifier[@type='Barcode']`)
  - нормализовать barcode (digits only) + catalog (uppercase, strip)
  - собрать минимальный raw_payload как JSONB
  - добавить в батч
- Каждые 5-10K записей → flush батча через **PostgreSQL COPY FROM STDIN**
  (10× быстрее `INSERT`, 100× быстрее single-row INSERT'ов)
- После каждого батча `element.clear()` чтобы освободить память
  (классический lxml-pattern)
- Прогресс-репорт каждые 50K записей: «X записей, Y MB обработано, ETA»
- Checkpoint в Redis: при сбое можно продолжить с последнего offset'а
  (просто запоминаем последний `discogs_id`)

**Псевдокод:**
```python
import gzip
from lxml import etree
from sqlalchemy import text

BATCH_SIZE = 5000
DUMP_PATH = "/data/discogs_20260501_releases.xml.gz"

async def main():
    async with async_session_maker() as db:
        batch = []
        with gzip.open(DUMP_PATH, "rb") as f:
            for event, elem in etree.iterparse(f, tag="release"):
                if elem.get("status") != "Accepted":
                    elem.clear()
                    continue
                row = parse_release(elem)
                batch.append(row)
                elem.clear()  # free memory
                if len(batch) >= BATCH_SIZE:
                    await flush_via_copy(db, batch)
                    batch = []
        if batch:
            await flush_via_copy(db, batch)

def parse_release(elem) -> dict:
    return {
        "discogs_id": int(elem.get("id")),
        "master_id": _xpath_int(elem, ".//master_id"),
        "artist": _xpath_text(elem, ".//artists/artist/name"),
        "title": _xpath_text(elem, "title"),
        "year": _parse_year(elem),
        "country": _xpath_text(elem, "country"),
        "format_type": _derive_format(elem),
        "label": _xpath_attr(elem, ".//labels/label", "name"),
        "barcode_norm": _norm_barcode(elem),
        "catalog_norm": _norm_catalog(elem),
        "cover_image_url": _xpath_attr(elem, ".//images/image[@type='primary']", "uri"),
        "raw_payload": json.dumps(_build_raw(elem)),
    }

async def flush_via_copy(db, batch):
    # asyncpg / psycopg COPY FROM STDIN — fastest bulk path
    conn = await db.connection()
    raw_conn = await conn.get_raw_connection()
    async with raw_conn.cursor() as cur:
        await cur.copy_records_to_table(
            "discogs_releases_index",
            records=[(r["discogs_id"], r["master_id"], ...) for r in batch],
        )
```

**Дедупликация:**
- Используем `ON CONFLICT (discogs_id) DO NOTHING` если повторно
  запускаем (но через COPY сложнее, можно сделать staging table → MERGE)

**Время:**
- 30M записей ÷ 5K/sec = ~6 000 сек = **100 минут чистого парсинга**
- + COPY вставка с индексами: ~2× медленнее без индексов, поэтому
  **создаём индексы ПОСЛЕ ingest'а**
- + `CREATE INDEX` на 12 GB таблице: ~1 час
- **Итого: 3-5 часов на проде**

### 3.3 Matcher изменения `Backend/app/services/listing_matcher.py`

Добавляем новый шаг 1.5 (между текущими шагами 1 и 2):

```python
# Текущий каскад:
# 1. discogs_release_url (raw_payload) → Record.discogs_id  → 1.0
# 2. barcode → Record.barcode                                → 1.0
# 3. catalog_number → Record.catalog_number                  → 0.9
# 4. fuzzy(artist+title+year) через pg_trgm + rapidfuzz      → score
# 5. on-demand fetch через Discogs API                       → 0.95

# ДОБАВЛЯЕМ:
# 1.5. discogs_releases_index lookup → создаём Record из index entry
#      приоритет: barcode → catalog → fuzzy(artist+title)
```

Реализация:

```python
async def _find_in_dump_index(
    db: AsyncSession,
    *,
    barcode: str | None = None,
    catalog: str | None = None,
    artist: str | None = None,
    title: str | None = None,
    year: int | None = None,
) -> dict | None:
    """Ищет в discogs_releases_index. Возвращает dict с полями для
    создания Record, или None если не нашлось."""

    # Strategy 1: точный по barcode
    if barcode:
        sql = text("""
            SELECT discogs_id, master_id, artist, title, year, country,
                   format_type, label, cover_image_url, raw_payload
            FROM discogs_releases_index
            WHERE barcode_norm = :barcode
            LIMIT 1
        """)
        row = (await db.execute(sql, {"barcode": _norm_barcode(barcode)})).mappings().first()
        if row:
            return dict(row)

    # Strategy 2: точный по catalog
    if catalog:
        sql = text("""
            SELECT ...
            FROM discogs_releases_index
            WHERE catalog_norm = :catalog
            LIMIT 1
        """)
        row = (await db.execute(sql, {"catalog": _norm_catalog(catalog)})).mappings().first()
        if row:
            return dict(row)

    # Strategy 3: fuzzy artist+title (через pg_trgm similarity)
    if artist and title:
        sql = text("""
            SELECT *, similarity(artist, :artist) + similarity(title, :title) AS score
            FROM discogs_releases_index
            WHERE artist % :artist AND title % :title
              AND (:year IS NULL OR year = :year OR ABS(year - :year) <= 2)
            ORDER BY score DESC
            LIMIT 1
        """)
        row = (await db.execute(sql, {"artist": artist, "title": title, "year": year})).mappings().first()
        if row and row["score"] >= 1.4:  # threshold tune'абельный
            return dict(row)

    return None


async def match_listing(listing: StoreListing, db: AsyncSession) -> bool:
    # ... шаги 1-3 (текущие, проверка в records) ...

    # НОВЫЙ ШАГ 4 (раньше — был fuzzy на records, теперь сначала dump):
    index_hit = await _find_in_dump_index(
        db,
        barcode=listing.barcode_norm,
        catalog=listing.catalog_norm,
        artist=_extract_artist(listing),
        title=_extract_title(listing),
        year=_extract_year(listing),
    )
    if index_hit:
        record = await _get_or_create_record_from_dump(db, index_hit)
        _apply_match(listing, record, Decimal("0.95"), MatchMethod.dump_index)
        return True

    # ... остальные шаги (fuzzy на records, on-demand Discogs API) ...


async def _get_or_create_record_from_dump(
    db: AsyncSession,
    index_entry: dict,
) -> Record:
    """Создаёт или находит Record из dump-entry. Минимальный набор полей —
    остальное (tracklist, artist_thumb, цены) ленится через
    _ensure_record_discogs_payload при первом detail-view."""
    discogs_id = str(index_entry["discogs_id"])
    existing = await _find_by_discogs_id(db, discogs_id)
    if existing:
        return existing

    record = Record(
        discogs_id=discogs_id,
        discogs_master_id=str(index_entry["master_id"]) if index_entry["master_id"] else None,
        title=index_entry["title"],
        artist=index_entry["artist"],
        label=index_entry["label"],
        catalog_number=index_entry.get("catalog_norm"),
        year=index_entry["year"],
        country=index_entry["country"],
        format_type=index_entry["format_type"],
        cover_image_url=index_entry["cover_image_url"],
        discogs_data=index_entry["raw_payload"] or {},
        # tracklist пока null — заполнится при первом visit'е через
        # _ensure_record_discogs_payload (см. records.py)
    )
    db.add(record)
    try:
        await db.commit()
        await db.refresh(record)
    except IntegrityError:
        # Race condition: кто-то параллельно создал. Читаем существующую.
        await db.rollback()
        existing = await _find_by_discogs_id(db, discogs_id)
        if existing:
            return existing
        raise
    return record
```

Добавить в `MatchMethod` enum: `dump_index = "dump_index"`.

### 3.4 Lazy enrichment (уже есть — не меняем)

Когда юзер впервые откроет такую запись:
- `/api/records/discogs/{id}` запускает `_ensure_record_discogs_payload`
  (уже реализован в `records.py`)
- Тот заметит что `tracklist` пустой → дёрнет Discogs API один раз
  → положит tracklist, master_id, artist_thumb в discogs_data
- В этот момент Discogs API дёргается ровно один раз на пользовательский
  visit — не на массовое матчинге

---

## 4. Workflow одного ingest'а на проде

### Шаг 1: подготовка диска
```bash
ssh deploy@85.198.85.12 'df -h /var/lib/docker'
# Должно быть свободно ≥ 50 GB (XML 30 + COPY temp + postgres index build)
```

### Шаг 2: download дампа
```bash
ssh deploy@85.198.85.12 'cd /tmp && \
  wget https://discogs-data-dumps.s3-us-west-2.amazonaws.com/data/2026/discogs_20260501_releases.xml.gz \
  --progress=dot:giga'
# ~7 GB, время зависит от канала. На обычном 100Mbps ~10-15 минут.
```

### Шаг 3: copy в контейнер
```bash
ssh deploy@85.198.85.12 'docker cp /tmp/discogs_20260501_releases.xml.gz vertushka_api:/data/'
```

### Шаг 4: Alembic migration (если ещё не применена)
```bash
ssh deploy@85.198.85.12 'docker exec vertushka_api alembic upgrade head'
```

### Шаг 5: запуск ingest'а в background
```bash
ssh deploy@85.198.85.12 'docker exec -d vertushka_api sh -c \
  "python -m app.scripts.ingest_discogs_dump \
    --file /data/discogs_20260501_releases.xml.gz \
    --batch-size 5000 \
    > /tmp/ingest.log 2>&1"'

# Мониторинг
ssh deploy@85.198.85.12 'docker exec vertushka_api tail -f /tmp/ingest.log'
```

### Шаг 6: создание индексов после ingest'а
```bash
# Скрипт создаст индексы на финальном шаге. Или вручную:
ssh deploy@85.198.85.12 'docker exec vertushka_api python -m app.scripts.ingest_discogs_dump --build-indexes-only'
```

### Шаг 7: верификация
```sql
SELECT COUNT(*) FROM discogs_releases_index;  -- ожидаем ~30M
SELECT COUNT(*) FROM discogs_releases_index WHERE barcode_norm IS NOT NULL;
SELECT COUNT(*) FROM discogs_releases_index WHERE catalog_norm IS NOT NULL;

-- Sanity check: ищем известный barcode
SELECT discogs_id, artist, title FROM discogs_releases_index
WHERE barcode_norm = '075678657238';
```

### Шаг 8: cleanup
```bash
ssh deploy@85.198.85.12 'docker exec vertushka_api rm /data/discogs_20260501_releases.xml.gz'
ssh deploy@85.198.85.12 'rm /tmp/discogs_20260501_releases.xml.gz'
```

### Шаг 9: re-run matcher
```bash
ssh deploy@85.198.85.12 'docker exec -d vertushka_api sh -c \
  "while true; do \
     python -m app.scripts.scrape_all --match-only >> /tmp/matcher.log 2>&1; \
     sleep 30; \
   done"'
```

Должны увидеть скачок покрытия:
- vinyl_ru: 0.9% → 80%+ за пару часов
- stoprobot: 11% → 85%+ за пару часов

---

## 5. План реализации (порядок коммитов)

### Коммит 1: миграция
- `Backend/alembic/versions/XXX_discogs_releases_index.py`
- Создаёт таблицу + индексы. Indexes изначально **без** trigram (создадим
  потом, после ingest'а — иначе вставка станет в 10× медленнее).

### Коммит 2: ingest скрипт
- `Backend/app/scripts/ingest_discogs_dump.py`
- CLI: `--file PATH`, `--batch-size N`, `--limit N` (для тестов на mini-dump),
  `--build-indexes-only`, `--resume-from DISCOGS_ID`
- Зависимость: `lxml` (добавить в `requirements.txt`)
- Unit-тесты на парсинг XML с mini-фикстурой (5-10 release-элементов)

### Коммит 3: matcher patch
- `Backend/app/services/listing_matcher.py`: новый `_find_in_dump_index`
  + интеграция в `match_listing` (между catalog-match и fuzzy)
- `Backend/app/services/listing_matcher.py`: новый
  `_get_or_create_record_from_dump`
- `Backend/app/models/store_listing.py`: `MatchMethod.dump_index`
- Логирование: счётчики в `match_unmatched_batch` отдельно для dump-hits

### Коммит 4: runbook + docs
- `docs/runbooks/discogs-dump-ingest.md` — пошаговый бек-офис гайд
  (повторное использование при появлении новых дампов)
- Обновить `Backend/README.md` с упоминанием новой команды
- Обновить ROADMAP.md (закрыть milestone «дамп-индекс»)

---

## 6. Открытые вопросы / решения

### 6.1 Дата дампа
**Решение:** берём последний доступный (`discogs_YYYY0501_releases.xml.gz`
для большинства месяцев). Релизы после этой даты → fallback на Discogs API.

### 6.2 raw_payload — что класть
**Решение:** минимум для скоростного создания Record без API:
- tracklist (массив треков)
- vinyl_color_raw (если есть в формате `text`)
- format_descriptions (LP / 2xLP / etc)
- formats[].qty (количество дисков)
- labels[] (все, не только первый)
- identifiers[] (все, не только barcode)
- artists[] (с id'ами — для artist navigation)

НЕ кладём:
- companies (звукозапись, mastering — лишний bloat)
- videos
- notes (длинные текстовые)
- images[] (только первичную uri в отдельной колонке)

Это снижает raw_payload до ~1-2 KB на запись, итого +30-60 GB на колонку.
**На таблицу = ~15-20 GB.**

### 6.3 Versioning дампа
**Решение:** Добавить колонку `dump_version` (YYYY-MM-DD когда дамп был
загружен) в `discogs_releases_index`. Это позволит:
- мониторить «как давно индекс стареет»
- частично/инкрементально обновлять (загружать новый дамп → upsert
  по discogs_id → старые записи остаются, новые добавляются)

### 6.4 Обновление в будущем
**Решение:** пока — manual. Скрипт ingest'а поддерживает повторный запуск
с `ON CONFLICT DO UPDATE` чтобы перезаписать существующие записи. Через
3-6 месяцев когда дамп заметно устареет, повторяем процедуру с свежим
дампом. Автоматизировать через scheduler (раз в N месяцев) — можно
позже, отдельным шагом.

### 6.5 Производительность fuzzy-запроса
**Решение:** trigram-индексы на 30M строк могут давать запросы 100-500ms.
Это всё ещё в разы быстрее Discogs API (~1-3 сек). Если станет узким
местом — добавим LIMIT в fuzzy-запрос (TOP-10 кандидатов → проверка
fuzz_ratio в Python) и/или filter по year/country перед fuzzy.

### 6.6 Memory footprint ingest'а
**Решение:** lxml + `element.clear()` после каждого release держит память
константной (~100-200 MB). НЕ грузим всё в память. Тестировали на других
проектах — стабильно.

---

## 7. Verification (после внедрения)

### 7.1 Технические
```sql
-- Запись в индексе должна быть
SELECT COUNT(*) FROM discogs_releases_index;  -- ≥ 25M

-- Индексы используются
EXPLAIN SELECT * FROM discogs_releases_index WHERE barcode_norm = '075678657238';
-- Должно показать Index Scan, не Seq Scan
```

### 7.2 Business
- Покрытие vinyl_ru: **0.9% → 80%+** за 2 часа после re-run matcher'а
- Покрытие stoprobot: **11% → 85%+** за 2 часа
- Total: **27.6% → 80%+** на всех магазинах
- Discogs API quota использование: -90% (только enrich detail-screen
  visit'ы + неиндексированные новинки)

### 7.3 UX
- В Маркете все 4 магазина показывают полные витрины
- На детальной OffersBlock показывает alt-version из всех магазинов
- Никаких "плашек с 0 пластинок"

---

## 8. Откат и безопасность

### Откат
Если что-то пошло не так:
```sql
DROP TABLE discogs_releases_index;
```
+ откатить matcher patch через `git revert`. Никаких side-effect'ов на
существующих `records`/`store_listings` — мы их не трогаем.

### Безопасность данных
- Discogs Dumps под CC0 — публичные данные, no PII
- `raw_payload` не содержит наших юзерских данных
- Не передаём наружу, всё локально

---

## 9. Ссылки

- [Discogs Data Dumps documentation](https://www.discogs.com/data/)
- [lxml streaming parsing recipe](https://lxml.de/parsing.html#iterparse-and-iterwalk)
- [PostgreSQL COPY FROM STDIN](https://www.postgresql.org/docs/current/sql-copy.html)
- [pg_trgm extension](https://www.postgresql.org/docs/current/pgtrgm.html)
- Текущий matcher: `Backend/app/services/listing_matcher.py`
- Текущий records API: `Backend/app/api/records.py` (`_ensure_record_discogs_payload`)
