"""CLI: загрузка artist-CSV в Postgres (на сервере, в контейнере).

Входные CSV готовит локальный app/scripts/extract_discogs_artist_map.py:
  artists.csv.gz         → discogs_artists (TRUNCATE + COPY)
  release_artists.csv.gz → discogs_releases_index.artist_ids (staging + UPDATE)

После backfill'а строит GIN-индекс по artist_ids (CONCURRENTLY).

Использование:
  docker cp artists.csv.gz vertushka_api:/tmp/
  docker cp release_artists.csv.gz vertushka_api:/tmp/
  docker exec -d vertushka_api sh -c \
    "python -m app.scripts.load_artist_map \
     --artists-csv /tmp/artists.csv.gz \
     --map-csv /tmp/release_artists.csv.gz > /tmp/artist_map.log 2>&1"

UPDATE 13M строк — тяжёлый (перезапись кортежей): ~10-20 мин + WAL.
Повторный запуск безопасен (TRUNCATE artists; map-UPDATE идемпотентен).
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

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger("artist_map_load")

_BATCH = 20_000


async def load_artists(pg, csv_path: Path) -> None:
    started = time.monotonic()
    await pg.execute("TRUNCATE discogs_artists")
    total = 0
    batch: list[tuple[int, str]] = []
    with gzip.open(csv_path, "rt", newline="") as fh:
        for row in csv.reader(fh):
            if len(row) != 2 or not row[0].isdigit() or not row[1]:
                continue
            batch.append((int(row[0]), row[1]))
            if len(batch) >= _BATCH:
                await pg.copy_records_to_table(
                    "discogs_artists", records=batch, columns=("artist_id", "name"),
                )
                total += len(batch)
                batch = []
                if total % 2_000_000 == 0:
                    logger.info("artists: %dM", total // 1_000_000)
    if batch:
        await pg.copy_records_to_table(
            "discogs_artists", records=batch, columns=("artist_id", "name"),
        )
        total += len(batch)
    logger.info("discogs_artists: %d строк за %.0fs", total, time.monotonic() - started)


async def load_release_map(pg, csv_path: Path) -> None:
    started = time.monotonic()
    # Без PK: дубликаты release_id в дампе не встречаются, а set-дедуп на
    # 16M id съел бы ~1.5 GB RAM контейнера. UPDATE-join дубликаты переживёт.
    await pg.execute(
        "CREATE TEMP TABLE _ra_stage (release_id BIGINT, ids TEXT)"
    )
    total = 0
    batch: list[tuple[int, str]] = []
    with gzip.open(csv_path, "rt", newline="") as fh:
        for row in csv.reader(fh):
            if len(row) != 2 or not row[0].isdigit():
                continue
            batch.append((int(row[0]), row[1]))
            if len(batch) >= _BATCH:
                await pg.copy_records_to_table(
                    "_ra_stage", records=batch, columns=("release_id", "ids"),
                )
                total += len(batch)
                batch = []
                if total % 2_000_000 == 0:
                    logger.info("map staging: %dM (%.0f мин)", total // 1_000_000,
                                (time.monotonic() - started) / 60)
    if batch:
        await pg.copy_records_to_table(
            "_ra_stage", records=batch, columns=("release_id", "ids"),
        )
        total += len(batch)
    logger.info("staging загружен: %d строк, начинаю UPDATE (10-20 мин)...", total)

    updated = await pg.fetchval(
        "WITH upd AS ("
        " UPDATE discogs_releases_index d "
        " SET artist_ids = string_to_array(s.ids, ';')::bigint[] "
        " FROM _ra_stage s "
        " WHERE d.discogs_id = s.release_id "
        " AND d.artist_ids IS DISTINCT FROM string_to_array(s.ids, ';')::bigint[] "
        " RETURNING 1"
        ") SELECT COUNT(*) FROM upd"
    )
    logger.info("artist_ids: %d строк обновлено за %.0f мин",
                updated, (time.monotonic() - started) / 60)


async def build_gin(pg) -> None:
    logger.info("строю GIN-индекс по artist_ids (CONCURRENTLY)...")
    started = time.monotonic()
    await pg.execute(
        "CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_dri_artist_ids "
        "ON discogs_releases_index USING GIN (artist_ids)"
    )
    logger.info("GIN готов за %.0f мин", (time.monotonic() - started) / 60)


async def run(artists_csv: Path | None, map_csv: Path | None) -> None:
    async with engine.connect() as conn:
        raw_conn = await conn.get_raw_connection()
        pg = raw_conn.driver_connection
        if artists_csv:
            await load_artists(pg, artists_csv)
        if map_csv:
            await load_release_map(pg, map_csv)
            await build_gin(pg)
    logger.info("ГОТОВО")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artists-csv")
    parser.add_argument("--map-csv")
    args = parser.parse_args()
    if not args.artists_csv and not args.map_csv:
        raise SystemExit("Укажи --artists-csv и/или --map-csv")
    asyncio.run(run(
        Path(args.artists_csv) if args.artists_csv else None,
        Path(args.map_csv) if args.map_csv else None,
    ))


if __name__ == "__main__":
    main()
