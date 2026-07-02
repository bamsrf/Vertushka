"""CLI: маппинг Discogs release ID → MusicBrainz MBID (+ наличие обложки CAA).

Зачем: MusicBrainz full-export содержит (а) готовые связи release↔discogs-URL
и (б) индекс Cover Art Archive — у каких релизов есть front-обложка. Вместе
это даёт обложки для dump-строк ВООБЩЕ без запросов к каким-либо API:

  discogs_id → mbid → https://coverartarchive.org/release/{mbid}/front-1200
                       (существование известно офлайн из caa-индекса)

Два режима — тяжёлый парсинг на локальной машине, на сервер едет только CSV:

  РЕЖИМ 1 (локально, БЕЗ зависимостей бэкенда — чистый stdlib):
    python3 Backend/app/scripts/ingest_mb_discogs_map.py \
      --dir ~/mbdump --caa-dir ~/mbdump-caa --export-csv ~/mb_map.csv.gz

  РЕЖИМ 2 (на сервере, грузит CSV в Postgres и сразу проставляет обложки):
    docker exec -d vertushka_api sh -c \
      "python -m app.scripts.ingest_mb_discogs_map --from-csv /tmp/mb_map.csv.gz \
       > /tmp/mb_map.log 2>&1"

Источник данных (https://data.metabrainz.org/pub/musicbrainz/data/fullexport/):
  mbdump.tar.bz2 (~7 GB)            → mbdump/url, mbdump/l_release_url, mbdump/release
  mbdump-cover-art-archive.tar.bz2  → mbdump/cover_art, mbdump/art_type,
     (~155 MB)                        mbdump/cover_art_type

Стрим-скачивание без хранения архива (пик диска = только 3 TSV, ~4 GB):
  curl -s .../mbdump.tar.bz2 | tar -xjf - -C ~/mbdump --strip-components=1 \
    mbdump/url mbdump/l_release_url mbdump/release
  curl -s .../mbdump-cover-art-archive.tar.bz2 | tar -xjf - -C ~/mbdump-caa \
    --strip-components=1 mbdump/cover_art mbdump/art_type mbdump/cover_art_type

CSV (gzip): discogs_id,mbid,has_front. Сервер при загрузке:
  1. TRUNCATE + COPY в mb_discogs_map; has_front=1 → caa_checked_at=now()
     (проверять нечего — знание офлайн), has_front=0 → тоже checked (front
     точно нет, HEAD не нужен).
  2. Массовый UPDATE discogs_releases_index.cover_image_url CAA-ссылками
     для has_front-пар — обложки появляются в выдаче сразу.

Формат TSV: колонки табом, \\N = NULL.
  url:            0=id, 2=url
  l_release_url:  2=entity0 (release id), 3=entity1 (url id)
  release:        0=id, 1=gid (MBID)
  cover_art:      0=id, ?=release  — колонку release ищем эвристикой
  art_type:       0=id, 1=name    — находим id типа "Front"
  cover_art_type: 0=id (cover_art), 1=type_id
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

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger("mb_map_ingest")

# Матчит и канонический /release/123, и legacy /Artist-Title/release/123.
_DISCOGS_RELEASE_RE = re.compile(r"discogs\.com/(?:[^\t]*?/)?release/(\d+)")

_BATCH = 10_000


# ────────────────────────────────────────────────────────────────────────
# Парсинг TSV (stdlib-only, работает без зависимостей бэкенда)
# ────────────────────────────────────────────────────────────────────────


def _parse_url_table(path: Path) -> dict[int, int]:
    """mbdump/url → {url_internal_id: discogs_release_id}."""
    mapping: dict[int, int] = {}
    started = time.monotonic()
    with path.open("r", encoding="utf-8", errors="replace") as fh:
        for n, line in enumerate(fh, 1):
            cols = line.rstrip("\n").split("\t")
            if len(cols) < 3:
                continue
            m = _DISCOGS_RELEASE_RE.search(cols[2])
            if m:
                mapping[int(cols[0])] = int(m.group(1))
            if n % 2_000_000 == 0:
                logger.info("url: %dM строк, %d discogs-ссылок", n // 1_000_000, len(mapping))
    logger.info(
        "url готов: %d discogs release-ссылок за %.0fs",
        len(mapping), time.monotonic() - started,
    )
    return mapping


def _parse_link_table(path: Path, url_map: dict[int, int]) -> dict[int, int]:
    """mbdump/l_release_url → {release_internal_id: discogs_release_id}.

    entity0 = release id, entity1 = url id. Один release может иметь
    несколько discogs-ссылок — берём первую.
    """
    mapping: dict[int, int] = {}
    with path.open("r", encoding="utf-8", errors="replace") as fh:
        for line in fh:
            cols = line.rstrip("\n").split("\t")
            if len(cols) < 4 or not cols[2].isdigit() or not cols[3].isdigit():
                continue
            discogs_id = url_map.get(int(cols[3]))
            if discogs_id is not None:
                mapping.setdefault(int(cols[2]), discogs_id)
    logger.info("l_release_url готов: %d release→discogs пар", len(mapping))
    return mapping


def _find_front_type_id(art_type_path: Path) -> int:
    """mbdump/art_type → id типа 'Front' (исторически 1, но не хардкодим)."""
    with art_type_path.open("r", encoding="utf-8", errors="replace") as fh:
        for line in fh:
            cols = line.rstrip("\n").split("\t")
            if len(cols) >= 2 and cols[1] == "Front" and cols[0].isdigit():
                return int(cols[0])
    raise SystemExit("Тип 'Front' не найден в art_type — формат дампа изменился?")


def _detect_release_col(cover_art_path: Path) -> int:
    """Колонка `release` в cover_art. В текущей схеме это idx 1, но порядок
    колонок в дампе не контрактный — проверяем по первой строке: ищем самое
    правдоподобное поле (целое число, не id и не edit)."""
    with cover_art_path.open("r", encoding="utf-8", errors="replace") as fh:
        first = fh.readline().rstrip("\n").split("\t")
    # Кандидаты: целочисленные колонки после id. release id — большой int.
    for idx in (1, 2, 3):
        if idx < len(first) and first[idx].isdigit():
            return idx
    raise SystemExit(f"Не могу определить колонку release в cover_art: {first[:6]}")


def _parse_front_covers(caa_dir: Path) -> set[int]:
    """→ множество MB release internal id, у которых есть front-обложка."""
    front_type = _find_front_type_id(caa_dir / "art_type")
    release_col = _detect_release_col(caa_dir / "cover_art")
    logger.info("caa: front type_id=%d, release col=%d", front_type, release_col)

    # cover_art id → release id
    art_release: dict[int, int] = {}
    with (caa_dir / "cover_art").open("r", encoding="utf-8", errors="replace") as fh:
        for line in fh:
            cols = line.rstrip("\n").split("\t")
            if len(cols) > release_col and cols[0].isdigit() and cols[release_col].isdigit():
                art_release[int(cols[0])] = int(cols[release_col])

    front_releases: set[int] = set()
    with (caa_dir / "cover_art_type").open("r", encoding="utf-8", errors="replace") as fh:
        for line in fh:
            cols = line.rstrip("\n").split("\t")
            if len(cols) >= 2 and cols[0].isdigit() and cols[1].isdigit():
                if int(cols[1]) == front_type:
                    rel = art_release.get(int(cols[0]))
                    if rel is not None:
                        front_releases.add(rel)
    logger.info("caa готов: %d релизов с front-обложкой", len(front_releases))
    return front_releases


def _iter_pairs(dump_dir: Path, caa_dir: Path | None):
    """Генератор (discogs_id, mbid, has_front) по release-таблице."""
    url_map = _parse_url_table(dump_dir / "url")
    release_map = _parse_link_table(dump_dir / "l_release_url", url_map)
    del url_map
    front = _parse_front_covers(caa_dir) if caa_dir else set()

    seen: set[int] = set()
    with (dump_dir / "release").open("r", encoding="utf-8", errors="replace") as fh:
        for line in fh:
            cols = line.split("\t", 2)
            if len(cols) < 2 or not cols[0].isdigit():
                continue
            internal_id = int(cols[0])
            discogs_id = release_map.get(internal_id)
            if discogs_id is None or discogs_id in seen:
                continue
            seen.add(discogs_id)
            yield discogs_id, cols[1], 1 if internal_id in front else 0


# ────────────────────────────────────────────────────────────────────────
# Режим 1: экспорт CSV (локальная машина)
# ────────────────────────────────────────────────────────────────────────


def export_csv(dump_dir: Path, caa_dir: Path | None, out_path: Path) -> None:
    for name in ("url", "l_release_url", "release"):
        if not (dump_dir / name).exists():
            raise SystemExit(f"Файл не найден: {dump_dir / name}")
    if caa_dir:
        for name in ("cover_art", "art_type", "cover_art_type"):
            if not (caa_dir / name).exists():
                raise SystemExit(f"Файл не найден: {caa_dir / name}")

    started = time.monotonic()
    total = with_front = 0
    with gzip.open(out_path, "wt", newline="") as fh:
        writer = csv.writer(fh)
        for discogs_id, mbid, has_front in _iter_pairs(dump_dir, caa_dir):
            writer.writerow((discogs_id, mbid, has_front))
            total += 1
            with_front += has_front
            if total % 500_000 == 0:
                logger.info("экспортировано ~%d пар", total)
    logger.info(
        "ГОТОВО: %d пар (%d с front-обложкой, %.0f%%) → %s за %.0fs",
        total, with_front, 100.0 * with_front / max(total, 1),
        out_path, time.monotonic() - started,
    )


# ────────────────────────────────────────────────────────────────────────
# Режим 2: загрузка CSV в Postgres (сервер)
# ────────────────────────────────────────────────────────────────────────


async def load_csv(csv_path: Path) -> None:
    # Импорт здесь, а не на уровне модуля: режим 1 работает без зависимостей.
    from app.database import engine

    started = time.monotonic()
    async with engine.connect() as conn:
        raw_conn = await conn.get_raw_connection()
        pg = raw_conn.driver_connection  # asyncpg.Connection

        await pg.execute("TRUNCATE mb_discogs_map")

        total = 0
        batch: list[tuple[int, str, bool]] = []
        opener = gzip.open if csv_path.suffix == ".gz" else open
        with opener(csv_path, "rt", newline="") as fh:
            for row in csv.reader(fh):
                if len(row) != 3 or not row[0].isdigit():
                    continue
                batch.append((int(row[0]), row[1], row[2] == "1"))
                if len(batch) >= _BATCH:
                    total += await _copy_batch(pg, batch)
                    batch = []
                    if total % 500_000 == 0:
                        logger.info("загружено ~%d пар", total)
        if batch:
            total += await _copy_batch(pg, batch)

        # Наличие front известно офлайн — все строки сразу checked,
        # HEAD-проверки CAA (warm_caa_covers) не нужны.
        await pg.execute("UPDATE mb_discogs_map SET caa_checked_at = now()")

        # Массовая простановка обложек: has_front → CAA URL в dump-индекс.
        updated = await pg.fetchval(
            "WITH upd AS ("
            " UPDATE discogs_releases_index d "
            " SET cover_image_url = "
            "   'https://coverartarchive.org/release/' || m.mbid || '/front-1200' "
            " FROM mb_discogs_map m "
            " WHERE m.discogs_id = d.discogs_id "
            " AND m.has_front "
            " AND d.cover_image_url IS NULL "
            " RETURNING 1"
            ") SELECT COUNT(*) FROM upd"
        )

        final = await pg.fetchval("SELECT COUNT(*) FROM mb_discogs_map")

    logger.info(
        "ГОТОВО: %d пар в mb_discogs_map, %d обложек проставлено в "
        "discogs_releases_index за %.0fs",
        final, updated, time.monotonic() - started,
    )


async def _copy_batch(pg, batch: list[tuple[int, str, bool]]) -> int:
    await pg.copy_records_to_table(
        "mb_discogs_map", records=batch,
        columns=("discogs_id", "mbid", "has_front"),
    )
    return len(batch)


# ────────────────────────────────────────────────────────────────────────


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dir", help="папка с mbdump/url, l_release_url, release")
    parser.add_argument("--caa-dir", help="папка с cover_art, art_type, cover_art_type")
    parser.add_argument("--export-csv", help="режим 1: выгрузить пары в CSV (gzip)")
    parser.add_argument("--from-csv", help="режим 2: загрузить CSV в Postgres")
    args = parser.parse_args()

    if args.export_csv:
        if not args.dir:
            raise SystemExit("--export-csv требует --dir")
        export_csv(
            Path(args.dir),
            Path(args.caa_dir) if args.caa_dir else None,
            Path(args.export_csv),
        )
    elif args.from_csv:
        asyncio.run(load_csv(Path(args.from_csv)))
    else:
        raise SystemExit("Укажи --export-csv (локально) или --from-csv (сервер)")


if __name__ == "__main__":
    main()
