# Парсинг магазинов винила — единый документ

> Living document. Обновляй когда меняешь архитектуру, добавляешь магазин или находишь подводный камень.

---

## 1. Зачем мы это делаем

В Вертушке у юзера на карточке пластинки есть **«Примерная стоимость»** (median по Discogs Marketplace USD → ₽). Это справочная цифра — не значит что прямо сейчас её где-то можно купить.

**Цель:** показывать **живые предложения** реальных РФ-магазинов. Юзер открывает Khruangbin – Mordechai → видит «4 990 ₽ в Коробке Винила, [Купить]» → тапает → попадает на сайт магазина → покупает.

Дополнительно: партнёрские ссылки (Admitad/EPN) — пассивный доход с покупок.

---

## 2. Как часто обновляется (точное расписание)

**Парсер обновляется не еженедельно, а намного чаще** — это твоё уточнение из чата. Точная картина:

| Задача | Когда | Что делает | Файл |
|---|---|---|---|
| `daily_market_sync` | **каждый день в 02:00** | Цепочка: полный обход HTTP-магазинов → матчинг → сброс offers-кэша → обложки. Магазины параллельно (`SCRAPER_CONCURRENCY`, дефолт 5) | `tasks/scraper_tasks.py` |
| `weekly_full_crawl_browser` | каждую **субботу в 02:00** | Полный обход магазинов с Cloudflare (через Playwright) | там же |
| `daily_incremental_crawl_browser` | **каждый день в 05:30** | Новинки browser-магазинов (по lastmod из sitemap) | там же |
| `incremental_market_sync` | **каждый день в 14:00** | Новинки HTTP-магазинов той же цепочкой crawl→match→offers→covers | там же |
| `stock_refresh_active` | **каждые 6 часов** | Точечно перепарсивает URL протухших (>6ч) листингов, привязанных к Record. 404/410 → `removed` | там же |
| `hourly_match_unmatched` | **каждый час**, batch 2000 | Привязывает свежие листинги к Record | там же |
| `weekly_cleanup_stale` | каждое **воскресенье в 04:00** | Удаляет листинги с `last_seen_at > 30 дней` | там же |
| `invalidate_offers_for_recently_updated` | **каждые 15 минут** | Сбрасывает Redis-кэш `/offers` для свежих изменений | там же |

**Включается флагом** `SCRAPERS_ENABLED=true` в env прод-инстанса. На dev держим `false` — парсим вручную через CLI.

**Smoke-check после каждого crawl** (`runner._smoke_check`): если магазин с историей листингов внезапно отдал 0 discovered (или <10% от истории при full-обходе, или >50% ошибок) — `last_successful_scrape_at` не обновляется, в `store.last_error` пишется диагноз, в лог летит ERROR (попадает в GlitchTip). Ловит «магазин сменил HTML → парсер тихо умер».

**Что это значит для юзера:**
- Цена в магазине поменялась → у юзера в приложении актуальная **в течение 6 часов** (точечный refresh именно протухших листингов)
- Новая пластинка появилась в продаже → видна **в маркете сразу после обхода** (02:00 / 14:00 — матчинг и обложки в той же цепочке, без межзадачного лага 1–3 ч)
- Снятая с продажи → 404/410 ловится stock-refresh'ем → исчезает за часы; страховочный cleanup по `last_seen_at > 30 дней` остаётся

---

## 3. Архитектура одним рисунком

```
┌──────────────────┐  ежедневно   ┌──────────────────┐
│ Sitemap магазина │ ──────────► │ Парсер магазина  │
│ (sitemap.xml/YML)│              │ (BaseStoreParser)│
└──────────────────┘              └────────┬─────────┘
                                            │ ListingDTO
                                            ▼
                                  ┌──────────────────┐
                                  │  store_listings  │ ← UPSERT по (store_id, external_id)
                                  │  (БД, ~600 байт) │
                                  └────────┬─────────┘
                                            │ каждый час
                                            ▼
                              ┌─────────────────────────┐
                              │   listing_matcher       │
                              │ 1. discogs_release_url  │ ─┐
                              │ 2. barcode (EAN-13)     │ ─┤  каскад до первого
                              │ 3. catalog_number       │ ─┤  попадания
                              │ 4. fuzzy (artist+title) │ ─┤
                              │ 5. on-demand Discogs    │ ─┘  ← создаёт Record
                              │    (если нет в БД)      │     если в Discogs нашёлся
                              └────────┬────────────────┘
                                       │ matched_record_id
                                       ▼
                            ┌──────────────────┐
                            │     records      │ ← уже есть от Discogs
                            │  (БД, ~5 КБ)     │
                            └────────┬─────────┘
                                     │
                                     ▼
                       ┌──────────────────────────────────┐
                       │ GET /api/records/{discogs_id}/   │ ← Mobile дёргает
                       │     offers   (Redis кэш 30 мин)  │
                       └──────────────┬───────────────────┘
                                      ▼
                          ┌────────────────────┐
                          │  <OffersBlock />   │ ← на карточке пластинки
                          │  [4 990 ₽ Купить]  │
                          └────────────────────┘
```

---

## 4. Что видит конечный юзер

На экране пластинки между блоками «Примерная стоимость» и «Треклист»:

```
┌──────────────────────────────────────────┐
│  ГДЕ КУПИТЬ                              │
│                                          │
│  🏪 Коробка Винила     4 990 ₽  Купить → │
│      LP · Red                             │
│                                          │
│  🏪 Plastinka.com      4 890 ₽  Купить → │
│      LP · Black                           │
│                                          │
│  🏪 Vinyla.ru          5 200 ₽  Купить → │
│      LP · Black · Предзаказ              │
│                                          │
│  Цены и наличие — со страниц магазинов,  │
│  обновляются ежедневно.                  │
└──────────────────────────────────────────┘
```

При тапе «Купить» → `Linking.openURL(offer.url)` открывает страницу магазина в браузере / приложении. Через Admitad-link если у магазина есть партнёрка.

**Что НЕ показываем:**
- Out of stock (отфильтрованы)
- «По запросу» без цены
- Старее 7 дней `last_seen_at` (на случай если парсер сломался — лучше пусто чем устаревшая цена)

---

## 5. Что лежит в БД

| Таблица | Сколько строк на 30 магазинов | Размер |
|---|---|---|
| `stores` | 30 | ~5 КБ |
| `store_listings` | ~150 000 | **~100 МБ** + индексы |
| `records` (новые от on-demand) | +50-100к (поверх существующих 442) | **+250-500 МБ** |
| **Итого +/- в БД** | | **~400-700 МБ** разово |

Растёт незначительно: при следующих прогонах UPSERT, не append. Cleanup раз в неделю чистит stale.

---

## 6. Текущий статус (16.05.2026)

### ✅ Готово (закоммичено)
- [x] **Backend инфра**: модели Store/StoreListing, миграция с pg_trgm, парсер-фреймворк, matcher, API endpoint
- [x] **Cron-задачи** для APScheduler (под флагом)
- [x] **CLI**: `python -m app.scripts.scrape_all` (для ручных прогонов и backfill)
- [x] **Сидинг магазинов**: `python -m app.scripts.seed_stores`
- [x] **Dev-среда**: локальный Supabase + Redis в Docker, Makefile-команды
- [x] **Пилотный парсер**: `korobkavinyla` — Tilda-магазин, ~3500 товаров. **Проверено на 200 — 199 matched (99.5%)**
- [x] **Store-API принцип** (`shops/_tilda_store.py`): `TildaStoreParser` — весь каталог Tilda одним API вместо per-page. Первый магазин — **Found** (`shops/found.py`): live-проверка 1652 товара за ~17 запросов, parse-rate 98/100 (§9.1)
- [x] **Mobile**: типы Offer/Store, `api.getRecordOffers()`, `<OffersBlock />`, analytics
- [x] **Affiliate Phase A** (коммит `86d3526`): таблица `offer_clicks`, `POST /api/offers/{id}/click`, UTM-обёртка для всех ссылок, каркас под Admitad/direct
- [x] Документация: [DEV_SETUP_LOCAL.md](dev/DEV_SETUP_LOCAL.md), этот файл, [AFFILIATE_OUTREACH_TEMPLATE.md](AFFILIATE_OUTREACH_TEMPLATE.md)

### ⚠️ В работе / не закоммичено
- [ ] **Встройка `<OffersBlock />` в `Mobile/app/record/[id].tsx`** — лежит в твоём working tree, отделена от твоей параллельной работы над preview-mode. Закоммить когда сольёшь preview-mode.
- [x] **Фикс `rate_limiter` для `Priority.ENRICHMENT`** — закрыт коммитом `b4f09eb` (ленивый старт processor task в `acquire()`). Проверено 12.06: 5 acquires с ENRICHMENT из голого скрипта без lifespan — мгновенно, без 30s-таймаута. Блокер на `SCRAPERS_ENABLED=true` снят.

### ⏳ Не начато
- [ ] Сидинг следующих магазинов (см. §8)
- [ ] Парсеры для них (по одному, ~30 мин на магазин)
- [ ] Playwright pool (нужен для магазинов под Cloudflare)
- [ ] **Affiliate Phase B-direct** — outreach к владельцам после 1-2 мес UTM-данных (см. §13)
- [ ] **Affiliate Phase B-CPA** — регистрация в Admitad (только если будут маркетплейсы)
- [ ] **Affiliate Phase C** — cron `fetch_affiliate_conversions` + дашборд
- [ ] Админ-страница `/admin/unmatched` для ручной привязки
- [x] Smoke-tests парсеров — `runner._smoke_check` после каждого crawl (0 discovered / <10% от истории / >50% ошибок → ERROR-лог + `store.last_error`, см. §2)
- [ ] Кнопка «Не нашёл? Запросить парсинг» — для отсутствующих магазинов
- [ ] Расширение «source=store Record» (релизы которых нет в Discogs) — **только если будет нужно** после реальных цифр

---

## 7. Roadmap по фазам

### Фаза 0 — фундамент ✅ **DONE**
Парсер-фреймворк + 1 пилотный магазин + Mobile блок. Доказано что цепочка работает.

### Фаза 1 — 5-10 магазинов (2-3 недели) ← **СЛЕДУЮЩИЙ ШАГ**
1. ~~Фиксануть `rate_limiter` (Priority.ENRICHMENT timeout)~~ ✅ `b4f09eb`
2. Добавить 5-9 парсеров для магазинов **с sitemap + JSON-LD** (это самые простые)
3. Локальный smoke-тест каждого
4. Включить `SCRAPERS_ENABLED=true` на staging
5. Неделю наблюдать: % matched, ошибки, нагрузка

### Фаза 2 — все 30+ магазинов + сложные кейсы (3-4 недели)
1. Playwright pool для магазинов под Cloudflare
2. Парсеры для оставшихся ~20 магазинов
3. Прокси-пул (через env `SCRAPER_PROXIES`)
4. Initial backfill через CLI (по 2-3 магазина в день)

### Фаза 3 — мониторинг и оптимизация (2-3 недели)
1. `parsers_smoke_test` cron — каждую ночь сверяет 3 эталонных URL с фикстурой
2. Sentry/Slack-алерт если smoke fail → автодеактивация магазина
3. Дашборд «здоровье парсеров» (`/admin/scrapers`)
4. История цен (`listing_price_history`) + график на карточке
5. Click-tracking (`offer_clicks`) для CTR-метрик

### Фаза 4 — UX-расширение и монетизация (параллельно)

**4.0 UX поверх данных парсера** — см. [OFFERS_UX.md](OFFERS_UX.md)

5 фич роста использования offer-данных в приложении:
- **Фича 1** — push-уведомления о вишлисте (точный матч + другая версия мастера)
- **Фича 2** — бейдж «В продаже» с минимальной ценой на карточках поиска/коллекции
- **Фича 3** — чип-фильтр «🟢 В продаже» в поиске
- **Фича 4** — витрина «Маркет» (карусель «свежее» на главной + полный экран)
- **Фича 5** — в вишлисте swipe вправо → drawer со сравнением цен → BottomSheet с деталями

**4.1+ Монетизация** — см. §14 ниже. Кратко:

**4.1 Direct-партнёрки с винил-магазинами** (главный канал — нишевая аудитория)
- Накопить 1-2 месяца UTM-данных по каждому магазину (трафик в их GA)
- Написать владельцам с цифрами «мы дали вам X юзеров за месяц»
- Договориться о 3-8% с продаж + промокод/трекинг-параметр
- Заполнить `Store.affiliate_program` типом `direct` с `promo_code` и `commission_pct`

**4.2 CPA-сети для маркетплейсов** (доп.канал — OZON/WB)
- Зарегистрироваться в Admitad как паблишер (ИП/самозанятый)
- Подключить только тех рекламодателей где есть винил: OZON, WB, СберМегаМаркет
- Заполнить `Store.affiliate_program` типом `admitad`/`epn`

**4.3 Аналитика и UX**
- Cron `fetch_affiliate_conversions` (Phase C по affiliate-документу)
- Дашборд: магазины × клики × конверсии × выплаты
- UX-эксперимент: порядок магазинов (по цене / по комиссии / по рейтингу)

---

## 8. Список магазинов (план)

> Заполняй по мере того как реально парсишь. Колонки:
> - **Сложность**: sitemap+JSON-LD = easy, нужен JS-рендеринг или CF = hard
> - **Affiliate-канал**: «direct» = договариваемся напрямую с владельцем, «admitad» = есть в каталоге Admitad/EPN, «utm» = только UTM-трекинг без денег

| # | Магазин | URL | Статус | Сложность | Affiliate | Заметки |
|---|---|---|---|---|---|---|
| 1 | Коробка Винила | korobkavinyla.ru | ✅ парсер готов, 199/200 match | easy (Tilda) | direct (?) | `tproduct/`, sku=EAN-13 |
| 2 | Plastinka.com | plastinka.com | ⏳ | ? | direct | флагман РФ-винила с 2008, ~10k+ позиций |
| 3 | Vinylpark | vinylpark.ru | ⏳ | ? | direct | моют Б/У в вакууме, нишевая аудитория |
| 4 | Vinyl.ru | vinyl.ru | ⏳ | ? | direct | 20k+ позиций, центр Москвы |
| 5 | Vinylmarkt | vinylmarkt.ru | ⏳ | ? | direct | быстрая доставка по МСК |
| 6 | Collectomania | collectomania.ru | ⏳ | ? | direct | широкая география доставки |
| 7 | Audiomania (винил-раздел) | audiomania.ru/vinilovye_plastinki | ⏳ | medium | direct/admitad? | проверить — могут быть в CPA-сетях |
| 8 | MarketVinila | marketvinila.ru | ⏳ | ? | direct | агрегатор «весь винил России» |
| 9 | Vinyla.ru | vinyla.ru | ⏳ | возможно CF | direct | |
| 10 | DTH Music | dth-music.ru | ⏳ | ? | direct | |
| 11 | Союз | soyuz.ru | ⏳ | medium (Bitrix?) | utm/direct | крупный, винил — небольшая категория |
| 12 | Stereozona (СПб) | stereozona.ru | ⏳ | ? | direct | СПб-аудитория |
| 13 | Мир Винила | mirvinila.com | ⏳ | ? | direct | |
| 14 | Found | pizza.foundmoscow.com/vinyl | ✅ парсер готов, 98/100 parse-rate | easy (Tilda store-API) | direct | **новый принцип** — весь каталог 1 API, ~1.6k товаров; barcode нет, матч по artist+title |
| — | OZON (винил) | ozon.ru | потом | — | **admitad** | если будут пользовательские запросы |
| — | Wildberries (винил) | wildberries.ru | потом | — | **admitad** | то же самое |

---

## 9. Чек-лист «как добавить новый магазин»

Шаги примерно по 30 минут на магазин (опытно):

1. **Разведка URL** (5 мин):
   ```bash
   curl -s https://shop.ru/robots.txt | head
   curl -s https://shop.ru/sitemap.xml | head -20
   ```
   Если sitemap пустой — поискать sitemap-products.xml, /yml.xml, /feed.xml.

2. **Посмотреть HTML товара** (10 мин):
   - Найти 2-3 случайных товара
   - Проверить наличие JSON-LD (`<script type="application/ld+json">`)
   - Если есть — извлечение тривиальное
   - Если нет — изучить CSS-классы / microdata

3. **Написать парсер** (10 мин): скопировать `shops/_template.py.example` → `shops/{slug}.py`, заполнить `parse_listing()`.

4. **Зарегистрировать** в `shops/__init__.py`: `from app.services.scrapers.shops import {slug}`

5. **Добавить в сидинг** `app/scripts/seed_stores.py` → STORES list.

6. **Локальный тест**:
   ```bash
   make seed
   ./venv/bin/python -m app.scripts.scrape_all --slug={slug} --limit=20 --no-match
   docker exec supabase_db_vertushka psql -U postgres -d postgres \
     -c "SELECT count(*), count(price_rub IS NOT NULL) FROM store_listings WHERE store_id IN (SELECT id FROM stores WHERE slug='{slug}');"
   ```

7. **Проверить match-rate**: `make scrape-match`.

8. **Если match-rate < 90%** — посмотреть какие поля плохо извлекаются (barcode? catalog?).

### 9.1 Два принципа harvest'а каталога

**Старый принцип (sitemap + per-page):** `discover_urls()` из sitemap → `parse_listing(url)` на каждый товар. N запросов на N товаров (korobkavinyla ≈ 3500). Подходит магазинам без публичного data-API.

**Новый принцип (store-API):** магазин отдаёт весь каталог одним JSON-эндпоинтом, парсер тянет его постранично — десятки запросов вместо тысяч. Вежливее, быстрее, данные структурированы.

**Tilda-магазины** (Found, и korobkavinyla тоже может мигрировать) — реализован в `shops/_tilda_store.py` (`TildaStoreParser`):

```
GET https://store.tildaapi.com/api/getproductslist/
    ?storepartuid=<storepart>&recid=<recid>&getparts=true&slice=<page>&size=100
→ {"total": N, "products": [{uid,title,price,priceold,quantity,gallery,url,...}, ...]}
```

`recid` / `storepart` берутся из HTML витрины — в вызове `t_store_init('<recid>', {... storepart:'<storepart>' ...})`. Подкласс задаёт `store_recid`/`store_partuid` и реализует только `parse_product(dict) → ListingDTO | None` (None = пропустить нон-медиа). `crawl_full`/`refresh_urls` переопределены в базе (refresh — один проход каталога + map по `uid` из url).

Пример Found: `title` = `«Виниловая пластинка {Artist} – {Album} (формат, год) [Лейбл, год] Style: жанры»`, sku/characteristics пусты → barcode нет, матч по artist+title (fuzzy + on-demand Discogs). Парсинг title в `shops/found.py:_parse_title`.

**Чек-лист для Tilda-магазина** (вместо шагов 1–4 выше): `curl` витрину → найти `t_store_init(...)` → скопировать recid+storepart → `shops/{slug}.py(TildaStoreParser)` с `parse_product()`.

---

## 10. Деплой на прод

### Первый раз
```bash
# 1. Деплой кода
git push origin main
ssh deploy@85.198.85.12 'cd ~/vertushka && bash Backend/scripts/deploy.sh'

# 2. На проде применить миграции (deploy.sh должен это делать сам)
ssh deploy@85.198.85.12 'cd ~/vertushka/Backend && alembic upgrade head'

# 3. Засеять магазины
ssh deploy@85.198.85.12 'cd ~/vertushka/Backend && python -m app.scripts.seed_stores'

# 4. ВРУЧНУЮ прогнать 1 магазин с ограничением (НЕ включать cron!):
ssh deploy@85.198.85.12 'cd ~/vertushka/Backend && python -m app.scripts.scrape_all --slug=korobkavinyla --limit=50'

# 5. Проверить через API:
curl https://api.vinyl-vertushka.ru/api/records/7782094/offers | jq

# 6. Если ОК — включить cron:
# в .env прода: SCRAPERS_ENABLED=true
# рестарт API сервиса
```

### Кнопка «выключить парсер»
В случае проблем:
```sql
UPDATE stores SET is_active=false WHERE slug='{slug}';
-- ИЛИ всех:
UPDATE stores SET is_active=false;
```
+ убрать env-флаг и рестарт.

---

## 11. Подводные камни

### Юридические
- **Чистый скрапинг без договорённостей** — техническая зона риска (ст. 1276 ГК, нарушение ToS магазинов).
- **Митигация:**
  - Уважение `robots.txt` (автоматически в `app/services/scrapers/robots.py`)
  - Низкий rate-limit `0.5 req/sec` per-shop (1 запрос в 2 секунды)
  - Атрибуция «Данные с сайта *plastinka.com*» в UI (пока нет — добавить в Фазе 3)
  - Готов kill-switch `is_active=false` для любого магазина
  - Магазины-«доски» (где продавцы-частники, типа Avito) — **не парсим** (152-ФЗ риски)

### Технические
| Риск | Защита |
|---|---|
| Магазин поменял HTML → парсер ломается | smoke-test (Фаза 3) + auto-disable магазина |
| Cloudflare блокирует | автодетект → Playwright + `cloudscraper` |
| Прод-инстанс на иностранном IP → 403 от РФ-магазинов | парсер-воркер должен быть на РФ-IP (Selectel/Timeweb) |
| Discogs hourly cap (60 req/min) | per-priority rate-limiter, on-demand cap 50/час |
| Postgres рост | autovacuum + еженедельный cleanup_stale + опционально партиционирование price_history |

### Качество данных
| Проблема | Что делаем |
|---|---|
| Магазин неверно указал год/формат | Парсер «робко» (`try/except` на каждом поле, `None` допустим) |
| «По запросу» без цены | Статус `on_request`, не отдаём в API |
| Разные варианты pressing (оригинал/репресс) | `ListingDTO.variants` → разные `external_id` |
| Дубликаты между магазинами | Норма! Разные магазины ➜ разные листинги ➜ один Record |

---

## 12. Метрики успеха

Что мерять чтобы понять «работает или нет»:

| Метрика | Цель | Где смотреть |
|---|---|---|
| **% matched** среди свежих листингов | >85% | `SELECT match_method, count(*) FROM store_listings GROUP BY 1` |
| Coverage: сколько пластинок в БД имеют хотя бы 1 offer | >40% (по Mobile-юзерам) | `SELECT count(DISTINCT matched_record_id) FROM store_listings` |
| **CTR кнопки «Купить»** | >15% от просмотров карточки | Amplitude: `offer_click` / `view_record` |
| Smoke-test pass-rate | 100% (автодизайбл при fail) | дашборд `/admin/scrapers` (Фаза 3) |
| Среднее время первого UX `/offers` | <300 мс | Sentry performance |
| Конверсия в покупку (Phase 4) | TBD | Affiliate-партнёрка отчёты |

---

## 13. Affiliate-стратегия: гибрид (direct + CPA)

> Реалистичная картина РФ 2026: винил — нишевая вертикаль, в крупных CPA-сетях
> (Admitad, EPN, CityAds) специализированных винил-магазинов **почти нет**.
> Поэтому ставим на **гибрид**: direct для нишевых, CPA для маркетплейсов.

### 13.1 Direct-партнёрки (основной канал, винильные магазины)

**Принцип:** мы — поставщик трафика. Магазин видит наши UTM в Google Analytics → платит % от заказов с этих UTM. Без посредников. Без CPA-сетей.

**Технически** в `Store.affiliate_program` JSONB:
```json
{
  "type": "direct",
  "deeplink_template": null,
  "params": {},
  "commission_pct": 5.0,
  "promo_code": "VERTUSHKA10",
  "contact": "owner@plastinka.com",
  "negotiated_at": "2026-06-15",
  "payout_method": "bank_transfer | yandex_pay | crypto",
  "notes": "5% от чистого заказа, выплата 1-го числа месяца"
}
```

`wrap_url()` для `type: "direct"` отдаёт исходный URL + UTM-метки.
Магазин в своём GA фильтрует `utm_source=vertushka` → видит наши заказы.
Если есть `promo_code` — Mobile может показывать «Промокод VERTUSHKA10 — 10% скидка от партнёра».

**Workflow договорённости:**

1. **Накопить данные** (1-2 месяца после запуска парсера):
   - SQL: сколько кликов на магазин, на какие пластинки
   - Скриншот их Google Analytics — найди в Audience → Traffic Sources → `utm_source=vertushka`

2. **Написать владельцу** — см. шаблон [AFFILIATE_OUTREACH_TEMPLATE.md](AFFILIATE_OUTREACH_TEMPLATE.md)

3. **Договориться об условиях:**
   - Комиссия: обычно 3-8% для винила (это маржинальный товар, ритейлеры могут пойти на 5%)
   - Промокод (даёт юзеру скидку = аргумент кликнуть именно через нас)
   - Метод выплаты: банк/Юmoney/крипта/взаимозачёт за рекламу
   - Юр.форма: ИП ↔ ИП через ЭДО (для сумм >100к/мес — обязательно)

4. **Настроить** `Store.affiliate_program` через SQL (или admin-страница, когда будет)

5. **Раз в месяц** — сводка по магазину (свой SQL-отчёт), сверка с магазином, выплата

**Целевой пул:** 5-10 magазинов в первый год. Не больше — каждый = договор + ежемесячный учёт.

### 13.2 CPA-сети (Admitad — для маркетплейсов)

Для **маркетплейсов** (OZON, WB, СберМегаМаркет, Lamoda — у них есть винильные категории) — стандартный Admitad-flow:

1. **Регистрация паблишером** на admitad.com (нужно ИП / самозанятый в РФ)
2. **Подключить только нужных рекламодателей** из их каталога — фильтр по `Категория = Музыка/Винил/Грампластинки`
3. **Получить deeplink-токен** для каждого магазина (1 строка в Store.affiliate_program)
4. **Заполнить** `Store.affiliate_program`:
   ```json
   {
     "type": "admitad",
     "deeplink_template": "https://ad.admitad.com/g/{token}/?ulp={url}&subid={subid}",
     "token": "abc123xyz",
     "commission_pct": 5.0,
     "cookie_window_days": 30
   }
   ```

Admitad в РФ работает (Mitgo-холдинг переехал в Люксембург в 2022, но российская часть выделена в отдельное юрлицо и платит ИП/самозанятым).

### 13.3 Что уже сделано (Phase A, коммит `86d3526`)

- ✅ Таблица `offer_clicks` — лог каждого тапа «Купить»
- ✅ Endpoint `POST /api/offers/{id}/click` — пишет клик, возвращает финальный URL
- ✅ `services/affiliate.wrap_url(store, url, subid)` — собирает Admitad / EPN / direct ссылку с UTM
- ✅ Mobile `OffersBlock` уже дёргает `trackOfferClick` перед `openURL`

**То есть инфра готова сразу под оба сценария** — direct и CPA. Когда будет договорённость, просто заполняешь JSON в `stores.affiliate_program`.

### 13.4 Roadmap affiliate

| Шаг | Когда | Что делаем |
|---|---|---|
| **A0** ✅ DONE | сейчас | Клик-трекинг + UTM на всех ссылках |
| **A1** | по мере добавления магазинов | UTM-данные накапливаются |
| **B1** | через 1-2 месяца после первых 5 парсеров | Письма владельцам с UTM-цифрами → direct-договорённости |
| **B2** | параллельно | Регистрация в Admitad как паблишер (если хочется маркетплейсы) |
| **C** | когда будут первые конверсии | Cron `fetch_affiliate_conversions`, дашборд, A/B сортировки |

### 13.5 Юр.и налоговые тонкости

- **До первой выплаты** — можно не оформлять ИП (но обсудить с магазином что выплата будет физлицу). Это срабатывает 1-2 раза для теста.
- **При регулярных выплатах** — обязательно ИП или самозанятый. Самозанятый проще (≤2.4М₽/год, 6% налог), ИП — если планируешь масштаб.
- **С Admitad** — выплата идёт от их юрлица (РФ-часть платит ИП/самозанятым) → стандартный 6% налог + чек.
- **При direct-партнёрке** — магазин платит как услугу «маркетинг/трафик» → чек от тебя как ИП/самозанятого → они учитывают в расходах.

### 13.6 Что НЕ делаем (антипаттерны)

- ❌ Не открывать affiliate-ссылки в встроенном WebView — cookie сломается. Только `Linking.openURL()` в системный браузер.
- ❌ Не использовать app-to-app deeplinks (`shop-app://product/123`) — affiliate-cookie не передастся. Только HTTPS-ссылки.
- ❌ Не показывать affiliate-ссылку в текстовом виде («скопируй URL и вставь») — последовательность кликов потеряется, конверсии не будет.
- ❌ Не подключать Admitad для нишевых винил-магазинов — их там нет, время потратишь, ноль outcomes.

---

## 14. Что от тебя сейчас

В порядке приоритета:

1. **Слить твою preview-mode правку** в `Mobile/app/record/[id].tsx` + закоммитить вместе с добавленной строкой `<OffersBlock />`.
2. **Прислать мне список магазинов** (топ-10 которые хочешь подключить первыми) — для каждого пройду чек-лист §9 (по 30 мин).
3. ~~**Решить про rate_limiter фикс**~~ — ✅ закрыт `b4f09eb` (ленивый старт processor).
4. **Подумать про affiliate** — есть ли уже договорённости с кем-то? Параметры Admitad/EPN?
5. **Когда будут 5+ магазинов** — задеплоить и неделю наблюдать (фаза 1).

---

## Связанные документы

- [OFFERS_UX.md](OFFERS_UX.md) — **детальный UX-план** (бейджи, уведомления, маркет, swipe-сравнение)
- [AFFILIATE_OUTREACH_TEMPLATE.md](AFFILIATE_OUTREACH_TEMPLATE.md) — шаблон письма владельцу магазина
- [DEV_SETUP_LOCAL.md](dev/DEV_SETUP_LOCAL.md) — как поднять локально
- `~/.claude/plans/compiled-churning-taco.md` — исходный архитектурный план (тех-уровень)
- [Backend/app/services/scrapers/](../../Backend/app/services/scrapers/) — код парсер-фреймворка
- [Backend/app/services/listing_matcher.py](../../Backend/app/services/listing_matcher.py) — каскад матчинга
- [Backend/app/api/offers.py](../../Backend/app/api/offers.py) — API endpoint
- [Mobile/components/OffersBlock.tsx](../../Mobile/components/OffersBlock.tsx) — Mobile блок
