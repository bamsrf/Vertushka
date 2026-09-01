# План C — месячный рефреш дампов (MB + CAA), обложки без API

> Статус: **прогнан 2026-08-27** (дамп 2026-08-26): +12 718 обложек по URL-связям,
> +11 671 по штрихкодам, +3 784 master-обложек, затем catno-канал: **+287 329**.
> Оба финальных UPDATE map/barcode срезались statement_timeout'ом — добиты руками,
> см. грабли в шаге 4.
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
# ⚠️ CAA-дамп с августа-2026 префиксует имена схемой: cover_art_archive.cover_art
# (основной дамп при этом БЕЗ префикса — не «чинить» его по аналогии!).
# После распаковки срезать префикс, скрипты ждут голые имена.
curl -s $BASE/mbdump-cover-art-archive.tar.bz2 | tar -xjf - -C ~/mbdump-caa \
  --strip-components=1 'mbdump/*.cover_art' 'mbdump/*.art_type' 'mbdump/*.cover_art_type'
(cd ~/mbdump-caa && for f in *.*; do mv "$f" "${f#*.}"; done)
```

Пик диска на Mac: ~5.5GB TSV (архивы не сохраняются — стрим).
Если tar ругается «Not found in archive» — раскладка снова поменялась:
`tar -tjf` на CAA-дампе (он маленький) и поправить пути тут.

### 2. Mac: спарсить → 4 CSV (минуты, stdlib-only)

```bash
cd ~/Cursor/Вертушка
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

### 3. Сервер: залить CSV (~300MB суммарно)

```bash
# перед началом: df -h на сервере, нужно ≥1.5GB свободно
scp ~/mb_map.csv.gz ~/mb_barcode_covers.csv.gz \
    ~/mb_catno_covers.csv.gz ~/mb_catno_covers.rg.csv.gz deploy@85.198.85.12:/tmp/
ssh deploy@85.198.85.12 '
  for f in mb_map mb_barcode_covers mb_catno_covers mb_catno_covers.rg; do
    docker cp /tmp/$f.csv.gz vertushka_api:/tmp/ && rm /tmp/$f.csv.gz
  done'
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

# СТРОГО ПОСЛЕ map+barcode: catno — загрузка+валидация, потом отдельный --apply
ssh deploy@85.198.85.12 '
  docker exec -d vertushka_api sh -c \
    "python -m app.scripts.ingest_mb_catno_covers --from-csv /tmp/mb_catno_covers.csv.gz \
     > /tmp/mb_catno.log 2>&1"'
# в /tmp/mb_catno.log посмотреть блок «непокрытые (популяция --apply)»: если
# «тот же альбом» ≥ 97% — запускать запись (гейт перепроверится сам):
ssh deploy@85.198.85.12 '
  docker exec -d vertushka_api sh -c \
    "python -m app.scripts.ingest_mb_catno_covers --apply > /tmp/mb_catno_apply.log 2>&1"'
```

⚠️ **Грабли (2026-07-12):** большой UPDATE может упереться в `statement_timeout=30s`
приложения. Если в логе `QueryCanceledError` — COPY уже прошёл, добить UPDATE
руками через psql (`SET statement_timeout = 0;` + UPDATE из скрипта), detached:
`nohup docker compose -f docker-compose.prod.yml exec -T db ... &`.
(catno-скрипт этому не подвержен: он ходит напрямую через asyncpg и батчит
UPDATE по 1000 — заодно не травит пул приложения session-level SET'ом.)
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
# сервер: docker exec vertushka_api sh -c 'rm /tmp/mb_*.csv.gz'
```

## Бейзлайн после прогона 2026-08-27 (дамп 2026-08-26)

- `discogs_releases_index`: covers total **2,298,031** (CAA **1,590,410**)
  — до catno-канала было 2,008,531 / 1,303,080
- `mb_discogs_map`: 1,847,357 пар (1,183,125 has_front)
- `mb_barcode_covers`: 1,925,589 пар
- `mb_catno_covers`: 1,694,362 однозначных ключей (16,256 неоднозначных отброшено)
- `discogs_master_covers`: deezer 443,911 / caa 417,191 / store 4,923 / discogs 375
- В сыром CAA-дампе 3,795,202 релиза с front — покрыто ~1.59 млн; остаток
  недостижим по URL/штрихкоду/катномеру (нет ключа либо срезан гейтами).

### Итог catno-канала 27.08 (первый прогон, PR #135)

Гейт самопроверки: 98.69% «тот же альбом» на непокрытой популяции (порог 97%),
на всей ground truth — 99.89%. **+287,329 обложек за 742s**, полный след в
`catno_cover_audit`. Кандидатов из префильтра 340,618; 5,886 ключей срезано
веерным капом (>5 релизов на ключ). Выборка из аудита (5 случайных URL) —
все отдают HTTP 200.

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
- Катномер — самый слабый ключ, поэтому обвес: junk-списки catno/лейблов,
  однозначность по ВСЕМУ MB (включая релизы без обложек), |Δгода| ≤ 2,
  веерный кап 5, гейт точности 97% перед записью, аудит каждой строки.

## Не автоматизировать (пока)

Cron на Mac хрупок: Mac должен быть включён, URL дампа содержит дату, молча
сломается. Ручной прогон раз в месяц (10 мин участия) — правильный уровень.
Склеить с месячным рефрешем Discogs-дампа в один ритуал, когда тот появится.
