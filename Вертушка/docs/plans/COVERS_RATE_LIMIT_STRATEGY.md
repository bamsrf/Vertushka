# Обложки: стратегия ухода от Discogs rate-limit (60/min)

> Статус: реализовано 2026-07-02 (слои 1–3). Осталось: прогнать импорт MB-дампа
> и bulk-warm на проде (runbook ниже).

## Проблема

Slim dump (`discogs_releases_index`, ~16M строк) не несёт image URLs → холодные
релизы без обложек. Единственный live-источник — Discogs API c общим лимитом
60 req/min на app-токен. С ростом юзеров без Discogs OAuth лимит делится на всех.

## Решение: 4 слоя

Ключевая идея: **проблема — это прогрев, а не runtime**. Обложка качается один
раз за жизнь (зеркало `uploads/covers/`), дальше — nginx-статика. Прогрев
конечен и почти весь идёт мимо Discogs.

### Слой 1 — офлайн-маппинг MusicBrainz → Cover Art Archive

MB full-export содержит связи release↔discogs-URL. Из него строится таблица
`mb_discogs_map (discogs_id PK, mbid, caa_checked_at)`:

```
discogs_id → mbid → https://coverartarchive.org/release/{mbid}/front-1200
```

CAA **без rate limit** (archive.org). Ни одного запроса к Discogs/MB API.

Бонус: `mbdump-cover-art-archive.tar.bz2` (155 MB) — офлайн-индекс самого CAA
(cover_art + cover_art_type). Наличие front-обложки известно без HEAD-проверок:
`has_front` пишется в маппинг, при загрузке CSV обложки массово проставляются
в `discogs_releases_index` одним UPDATE.

- Миграция: `20260702_mb_discogs_map.py`
- Импорт: `app/scripts/ingest_mb_discogs_map.py` — два режима:
  `--export-csv` (локальная машина, stdlib-only, тяжёлый парсинг TSV) и
  `--from-csv` (сервер, грузит готовый CSV ~50-100 MB → серверу НЕ нужно
  15 GB под дамп)
- Bulk-warm: `app/scripts/warm_caa_covers.py` — резервный HEAD-путь; при
  наличии офлайн-индекса не нужен (все строки сразу caa_checked_at)
- Runtime: `cover_url_by_discogs_id()` в `cover_fallback.py` — первый шаг
  цепочки `cover_warm`

### Слой 2 — drip-воркер: простой app-bucket'а → прогрев

60 req/min × 24ч = ~86K обложек/день, если bucket простаивает.
`app/tasks/cover_drip_tasks.py`, APScheduler каждую минуту (scheduler-контейнер):

- `cache.peek_tokens()` (новое, без изъятия) — работаем только когда
  tokens > 25 (headroom для живых юзеров), re-peek перед каждым запросом
- Кап 25 запросов/прогон; кандидаты `year DESC` (свежий каталог первым)
- Строки, ждущие CAA bulk-warm, пропускаются (их закроет бесплатный источник)
- `cover_checked_at` ставится после каждой попытки — из очереди строка уходит
  навсегда (перепроверка: `SET cover_checked_at = NULL`)
- Выключатель: `COVER_DRIP_ENABLED=false`

### Слой 3 — iTunes Search API fallback

`cover_url_by_artist_title()` в `cover_fallback.py` — последний шаг цепочки
`cover_warm` (album-level artwork, не издание). ~19 req/min троттл, строгий
матч artist+title, guard от `- Single`/`- EP` подмен. Картинки — mzstatic CDN
600x600, зеркалятся как обычно.

### Слой 4 — per-user OAuth bucket'ы (уже было)

Live-пути (inline обложки версий) идут через персональный bucket юзера.

## Итоговая цепочка cover_warm

1. CAA по `mb_discogs_map` (1 HEAD, бесплатно)
2. CAA по barcode (MusicBrainz 1 rps + HEAD)
3. Discogs `/releases/{id}` (бюджет 3/батч)
4. iTunes Search (строгий матч)

## Runbook

```bash
# 1. ЛОКАЛЬНО (Mac): стрим-скачивание 3 таблиц ядра (~4 GB TSV, архив не хранится)
BASE=https://data.metabrainz.org/pub/musicbrainz/data/fullexport
LATEST=$(curl -s $BASE/LATEST)
mkdir -p ~/mbdump ~/mbdump-caa
curl -s $BASE/$LATEST/mbdump.tar.bz2 | \
  tar -xjf - -C ~/mbdump --strip-components=1 mbdump/url mbdump/l_release_url mbdump/release
curl -s $BASE/$LATEST/mbdump-cover-art-archive.tar.bz2 | \
  tar -xjf - -C ~/mbdump-caa --strip-components=1 mbdump/cover_art mbdump/art_type mbdump/cover_art_type

# 2. ЛОКАЛЬНО: парсинг → CSV (stdlib-only, зависимости бэкенда не нужны)
python3 Backend/app/scripts/ingest_mb_discogs_map.py \
  --dir ~/mbdump --caa-dir ~/mbdump-caa --export-csv ~/mb_map.csv.gz

# 3. Деплой кода (миграция применится в deploy.sh)
git push && ssh deploy@85.198.85.12 'bash ~/vertushka/Вертушка/Backend/scripts/deploy.sh'

# 4. CSV на сервер и загрузка (минуты; сразу проставляет обложки has_front-парам)
scp ~/mb_map.csv.gz deploy@85.198.85.12:/tmp/
ssh deploy@85.198.85.12 'docker cp /tmp/mb_map.csv.gz vertushka_api:/tmp/ && \
  docker exec -d vertushka_api sh -c \
  "python -m app.scripts.ingest_mb_discogs_map --from-csv /tmp/mb_map.csv.gz > /tmp/mb_map.log 2>&1"'

# 5. Мониторинг
ssh deploy@85.198.85.12 'docker exec vertushka_api tail -5 /tmp/mb_map.log'
# drip: grep "cover drip" в логах scheduler-контейнера
```

Ежемесячное обновление: повторить шаги 1-2-4 со свежим дампом (загрузка
делает TRUNCATE + полный re-import; caa_checked_at проставляется заново из
офлайн-индекса, HEAD-проверки не нужны).

## Что осталось / связанное

- Monthly delta-ingest Discogs dump (новинки) — DISCOGS_DATA_DUMPS.md Phase 2;
  после инжеста новые id прогонять через слои 1–2.
- Discogs ToS: кэшировать сами картинки — разрешено (форум-модератор:
  «cache the images themselves, not the URLs»); нельзя обходить rate limit
  мульти-ключами и показывать метаданные старше 6ч.
