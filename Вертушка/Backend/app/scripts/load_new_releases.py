"""CLI: CSV.gz новых релизов дампа → discogs_releases_index.

Дельта-догон индекса: дамп выходит ~1-го числа каждого месяца, индекс наполнен
дампом 2026-05-01, и всё, что Discogs завёл позже, на экране артиста
отсутствует. `extract_release_formats --since-id` отбирает такие релизы (id
Discogs инкрементальны, «больше максимума в индексе» = «появился позже»), этот
скрипт их вставляет.

Что важно и чего не делает обычный ingest:
  * `artist_ids` и `is_unofficial` приезжают в той же CSV — без первого строка
    не видна на экране артиста (фильтр там по GIN `artist_ids`), без второго
    дискография тонет в бутлегах;
  * `ON CONFLICT DO NOTHING` — гонка с `index_single_release` (дозапись живых
    релизов из API) не роняет прогон;
  * `format_type` уже полный (все описания), усечения `_derive_format` в этой
    ветке нет.

Использование:

    docker exec vertushka_api python -m app.scripts.load_new_releases \\
      --file /tmp/new_20260801.csv.gz --dump-date 2026-08-01
"""
from __future__ import annotations

import argparse
import asyncio
import csv
import gzip
import logging
import sys
import time
from datetime import date, datetime
from pathlib import Path

from app.database import engine

logger = logging.getLogger("load_new_releases")

_BATCH = 5_000
_COLUMNS = (
    "discogs_id", "master_id", "artist", "title", "year", "country",
    "format_type", "label", "barcode_norm", "catalog_norm",
    "artist_ids", "is_unofficial", "dump_version", "created_at",
)


def _row_to_tuple(row: list[str], dump_date: date) -> tuple | None:
    if len(row) != 12 or not row[0].isdigit():
        return None
    artist_ids = [int(x) for x in row[10].split(";") if x.isdigit()] or None
    return (
        int(row[0]),
        int(row[1]) if row[1].isdigit() else None,
        row[2], row[3],
        int(row[4]) if row[4].lstrip("-").isdigit() else None,
        row[5] or None,
        row[6] or None,
        row[7] or None,
        row[8] or None,
        row[9] or None,
        artist_ids,
        row[11] == "1",
        dump_date,
        datetime.utcnow(),
    )


async def _flush(pg, rows: list[tuple]) -> int:
    """COPY батча через staging + вставка. Возвращает число вставленных строк.

    Staging чистится явным TRUNCATE, а НЕ через `ON COMMIT DELETE ROWS`:
    asyncpg в автокоммите, COPY коммитится сам, и `ON COMMIT` сносил бы staging
    ДО `INSERT ... SELECT` — загрузчик молча вставлял бы ноль (ровно это
    случилось с load_release_formats на первом прогоне).
    """
    if not rows:
        return 0
    await pg.execute("TRUNCATE _new_stage")
    await pg.copy_records_to_table("_new_stage", records=rows, columns=_COLUMNS)
    inserted = await pg.fetchval(
        "WITH ins AS ("
        " INSERT INTO discogs_releases_index "
        f" ({', '.join(_COLUMNS)}) SELECT {', '.join(_COLUMNS)} FROM _new_stage"
        " ON CONFLICT (discogs_id) DO NOTHING RETURNING 1"
        ") SELECT COUNT(*) FROM ins"
    )
    return int(inserted or 0)


async def _sync_artist_names(min_id: int) -> int:
    """Дозаписать имена новых артистов в `discogs_artist_names`.

    Поиск артистов жёстко фильтрует выдачу по этой таблице
    (`filter_artist_names_with_releases`): чей имени в ней нет — тот из выдачи
    выпадает. Без этого шага артисты, дебютировавшие между дампами, находились
    бы в индексе, но были бы невидимы в поиске.

    Ограничиваем скан только что вставленным диапазоном id — полный DISTINCT по
    13M строк занял бы минуты.

    Плейсхолдер `$1`, а не `%s`: идём напрямую в asyncpg, у которого свой
    синтаксис (через `exec_driver_sql` с `%s` падает PostgresSyntaxError).
    """
    async with engine.connect() as conn:
        raw = await conn.get_raw_connection()
        pg = raw.driver_connection
        status = await pg.execute(
            "INSERT INTO discogs_artist_names (name_norm) "
            "SELECT DISTINCT lower(artist) FROM discogs_releases_index "
            "WHERE discogs_id > $1 AND artist IS NOT NULL AND artist <> '' "
            "ON CONFLICT (name_norm) DO NOTHING",
            min_id,
        )
        # asyncpg возвращает тег вида "INSERT 0 42".
        return int(status.rsplit(" ", 1)[-1]) if status else 0


async def load(file_path: Path, dump_date: date) -> dict[str, int]:
    counters = {"read": 0, "inserted": 0, "bad": 0}
    started = time.time()
    last_report = started
    batch: list[tuple] = []
    min_id: int | None = None

    async with engine.connect() as conn:
        raw = await conn.get_raw_connection()
        pg = raw.driver_connection
        await pg.execute(
            "CREATE TEMP TABLE IF NOT EXISTS _new_stage "
            "(LIKE discogs_releases_index INCLUDING DEFAULTS)"
        )
        with gzip.open(file_path, "rt", encoding="utf-8", newline="") as fh:
            for raw_row in csv.reader(fh):
                parsed = _row_to_tuple(raw_row, dump_date)
                if parsed is None:
                    counters["bad"] += 1
                    continue
                batch.append(parsed)
                counters["read"] += 1
                if min_id is None or parsed[0] < min_id:
                    min_id = parsed[0]
                if len(batch) >= _BATCH:
                    counters["inserted"] += await _flush(pg, batch)
                    batch = []
                    now = time.time()
                    if now - last_report >= 30:
                        logger.info(
                            "read=%d inserted=%d bad=%d rate=%.0f/s",
                            counters["read"], counters["inserted"], counters["bad"],
                            counters["read"] / (now - started),
                        )
                        last_report = now
        counters["inserted"] += await _flush(pg, batch)

    if counters["inserted"] and min_id is not None:
        names = await _sync_artist_names(min_id - 1)
        logger.info("новых имён артистов в поиске: %d", names)

    logger.info(
        "ГОТОВО за %.1f мин: read=%d inserted=%d (дубли пропущены) bad=%d",
        (time.time() - started) / 60,
        counters["read"], counters["inserted"], counters["bad"],
    )
    return counters


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--file", required=True, type=Path)
    parser.add_argument("--dump-date", required=True, help="YYYY-MM-DD")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        stream=sys.stdout,
    )
    if not args.file.exists():
        parser.error(f"нет файла: {args.file}")

    asyncio.run(load(args.file, date.fromisoformat(args.dump_date)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
