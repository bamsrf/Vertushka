"""CLI: barcode-канал обложек — MB release.barcode → CAA front, мимо всех API.

Дополняет ingest_mb_discogs_map (URL-связи): тот покрыл релизы, которые
MB-редакторы вручную связали с discogs.com. Здесь матчим ОСТАЛЬНЫЕ через
штрихкод: mb release.barcode (нормализованный до цифр, как barcode_norm
в discogs_releases_index) → mbid с front-обложкой в CAA-индексе.

Результат пишется ТОЛЬКО в discogs_releases_index.cover_image_url (для строк
без обложки). В mb_discogs_map НЕ пишем: barcode-матч слабее URL-связи
(один штрихкод может носить несколько региональных изданий) — для обложки
это неважно (арт один), для identity-маппинга (треклисты) — важно.

РЕЖИМ 1 (локально, stdlib-only; дампы уже лежат ~/mbdump, ~/mbdump-caa):
  python3 Backend/app/scripts/ingest_mb_barcode_covers.py \
    --dir ~/mbdump --caa-dir ~/mbdump-caa --export-csv ~/mb_barcode_covers.csv.gz

РЕЖИМ 2 (на сервере, в контейнере api):
  python -m app.scripts.ingest_mb_barcode_covers --from-csv /tmp/mb_barcode_covers.csv.gz

CSV (gzip): barcode_norm,mbid — только пары с front-обложкой (has_front=0
бесполезны для этого канала и раздувают файл).

Формат release TSV: 0=id, 1=gid (MBID), 9=barcode (\\N = NULL).
"""
from __future__ import annotations

import argparse
import asyncio
import csv
import gzip
import logging
import re
import sys
import time
from pathlib import Path

# Режим 1 запускается напрямую файлом (без пакета app на path) — шим.
try:
    from app.scripts.ingest_mb_discogs_map import _parse_front_covers
except ModuleNotFoundError:  # локальный запуск: python3 .../ingest_mb_barcode_covers.py
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from app.scripts.ingest_mb_discogs_map import _parse_front_covers

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger("mb_barcode_ingest")

_BATCH = 10_000
_NON_DIGIT = re.compile(r"\D+")  # идентично _norm_barcode в ingest_discogs_dump
_BARCODE_COL = 9
_MIN_BARCODE_LEN = 7  # короче — не EAN/UPC, шум (например "0", даты)


def _iter_barcode_pairs(dump_dir: Path, caa_dir: Path):
    """Генератор (barcode_norm, mbid) для MB-релизов с front-обложкой.

    Один штрихкод → один mbid (первый с front): арт у изданий с одинаковым
    штрихкодом один и тот же, коллизии не важны.
    """
    front = _parse_front_covers(caa_dir)

    seen: set[str] = set()
    total = matched = 0
    with (dump_dir / "release").open("r", encoding="utf-8", errors="replace") as fh:
        for line in fh:
            cols = line.rstrip("\n").split("\t")
            total += 1
            if len(cols) <= _BARCODE_COL or not cols[0].isdigit():
                continue
            if int(cols[0]) not in front:
                continue
            raw = cols[_BARCODE_COL]
            if not raw or raw == "\\N":
                continue
            norm = _NON_DIGIT.sub("", raw)
            if len(norm) < _MIN_BARCODE_LEN or norm in seen:
                continue
            seen.add(norm)
            matched += 1
            yield norm, cols[1]
            if matched % 500_000 == 0:
                logger.info("release: %d строк, %d barcode-пар", total, matched)
    logger.info("release готов: %d строк, %d уникальных barcode с front", total, matched)


def export_csv(dump_dir: Path, caa_dir: Path, out_path: Path) -> None:
    if not (dump_dir / "release").exists():
        raise SystemExit(f"Файл не найден: {dump_dir / 'release'}")
    for name in ("cover_art", "art_type", "cover_art_type"):
        if not (caa_dir / name).exists():
            raise SystemExit(f"Файл не найден: {caa_dir / name}")

    started = time.monotonic()
    total = 0
    with gzip.open(out_path, "wt", newline="") as fh:
        writer = csv.writer(fh)
        for barcode_norm, mbid in _iter_barcode_pairs(dump_dir, caa_dir):
            writer.writerow((barcode_norm, mbid))
            total += 1
    logger.info(
        "ГОТОВО: %d barcode-пар → %s за %.0fs",
        total, out_path, time.monotonic() - started,
    )


async def load_csv(csv_path: Path) -> None:
    from app.database import engine

    started = time.monotonic()
    async with engine.connect() as conn:
        raw_conn = await conn.get_raw_connection()
        pg = raw_conn.driver_connection  # asyncpg.Connection

        await pg.execute(
            "CREATE TABLE IF NOT EXISTS mb_barcode_covers ("
            " barcode_norm TEXT PRIMARY KEY,"
            " mbid TEXT NOT NULL)"
        )
        await pg.execute("TRUNCATE mb_barcode_covers")

        total = 0
        batch: list[tuple[str, str]] = []
        seen: set[str] = set()
        opener = gzip.open if csv_path.suffix == ".gz" else open
        with opener(csv_path, "rt", newline="") as fh:
            for row in csv.reader(fh):
                if len(row) != 2 or not row[0].isdigit() or row[0] in seen:
                    continue
                seen.add(row[0])
                batch.append((row[0], row[1]))
                if len(batch) >= _BATCH:
                    await pg.copy_records_to_table(
                        "mb_barcode_covers", records=batch,
                        columns=("barcode_norm", "mbid"),
                    )
                    total += len(batch)
                    batch = []
                    if total % 500_000 == 0:
                        logger.info("загружено ~%d пар", total)
        if batch:
            await pg.copy_records_to_table(
                "mb_barcode_covers", records=batch,
                columns=("barcode_norm", "mbid"),
            )
            total += len(batch)

        # Простановка обложек: только строки БЕЗ обложки (URL-канал и все
        # прочие источники приоритетнее — их не трогаем).
        updated = await pg.fetchval(
            "WITH upd AS ("
            " UPDATE discogs_releases_index d "
            " SET cover_image_url = "
            "   'https://coverartarchive.org/release/' || b.mbid || '/front-1200' "
            " FROM mb_barcode_covers b "
            " WHERE b.barcode_norm = d.barcode_norm "
            " AND d.cover_image_url IS NULL "
            " RETURNING 1"
            ") SELECT COUNT(*) FROM upd"
        )

    logger.info(
        "ГОТОВО: %d пар в mb_barcode_covers, %d обложек проставлено в "
        "discogs_releases_index за %.0fs",
        total, updated, time.monotonic() - started,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dir", type=Path, help="Каталог mbdump (release)")
    parser.add_argument("--caa-dir", type=Path, help="Каталог mbdump-caa")
    parser.add_argument("--export-csv", type=Path, help="Режим 1: путь CSV.gz")
    parser.add_argument("--from-csv", type=Path, help="Режим 2: загрузка CSV в PG")
    args = parser.parse_args()

    if args.export_csv:
        if not args.dir or not args.caa_dir:
            raise SystemExit("--export-csv требует --dir и --caa-dir")
        export_csv(args.dir, args.caa_dir, args.export_csv)
    elif args.from_csv:
        asyncio.run(load_csv(args.from_csv))
    else:
        parser.print_help()
        raise SystemExit(1)


if __name__ == "__main__":
    main()
