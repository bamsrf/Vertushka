# Локальная разработка: Supabase + Redis

Постgres держим в локальном Supabase (через `supabase-cli`), Redis — в Docker (`docker-compose.dev.yml`). Сам Backend (FastAPI) запускаем в venv.

> Supabase используем как Postgres + UI (Studio). Auth/Storage/Realtime/Edge Functions у нас своя реализация — в `supabase/config.toml` они отключены, чтобы экономить RAM.

## 0. Требования

- macOS / Linux
- **Docker Desktop** (или OrbStack) — должен быть запущен
- **Homebrew** (для установки supabase-cli)
- **Python 3.11+** уже стоит, venv уже создан в `Backend/venv/`

## 1. Установить supabase-cli (один раз)

```bash
brew install supabase/tap/supabase
supabase --version   # должно показать версию
```

## 2. Поднять инфраструктуру

```bash
cd Backend
make dev-up
```

Под капотом:
- `supabase start` — поднимет Postgres 15 на `127.0.0.1:54322` + Studio на `127.0.0.1:54323`
- `docker compose -f docker-compose.dev.yml up -d` — поднимет Redis на `localhost:6379`

Первый запуск Supabase качает образы — это 5-10 минут. Дальнейшие — секунды.

Проверить статус:
```bash
make dev-status
```

## 3. Настроить .env

```bash
cd Backend
cp .env.local.example .env
```

Затем открой `.env` и впиши **Discogs-ключи** (без них поиск пластинок не работает):
```
DISCOGS_API_KEY=...
DISCOGS_API_SECRET=...
DISCOGS_TOKEN=...   # personal access token для marketplace stats
```
Все остальные значения уже подходят для локальной разработки.

> ⚠️ **Проверь `DATABASE_URL`** — должен указывать на supabase-Postgres `127.0.0.1:54322/postgres`. Если в `.env` остался старый `localhost:5432/vertushka` (контейнер `vertushka_db` из ранней docker-compose-эры), `make migrate` упадёт с `DuplicateColumnError: column "estimated_price_rub" already exists` — та БД создана через `create_all` без `alembic_version`, и alembic гонит всю цепочку с нуля.

## 4. Накатить миграции

```bash
make migrate
```

Это создаст в локальном Postgres все таблицы (`users`, `records`, `collections`, `wishlists`, `stores`, `store_listings`, и т.д.) и поставит расширение `pg_trgm` для fuzzy-матчинга.

## 5. Засеять магазины

```bash
make seed
```

Сейчас в [Backend/app/scripts/seed_stores.py](../../Backend/app/scripts/seed_stores.py) есть `korobkavinyla`. Чтобы добавить ещё — просто допиши в список `STORES` и запусти `make seed` снова (идемпотентно — обновит существующие, создаст новые).

## 6. Запустить API

```bash
make run
```
→ FastAPI на `http://localhost:8000`. Swagger: `http://localhost:8000/api/docs`.

## 7. Тестовый прогон парсера

В отдельном терминале:
```bash
cd Backend
make scrape-test       # 10 товаров с korobkavinyla
make scrape-match      # сматчить с Record-ами
```

Посмотреть результат в Studio:
```bash
make studio            # откроет http://127.0.0.1:54323
```
В Studio → таблица `store_listings` — увидишь спарсенные товары. Колонка `matched_record_id` будет заполнена для тех, что сматчились с Record по штрихкоду.

Прямой запрос:
```bash
make psql
```
```sql
SELECT count(*), count(matched_record_id) AS matched
FROM store_listings;

SELECT s.slug, count(*) AS listings
FROM store_listings sl JOIN stores s ON s.id = sl.store_id
GROUP BY s.slug;
```

## 8. Проверить API offers

```bash
# найти любой Record с matched_record_id
make psql
```
```sql
SELECT r.discogs_id, r.artist, r.title
FROM records r JOIN store_listings sl ON sl.matched_record_id = r.id
LIMIT 1;
```

С полученным `discogs_id`:
```bash
curl http://localhost:8000/api/records/<discogs_id>/offers | jq
```

## Полезные команды

| Команда | Что делает |
|---|---|
| `make help` | список всех команд |
| `make dev-up` / `dev-down` | поднять/остановить Supabase + Redis |
| `make migrate` / `downgrade` | Alembic up/down |
| `make psql` | psql к локальной БД |
| `make studio` | Supabase Studio в браузере |
| `make seed` / `seed-list` | сидинг магазинов |
| `make scrape-test` | пилот парсера (10 товаров) |
| `make scrape-list` | список зарегистрированных парсеров |
| `make scrape-match` | сматчить unmatched листинги |
| `make run` | FastAPI с `--reload` на :8000 |

## Решение проблем

### `supabase start` падает с «port already in use»
Что-то уже занимает 54322/54323. Проверь:
```bash
lsof -i :54322
```
Либо это старая инстанция Supabase (`supabase stop`), либо локальный Postgres (выключи через `brew services stop postgresql`).

### `make migrate` пишет «database does not exist»
Supabase ещё не поднялся. Подожди, проверь `make dev-status`.

### Парсер падает с `playwright` ImportError
Браузерные парсеры пока не нужны для пилота. Если понадобятся:
```bash
./venv/bin/playwright install chromium
```

### Redis недоступен — приложение всё равно работает
По дизайну: `cache.py` имеет graceful fallback. Просто без кэша медленнее. Но `make dev-up` обычно поднимает Redis за пару секунд — проверь `docker ps`.

### Хочу свежую БД
```bash
make dev-down
docker volume rm vertushka_redis_data
cd /Users/vladislavrumancev/Desktop/Cursor/Вертушка && supabase db reset --no-seed
make dev-up
make migrate
make seed
```

## Когда отключать `IS_SCHEDULER` / `SCRAPERS_ENABLED`

В `.env.local.example` они оба `false` — намеренно. На dev:
- **Не нужен фоновый прогон цен** (DigosCS API quota пожалеется)
- **Не нужен парсинг по расписанию** — лучше дёргать `make scrape-test` руками

Включай только если **хочешь воспроизвести prod-поведение** локально.
