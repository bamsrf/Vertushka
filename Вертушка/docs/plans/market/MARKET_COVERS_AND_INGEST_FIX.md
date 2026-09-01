# Маркет: надёжность обложек + ingest «нет в Discogs»

> **Цель:** убрать серые квадраты в маркете, максимизировать ассортимент (включая пластинки, которых нет в Discogs локально), связать slim Discogs dump с обложками и enrichment.
> **Родительские документы:** [MARKET_AND_PRICE_DRAWER.md](MARKET_AND_PRICE_DRAWER.md), [DISCOGS_DUMP_BULK_INGEST.md](../discogs/DISCOGS_DUMP_BULK_INGEST.md)

## Как маркет работает сейчас

Pipeline обложки:
- **Источник URL** — `records.cover_image_url`. Для Discogs-матчей это CDN Discogs, для store-native — CDN магазина.
- **Зеркало** — `cover_storage` качает в `uploads/covers/{discogs_id}.jpg` (или `covers/store/{uuid}.jpg`), пишет `cover_local_path`.
- **Что отдаёт маркет** ([market.py:66](../../../Backend/app/api/market.py)): `COALESCE(локальное зеркало → cover_image_url → raw_payload.image_url)`. Локальное `/uploads/...`, мобайл резолвит через `resolveMediaUrl`.
- **Зеркалирование** — fire-and-forget ПОСЛЕ ответа ([market.py:101](../../../Backend/app/api/market.py)), + при добавлении в коллекцию/вишлист. Плюс nginx-fallback `/covers/{id}` качает по запросу.
- Все market-эндпоинты **выкидывают записи без обложки** (`COALESCE(...) IS NOT NULL`).

## Корневые причины недогрузки обложек

1. **Маркет отдаёт сырой Discogs/store URL, минуя свой же self-healing прокси.** На первом визите `cover_local_path` пуст → мобайл получает CDN-ссылку напрямую. Discogs `api-img.discogs.com` URL подписанные, истекают → 403 → серый плейсхолдер. Прокси `/covers/{id}` (nginx fallback → фоновое скачивание → 302) для маркета не задействуется.
2. **`/market/search`** использует record-only cover-expr (без store-фото fallback) — отдельный баг серых квадратов.
3. **Dump НЕ содержит обложек.** Публичные Discogs data dumps вырезали `uri/uri150` (~2020). `_cover_image` ([ingest_discogs_dump.py:189](../../../Backend/app/scripts/ingest_discogs_dump.py)) почти всегда NULL → dump-записи без обложки → выпадают из ассортимента. **Требует verify-SQL на проде (WS2.1).**

## Путь «нет в Discogs» (шаг 6 каскада) и его проблемы

Каскад матчинга ([listing_matcher.py:307](../../../Backend/app/services/listing_matcher.py)): Discogs URL → barcode → catalog → fuzzy(records) → dump-index → API → **store-native fallback**.

Store-native gate `_should_create_store_native` ([:584](../../../Backend/app/services/listing_matcher.py)) — ВСЕ условия: не аксессуар; есть `artist + title + year + image_url`; прожил ≥7 дней ИЛИ есть второй unmatched-листинг похожего релиза в другом магазине.

Проблемы ассортимента:
1. `year_raw` обязателен ([:596](../../../Backend/app/services/listing_matcher.py)) → листинги без распарсенного года отброшены навсегда. Дедуп NULL-год терпит → можно ослабить до optional.
2. Gate ≥7 дней → одиночный листинг невидим неделю (бьёт Plastinka).
3. Дедуп только fuzzy artist+title, не использует barcode/catalog → дубли store-native (master-дедуп их не схлопнет — нет master_id).
4. Нет нормализации перед similarity (кириллица vs translit, «feat.» варианты) → ещё дубли.
5. Store-native не повышается до Discogs. Merge-инфра есть (`merged_into_id`, `safe_merge_store_native_into`), но обратного промоушена нет.

## План — 5 воркстримов

### WS1 — Надёжность обложек
| | Фикс | Файлы |
|---|---|---|
| 1.1 | Единый cover-expr во всех 3 эндпоинтах: `mirror → cover_image_url → store-фото`. Чинит баг серых квадратов в `/market/search` (там record-only expr) | [market.py:66](../../../Backend/app/api/market.py) |
| 1.2 | Стабильный прокси-путь `/uploads/covers/{id}.jpg` вместо сырого Discogs URL + новый `/covers/store/{uuid}` для store-native | [covers.py](../../../Backend/app/api/covers.py), nginx |
| 1.3 | LRU-cleanup щадит зеркала активных in_stock | [cover_storage.py:165](../../../Backend/app/services/cover_storage.py) |
| 1.4 | Клиент: onError-плейсхолдер/1 ретрай на market-карточках | [MarketCarouselCard.tsx:57](../../../Mobile/components/market/MarketCarouselCard.tsx) |

### WS2 — Dump-линковка и enrichment обложек
| | Фикс | |
|---|---|---|
| 2.1 | Verify: `discogs_releases_index.cover_image_url` пустой (dump режет URI) → если так, признать dump НЕ источником обложек | SQL-проверка |
| 2.2 | enrichment-джоб: in_stock matched без cover, но с master_id → батч по master_id → `get_master_versions` (1 вызов/мастер) → cover_image_url + mirror | новый task + [discogs.py:954](../../../Backend/app/services/discogs.py) |
| 2.3 | (опц.) убрать мёртвый `_cover_image` из ingest dump'а | [ingest_discogs_dump.py:189](../../../Backend/app/scripts/ingest_discogs_dump.py) |

### WS3 — Ingest «нет в Discogs» (store-native)
| | Фикс | |
|---|---|---|
| 3.1 | Жёсткий дедуп barcode→catalog→fuzzy + нормализация artist/title | [listing_matcher.py:640](../../../Backend/app/services/listing_matcher.py) |
| 3.2 | Gate: year optional + trusted-store immediate-accept | [:584](../../../Backend/app/services/listing_matcher.py) |
| 3.3 | Промоушен-луп store-native → Discogs через dump/API + merge | новый task + `safe_merge_store_native_into` |

### WS4 — Консистентность и перф маркета
| | Фикс | |
|---|---|---|
| 4.1 | Построить matview `market_store_stats` (в плане есть, в миграциях нет) → `/market/stores` с агрегата на matview | новая миграция + [market.py:159](../../../Backend/app/api/market.py) |
| 4.2 | Метрика покрытия обложек (% in_stock matched с рабочей обложкой) + алерт | analytics |
| 4.3 | (опц.) ужать `STALE_AFTER_DAYS=7` или показывать «last seen» | [market.py:47](../../../Backend/app/api/market.py) |

## Порядок исполнения (по зависимостям)
1. **WS1.1 + WS4.2** — быстрый фикс видимого бага + метрика, чтобы мерить эффект.
2. **WS2.2** — enrichment-джоб: максимум прироста обложек/ассортимента дёшево.
3. **WS3.1 + WS3.2** — расширить store-native ingest.
4. **WS1.2 + WS1.3** — стабильный прокси + LRU.
5. **WS3.3 + WS4.1** — промоушен-луп + matview.
6. **WS1.4, WS2.3, WS4.3** — мелочи/уборка.
