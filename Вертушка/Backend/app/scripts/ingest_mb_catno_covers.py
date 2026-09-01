"""CLI: катномер-канал обложек — MB (catno+label) → CAA front, мимо всех API.

Третий офлайн-ключ после URL-связей (ingest_mb_discogs_map) и штрихкодов
(ingest_mb_barcode_covers). ЗАПУСКАТЬ СТРОГО ПОСЛЕ НИХ: все каналы пишут по
правилу «заполни NULL», слот занимается навсегда, и догадка по катномеру не
должна опережать точный ключ.

Мотивация в цифрах (замер 27.08.2026): у 99.96% непокрытых релизов индекса
есть каталожный номер + лейбл, штрихкод — только у 22%. В CAA 3.8M
front-обложек, первые два ключа достали ~1.3M.

Ключ слабее штрихкода, поэтому канал обороняется в глубину:

  1. нормализация зеркалит Discogs-сторону (_CATALOG_RE → strip → upper);
  2. неоднозначность считается по ВСЕМУ MB: ключ (catno, label), под которым
     в MB больше одного release group — С АРТОМ ИЛИ БЕЗ — выбрасывается;
  3. вырожденные катномера И лейблы (NONE, [none], Not On Label, White
     Label…) не участвуют;
  4. применение требует год с обеих сторон, |Δ| <= 2;
  5. веерность ограничена: ключ, накрывающий больше _MAX_KEY_FANOUT строк
     индекса, пропускается целиком (серийные номера, боксы);
  6. решающая проверка лейбла — в Python (_norm_key), SQL-джойн лишь
     префильтр: расхождение двух нормализаций не может дать ложный матч;
  7. --apply сам гоняет валидацию на НЕПОКРЫТОЙ популяции и отказывается
     ниже порога; каждая записанная строка фиксируется в catno_cover_audit —
     откат возможен всегда (урок инцидента с подменёнными обложками).

Известное ограничение: пара (catalog_norm, label) в самом Discogs-индексе
может быть «химерой» — catno и имя от разных <label>-элементов
мультилейблового релиза (ingest_discogs_dump берёт первый непустой каждого).
Каналом это не лечится; защита — пп. 2, 4, 5.

Что считается успехом: обложка ТОГО ЖЕ АЛЬБОМА (release group). Другой пресс
того же альбома — допустимый исход by design, как у master-фолбэка.

РЕЖИМ 1 (локально, stdlib-only; дампы в ~/mbdump и ~/mbdump-caa):
  python3 Backend/app/scripts/ingest_mb_catno_covers.py \
    --dir ~/mbdump --caa-dir ~/mbdump-caa --export-csv ~/mb_catno_covers.csv.gz
  Пишет ДВА файла: основной и ~/mb_catno_covers.rg.csv.gz (mbid → release
  group всех MB-релизов — независимый источник правды для валидации).

РЕЖИМ 2 (сервер): загрузка обоих CSV + отчёт точности, БЕЗ записи в индекс:
  python -m app.scripts.ingest_mb_catno_covers --from-csv /tmp/mb_catno_covers.csv.gz

РЕЖИМ 3 (сервер, после просмотра отчёта): гейт + простановка + аудит:
  python -m app.scripts.ingest_mb_catno_covers --apply

Форматы TSV:
  release_label: 0=id, 1=release, 2=label, 3=catalog_number
  label:         0=id, 1=gid, 2=name
  release:       0=id, 1=gid (MBID), 4=release_group
  release_country: 0=release, 1=country, 2=year;  release_unknown_country:
  0=release, 1=year.
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

# ЗЕРКАЛО ingest_discogs_dump._CATALOG_RE + NBSP (Python \s его и так ест,
# добавлен явно, чтобы SQL-префильтр ниже использовал тот же класс символов).
_NORM_RE = re.compile(r"[\s\-\. ]+")
# Тот же класс для SQL regexp_replace — с literal NBSP, без escape-рулетки.
_SQL_NORM_PATTERN = "[\\s\\-\\. ]+"

# Вырожденные катномера: дискогсовское «без номера», MB-заглушки, шум.
_JUNK_CATNOS = {
    "NONE", "NOCAT", "N/A", "NA", "UNKNOWN", "[NONE]", "[UNKNOWN]",
    "NONUMBER", "БЕЗНОМЕРА", "Б/Н", "PROMO", "TESTPRESSING",
}
# Вырожденные «лейблы»: самиздат-вёдра, в которых один ключ накрывает
# сотни разных релизов. Нормализованные формы.
_JUNK_LABELS = {
    "NOTONLABEL", "NOLABEL", "[NOLABEL]", "WHITELABEL", "SELFRELEASED",
    "NOTONLABELSELFRELEASED", "UNKNOWN", "[UNKNOWN]", "NONE",
}
_MIN_CATNO_LEN = 3

# Применение/валидация: год обязан быть с обеих сторон и близко.
_MAX_YEAR_DIFF = 2
# Ключ, накрывающий больше строк индекса, — серийный номер, пропускаем весь.
_MAX_KEY_FANOUT = 5
# Гейт --apply: same_group на непокрытой популяции и минимум размеченных.
_GATE_MIN_SAME_GROUP = 0.97
_GATE_MIN_RG_KNOWN = 500


def _norm_key(raw: str | None) -> str | None:
    """Одна нормализация на катномер и лейбл: [\\s\\-\\.NBSP]+ → '' → upper."""
    if not raw or raw == "\\N":
        return None
    cleaned = _NORM_RE.sub("", raw).upper().strip()
    return cleaned or None


def _catno_ok(norm: str | None) -> bool:
    return norm is not None and len(norm) >= _MIN_CATNO_LEN and norm not in _JUNK_CATNOS


def _label_ok(norm: str | None) -> bool:
    return norm is not None and norm not in _JUNK_LABELS


def _resolve_key(
    candidates: list[tuple[str, int, int | None]], all_groups: set[int]
) -> tuple[str, int, int | None] | None:
    """Кому достаётся ключ: (mbid, release_group, year) | None.

    candidates — MB-релизы С front-обложкой под этим ключом; all_groups —
    release group'ы ВСЕХ MB-релизов под ним, включая релизы без арта.
    Неоднозначность считается по all_groups: если под ключом в MB живут два
    альбома — даже когда у второго нет обложки и «кандидатом» он не стал —
    ключ выбрасывается: Discogs-строка могла быть именно вторым альбомом.
    Внутри одного альбома берём самый ранний датированный пресс, без дат —
    первый по mbid (детерминизм экспорта).
    """
    if not candidates or len(all_groups) != 1:
        return None
    dated = [c for c in candidates if c[2] is not None]
    pool = dated or candidates
    return min(pool, key=lambda c: (c[2] if c[2] is not None else 9999, c[0]))


def _parse_labels(dump_dir: Path) -> dict[int, str]:
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


def _parse_years(dump_dir: Path, wanted: dict[int, tuple[str, int]]) -> dict[int, int]:
    """Минимальный год релиза; wanted — front-релизы (dict, membership O(1))."""
    years: dict[int, int] = {}

    def eat(path: Path, year_col: int) -> None:
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

    eat(dump_dir / "release_country", 2)
    eat(dump_dir / "release_unknown_country", 1)
    logger.info("годы: %d релизов датированы", len(years))
    return years


def _export(dump_dir: Path, caa_dir: Path, out_path: Path, rg_path: Path) -> None:
    front = _parse_front_covers(caa_dir)
    labels = _parse_labels(dump_dir)

    # release: id → rg для ВСЕХ (коллизии), id → (mbid, rg) для front.
    rel_rg: dict[int, int] = {}
    front_info: dict[int, tuple[str, int]] = {}
    with (dump_dir / "release").open("r", encoding="utf-8", errors="replace") as fh:
        for line in fh:
            cols = line.rstrip("\n").split("\t")
            if len(cols) < 5 or not cols[0].isdigit() or not cols[4].isdigit():
                continue
            rid = int(cols[0])
            rel_rg[rid] = int(cols[4])
            if rid in front:
                front_info[rid] = (cols[1], int(cols[4]))
    logger.info(
        "release готов: %d всего, %d с front-обложкой", len(rel_rg), len(front_info)
    )
    del front

    # Независимый mbid → rg (для валидации) — по ВСЕМ релизам.
    with gzip.open(rg_path, "wt", newline="") as fh:
        writer = csv.writer(fh)
        rg_rows = 0
        with (dump_dir / "release").open("r", encoding="utf-8", errors="replace") as src:
            for line in src:
                cols = line.rstrip("\n").split("\t")
                if len(cols) < 5 or not cols[0].isdigit() or not cols[4].isdigit():
                    continue
                writer.writerow((cols[1], cols[4]))
                rg_rows += 1
    logger.info("rg-карта: %d строк → %s", rg_rows, rg_path)

    years = _parse_years(dump_dir, front_info)
    if not years:
        raise SystemExit(
            "0 датированных релизов — release_country/release_unknown_country "
            "пусты или не распакованы. Год обязателен для применения; экспорт "
            "без него дал бы канал, который молча ставит 0 обложек."
        )

    # release_label: кандидаты (front) и полная карта неоднозначности (все).
    cands: dict[tuple[str, str], list[tuple[str, int, int | None]]] = defaultdict(list)
    key_rgs: dict[tuple[str, str], set[int]] = defaultdict(set)
    rows = 0
    with (dump_dir / "release_label").open("r", encoding="utf-8", errors="replace") as fh:
        for line in fh:
            cols = line.rstrip("\n").split("\t")
            if len(cols) < 4 or not cols[1].isdigit():
                continue
            rid = int(cols[1])
            rg = rel_rg.get(rid)
            if rg is None:
                continue
            label_norm = labels.get(int(cols[2])) if cols[2].isdigit() else None
            catno = _norm_key(cols[3])
            if not _label_ok(label_norm) or not _catno_ok(catno):
                continue
            key = (catno, label_norm)
            key_rgs[key].add(rg)
            if rid in front_info:
                mbid, _ = front_info[rid]
                cands[key].append((mbid, rg, years.get(rid)))
            rows += 1
    logger.info("release_label готов: %d связок, %d ключей", rows, len(key_rgs))
    del labels, rel_rg, front_info, years

    kept = ambiguous = artless = 0
    with gzip.open(out_path, "wt", newline="") as fh:
        writer = csv.writer(fh)
        for key, groups in key_rgs.items():
            row = _resolve_key(cands.get(key, []), groups)
            if row is None:
                if len(groups) > 1:
                    ambiguous += 1
                else:
                    artless += 1  # ключ однозначен, но арта в MB нет
                continue
            mbid, rg, year = row
            kept += 1
            writer.writerow((key[0], key[1], year if year is not None else "", mbid, rg))
    logger.info(
        "ключи: %d с обложкой, %d неоднозначных выброшено, %d без арта",
        kept, ambiguous, artless,
    )
    logger.info("ГОТОВО: %s + %s", out_path, rg_path)


def export_csv(dump_dir: Path, caa_dir: Path, out_path: Path) -> None:
    needed = ("release", "release_label", "label", "release_country", "release_unknown_country")
    for name in needed:
        if not (dump_dir / name).exists():
            raise SystemExit(f"Файл не найден: {dump_dir / name} (нужны все: {needed})")
    for name in ("cover_art", "art_type", "cover_art_type"):
        if not (caa_dir / name).exists():
            raise SystemExit(f"Файл не найден: {caa_dir / name}")
    started = time.monotonic()
    rg_path = out_path.parent / (out_path.name.replace(".csv.gz", "") + ".rg.csv.gz")
    _export(dump_dir, caa_dir, out_path, rg_path)
    logger.info("экспорт занял %.0fs", time.monotonic() - started)


# ---------------------------------------------------------------- сервер ---

def _dsn() -> str:
    from app.config import get_settings
    return get_settings().database_url.replace("postgresql+asyncpg://", "postgresql://")


async def _connect():
    """Отдельное asyncpg-соединение МИМО пула приложения.

    У app-пула statement_timeout=30s прибит в connect_args (грабли July-
    прогонов), а SET на пуловом коннекте отравил бы его для чужих запросов —
    коннект возвращается в пул вместе с сессионными настройками.
    """
    import asyncpg
    return await asyncpg.connect(_dsn())


def _label_norm_sql(col: str) -> str:
    return f"upper(regexp_replace({col}, $${_SQL_NORM_PATTERN}$$, '', 'g'))"


async def load_csv(csv_path: Path) -> None:
    started = time.monotonic()
    rg_path = csv_path.parent / (csv_path.name.replace(".csv.gz", "") + ".rg.csv.gz")
    if not rg_path.exists():
        raise SystemExit(
            f"Нет rg-карты {rg_path} — без неё валидация мерит точность по "
            "самой проверяемой таблице (смещение вверх). Скопируй оба файла."
        )
    pg = await _connect()
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
        await pg.execute(
            "CREATE TABLE IF NOT EXISTS mb_mbid_rg ("
            " mbid TEXT PRIMARY KEY, release_group BIGINT NOT NULL)"
        )

        async def copy(table: str, cols: tuple, path: Path, parse) -> int:
            total = bad = 0
            batch: list[tuple] = []
            # Транзакция: упавший COPY откатывает TRUNCATE — частично залитая
            # таблица неотличима от полной, и --apply отработал бы по ней.
            async with pg.transaction():
                await pg.execute(f"TRUNCATE {table}")
                with gzip.open(path, "rt", newline="") as fh:
                    for row in csv.reader(fh):
                        try:
                            rec = parse(row)
                        except (ValueError, IndexError):
                            bad += 1
                            continue
                        batch.append(rec)
                        if len(batch) >= _BATCH:
                            await pg.copy_records_to_table(table, records=batch, columns=cols)
                            total += len(batch)
                            batch = []
                    if batch:
                        await pg.copy_records_to_table(table, records=batch, columns=cols)
                        total += len(batch)
            if bad:
                logger.warning("%s: %d битых строк CSV пропущено", table, bad)
            return total

        n1 = await copy(
            "mb_catno_covers",
            ("catno_norm", "label_norm", "year", "mbid", "release_group"),
            csv_path,
            lambda r: (r[0], r[1], int(r[2]) if r[2] else None, r[3], int(r[4])),
        )
        n2 = await copy(
            "mb_mbid_rg", ("mbid", "release_group"), rg_path,
            lambda r: (r[0], int(r[1])),
        )
        logger.info(
            "загружено: %d ключей, %d строк rg-карты за %.0fs",
            n1, n2, time.monotonic() - started,
        )
        await validate(pg)
        logger.info(
            "Запись в индекс НЕ выполнялась. Если на НЕПОКРЫТОЙ популяции "
            "same_group >= %d%% и размеченных >= %d — запускай --apply "
            "(он перепроверит сам).",
            int(_GATE_MIN_SAME_GROUP * 100), _GATE_MIN_RG_KNOWN,
        )
    finally:
        await pg.close()


def _validate_sql(only_uncovered: bool) -> str:
    extra = "AND d.cover_image_url IS NULL" if only_uncovered else ""
    return f"""
WITH cand AS (
  SELECT d.discogs_id, t.mbid::text AS truth_mbid,
         m.mbid AS cand_mbid, m.release_group AS cand_rg
  FROM discogs_releases_index d
  JOIN mb_discogs_map t ON t.discogs_id = d.discogs_id
  JOIN mb_catno_covers m
    ON m.catno_norm = d.catalog_norm
   AND m.label_norm = {_label_norm_sql('d.label')}
   AND d.year IS NOT NULL AND m.year IS NOT NULL
   AND abs(d.year - m.year) <= {_MAX_YEAR_DIFF}
  WHERE true {extra}
)
SELECT count(*) AS matched,
       count(*) FILTER (WHERE cand_mbid = truth_mbid) AS exact_mbid,
       count(tr.release_group) AS rg_known,
       count(*) FILTER (WHERE cand_rg = tr.release_group) AS same_group
FROM cand
LEFT JOIN mb_mbid_rg tr ON tr.mbid = cand.truth_mbid
"""


async def validate(pg=None) -> dict:
    """Точность на ground truth (URL-связи), rg — из независимой mb_mbid_rg.

    Возвращает метрики НЕПОКРЫТОЙ популяции (по ней гейтится --apply):
    покрытые строки — курируемые релизы с богатыми метаданными, apply же
    пишет в тёмный хвост; мерить одно и применять к другому нельзя.
    """
    own = pg is None
    if own:
        pg = await _connect()
    try:
        result = {}
        for name, flag in (("вся ground truth", False), ("непокрытые (популяция --apply)", True)):
            row = await pg.fetchrow(_validate_sql(flag))
            matched, exact, rg_known, same_group = (
                row["matched"], row["exact_mbid"], row["rg_known"], row["same_group"],
            )
            logger.info("=== ВАЛИДАЦИЯ: %s ===", name)
            logger.info("  матчей: %d", matched)
            if matched:
                logger.info("  точный mbid: %d (%.1f%%)", exact, 100.0 * exact / matched)
                logger.info("  rg неизвестен (не проверено): %d", matched - rg_known)
            if rg_known:
                logger.info(
                    "  тот же альбом: %d из %d проверенных (%.2f%%)",
                    same_group, rg_known, 100.0 * same_group / rg_known,
                )
            if flag:
                result = {"matched": matched, "rg_known": rg_known, "same_group": same_group}
        return result
    finally:
        if own:
            await pg.close()


async def apply_updates() -> None:
    started = time.monotonic()
    pg = await _connect()
    try:
        # Гейт: --apply не верит оператору на слово, перепроверяет сам.
        m = await validate(pg)
        if m["rg_known"] < _GATE_MIN_RG_KNOWN:
            raise SystemExit(
                f"ГЕЙТ: проверенных матчей на непокрытой популяции {m['rg_known']} "
                f"< {_GATE_MIN_RG_KNOWN} — точность не измерена, применять нельзя."
            )
        ratio = m["same_group"] / m["rg_known"]
        if ratio < _GATE_MIN_SAME_GROUP:
            raise SystemExit(
                f"ГЕЙТ: same_group {ratio:.1%} < {_GATE_MIN_SAME_GROUP:.0%} — "
                "канал недостаточно точен на целевой популяции."
            )

        await pg.execute(
            "CREATE TABLE IF NOT EXISTS catno_cover_audit ("
            " discogs_id BIGINT PRIMARY KEY,"
            " catno_norm TEXT NOT NULL, label_norm TEXT NOT NULL,"
            " mbid TEXT NOT NULL, applied_at TIMESTAMP NOT NULL DEFAULT now())"
        )

        # Фаза 1: кандидаты. SQL — префильтр; решающая сверка лейбла в Python
        # (пункт 6 докстринга): расхождение нормализаций не даст ложный матч.
        rows = await pg.fetch(f"""
            SELECT d.discogs_id, d.label AS d_label,
                   m.catno_norm, m.label_norm, m.mbid
            FROM discogs_releases_index d
            JOIN mb_catno_covers m
              ON m.catno_norm = d.catalog_norm
             AND m.label_norm = {_label_norm_sql('d.label')}
             AND d.year IS NOT NULL AND m.year IS NOT NULL
             AND abs(d.year - m.year) <= {_MAX_YEAR_DIFF}
            WHERE d.cover_image_url IS NULL
        """)
        logger.info("кандидатов из префильтра: %d", len(rows))

        by_key: dict[tuple[str, str], list] = defaultdict(list)
        label_mismatch = 0
        for r in rows:
            if _norm_key(r["d_label"]) != r["label_norm"]:
                label_mismatch += 1
                continue
            by_key[(r["catno_norm"], r["label_norm"])].append(r)
        if label_mismatch:
            logger.warning(
                "Python-сверка лейбла отвергла %d кандидатов (SQL-префильтр "
                "разошёлся с _norm_key — посмотреть примеры руками)",
                label_mismatch,
            )

        todo, fanout_skipped = [], 0
        for key, group in by_key.items():
            if len(group) > _MAX_KEY_FANOUT:
                fanout_skipped += 1
                continue
            todo.extend(group)
        logger.info(
            "к применению: %d строк; %d ключей пропущено по веерности (> %d)",
            len(todo), fanout_skipped, _MAX_KEY_FANOUT,
        )

        # Фаза 2: батчи по 1000 — короткие транзакции, никаких часовых локов.
        applied = 0
        for i in range(0, len(todo), 1000):
            chunk = todo[i : i + 1000]
            async with pg.transaction():
                for r in chunk:
                    res = await pg.execute(
                        "UPDATE discogs_releases_index SET cover_image_url = "
                        " 'https://coverartarchive.org/release/' || $2 || '/front-1200' "
                        "WHERE discogs_id = $1 AND cover_image_url IS NULL",
                        r["discogs_id"], r["mbid"],
                    )
                    if res.endswith("1"):
                        applied += 1
                        await pg.execute(
                            "INSERT INTO catno_cover_audit "
                            " (discogs_id, catno_norm, label_norm, mbid) "
                            "VALUES ($1, $2, $3, $4) ON CONFLICT DO NOTHING",
                            r["discogs_id"], r["catno_norm"], r["label_norm"], r["mbid"],
                        )
            if applied and applied % 50_000 < 1000:
                logger.info("применено ~%d", applied)
        logger.info(
            "ГОТОВО: %d обложек проставлено (аудит в catno_cover_audit) за %.0fs",
            applied, time.monotonic() - started,
        )
    finally:
        await pg.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dir", type=Path, help="Каталог mbdump")
    parser.add_argument("--caa-dir", type=Path, help="Каталог mbdump-caa")
    parser.add_argument("--export-csv", type=Path, help="Режим 1: путь CSV.gz (+ .rg.csv.gz рядом)")
    parser.add_argument("--from-csv", type=Path, help="Режим 2: загрузка + отчёт точности (без записи)")
    parser.add_argument("--validate", action="store_true", help="Только отчёт точности")
    parser.add_argument("--apply", action="store_true", help="Режим 3: гейт + простановка + аудит")
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
