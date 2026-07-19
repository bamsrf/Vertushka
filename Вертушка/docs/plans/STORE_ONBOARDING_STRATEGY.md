# Стратегия учёта магазинов — онбординг новых игроков без деградации медиатеки

> Living document. Обновляй при изменении процесса заведения магазина, метрик здоровья или гейтов.
> Родственные доки: [SHOPS_PARSING.md](SHOPS_PARSING.md) (архитектура + расписание), [PARSING.md](PARSING.md) (операционка/лимиты), [STORE_NATIVE_RECORDS.md](STORE_NATIVE_RECORDS.md) (fallback-записи вне Discogs).
> Milestone: **M6. Парсинг магазинов РФ** (см. [ROADMAP.md](../../ROADMAP.md)).

---

## 0. Зачем этот документ

Сейчас магазин — это класс-парсер + строка в `STORES` ([seed_stores.py](../../Backend/app/scripts/seed_stores.py)). Всё состояние магазина (здоров / мусорит / сколько реально матчится) живёт **в логах**, а не в данных. Пока магазинов 5 — это терпимо. При росте до 20–30 «тихие отказы» становятся системной проблемой: магазин может успешно краулиться и при этом давать пользователю **ноль офферов**.

**Приоритет №1 (зафиксирован): стабильность обновления медиатеки.** Главный риск — не «не спарсили», а **«спарсили, но перестало матчиться, и никто не заметил»**. Стратегия строится вокруг того, чтобы сделать это состояние наблюдаемым и заводить каждый следующий магазин по одному воспроизводимому конвейеру.

### Ключевой тезис
> Успешный crawl ≠ офферы у пользователя. Учитывать надо **match-rate**, а не crawl-success.

Оффер попадает в Маркет только если листинг сматчился на `Record`: Market API делает INNER JOIN по `matched_record_id` ([market.py](../../Backend/app/api/market.py), см. [STORE_NATIVE_RECORDS.md](STORE_NATIVE_RECORDS.md)). Всё, что не сматчилось, — невидимо.

---

## 1. Что уже защищает нас (baseline)

Не строим с нуля — фиксируем существующие предохранители, чтобы не дублировать:

| Механизм | Где | Что ловит | Дыра |
|---|---|---|---|
| `_smoke_check` | [runner.py:289](../../Backend/app/services/scrapers/runner.py) | «0 discovered / <10% от БД / >50% ошибок» → `last_error` + ERROR в GlitchTip | Только full-режим без limit; **только если в БД уже есть листинги** (новый магазин на 1-м прогоне не защищён); не ловит «спарсилось, но не матчится» |
| Circuit breaker + CF-детект | [http_client.py](../../Backend/app/services/scrapers/http_client.py) | Cloudflare/DDoS-Guard → `requires_browser=True` | Молчаливый уход в еженедельный browser-краул |
| Anti-noise gate | [listing_matcher.py:739](../../Backend/app/services/listing_matcher.py) | Мусорные store-native (нужен artist+title+year+cover + persist/cross-shop) | Обходится флагом `is_trusted` |
| `signals` в match-батче | [listing_matcher.py:932](../../Backend/app/services/listing_matcher.py) | Диагностика «есть ли у листингов ID для матчинга» | **Уходит только в лог**, не хранится, не алертит |

**Вывод:** самый ценный сигнал (`signals` + match-rate) уже вычисляется, но выбрасывается в лог. Первый шаг стратегии — перестать его выбрасывать.

---

## 2. Шесть слоёв стратегии

### Слой 1. Паспорт магазина — декларация возможностей
Добавить в [Store](../../Backend/app/models/store.py) явную декларацию (JSONB `capabilities` или отдельные колонки), заполняется при заведении:

- `has_barcode` / `has_catalog` / `has_discogs_url` — какие сигналы для матчинга отдаёт;
- `sells`: `{vinyl, cd, accessories}` — что в каталоге;
- `discovery`: `sitemap | yml | custom`;
- `catalog_size_est` — порядок величины;
- `tier`: `A | B | C` (см. слой 5).

Зачем: входной чек-лист становится **данными**. По нему заранее видно «магазин без barcode → слабый text-матч + жрёт Discogs-квоту» и считаются бюджеты/расписание программно.

### Слой 2. Метрики здоровья — таблица `store_health` (★ ядро стратегии, приоритет)
**Решение: отдельная таблица `store_health`, а не колонки в `stores`.** Причина — нужна *история* прогонов, чтобы считать дельту «неделя-к-неделе» и строить тренд; колонки в `stores` хранили бы только последний срез. Одна строка = один снапшот на (store_id, captured_at).

Черновик схемы:
```sql
CREATE TABLE store_health (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    store_id        uuid NOT NULL REFERENCES stores(id) ON DELETE CASCADE,
    captured_at     timestamptz NOT NULL DEFAULT now(),
    total_listings      int  NOT NULL,
    matched_listings    int  NOT NULL,
    match_rate          numeric(5,4) NOT NULL,     -- matched / total
    -- разбивка по методам (сколько листингов сматчено каждым)
    by_method       jsonb NOT NULL DEFAULT '{}',   -- {barcode, catalog, fuzzy, dump, discogs_fetch, store_native, unmatched}
    store_native_share  numeric(5,4),
    last_discovered     int,                        -- discovered в последнем crawl
    last_error          text,
    crawl_mode          text                        -- full | incremental
);
CREATE INDEX ix_store_health_store_time ON store_health (store_id, captured_at DESC);
```
Ретеншн: снапшоты старше ~90 дней чистить (агрегат-тренда достаточно). Писать снапшот в конце `_market_sync` / после `match_unmatched_batch` — там счётчики `signals` уже собраны.

**Алерт на просадку** (в GlitchTip, рядом со smoke-check): сравниваем свежий снапшот с предыдущим по store_id — `match_rate` упал > X% неделя-к-неделе, или `store_native_share` скакнул → магазин сменил вёрстку либо начал лить мусор. Это **закрывает главный тихий отказ**, который `_smoke_check` не видит.

### Слой 3. Онбординг-конвейер с гейтами
Заменить «залил в прод» на три стадии со стоп-гейтами:

1. **Staging**: `crawl_store(slug, limit=50)` → проверить `raw_payload` (скрипт + глаза). Гейт: поля не пустые, CD/аксессуары отфильтрованы.
2. **Canary**: `is_active=true`, `is_trusted=false`, **отдельный низкий Discogs-бюджет**. Наблюдаем match-rate неделю.
3. **Full**: снимаем ограничения, только если match-rate выше порога и store-native не задваивает.

Формализует чек-лист «что проверить руками» в воспроизводимый процесс — память оператора → процедура.

### Слой 4. Бюджетирование Discogs-квоты по магазинам
`DISCOGS_FETCH_HOURLY_LIMIT = 2000` ([listing_matcher.py:148](../../Backend/app/services/listing_matcher.py)) — **общий на всех**, счётчик глобальный. Новый магазин на 10k unmatched без локальных ID выжрет квоту и затормозит и матчинг, и живой поиск.

- **Per-store суб-лимит**: ключ счётчика `discogs_ondemand_hits:{store_id}`.
- **Приоритет** магазинам с barcode (матчатся локально/дёшево) над text-only.
- Для гигантских каталогов — опираться на локальный **dump-index** ([listing_matcher.py:197](../../Backend/app/services/listing_matcher.py), покрытие 80%+), on-demand держать как хвост.

### Слой 5. Тиры обхода вместо одной задачи
Код прямо предупреждает: [«если магазинов > 20 — разбить на группы»](../../Backend/app/tasks/scraper_tasks.py) (сейчас все в одной `daily_full_crawl_http`, `SCRAPER_CONCURRENCY=5`). Раз есть паспорт (`catalog_size`) и match-rate — тир выводится естественно:

| Tier | Кто | Обход |
|---|---|---|
| A | Крупные/ценные, высокий match-rate | Ежедневно, инкрементально |
| B | Средние | Раз в 2–3 дня |
| C | Мелкие / browser / нестабильные | Еженедельно |

Тир — поле магазина, `_crawl_active_stores` фильтрует по нему. Ночное окно перестаёт быть узким местом при росте числа игроков.

### Слой 6. Governance store-native и целостность медиатеки
- **Trust-лестница вместо флага**: `is_trusted` включается **только** после N недель хорошего match-rate (метрика из слоя 2), а не «вручную на глаз» ([store.py:33](../../Backend/app/models/store.py)).
- **Квота на store-native per store**: неправдоподобно много новых Record за прогон = красный флаг (грязный парсер) → стоп-гейт.
- **Дашборд задвоений**: дубли store-native, что не схлопнул дедуп ([`STORE_NATIVE_DEDUP_SCORE`](../../Backend/app/services/listing_matcher.py)), — на ревью: auto-merge необратим и таскает коллекции/вишлисты юзеров ([safe_merge_store_native_into](../../Backend/app/services/listing_matcher.py)).

---

## 3. Дорожная карта внедрения (по приоритету «стабильность»)

| Фаза | Что | Слой | Эффект | Объём |
|---|---|---|---|---|
| **P0 (MVP)** | Таблица `store_health` + вынос `match_rate`/`signals` из логов + алерт на просадку | 2 | Закрывает «магазин молча перестал матчиться» — главный тихий отказ | S |
| **P1** | Паспорт магазина (`capabilities`, `tier`) + гейт staging→canary | 1, 3 | Каждый новый магазин заходит по одному конвейеру | M |
| **P2** | Per-store Discogs-бюджет | 4 | Новый крупный магазин не топит общую квоту | S |
| **P3** | Тиры обхода в расписании | 5 | Расписание выдерживает 20–30+ магазинов | M |
| **P4** | Trust-лестница + квота store-native + дашборд задвоений | 6 | Медиатека не деградирует от нового игрока | M |

**Минимальный первый шаг (80/20):** P0. Вся телеметрия уже считается в [match_unmatched_batch](../../Backend/app/services/listing_matcher.py) — надо лишь сохранить её в таблицу и повесить алерт.

---

## 4. Definition of Done для «завести новый магазин» (целевой чек-лист)

1. Заполнен паспорт (`capabilities`, `tier`).
2. Staging-прогон `limit=50` — `raw_payload` вручную проверен.
3. CD/аксессуары отфильтрованы (иначе зальются как винил + жгут квоту).
4. Есть ли barcode/catalog — если нет, зафиксировано, что матч будет слабым.
5. Canary-неделя: match-rate выше порога, store-native не задваивает.
6. `is_trusted` **не** включаем до прохождения trust-лестницы.
7. Объём каталога × rate-limit укладывается в окно тира и в Discogs-бюджет.

---

## 5. Открытые вопросы
- Пороги алертов (просадка match-rate в %) — подбирать эмпирически на проде, как и `STORE_NATIVE_DEDUP_SCORE`.
- Нужен ли админ-UI для гейтов/тиров, или достаточно CLI + метрик в GlitchTip на текущем масштабе.
- Ретеншн `store_health` — 90 дней снапшотов или дольше для сезонного тренда.

_Решено:_ `store_health` — отдельная таблица (нужна история дельт), см. слой 2.
