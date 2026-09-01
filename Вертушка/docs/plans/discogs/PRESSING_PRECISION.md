# §A — Pressing-precision: матч по прессу, не по альбому

> Контекст: офферы магазинов матчатся к `Record` по barcode/catalog/fuzzy(artist+title) —
> ни один ключ не опознаёт конкретный **цветной пресс**. Fuzzy схлопывает все
> прессы одного альбома на одну запись (напр. чёрный In Utero → зелёная запись).
> Фаза 0 (shipped, commit `fe7d193`) — `pressing_match` tier в offers: не выдаём
> чужой пресс за «этот», но честность отображения ≠ верный матч. §A чинит сам матч.

## Корни
1. Ключи матча опознают альбом, не пресс → fuzzy collapse.
2. Инжестим мало прессов (master = десятки версий, у нас обычно 1).
3. Цвет Record редкий (0.7% от 15 236) и приходит из грязного `formats[0].text`.
4. Цвет листинга парсится у 21.5%.

## Замер охвата (прод, 7 дней, 10 744 exact in_stock)
- цвет листинга известен: 2314 (21.5%)
- цвет Record известен: 75 (0.7%)
- оба известны: 28 → **настоящий конфликт семьи 6**
- цвет листинга есть, Record нет: 1397
- match_method: fuzzy 1115, на цветных Record'ах fuzzy = 55%
- tier-split: exact 40% / album 60%

## Воркстримы

### WS-A1 — цвето-aware матчинг (precision) ← ПЕРВЫЙ
Штраф в `_fuzzy_score` ([listing_matcher.py](../../../Backend/app/services/listing_matcher.py)) по
образцу `FORMAT_MISMATCH_PENALTY`: обе семьи цвета известны и разные → `score × 0.3`
→ ниже `FUZZY_THRESHOLD` → кандидат отсекается. Чёрный листинг перестаёт липнуть к
зелёной записи **на этапе матча**. Штрафуем только когда обе семьи известны (нет
над-отсечения при неизвестном цвете). Использует `vinyl_color.color_family`.

**Намеренно НЕ делаем агрессивный reset-sweep существующих конфликтов** — это
убрало бы офферы с записи в никуда (правильного пресса ещё нет в БД до A4). Фаза-0
tier уже помечает их «пресс может отличаться». Reset включаем только после A4,
когда есть куда переехать.

### WS-A2 — приоритет exact-сигнала над fuzzy
Если у листинга есть barcode/catalog — пробовать dump/discogs_fetch (exact,
per-pressing) **до** локального fuzzy. Сейчас fuzzy (шаг 4) раньше dump (4.5) и
discogs_fetch (5) → barcode-листинг может схлопнуться по имени раньше, чем найдём
верный пресс. Вставить «exact dump (barcode/catalog only)» между шагом 3 и fuzzy.

### WS-A3 — цвет Record: чистая экстракция (охват — НИЗКИЙ ПОТОЛОК)
`color_family` уже чистит шум на чтении (offers). Бэкфилл цвета даёт мало: у 98%
записей цвета нет, т.к. Discogs не пишет `formats.text` для стандартных чёрных
прессов (отсутствие ≠ чёрный, домысливать рискованно). Ограничиваемся:
извлекать цвет в `_ensure_record_discogs_payload` при детальной загрузке. Полный
bulk-бэкфилл не окупается — отложено.

### WS-A4 — barcode/цвет в скраперах (ГЛАВНЫЙ РЫЧАГ)
[korobkavinyla.py](../../../Backend/app/services/scrapers/shops/korobkavinyla.py),
[stoprobotvinyl.py](../../../Backend/app/services/scrapers/shops/stoprobotvinyl.py) и др.:
надёжно вытаскивать **barcode** (+ catalog, цвет). Barcode = per-pressing → матч
1.0 минуя fuzzy. Чёрный In Utero с barcode → on-demand fetch создаёт чёрную запись
→ листинг цепляется туда. Риск: скраперы хрупкие, тестировать на живых страницах.

### WS-A5 — UX «аналог / верная версия»
На записи без exact-офферов, но с офферами на других прессах мастера → блок «В
наличии в других изданиях» с цвето-чипами → детальная верного пресса. Кросс-линк
офферы → [master/versions](../../../Mobile/app/master/[id]/versions.tsx).

## Порядок
`A1 (штраф)` → `A2 (приоритет exact)` → `A4 (barcode)` → `A4.5 (reset-sweep)` →
`A3 (цвет при детали)` → `A5 (UX)`.

## Статус (реализовано)
- ✅ **Фаза 0** — `pressing_match` tier в offers (commit `fe7d193`, в проде).
- ✅ **A1** — цвето-штраф в `_fuzzy_score` (commit `67621a1`).
- ✅ **A2** — exact dump (barcode/catalog) до fuzzy (commit `8da93ec`).
- ✅ **A4** — `normalize_barcode` чинит SKU-паддинг (`000`+EAN→EAN); `barcode_variants`
  (UPC↔EAN-13) в dump + local lookup. Корень: 15-значный SKU ронялся → терялся
  barcode → fuzzy. In Utero SKU `000720642453612` → `720642453612` → винил-пресс
  master 13859 (не зелёный).
- ✅ **A4.5** — `rematch_album_with_barcode_batch` + `daily_rematch_album_with_barcode`
  (cron 04:15): перематч album-tier листингов с появившимся barcode, inline-rematch
  со сравнением (без loop/churn, оффер не теряется). Чинит существующие (In Utero
  переедет с зелёной на чёрную запись после ре-скрейпа+sweep).
- ⏸️ **A3** — отложено (потолок низкий, см. выше).
- ✅ **A5** — покрыто Фазой 0 (секция «Пресс может отличаться» + Market-CTA +
  навигация alt-строк на верный пресс) и кнопкой «Смотреть другие версии релиза»
  → master/versions. Доп-UI не делаем без конкретного гэпа.
