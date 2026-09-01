# Парсинг магазинов — операционная инструкция

> Что делает наша scraping-инфра, какие у неё периодичность, лимиты и ресурсы.
> План более высокого уровня (UX, бизнес-логика, аффилиаты) — в [SHOPS_PARSING.md](SHOPS_PARSING.md).
> Будущее решение независимости от Discogs API — в [DISCOGS_DATA_DUMPS.md](../discogs/DISCOGS_DATA_DUMPS.md).

---

## 1. Общая архитектура

```
┌──────────────┐    sitemap.xml      ┌──────────────┐
│   Магазин    │ ─────────────────► │  Discovery   │
│  (сайт)      │   ~5к-50к URL'ов   │  layer       │
└──────────────┘                    └──────┬───────┘
                                           │ URL each ~2s
                                           ▼
                                    ┌──────────────┐
                                    │ HTTP fetcher │  httpx async + Cloudflare detect
                                    │ + rate limit │  + per-domain circuit breaker
                                    └──────┬───────┘
                                           │ HTML
                                           ▼
                                    ┌──────────────┐
                                    │   Parser     │  Per-shop: regex / Schema.org /
                                    │ (per-shop)   │  microdata / Tilda JSON
                                    └──────┬───────┘
                                           │ ListingDTO
                                           ▼
                                    ┌──────────────┐
                                    │   UPSERT     │  ON CONFLICT (store_id, ext_id)
                                    │ store_listings│  DO UPDATE SET status/price/...
                                    └──────┬───────┘
                                           │
                                           ▼
                                    ┌──────────────┐    Discogs API
                                    │   Matcher    │ ─────────────────►
                                    │ (отдельный)  │   barcode / artist+title
                                    └──────┬───────┘   ◄────  record_id
                                           │
                                           ▼
                                    matched_record_id
                                           │
                                           ▼
                              ┌──────────────────────┐
                              │  /api/market endpoint │  Redis cache + 1 SQL
                              │  Mobile app: карусель │
                              └──────────────────────┘
```

**Стек:**
- `httpx` (async HTTP с HTTP/2) + кастомные circuit-breaker / token-bucket per-domain
- `BeautifulSoup4` + `lxml` для парсинга HTML
- `Tilda product JSON` для магазинов на Tilda (regex `var product = {...};`)
- `Schema.org microdata` (`itemprop=...`) для магазинов с грамотной разметкой
- `APScheduler` cron в scheduler-контейнере
- `Redis` для кэша + rate-limiter counter'а

---

## 2. Какие форматы парсим

**Не только винил.** Магазины торгуют разными носителями, мы сохраняем всё что в каталоге, размечая через `ListingDTO.format_raw`:

| Формат | Значение `format_raw` | Где |
|---|---|---|
| LP / 12" винил | `LP` или `Vinyl` | основной формат |
| 7" сингл | `7"` или `7 inch` | |
| CD | `CD` | у Plastinka — отдельный `/cd/`; у Tilda-магазинов в общем sitemap |
| Cassette | `Cassette` | редко, но есть |
| Box Set | `Box Set` | подарочные/коллекционные издания |
| File | `File` | цифровые (редко в физических магазинах) |

**Определение формата** — `extractors.infer_format()` ищет в тексте страницы. Парсер per-shop **обязан** заполнить `format_raw`; если не уверен — ставит `LP` (дефолт для винил-магазинов).

### Что показывать пользователю

API endpoint `/api/market/new-arrivals` сейчас **не фильтрует** по формату — карусель показывает всё. Решение per-UX (фильтр «только LP» / отдельные карусели по форматам / иконка-маркер) — на будущее, см. `OFFERS_UX.md`.

---

## 3. Per-shop парсеры

Каждый магазин = отдельный класс-наследник `BaseStoreParser` в `Backend/app/services/scrapers/shops/<slug>.py`. Регистрация через `@register_parser("<slug>")`.

| Slug | Магазин | URL pattern | Поля доступны | Статус |
|---|---|---|---|---|
| `korobkavinyla` | Коробка Винила | `/tproduct/{rootpartid}-{barcode}-{slug}` | barcode (EAN из URL/SKU), quantity (для out-of-stock), цена, артист/альбом из title | ✅ Активен, 5к+ листингов |
| `plastinka_com` | Plastinka.com | `/lp/item/{id}-{slug}` (LP) | artist/album/year/condition из title regex, price/availability из Schema.org; **нет barcode** | ✅ Активен, ~7к LP. CD (`/cd/item/`) пока **не парсим** — TODO |

### Что должен реализовать новый парсер

1. **`base_url`, `slug`** — атрибуты класса
2. **`sitemap_paths`** — массив путей к sitemap (если не стандартный `/sitemap.xml`)
3. **`listing_url_pattern`** — regex для фильтра URL'ов из sitemap (например, только `/lp/item/\d+`)
4. **`rate_limit_per_sec`** — обычно `0.5` (1 запрос в 2 секунды) — вежливо к магазину
5. **`async def parse_listing(url) -> ListingDTO`** — главный метод: скачать HTML, извлечь поля

### Поля `ListingDTO` (что заполнять)

| Поле | Что | Обязательно |
|---|---|---|
| `external_id` | ID товара в магазине (для UPSERT) | ✅ |
| `url` | Прямая ссылка на товар | ✅ |
| `title_raw`, `artist_raw` | Название и артист | ✅ |
| `year_raw` | Год | желательно |
| `format_raw` | LP/CD/Cassette/Box | желательно |
| `price_rub`, `status` | Цена в рублях, `in_stock` / `out_of_stock` / `preorder` / `on_request` | ✅ |
| `barcode` (EAN-12/13) | для on-demand Discogs fetch | **очень желательно** |
| `catalog_number` | каталожный номер лейбла | желательно |
| `discogs_release_url` | если магазин ставит ссылки | редко |
| `vinyl_color_raw`, `condition` | детали | опционально |
| `image_url` | обложка | опционально |
| `raw_payload` | dict со всем остальным сырым (для дебага) | свободно |

**Зачем barcode критичен:** matcher идёт в Discogs API → находит record по barcode → создаёт нашу запись `records` → ставит `matched_record_id` на листинг → листинг попадает в карусель. Без barcode — fallback на `artist+title` search (есть, но менее точен).

---

## 4. Cron-расписание

Все задачи в `Backend/app/tasks/scraper_tasks.py`, регистрируются в `main.py` только в scheduler-контейнере (`IS_SCHEDULER=true`).

| Задача | Расписание | Что делает | Время на 10 магазинов |
|---|---|---|---|
| `daily_incremental_crawl` | каждую ночь 03:00 | Парсит только URL'ы с `<lastmod>` сегодня. Дельты ~50-200 на магазин | 10-30 мин |
| `weekly_full_crawl_*` | пн-сб 02:00 по группам | Полный обход sitemap каждого магазина (sanity check) | 2-4 часа на магазин |
| `stock_refresh_active` | каждые 6 часов | Повторно парсит листинги уже-в-карусели — проверка цены/наличия | 5-15 мин |
| `hourly_match_unmatched` | каждый час | Сматчить batch из 200 unmatched (создать `records` через Discogs API) | 5-10 мин (упирается в hourly limit) |
| `weekly_cleanup_stale` | вс 04:00 | Удалить листинги с `last_seen_at < 30 дней` | секунды |
| `parsers_smoke_test` | каждый день 08:00 | Парсит 3 эталонных URL/магазин, сверяет с фикстурой → детект сломанного селектора | минуты |

**Сейчас включено в проде**: `SCRAPERS_ENABLED=true` flag в env (после доработок 18.05). До этого cron был выключен — парсили вручную через CLI.

### CLI команды (ручной запуск)

```bash
# Все магазины активны / зарегистрированы
python -m app.scripts.scrape_all --list

# Один магазин, полный обход
python -m app.scripts.scrape_all --slug=korobkavinyla --mode=full

# С лимитом для тестов
python -m app.scripts.scrape_all --slug=plastinka_com --mode=full --limit=50

# Только матчинг unmatched (Discogs API)
python -m app.scripts.scrape_all --match-only --batch=500

# Перепарсить уже-известные in_stock URL (после фикса парсера)
python -m app.scripts.scrape_all --refresh-known --slug=korobkavinyla
```

---

## 5. Лимиты и rate-limiting

### Per-domain (к самим магазинам)

`Backend/app/services/scrapers/http_client.py` — `_DomainBucket`:
- `capacity=2` (burst), `refill_rate=0.5` (1 req/2s)
- Per-domain — параллельные магазины не мешают друг другу
- Цель: не задудосить магазин, не получить бан по IP

### Discogs API (наша глобальная квота)

`Backend/app/services/rate_limiter.py` — `TokenBucketRateLimiter`:
- `capacity=55`, `refill_rate=0.95/s` = ~57 req/min
- Discogs официальный лимит: **60 req/min** на токен
- Приоритеты: `SEARCH > DETAIL > SCAN > ENRICHMENT > BATCH` (матчер использует `ENRICHMENT`)

### On-demand fetch (matcher → Discogs)

`Backend/app/services/listing_matcher.py`:
- `DISCOGS_FETCH_HOURLY_LIMIT = 500` (поднято с 50 — 19.05)
- Счётчик в Redis, TTL 3600s
- Защищает от того что batch matcher на 10к unmatched выжрет всю минутную квоту, мешая live-поиску юзера

### Что делать если хочется быстрее

- Поднять `DISCOGS_FETCH_HOURLY_LIMIT` до 1000-2000 (всё ещё в безопасной зоне 60/min среднем)
- Перейти на Discogs Data Dumps (см. [DISCOGS_DATA_DUMPS.md](../discogs/DISCOGS_DATA_DUMPS.md)) — это убирает зависимость от API полностью

---

## 6. Ресурсы — что и сколько

### На один листинг (single fetch)

| Ресурс | Значение |
|---|---|
| HTTP request | ~100-300 КБ HTML |
| CPU (парсинг) | ~50-100 мс |
| RAM (BeautifulSoup tree) | временно ~5-10 МБ, освобождается |
| Network | ~300 КБ in + ~5 КБ headers out |
| Disk (БД) | ~1.5 КБ на строку (с индексами и JSONB) |
| Время total | ~2.1 сек (2с rate-limit + 0.1с парсинг) |

### На полный обход одного магазина (~10к листингов)

| Ресурс | Значение |
|---|---|
| Время | ~6 часов (10000 × 2с) |
| Network | ~3 ГБ download (10000 × 300КБ) |
| RAM | ~150 МБ (один Python-воркер, константа) |
| CPU | ~5% одного ядра в среднем |
| Disk прирост | ~15 МБ (10000 × 1.5КБ) |

### На 10 магазинов в стационаре (после initial backfill)

| Ресурс | Значение |
|---|---|
| Storage | 150 МБ → ~1 ГБ через год |
| RAM | 150 МБ постоянно |
| CPU | 3-5% среднего ядра, пики до 30% во время incremental crawl |
| Network | ~55 ГБ/мес in+out |
| Discogs API | ~500-1000 req/час во время matcher-batch |
| Время ежедневных задач | ~2 часа суммарно (incremental + 4× stock-refresh + matcher) |

### Когда станет тяжело

| Сценарий | Что меняется |
|---|---|
| 30+ магазинов / 50к+ листингов каждый | БД ~10 ГБ, нужен partitioning по `last_seen_at` |
| Магазины под Cloudflare | Playwright pool (~1-2 ГБ RAM), на порядок медленнее |
| Real-time refresh | Kafka/queue + воркеры. Не нужно — 6-часовой snapshot устраивает |
| 100к юзеров активно ищут | Materialized view `record_offers_summary` + Redis pre-warm |

---

## 7. Размер БД (текущее, прод 19.05.2026)

| Таблица | Строк | Примерный размер |
|---|---|---|
| `store_listings` | ~5500 (korobkavinyla) + растёт (plastinka в процессе) | ~15-25 МБ |
| `records` (Discogs cache) | ~500-700 | ~2-3 МБ |
| `stores` | 2 | копейки |
| `offer_clicks` | 0 | 0 |
| **Итого offers-инфра** | | **~20-30 МБ** |

---

## 8. Антибан и анти-блок

| Угроза | Защита |
|---|---|
| 429 Too Many Requests | Per-domain rate-limit (0.5 req/s) + парсинг `Retry-After`, exponential backoff |
| 403 + Cloudflare challenge | Auto-detect (`__cf_chl` в HTML, `cf-mitigated: challenge` header) → `Store.requires_browser=True` → следующий проход через Playwright |
| 5xx подряд | Per-domain circuit breaker (3 failures → OPEN на 60s) |
| Detect by User-Agent | Pool из 10 реальных browser-UA, ротация |
| Detect по поведению | Jitter 0.3-1.5s между запросами + случайный порядок URL'ов |
| Бан по IP | TODO: пул прокси через env `SCRAPER_PROXIES` (CSV) |

**Операционное требование**: воркер-инстанс на РФ-IP (Selectel/Timeweb), иначе ~30% магазинов отдадут 403 (geo-блок).

---

## 9. Как добавить новый магазин (HOWTO)

```bash
# 1. Создать файл парсера
touch Backend/app/services/scrapers/shops/vinylpark_ru.py
```

```python
# vinylpark_ru.py
@register_parser("vinylpark_ru")
class VinylparkParser(BaseStoreParser):
    base_url = "https://vinylpark.ru"
    rate_limit_per_sec = 0.5
    sitemap_paths = ["/sitemap.xml"]
    listing_url_pattern = r"/catalog/.+"

    async def parse_listing(self, url: str) -> ListingDTO:
        html = await self.http.get_text(url)
        # ... извлечь поля ...
        return ListingDTO(...)
```

```python
# Backend/app/services/scrapers/shops/__init__.py
from app.services.scrapers.shops import vinylpark_ru  # noqa: F401
```

```python
# Backend/app/scripts/seed_stores.py — добавить в STORES list:
{"slug": "vinylpark_ru", "name": "Vinylpark", "domain": "vinylpark.ru",
 "base_url": "https://vinylpark.ru", "parser_class": "vinylpark_ru",
 "rating": Decimal("4.3"), "is_active": True, ...}
```

```bash
# 2. Тест локально
cd Backend && python -m app.scripts.scrape_all --slug=vinylpark_ru --limit=3

# 3. Deploy
git add -A && git commit -m "feat(scrapers): parser Vinylpark"
git push && ssh deploy@85.198.85.12 'cd ~/vertushka && bash Вертушка/Backend/scripts/deploy.sh'

# 4. Seed на проде
ssh deploy@85.198.85.12 "docker exec -e PYTHONPATH=/app -w /app vertushka_api python -m app.scripts.seed_stores --slug=vinylpark_ru"

# 5. Полный crawl (в фоне, ~часы)
ssh deploy@85.198.85.12 "docker exec -d -e PYTHONPATH=/app -w /app vertushka_api bash -lc 'python -m app.scripts.scrape_all --slug=vinylpark_ru --mode=full --no-match > /tmp/scrape_vinylpark.log 2>&1' && echo started"
```

---

## 10. Troubleshooting

| Симптом | Причина | Решение |
|---|---|---|
| `matcher: matched=0` | Парсер не извлёк barcode/catalog → matcher не идёт в Discogs | Проверить `signals` в логе матчинга. Если `with_barcode=0` → фиксить парсер |
| `matcher: matched=50` всегда | Уперлись в `DISCOGS_FETCH_HOURLY_LIMIT` | Подождать час или поднять лимит |
| `rate limiter timeout` в логах матчера | `discogs_limiter._processor_task` не стартовал (CLI без lifespan) | Уже пофикшено (`b4f09eb` — ленивый старт в `acquire()`) |
| Парсер сохранил `in_stock` но на сайте «нет в наличии» | Парсер игнорирует quantity-сигнал магазина | Расширить логику status в per-shop парсере. Пример: `korobkavinyla.py` использует Tilda `product.quantity` |
| Sitemap не парсится | XML invalid / сжатый / в нестандартном формате | Проверить `iter_sitemap_urls` в `sitemap.py`, добавить fallback |
| Cloudflare block | 403 + `__cf_chl` | Set `Store.requires_browser=True` → следующий запуск через Playwright |

---

## 11. Будущее (Roadmap)

- **Discogs Data Dumps**: импортировать local mirror `records` чтобы перестать зависеть от Discogs API на матчинге. План — [DISCOGS_DATA_DUMPS.md](../discogs/DISCOGS_DATA_DUMPS.md)
- **Расширение покрытия форматов**: парсер Plastinka сейчас берёт только LP. CD/Box/Cassette — добавить (URL pattern + UX в карусели)
- **Cloudflare-stack**: пока ни один из подключённых магазинов не под CF. Когда появится — `browser.py` (Playwright pool) ждёт в `scrapers/`
- **Direct affiliate** (см. [AFFILIATE_OUTREACH_TEMPLATE.md](AFFILIATE_OUTREACH_TEMPLATE.md)): после 1-2 месяцев данных в БД — слать письма владельцам магазинов с реальной статистикой кликов
- **Admin dashboard** «Здоровье парсеров»: success-rate, last_successful_scrape_at, CF-флаги — для оператора

---

## 12. Связанные документы

- [SHOPS_PARSING.md](SHOPS_PARSING.md) — план верхнего уровня (бизнес-обоснование, фазы, шопы списком)
- [DISCOGS_DATA_DUMPS.md](../discogs/DISCOGS_DATA_DUMPS.md) — план для независимости от Discogs API
- [OFFERS_UX.md](OFFERS_UX.md) — как офферы отображаются в Mobile (карусель, чипы, swipe)
- [AFFILIATE_OUTREACH_TEMPLATE.md](AFFILIATE_OUTREACH_TEMPLATE.md) — письмо владельцам магазинов
