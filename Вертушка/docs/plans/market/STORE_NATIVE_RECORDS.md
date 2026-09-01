# Store-native Records для листингов вне Discogs

## Context

Сейчас матчер `listing_matcher.match_listing` ([Backend/app/services/listing_matcher.py:144](../../../Backend/app/services/listing_matcher.py)) — каскад из 5 фолбэков (Discogs URL → barcode → catalog → fuzzy local → Discogs API search). Если ни один не сработал, листинг остаётся `matched_record_id=NULL` и **никогда** не показывается в Маркете — Market API делает INNER JOIN на `matched_record_id` ([Backend/app/api/market.py:216-224](../../../Backend/app/api/market.py)).

Реальный кейс: «Антоха МС — Родина 2024» (Coastal Pirates), русский инди, инди-лейблы — этих релизов **нет** на Discogs вовсе. Они вечно unmatched ⇒ Маркет показывает только то, что есть у Discogs, теряем покрытие рынка.

**Желаемый исход:** когда все 5 шагов матчера не нашли Record, создаём «store-native» Record (`source='store'`, `discogs_id=NULL`) из данных самого листинга. Маркет автоматически его подхватывает (INNER JOIN проходит). Запись живёт параллельно с Discogs-записями, и в Phase 2 при появлении на Discogs мёрджится в обычную.

Это **Phase 1** — минимальная безопасная реализация без merge tool и без записи store-native в коллекции/wishlist.

---

## Архитектура решения

### Где встраиваем
Новый **шаг 6** в `match_listing`, после `_try_discogs_fetch_by_text` ([Backend/app/services/listing_matcher.py:205-214](../../../Backend/app/services/listing_matcher.py)). Шаг создаёт Record и привязывает листинг тем же `_apply_match`. Никакого нового кода во фронте, никакого нового API.

### Anti-noise gate
Не создавать store-native при первом увиденном листинге — это защищает от опечаток парсера и временных артефактов. Условия (ВСЕ true):
1. **Не аксессуар** — `_ACCESSORY_TITLE_RE` уже существует, переиспользуем.
2. **Качество данных:** есть `artist_raw` и `title_raw` и `year_raw` и `image_url` в `raw_payload`. Без всего этого карточка в Маркете будет мусорной.
3. **Подтверждение существования** (OR-условие):
   - `last_seen_at - first_seen_at >= 7 days` (магазин re-сёл листинг при следующем скрапе спустя неделю), ИЛИ
   - Существует ≥1 другой `unmatched` листинг с похожим artist+title в другом `store_id` (fuzzy через pg_trgm, threshold 0.8).

   Любой из двух сигналов означает «релиз реален, не разовая ошибка парсера».

### Dedup между магазинами
Используем `_find_store_native_duplicate` через тот же `similarity()` что и `_fuzzy_candidates`. Threshold для score — **подбираем эмпирически на проде** (стартуем с `similarity(artist) + similarity(title) >= 1.6`, год ±1). Перед `INSERT` всегда искать существующий — даже когда unique index гарантирует отсутствие коллизии, это даёт человекочитаемый матч вместо `ON CONFLICT DO NOTHING`.

Дополнительно жёсткое страховочное **partial unique index**:
```sql
CREATE UNIQUE INDEX uq_store_native_artist_title_year
  ON records (lower(artist), lower(title), year)
  WHERE source = 'store';
```
с `ON CONFLICT DO NOTHING` в insert — на случай конкурентного вызова (будущий CLI / параллелизация скрапера).

### Cover caching
Парсеры берут `image_url` с CDN магазина — это hot-link, magazин уберёт картинку через полгода → пустая карточка. В момент создания store-native Record:
1. Записать оригинальный URL в `cover_image_url` (как сейчас Discogs-flow).
2. Сразу же поставить в очередь cover-cache job, заполнить `cover_local_path` + `cover_cached_at`.

### MatchMethod
Добавить значение в `MatchMethod` enum:
```python
STORE_NATIVE = "store_native"
```
Применяется при шаге 6 с `match_confidence = Decimal("1.000")` (мы сами создали Record под этот листинг — это не «вероятностный» матч).

### Запрет add-to-collection/wishlist для store-native
В Phase 1 — `source='store'` Record **не должен** быть добавлен в collection/wishlist (т.к. CASCADE FK создаёт риск потери юзер-данных при будущем merge).
- Backend: в POST-эндпоинтах collections/wishlists проверять `record.source != 'store'`, иначе 400 с понятным message.
- Frontend: на детальном экране Record читать `record.source` — кнопки add-to-collection / add-to-wishlist скрывать, показывать pill `Скоро будет на Discogs`.

### Re-match cron (новый APScheduler job)
Раз в неделю — для всех `Record where source='store'`:
1. Попытаться `_try_discogs_fetch_by_text(artist, title, year)` — может, релиз уже появился на Discogs.
2. Если нашёлся Discogs Record — пишем лог + помечаем `records.discogs_id_candidate` (новое поле, nullable), но не мёрджим автоматически. Phase 2 заберёт обработку.
3. Если не нашёлся — оставляем как есть.

---

## Изменения файл-за-файлом

| Файл | Что меняется |
|---|---|
| `Backend/alembic/versions/<new>.py` | `ALTER TABLE records ADD COLUMN source VARCHAR(20) NOT NULL DEFAULT 'discogs'`; partial unique index; `ix_records_source` |
| `Backend/app/models/record.py` | Поле `source: Mapped[str]`; optional `discogs_id_candidate: Mapped[str \| None]` |
| `Backend/app/models/store_listing.py` | Добавить `MatchMethod.STORE_NATIVE = "store_native"` |
| `Backend/app/services/listing_matcher.py` | Новый шаг 6 в `match_listing`; функции `_should_create_store_native`, `_find_store_native_duplicate`, `_create_store_native_record`; счётчик `store_native_created` в `match_unmatched_batch` |
| `Backend/app/services/cover_storage.py` | Скачивание + сохранение `cover_local_path` |
| `Backend/app/tasks/scraper_tasks.py` | Новая task `weekly_rematch_store_native` |
| `Backend/app/main.py` | Регистрация cron-job в scheduler |
| `Backend/app/api/collections.py`, `wishlists.py` | Guard `record.source != 'store'` в POST |
| `Backend/app/schemas/record.py` | Добавить `source` в response schema |
| `Mobile/components/...` | Скрыть add-to-collection / add-to-wishlist для `record.source === 'store'`, показать info-pill |

---

## Verification

### Backend
1. **Unit** — `_should_create_store_native` False для аксессуара/без cover/свежего; `_find_store_native_duplicate` находит по транслитерациям; полный `match_listing` flow создаёт `source='store'` Record.
2. **Integration** — фикстура «Антоха МС — Родина» от двух магазинов >7d → один Record на оба листинга, виден в `GET /api/market/stores/<slug>/listings`.
3. **Re-match cron** — `await weekly_rematch_store_native()` — проверить заполнение `discogs_id_candidate`.

### Frontend
- В Маркете store-native карточка: нет кнопок add-to-collection/wishlist, есть info-pill, цена и кнопка «Купить» работают, детальный экран не падает.
- `POST /api/collections/items` с store-native record_id → 400 с понятным error message.

### Metrics
- В логах `match batch:` новый счётчик `store_native_created`.
- Цель: рост matched-доли без взрыва Records. Если `store_native_created/день > 1000` — anti-noise gate сломался.

---

## Out of scope (Phase 2)

- **Merge tool** `store-native Record → Discogs Record` с переносом всех FK (CollectionItem, WishlistItem, Message.attached_record_id) в одной транзакции. Это блокер для разблокировки add-to-collection.
- **Auto-merge** на основе `discogs_id_candidate` из re-match cron (нужен human review на первом этапе).
- **Admin UI** для ручного merge / split / удаления store-native.
- После Phase 2 — снять guard на add-to-collection/wishlist для store-native.
