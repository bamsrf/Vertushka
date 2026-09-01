"""CLI: masters-дамп Discogs → CSV жанров, ключ — master_id.

## Зачем отдельный путь

Основной источник жанров — releases-дамп (`extract_release_formats --ids-file`),
он покрывает записи точнее всего: жанр берётся у конкретного пресса. Но весит
он 10.4 ГБ, а `data.discogs.com` **не поддерживает Range** — на ranged-запрос
отвечает 200 и полным телом, то есть докачки нет и каждый обрыв обнуляет
прогресс. Замер 25.08.2026: восемь попыток подряд легли с `curl rc=18` в
случайных точках от 672 МБ до 7.1 ГБ.

Masters-дамп — 593 МБ, скачивается целиком с первой попытки. Жанры Discogs
держит и на уровне мастера (мастер = альбом, релиз = его конкретное издание),
а для жанровых чипов Маркета разницы между ними нет: пресс не меняет жанр
альбома. Покрытие ограничено записями, у которых проставлен `discogs_master_id`
— на проде это 28 935 из 36 054 (80%).

То есть путь через мастеров — быстрая первая волна, releases-дамп потом добьёт
остаток. Оба выхода читает один и тот же `load_release_genres` (`--key master`).

## Использование

    # список master_id, которым нужен жанр (снять с прода)
    ssh deploy@... 'docker exec vertushka_db psql -U vertushka_user -d vertushka \\
      -t -A -c "SELECT DISTINCT discogs_master_id FROM records \\
      WHERE discogs_master_id IS NOT NULL AND merged_into_id IS NULL \\
        AND (genre IS NULL OR char_length(btrim(genre)) = 0);"' > master_ids.txt

    python -m app.scripts.extract_master_genres \\
      --file discogs_20260801_masters.xml.gz --ids-file master_ids.txt --out-dir .

    scp genres_masters_20260801.csv.gz deploy@...:/tmp/
    ssh deploy@... 'docker cp /tmp/genres_masters_20260801.csv.gz $API:/tmp/ && \\
      docker exec $API python -m app.scripts.load_release_genres \\
        --file /tmp/genres_masters_20260801.csv.gz --key master --dry-run'
"""
from __future__ import annotations

import argparse
import csv
import gzip
import logging
import sys
import time
from datetime import date, datetime
from pathlib import Path

from lxml import etree

from app.scripts.extract_release_formats import _joined, load_wanted_ids

logger = logging.getLogger("extract_master_genres")

#: Дамп 2026-08 содержит ~2.6M мастеров. Сильно меньше — почти наверняка
#: обрезанный файл, который iterparse дочитал «успешно» (gzip-поток кончился на
#: границе члена). Тот же предохранитель, что в extract_release_formats.
_MIN_EXPECTED = 2_000_000


def extract(
    file_path: Path,
    out_dir: Path,
    dump_date: date,
    wanted_ids: set[int],
    limit: int | None = None,
) -> dict[str, int]:
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = dump_date.strftime("%Y%m%d")
    out_path = out_dir / f"genres_masters_{stamp}.csv.gz"
    # Пишем в .part и переименовываем в конце: обрезанный дамп роняет iterparse
    # посреди потока, и без этого на диске остался бы полу-CSV, который
    # следующий шаг спокойно залил бы на прод.
    tmp_path = out_path.with_suffix(".gz.part")

    counters = {"seen": 0, "written": 0, "skipped": 0}
    started = time.time()
    last_report = started

    with gzip.open(file_path, "rb") as fh, \
            gzip.open(tmp_path, "wt", newline="", encoding="utf-8") as out:
        writer = csv.writer(out)
        for _event, elem in etree.iterparse(fh, tag="master"):
            try:
                raw_id = elem.get("id")
                if not raw_id or not raw_id.isdigit():
                    counters["skipped"] += 1
                    continue
                counters["seen"] += 1
                master_id = int(raw_id)
                if master_id not in wanted_ids:
                    continue
                genre = _joined(elem, "genres/genre")
                style = _joined(elem, "styles/style")
                if genre or style:
                    writer.writerow((master_id, genre or "", style or ""))
                    counters["written"] += 1

                now = time.time()
                if now - last_report >= 30:
                    logger.info(
                        "seen=%d written=%d rate=%.0f/s",
                        counters["seen"], counters["written"],
                        counters["seen"] / (now - started),
                    )
                    last_report = now

                if limit and counters["seen"] >= limit:
                    logger.info("limit %d — останов", limit)
                    break
            finally:
                # Без очистки lxml держит всё дерево в памяти.
                elem.clear()
                parent = elem.getparent()
                if parent is not None:
                    while elem.getprevious() is not None:
                        del parent[0]

    tmp_path.rename(out_path)

    if not limit and counters["seen"] < _MIN_EXPECTED:
        logger.warning(
            "ПОДОЗРИТЕЛЬНО МАЛО мастеров: %d (ожидается ~2.6M). "
            "Проверь sha256 дампа против CHECKSUM.txt — вероятно обрыв загрузки.",
            counters["seen"],
        )

    # Промах = master_id есть у нас, но в дампе его нет: мастер новее дампа либо
    # удалён/слит на Discogs. Их добьёт releases-дамп или живой API.
    missing = len(wanted_ids) - counters["written"]
    logger.info(
        "ГОТОВО за %.1f мин: seen=%d, нашли %d из %d запрошенных, не нашли %d",
        (time.time() - started) / 60, counters["seen"],
        counters["written"], len(wanted_ids), missing,
    )
    logger.info("→ %s (%.1f МБ)", out_path, out_path.stat().st_size / 1e6)
    return counters


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--file", required=True, type=Path, help="masters.xml.gz")
    parser.add_argument("--ids-file", required=True, type=Path, help="master_id по одному в строке")
    parser.add_argument("--out-dir", default=Path("."), type=Path)
    parser.add_argument("--dump-date", help="YYYY-MM-DD; по умолчанию из имени файла")
    parser.add_argument("--limit", type=int, help="остановиться после N мастеров (тест)")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        stream=sys.stdout,
    )

    if args.dump_date:
        dump_date = date.fromisoformat(args.dump_date)
    else:
        digits = "".join(c for c in args.file.stem if c.isdigit())[:8]
        if len(digits) != 8:
            parser.error("не смог вывести дату из имени файла — задай --dump-date")
        dump_date = datetime.strptime(digits, "%Y%m%d").date()

    if not args.file.exists():
        parser.error(f"нет файла: {args.file}")
    if not args.ids_file.exists():
        parser.error(f"нет файла со списком id: {args.ids_file}")

    wanted_ids = load_wanted_ids(args.ids_file)
    if not wanted_ids:
        # Пустой список молча дал бы пустой CSV, загрузчик отработал бы «успешно»
        # и ноль строк — тот класс тихих провалов, что уже стоил нам 6M
        # пропущенных релизов при ингесте дампа.
        parser.error(f"список id пуст: {args.ids_file}")
    logger.info("жанры запрошены для %d мастеров", len(wanted_ids))

    extract(args.file, args.out_dir, dump_date, wanted_ids, args.limit)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
