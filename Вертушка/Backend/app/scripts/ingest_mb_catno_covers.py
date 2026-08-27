"""CLI: катномер-канал обложек — MB (catno+label) → CAA front, мимо всех API.

Третий офлайн-ключ после URL-связей (ingest_mb_discogs_map) и штрихкодов
(ingest_mb_barcode_covers). Мотивация в цифрах (замер 27.08.2026): у 99.96%
непокрытых релизов в discogs_releases_index есть каталожный номер + лейбл,
штрихкод — только у 22%. Катномер — единственный ключ, дотягивающийся до
безштрихкодового винила, а в CAA лежит 3.8M front-обложек, из которых
первые два ключа достали ~1.3M.

Матч слабее URL-связи и штрихкода, поэтому канал НАМЕРЕННО консервативен:

  - ключ (catno_norm, label_norm) обязан быть однозначным внутри MB на
    уровне release group — два разных альбома с одним ключом выбрасывают
    ключ целиком (_resolve_key);
  - нормализация зеркалит Discogs-сторону символ в символ
    (_CATALOG_RE = [\\s\\-\\.]+ → strip → upper, см. ingest_discogs_dump);
  - вырожденные катномера (NONE, короче 3 символов) не участвуют;
  - применение к индексу требует год с обеих сторон и |Δyear| <= 2;
  - и главное: --from-csv только грузит таблицу и печатает ЗАМЕР ТОЧНОСТИ
    на ground truth (релизы, чей mbid уже известен из URL-связей).
    UPDATE индекса — отдельный явный --apply, запускать только после
    просмотра цифр. Урок инцидента с подменёнными обложками: массовые
    операции не запускаются без замера на выборке.

РЕЖИМ 1 (локально, stdlib-only; дампы в ~/mbdump и ~/mbdump-caa):
  python3 Backend/app/scripts/ingest_mb_catno_covers.py \
    --dir ~/mbdump --caa-dir ~/mbdump-caa --export-csv ~/mb_catno_covers.csv.gz

РЕЖИМ 2 (сервер, контейнер api): загрузка + отчёт точности, БЕЗ записи:
  python -m app.scripts.ingest_mb_catno_covers --from-csv /tmp/mb_catno_covers.csv.gz

РЕЖИМ 3 (сервер, после просмотра отчёта): простановка обложек:
  python -m app.scripts.ingest_mb_catno_covers --apply

Форматы TSV:
  release_label: 0=id, 1=release, 2=label, 3=catalog_number
  label:         0=id, 1=gid, 2=name
  release:       0=id, 1=gid (MBID), 4=release_group
  release_country / release_unknown_country: 0=release, [1=country,] дальше
    date_year — колонку года ищем по позиции (1 или 2, см. _YEAR_COL).
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
from collections import defaultdict
from pathlib import Path

try:
    from app.scripts.ingest_mb_discogs_map import _parse_front_covers
except ModuleNotFoundError:  # локальный запуск файлом
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from app.scripts.ingest_mb_discogs_map import _parse_front_covers

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger("mb_catno_ingest")

_BATCH = 10_000

# ЗЕРКАЛО ingest_discogs_dump._CATALOG_RE — менять только синхронно с ним,
# иначе ключи молча перестанут совпадать (тест сверяет оба модуля).
_CATALOG_RE = re.compile(r"[\s\-\.]+")

# Вырожденные значения: дискогсовское «без номера», MB-шные заглушки в
# скобках ([none] — реальная форма из release_label) и совсем короткий шум.
_JUNK_CATNOS = {"NONE", "NOCAT", "N/A", "NA", "UNKNOWN", "[NONE]", "[UNKNOWN]"}
_MIN_CATNO_LEN = 3

# Применение/валидация: год обязан быть с обеих сторон и близко.
_MAX_YEAR_DIFF = 2

# Discogs-сторона той же нормализации — для SQL-джойнов.
_SQL_LABEL_NORM = r"upper(regexp_replace(d.label, '[\s\-\.]+', '', 'g'))"


def _norm_key(raw: str | None) -> str | None:
    """Одна нормализация на катномер и лейбл: [\\s\\-\\.]+ → '' → upper."""
    if not raw or raw == "\\N":
        return None
    cleaned = _CATALOG_RE.sub("", raw).upper().strip()
    return cleaned or None


def _catno_ok(norm: str | None) -> bool:
    return norm is not None and len(norm) >= _MIN_CATNO_LEN and norm not in _JUNK_CATNOS


def _resolve_key(candidates: list[tuple[str, int, int | None]]) -> tuple[str, int, int | None] | None:
    """Кому достаётся ключ (catno, label): (mbid, release_group, year) | None.

    candidates — все MB-релизы с front-обложкой под этим ключом.
    Правило: все кандидаты обязаны быть ОДНИМ альбомом (release group);
    два разных альбома с одинаковым катномером и лейблом — неоднозначность,
    ключ выбрасывается целиком. Внутри одного альбома арт взаимозаменяем;
    берём кандидата с минимальным известным годом (оригинальный пресс),
    а без годов — первого по mbid (детерминизм для идемпотентного экспорта).
    """
    if not candidates:
        return None
    groups = {rg for _, rg, _ in candidates}
    if len(groups) != 1:
        return None
    dated = [c for c in candidates if c[2] is not None]
    pool = dated or candidates
    return min(pool, key=lambda c: (c[2] if c[2] is not None else 9999, c[0]))


def _parse_labels(dump_dir: Path) -> dict[int, str]:
    """label → {id: label_norm}."""
    out: dict[int, str] = {}
    with (dump_dir / "label").open("r", encoding="utf-8", errors="replace") as fh:
        for line in fh:
            cols = line.rstrip("\n").split("\t")
            if len(cols) < 3 or not cols[0].isdigit():
                continue
            norm = _norm_key(cols[2])
            if norm:
                out[int(cols[0])] = norm
    logger.info("label готов: %d лейблов", len(out))
    return out


def _parse_years(dump_dir: Path, wanted: set[int]) -> dict[int, int]:
    """Минимальный год релиза из release_country + release_unknown_country."""
    years: dict[int, int] = {}

    def eat(path: Path, year_col: int) -> None:
        if not path.exists():
            return
        with path.open("r", encoding="utf-8", errors="replace") as fh:
            for line in fh:
                cols = line.rstrip("\n").split("\t")
                if len(cols) <= year_col or not cols[0].isdigit():
                    continue
                rid = int(cols[0])
                if rid not in wanted:
                    continue
                y = cols[year_col]
                if y and y != "\\N" and y.isdigit():
                    yi = int(y)
                    if 1900 <= yi <= 2100 and (rid not in years or yi < years[rid]):
                        years[rid] = yi

    eat(dump_dir / "release_country", 2)          # 0=release,1=country,2=year
    eat(dump_dir / "release_unknown_country", 1)  # 0=release,1=year
    logger.info("годы: %d релизов датированы", len(years))
    return years


def _iter_catno_rows(dump_dir: Path, caa_dir: Path):
    """Генератор строк CSV: (catno_norm, label_norm, year|'', mbid, release_group)."""
    front = _parse_front_covers(caa_dir)
    labels = _parse_labels(dump_dir)

    # release: id → (mbid, release_group) только для релизов с front.
    rel: dict[int, tuple[str, int]] = {}
    with (dump_dir / "release").open("r", encoding="utf-8", errors="replace") as fh:
        for line in fh:
            cols = line.rstrip("\n").split("\t")
            if len(cols) < 5 or not cols[0].isdigit():
                continue
            rid = int(cols[0])
            if rid in front and cols[4].isdigit():
                rel[rid] = (cols[1], int(cols[4]))
    logger.info("release готов: %d релизов с front и группой", len(rel))

    years = _parse_years(dump_dir, set(rel))

    # release_label → кандидаты по ключу.
    buckets: dict[tuple[str, str], list[tuple[str, int, int | None]]] = defaultdict(list)
    rows = 0
    with (dump_dir / "release_label").open("r", encoding="utf-8", errors="replace") as fh:
        for line in fh:
            cols = line.rstrip("\n").split("\t")
            if len(cols) < 4 or not cols[1].isdigit():
                continue
            rid = int(cols[1])
            if rid not in rel:
                continue
            label_norm = labels.get(int(cols[2])) if cols[2].isdigit() else None
            catno = _norm_key(cols[3])
            if not label_norm or not _catno_ok(catno):
                continue
            mbid, rg = rel[rid]
            buckets[(catno, label_norm)].append((mbid, rg, years.get(rid)))
            rows += 1
    logger.info("release_label готов: %d связок, %d ключей", rows, len(buckets))

    kept = dropped = 0
    for (catno, label_norm), cands in buckets.items():
        row = _resolve_key(cands)
        if row is None:
            dropped += 1
            continue
        mbid, rg, year = row
        kept += 1
        yield catno, label_norm, year if year is not None else "", mbid, rg
    logger.info("ключи: %d однозначных, %d коллизий выброшено", kept, dropped)


def export_csv(dump_dir: Path, caa_dir: Path, out_path: Path) -> None:
    for name in ("release", "release_label", "label"):
        if not (dump_dir / name).exists():
            raise SystemExit(f"Файл не найден: {dump_dir / name}")
    for name in ("cover_art", "art_type", "cover_art_type"):
        if not (caa_dir / name).exists():
            raise SystemExit(f"Файл не найден: {caa_dir / name}")

    started = time.monotonic()
    total = 0
    with gzip.open(out_path, "wt", newline="") as fh:
        writer = csv.writer(fh)
        for row in _iter_catno_rows(dump_dir, caa_dir):
            writer.writerow(row)
            total += 1
    logger.info("ГОТОВО: %d ключей → %s за %.0fs", total, out_path, time.monotonic() - started)


_VALIDATE_SQL = f"""
WITH cand AS (
  SELECT d.discogs_id, t.mbid::text AS truth_mbid,
         m.mbid AS cand_mbid, m.release_group AS cand_rg
  FROM discogs_releases_index d
  JOIN mb_discogs_map t ON t.discogs_id = d.discogs_id
  JOIN mb_catno_covers m
    ON m.catno_norm = d.catalog_norm
   AND m.label_norm = {_SQL_LABEL_NORM}
   AND d.year IS NOT NULL AND m.year IS NOT NULL
   AND abs(d.year - m.year) <= {_MAX_YEAR_DIFF}
)
SELECT count(*) AS matched,
       count(*) FILTER (WHERE cand_mbid = truth_mbid) AS exact_mbid,
       count(tr.release_group) AS rg_known,
       count(*) FILTER (WHERE cand_rg = tr.release_group) AS same_group
FROM cand
LEFT JOIN (SELECT DISTINCT mbid, release_group FROM mb_catno_covers) tr
  ON tr.mbid = cand.truth_mbid
"""

_APPLY_SQL = f"""
WITH upd AS (
  UPDATE discogs_releases_index d
  SET cover_image_url =
    'https://coverartarchive.org/release/' || m.mbid || '/front-1200'
  FROM mb_catno_covers m
  WHERE m.catno_norm = d.catalog_norm
    AND m.label_norm = {_SQL_LABEL_NORM}
    AND d.year IS NOT NULL AND m.year IS NOT NULL
    AND abs(d.year - m.year) <= {_MAX_YEAR_DIFF}
    AND d.cover_image_url IS NULL
  RETURNING 1
) SELECT count(*) FROM upd
"""


async def _pg():
    from app.database import engine
    conn = await engine.connect()
    raw = await conn.get_raw_connection()
    pg = raw.driver_connection
    # Загрузка/джойны по 11M-таблице не влезают в app'шные 30s — грабли
    # July-прогонов (QueryCanceledError на финальном UPDATE). Своя сессия,
    # свой лимит.
    await pg.execute("SET statement_timeout = 0")
    return conn, pg


async def load_csv(csv_path: Path) -> None:
    started = time.monotonic()
    conn, pg = await _pg()
    try:
        await pg.execute(
            "CREATE TABLE IF NOT EXISTS mb_catno_covers ("
            " catno_norm TEXT NOT NULL,"
            " label_norm TEXT NOT NULL,"
            " year SMALLINT,"
            " mbid TEXT NOT NULL,"
            " release_group BIGINT NOT NULL,"
            " PRIMARY KEY (catno_norm, label_norm))"
        )
        await pg.execute("TRUNCATE mb_catno_covers")

        total = 0
        batch: list[tuple[str, str, int | None, str, int]] = []
        seen: set[tuple[str, str]] = set()
        opener = gzip.open if csv_path.suffix == ".gz" else open
        with opener(csv_path, "rt", newline="") as fh:
            for row in csv.reader(fh):
                if len(row) != 5:
                    continue
                key = (row[0], row[1])
                if key in seen:
                    continue
                seen.add(key)
                batch.append((row[0], row[1], int(row[2]) if row[2] else None, row[3], int(row[4])))
                if len(batch) >= _BATCH:
                    await pg.copy_records_to_table(
                        "mb_catno_covers", records=batch,
                        columns=("catno_norm", "label_norm", "year", "mbid", "release_group"),
                    )
                    total += len(batch)
                    batch = []
                    if total % 500_000 == 0:
                        logger.info("загружено ~%d ключей", total)
        if batch:
            await pg.copy_records_to_table(
                "mb_catno_covers", records=batch,
                columns=("catno_norm", "label_norm", "year", "mbid", "release_group"),
            )
            total += len(batch)
        logger.info("таблица загружена: %d ключей за %.0fs", total, time.monotonic() - started)

        await validate(pg)
        logger.info(
            "Запись в индекс НЕ выполнялась. Посмотри цифры выше; если "
            "same_group/rg_known >= 97%% — запускай --apply."
        )
    finally:
        await conn.close()


async def validate(pg=None) -> None:
    """Точность на ground truth: релизы, чей mbid известен из URL-связей."""
    own = pg is None
    if own:
        conn, pg = await _pg()
    try:
        row = await pg.fetchrow(_VALIDATE_SQL)
        matched, exact, rg_known, same_group = (
            row["matched"], row["exact_mbid"], row["rg_known"], row["same_group"],
        )
        logger.info("=== ВАЛИДАЦИЯ на ground truth (URL-связи) ===")
        logger.info("катномер-матчей на размеченных релизах: %d", matched)
        if matched:
            logger.info("  точный mbid:        %d (%.1f%%)", exact, 100.0 * exact / matched)
        if rg_known:
            logger.info(
                "  тот же альбом (rg): %d из %d размеченных (%.1f%%) — ключевая метрика",
                same_group, rg_known, 100.0 * same_group / rg_known,
            )
        if not matched:
            logger.warning("пересечения с ground truth нет — проверять нечего")
    finally:
        if own:
            await conn.close()


async def apply_updates() -> None:
    started = time.monotonic()
    conn, pg = await _pg()
    try:
        updated = await pg.fetchval(_APPLY_SQL)
        logger.info(
            "ГОТОВО: %d обложек проставлено в discogs_releases_index за %.0fs",
            updated, time.monotonic() - started,
        )
    finally:
        await conn.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dir", type=Path, help="Каталог mbdump")
    parser.add_argument("--caa-dir", type=Path, help="Каталог mbdump-caa")
    parser.add_argument("--export-csv", type=Path, help="Режим 1: путь CSV.gz")
    parser.add_argument("--from-csv", type=Path, help="Режим 2: загрузка + отчёт точности (без записи)")
    parser.add_argument("--validate", action="store_true", help="Только отчёт точности")
    parser.add_argument("--apply", action="store_true", help="Режим 3: простановка обложек в индекс")
    args = parser.parse_args()

    if args.export_csv:
        if not args.dir or not args.caa_dir:
            raise SystemExit("--export-csv требует --dir и --caa-dir")
        export_csv(args.dir, args.caa_dir, args.export_csv)
    elif args.from_csv:
        asyncio.run(load_csv(args.from_csv))
    elif args.validate:
        asyncio.run(validate())
    elif args.apply:
        asyncio.run(apply_updates())
    else:
        parser.print_help()
        raise SystemExit(1)


if __name__ == "__main__":
    main()
