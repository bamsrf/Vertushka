"""CLI: CSV.gz жанров из дампа → `records.genre` / `records.style`.

Вторая половина пары к `extract_release_formats --ids-file` (тот запускается НЕ
на проде: `data.discogs.com` встречает сервер JS-челленджем Cloudflare). Сюда
приезжает CSV `discogs_id,genre,style` и раскладывается по записям.

## Зачем

Жанровые чипы Маркета фильтруют по `records.genre`, а заполнялся он только
живым вызовом Discogs API — то есть у записей, которые кто-то открыл руками.
Склад магазинов матчер создаёт из дампа (`_get_or_create_record_from_dump`), где
колонок genre/style нет вовсе. Итог на 25.08.2026: жанр был у ~390 карточек из
~30 тысяч, и фильтр «Жанр» показывал сотые доли склада.

Догонять живым API — 33k релизов при 60 rpm это 9+ часов на квоте, которая и
так узкое место. Дамп отдаёт то же самое даром.

## Почему UPDATE, а не отдельная таблица

Жанр нужен ровно там, где его читает фильтр — в `records`. Данные ложатся в уже
существующие строки, дополнительного места на проде (свободно ~3 ГБ) это почти
не стоит, в отличие от полной таблицы жанров на 19M релизов (~0.9 ГБ).

## Грабли, на которые уже наступили

Staging чистится **явным TRUNCATE**, а не через `ON COMMIT DELETE ROWS`:
asyncpg работает в автокоммите, COPY коммитится сам, и `ON COMMIT` сносил бы
staging ДО того, как отработает UPDATE. В `load_release_formats` эта
конструкция уже стоила молчаливой заливки нуля строк.

Пустые значения не затирают заполненные (`COALESCE(NULLIF(...))`): у записи,
которую юзер открывал, жанр из живого API точнее дампного — там свежее.

Обновляются только строки, где реально что-то меняется. Postgres на каждый
UPDATE пишет новую версию строки, и «обновить» 30 тысяч записей теми же
значениями — это 30 тысяч мёртвых кортежей на диске, которого и так мало.

Использование:

    docker exec vertushka_api python -m app.scripts.load_release_genres \\
      --file /tmp/genres_20260801.csv.gz [--dry-run]

    # то же из masters-дампа (ключ — master_id, см. extract_master_genres)
    docker exec vertushka_api python -m app.scripts.load_release_genres \\
      --file /tmp/genres_masters_20260801.csv.gz --key master
"""
from __future__ import annotations

import argparse
import asyncio
import csv
import gzip
import logging
import sys
import time
from pathlib import Path

from app.database import engine

logger = logging.getLogger("load_release_genres")

_BATCH = 20_000

#: Колонка-ключ для каждого режима. release — точнее (жанр конкретного пресса),
#: master — шире по доступности: releases-дамп весит 10.4 ГБ и без поддержки
#: Range качается лотереей, masters — 593 МБ и берётся с первой попытки.
#: На одном master_id висят все прессы альбома, поэтому в режиме master одна
#: строка CSV может обновить несколько записей — это нормально и нужно.
KEY_COLUMNS = {"release": "discogs_id", "master": "discogs_master_id"}


def _where(key: str) -> str:
    """Условие «строке есть что взять из дампа».

    Вынесено отдельно от FROM, чтобы --dry-run считал ровно тот же набор строк,
    который потом обновит боевой прогон, — иначе «посмотреть перед заливкой»
    ничего не гарантирует.
    """
    col = KEY_COLUMNS[key]
    return f"""
    WHERE r.{col} ~ '^[0-9]+$'
      AND r.{col}::bigint = s.key_id
      AND r.merged_into_id IS NULL
      AND (
            (COALESCE(r.genre, '') = '' AND COALESCE(s.genre, '') <> '')
         OR (COALESCE(r.style, '') = '' AND COALESCE(s.style, '') <> '')
      )
"""


def _update_sql(key: str) -> str:
    return f"""
WITH upd AS (
    UPDATE records r
    SET genre = COALESCE(NULLIF(r.genre, ''), NULLIF(s.genre, '')),
        style = COALESCE(NULLIF(r.style, ''), NULLIF(s.style, '')),
        updated_at = NOW()
    FROM _genre_stage s
    {_where(key)}
    RETURNING 1
)
SELECT COUNT(*) FROM upd
"""


def _count_sql(key: str) -> str:
    """COUNT(DISTINCT r.id), а не COUNT(*): в режиме master на один ключ
    приходится несколько прессов, и пары «запись × строка дампа» посчитались бы
    как отдельные обновления, хотя UPDATE трогает каждую запись один раз."""
    return f"SELECT COUNT(DISTINCT r.id) FROM records r, _genre_stage s {_where(key)}"


async def _flush(pg, rows: list[tuple], key: str, dry_run: bool) -> int:
    if not rows:
        return 0
    await pg.execute("TRUNCATE _genre_stage")
    await pg.copy_records_to_table(
        "_genre_stage", records=rows, columns=("key_id", "genre", "style"),
    )
    sql = _count_sql(key) if dry_run else _update_sql(key)
    return int(await pg.fetchval(sql) or 0)


async def load(file_path: Path, dry_run: bool, key: str = "release") -> dict[str, int]:
    counters = {"read": 0, "updated": 0, "bad": 0}
    started = time.time()
    last_report = started
    batch: list[tuple] = []

    async with engine.connect() as conn:
        raw = await conn.get_raw_connection()
        pg = raw.driver_connection

        await pg.execute(
            "CREATE TEMP TABLE IF NOT EXISTS _genre_stage "
            "(key_id bigint, genre text, style text)"
        )

        with gzip.open(file_path, "rt", encoding="utf-8", newline="") as fh:
            for row in csv.reader(fh):
                # genre и style оба пустыми быть не могут — extractor такие
                # строки не пишет. Если такая приехала, CSV собран не тем.
                if len(row) != 3 or not row[0].isdigit() or not (row[1] or row[2]):
                    counters["bad"] += 1
                    continue
                batch.append((int(row[0]), row[1] or None, row[2] or None))
                counters["read"] += 1
                if len(batch) >= _BATCH:
                    counters["updated"] += await _flush(pg, batch, key, dry_run)
                    batch = []
                    now = time.time()
                    if now - last_report >= 30:
                        logger.info(
                            "read=%d updated=%d bad=%d rate=%.0f/s",
                            counters["read"], counters["updated"], counters["bad"],
                            counters["read"] / (now - started),
                        )
                        last_report = now
        counters["updated"] += await _flush(pg, batch, key, dry_run)

    logger.info(
        "ГОТОВО за %.1f мин: read=%d %s=%d bad=%d",
        (time.time() - started) / 60, counters["read"],
        "подошло бы" if dry_run else "обновлено", counters["updated"],
        counters["bad"],
    )
    if counters["read"] and not counters["updated"]:
        logger.error(
            "прочитано %d строк, изменено 0 — либо всё уже заполнено, либо "
            "список id снят не с этой базы; проверь staging",
            counters["read"],
        )
    return counters


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--file", required=True, type=Path)
    parser.add_argument(
        "--key", choices=sorted(KEY_COLUMNS), default="release",
        help=(
            "по какому ключу класть жанры: release (CSV из releases-дампа) или "
            "master (CSV из masters-дампа, extract_master_genres)"
        ),
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="только посчитать, сколько записей получат жанр — ничего не менять",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        stream=sys.stdout,
    )
    if not args.file.exists():
        parser.error(f"нет файла: {args.file}")

    asyncio.run(load(args.file, args.dry_run, args.key))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
