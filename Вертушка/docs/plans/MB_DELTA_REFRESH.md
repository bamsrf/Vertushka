# План C — месячный рефреш дампов (MB + CAA), обложки без API

> Статус: **не начато** (сознательно отложено — текущие дампы от 2026-07-01, свежее не нужно).
> Триггер запуска: раз в месяц, или когда свежие релизы (< 2 мес) заметно без обложек.
> Родственный хвост: monthly delta-ингест Discogs-дампа (docs/plans, заметка covers-rate-limit-saga).

## Зачем

MB/CAA-данные на проде — снимок от 1 июля. MusicBrainz растёт: ~30–60K релизов/мес,
плюс дозагрузка обложек к старым. Всё после снимка невидимо — а это самая горячая
зона (свежак в Маркете, кейс «Boards of Canada — INFERNO»). Один цикл рефреша
= +10–40K обложек, с уклоном в новые релизы. Ноль API-запросов, ноль rate-limit.

## Что уже есть (ничего кодить не надо)

| Скрипт | Канал | Куда пишет |
|---|---|---|
| `Backend/app/scripts/ingest_mb_discogs_map.py` | URL-связи MB↔Discogs + CAA front | `mb_discogs_map` + `discogs_releases_index.cover_image_url` (NULL-строки) |
| `Backend/app/scripts/ingest_mb_barcode_covers.py` | barcode → mbid c front | `mb_barcode_covers` + `discogs_releases_index.cover_image_url` (NULL-строки) |
| `Backend/app/scripts/ingest_mb_catno_covers.py` | catno+label → mbid c front | `mb_catno_covers`+`mb_mbid_rg`; UPDATE — только явным `--apply` после гейта, аудит в `catno_cover_audit` |
| SQL «B» (см. ниже) | master-обложки из маппинга | `discogs_master_covers` (source='caa', ON CONFLICT DO NOTHING) |

Всё идемпотентно: TRUNCATE+COPY, UPDATE только `cover_image_url IS NULL`,
INSERT `ON CONFLICT DO NOTHING`. Упало — перезапускай смело.

## Цикл (≈30–40 мин, из них ~25 — скачивание)

### 1. Mac: скачать свежий fullexport (~7GB + 155MB)

```bash
# каталог с датой последнего экспорта:
# https://data.metabrainz.org/pub/musicbrainz/data/fullexport/LATEST
BASE=https://data.metabrainz.org/pub/musicbrainz/data/fullexport/$(curl -s https://data.metabrainz.org/pub/musicbrainz/data/fullexport/LATEST)

mkdir -p ~/mbdump ~/mbdump-caa
curl -s $BASE/mbdump.tar.bz2 | tar -xjf - -C ~/mbdump --strip-components=1 \
  mbdump/url mbdump/l_release_url mbdump/release \
  mbdump/release_label mbdump/label mbdump/release_country mbdump/release_unknown_country
curl -s $BASE/mbdump-cover-art-archive.tar.bz2 | tar -xjf - -C ~/mbdump-caa \
  --strip-components=1 mbdump/cover_art mbdump/art_type mbdump/cover_art_type
```

Пик диска на Mac: ~4.5GB TSV (архивы не сохраняются — стрим).

### 2. Mac: спарсить → 4 CSV (минуты, stdlib-only)

```bash
cd ~/Desktop/Cursor/Вертушка
python3 Backend/app/scripts/ingest_mb_discogs_map.py \
  --dir ~/mbdump --caa-dir ~/mbdump-caa --export-csv ~/mb_map.csv.gz
python3 Backend/app/scripts/ingest_mb_barcode_covers.py \
  --dir ~/mbdump --caa-dir ~/mbdump-caa --export-csv ~/mb_barcode_covers.csv.gz
python3 Backend/app/scripts/ingest_mb_catno_covers.py \
  --dir ~/mbdump --caa-dir ~/mbdump-caa --export-csv ~/mb_catno_covers.csv.gz
# катномер-скрипт пишет ДВА файла: основной + mb_catno_covers.rg.csv.gz
```

⚠️ **Порядок каналов обязателен: map → barcode → catno.** Все три пишут по
правилу «заполни NULL», слот занимается навсегда — догадка по катномеру не
должна опережать точный ключ. Катномер-канал вдобавок гейтится: `--from-csv`
только грузит и мерит точность на непокрытой популяции, запись — отдельный
`--apply` (перепроверяет гейт сам, пишет аудит в `catno_cover_audit`).

### 3. Сервер: залить CSV (~100MB суммарно)

```bash
# перед началом: df -h на сервере, нужно ≥1.5GB свободно
scp ~/mb_map.csv.gz ~/mb_barcode_covers.csv.gz deploy@85.198.85.12:/tmp/
ssh deploy@85.198.85.12 '
  docker cp /tmp/mb_map.csv.gz vertushka_api:/tmp/ &&
  docker cp /tmp/mb_barcode_covers.csv.gz vertushka_api:/tmp/ &&
  rm /tmp/mb_map.csv.gz /tmp/mb_barcode_covers.csv.gz'
```

### 4. Сервер: прогнать загрузку (detached — переживает разрыв ssh)

```bash
ssh deploy@85.198.85.12 '
  docker exec -d vertushka_api sh -c \
    "python -m app.scripts.ingest_mb_discogs_map --from-csv /tmp/mb_map.csv.gz \
     > /tmp/mb_map.log 2>&1 && \
     python -m app.scripts.ingest_mb_barcode_covers --from-csv /tmp/mb_barcode_covers.csv.gz \
     > /tmp/mb_barcode.log 2>&1"'
# прогресс: ssh ... 'docker exec vertushka_api tail /tmp/mb_map.log /tmp/mb_barcode.log'
```

⚠️ **Грабли (2026-07-12):** большой UPDATE может упереться в `statement_timeout=30s`
приложения. Если в логе `QueryCanceledError` — COPY уже прошёл, добить UPDATE
руками через psql (`SET statement_timeout = 0;` + UPDATE из скрипта), detached:
`nohup docker compose -f docker-compose.prod.yml exec -T db ... &`.
⚠️ ssh-обрыв НЕ убивает psql внутри docker exec — прежде чем перезапускать,
проверь `pg_stat_activity` и счётчики: прогон мог доехать.

### 5. Сервер: SQL «B» — master-обложки из пополнившегося маппинга

```sql
SET statement_timeout = 0;
WITH src AS (
  SELECT DISTINCT ON (dri.master_id)
         dri.master_id,
         'https://coverartarchive.org/release/' || m.mbid || '/front-1200' AS url
  FROM discogs_releases_index dri
  JOIN mb_discogs_map m ON m.discogs_id = dri.discogs_id AND m.has_front
  WHERE dri.master_id IS NOT NULL
  ORDER BY dri.master_id, dri.year ASC NULLS LAST, dri.discogs_id ASC
), ins AS (
  INSERT INTO discogs_master_covers (master_id, cover_image_url, source)
  SELECT master_id, url, 'caa' FROM src
  ON CONFLICT (master_id) DO NOTHING
  RETURNING 1
) SELECT count(*) AS master_covers_added FROM ins;
```

### 6. Сверка + уборка

```sql
-- динамика (сравнить с прошлым прогоном):
SELECT count(*) FILTER (WHERE cover_image_url LIKE '%coverartarchive%') AS caa,
       count(*) AS total
FROM discogs_releases_index WHERE cover_image_url IS NOT NULL;
SELECT source, count(*) FROM discogs_master_covers GROUP BY source;
```

```bash
# Mac: TSV больше не нужны (CSV пересоздаются из свежего дампа)
rm -rf ~/mbdump ~/mbdump-caa
# сервер: docker exec vertushka_api rm /tmp/mb_map.csv.gz /tmp/mb_barcode_covers.csv.gz
```

## Бейзлайн после прогона 2026-07-12

- `discogs_releases_index`: covers total **1,404,129** (CAA 1,278,686)
- `mb_discogs_map`: 1,822,036 пар (1,163,690 has_front)
- `mb_barcode_covers`: 1,869,868 пар
- `discogs_master_covers`: deezer 110K+ (backfill крутится) + caa (B, 2026-07-13)

## Почему безопасно

- Все записи = «заполни NULL» / `DO NOTHING` — существующие URL не перезаписываются.
- Кэши не инвалидируются, приложение в цикле не участвует.
- Один штрихкод носит несколько изданий → в `mb_discogs_map` barcode-пары НЕ пишем
  (identity для треклистов должна оставаться чистой, URL-связи только).

## Не автоматизировать (пока)

Cron на Mac хрупок: Mac должен быть включён, URL дампа содержит дату, молча
сломается. Ручной прогон раз в месяц (10 мин участия) — правильный уровень.
Склеить с месячным рефрешем Discogs-дампа в один ритуал, когда тот появится.
