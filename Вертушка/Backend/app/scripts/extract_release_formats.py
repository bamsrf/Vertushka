"""CLI: releases-дамп → CSV полных описаний формата (+ дельта новых релизов).

## Зачем

`ingest_discogs_dump._derive_format` кладёт в `format_type` только ПЕРВОЕ
описание первого формата: у «Curtain Call (Album Sampler)» Discogs отдаёт
`['Sampler','Promo','Compilation']`, а в базе оказывается `CD, Sampler`. На
1.06M строк дампа типового маркера не остаётся вовсе, и классификатор
(`services/release_type.py`) вынужден гадать — отсюда мешанина в фильтре
«Альбомы» на экране артиста: radio-show LP теряют маркер Transcription,
промо-сэмплеры теряют Promo.

Этот скрипт достаёт **весь** список описаний. Строки, где описаний 0–1,
пропускаются: там `format_type` уже полон, и хранить дубль незачем — на проде
диска 4.3 ГБ, каждая сэкономленная строка на счету.

## Где запускать — НЕ на проде

`data.discogs.com` встречает прод-сервер JS-челленджем Cloudflare (IP
дата-центра): `curl` получает 403 и HTML вместо гигабайтов. Дамп качается и
парсится на машине с «обычным» IP, на прод уезжает только CSV.gz — он на два
порядка меньше дампа.

## Использование

    # 1. Скачать дамп (10.4 ГБ, ~40 мин)
    curl -L -o releases.xml.gz \\
      'https://data.discogs.com/?download=data%2F2026%2Fdiscogs_20260801_releases.xml.gz'

    # 2. Извлечь (≈1.5 ч, память константная ~200 МБ)
    python -m app.scripts.extract_release_formats \\
      --file releases.xml.gz --out-dir ./out --since-id 38016987

    # 3. Залить на прод
    scp out/formats_*.csv.gz deploy@85.198.85.12:/tmp/
    ssh deploy@... 'docker cp /tmp/formats_*.csv.gz vertushka_api:/tmp/ && \\
      docker exec vertushka_api python -m app.scripts.load_release_formats \\
        --file /tmp/formats_20260801.csv.gz'

`--since-id` (max(discogs_id) на проде) включает второй выход — `new_*.csv.gz`
с полными строками релизов, которых в индексе ещё нет. Discogs выдаёт id
инкрементально, так что «больше максимума» и есть «появилось после дампа,
которым индекс наполняли». Без флага пишется только formats.
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

from app.scripts.ingest_discogs_dump import _parse_release, derive_format

logger = logging.getLogger("extract_release_formats")

#: Ниже этого числа описаний полная строка совпадает с тем, что уже лежит в
#: `format_type` у строк дампа 2026-05 — писать дубль незачем.
_MIN_DESCRIPTIONS = 2


def _artist_ids(elem) -> list[str]:
    """id основных артистов, в порядке дампа. `<extraartists>` не берём —
    там сессионщики и ремиксёры, дискографию они бы замусорили."""
    ids = []
    artists = elem.find("artists")
    if artists is None:
        return ids
    for artist in artists.findall("artist"):
        node = artist.find("id")
        value = (node.text or "").strip() if node is not None else ""
        if value.isdigit():
            ids.append(value)
    return ids


def _is_unofficial(elem) -> bool:
    """Бутлег — маркер «Unofficial Release» в описаниях формата. Локальный путь
    дискографии фильтрует по нему, иначе топ артиста тонет в бутлегах."""
    for desc in elem.findall(".//formats/format/descriptions/description"):
        if (desc.text or "").strip() == "Unofficial Release":
            return True
    return False


#: `records.genre` / `records.style` — String(255). Дамп изредка отдаёт больше
#: (у сборников бывает десяток стилей), и без обрезки COPY упал бы на проде.
_MAX_FIELD = 255


def _joined(elem, path: str) -> str | None:
    """«Rock, Pop» из `<genres><genre>…`.

    Склейка через ", " — ровно так же делает `DiscogsService.get_release`
    (services/discogs.py). Разойдись форматы, одна и та же колонка заполнялась
    бы живым и дампным путём по-разному, и ILIKE-паттерны чипов ловили бы
    записи через раз.
    """
    values = [(node.text or "").strip() for node in elem.findall(path)]
    values = [v for v in values if v]
    if not values:
        return None
    out = ", ".join(values)
    if len(out) <= _MAX_FIELD:
        return out
    # Режем по границе элемента, а не посреди слова: огрызок «Ind» в style
    # матчился бы паттернами как попало.
    return out[:_MAX_FIELD].rsplit(", ", 1)[0] or out[:_MAX_FIELD]


def load_wanted_ids(path: Path) -> set[int]:
    """Список discogs_id (по одному в строке), которым нужны жанры.

    Снимается с прода: `SELECT discogs_id FROM records WHERE genre IS NULL`.
    Фильтр по списку, а не выгрузка всех 19M строк — потому что на прод-диске
    свободно ~3 ГБ, и полная таблица жанров (~0.9 ГБ) туда просто не влезет,
    тогда как выборка под наш склад весит единицы мегабайт.
    """
    ids: set[int] = set()
    with path.open() as fh:
        for line in fh:
            line = line.strip()
            if line.isdigit():
                ids.add(int(line))
    return ids


def extract(
    file_path: Path,
    out_dir: Path,
    dump_date: date,
    since_id: int | None,
    limit: int | None,
    wanted_ids: set[int] | None = None,
) -> dict[str, int]:
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = dump_date.strftime("%Y%m%d")
    formats_path = out_dir / f"formats_{stamp}.csv.gz"
    new_path = out_dir / f"new_{stamp}.csv.gz"
    genres_path = out_dir / f"genres_{stamp}.csv.gz"
    # Пишем в .part и переименовываем в самом конце. Обрезанный дамп (а
    # data.discogs.com отдаёт файл chunked, без Content-Length, так что curl
    # завершается успехом даже на обрыве) роняет iterparse посреди потока —
    # без этого на диске остался бы полу-CSV, который следующий шаг спокойно
    # залил бы на прод.
    formats_tmp = formats_path.with_suffix(".gz.part")
    new_tmp = new_path.with_suffix(".gz.part")
    genres_tmp = genres_path.with_suffix(".gz.part")

    counters = {"seen": 0, "formats": 0, "new": 0, "genres": 0, "skipped": 0}
    started = time.time()
    last_report = started
    # Суммарная длина записанных строк — по ней оцениваем вес таблицы на проде
    # ДО заливки, пока есть возможность передумать.
    bytes_written = 0

    new_file = gzip.open(new_tmp, "wt", newline="", encoding="utf-8") if since_id else None
    genres_file = (
        gzip.open(genres_tmp, "wt", newline="", encoding="utf-8") if wanted_ids else None
    )
    try:
        with gzip.open(file_path, "rb") as fh, \
                gzip.open(formats_tmp, "wt", newline="", encoding="utf-8") as fmt_out:
            fmt_writer = csv.writer(fmt_out)
            new_writer = csv.writer(new_file) if new_file else None
            genres_writer = csv.writer(genres_file) if genres_file else None

            for _event, elem in etree.iterparse(fh, tag="release"):
                try:
                    raw_id = elem.get("id")
                    if not raw_id or not raw_id.isdigit():
                        counters["skipped"] += 1
                        continue
                    discogs_id = int(raw_id)
                    counters["seen"] += 1

                    full, n_desc = derive_format(elem)
                    if full and n_desc >= _MIN_DESCRIPTIONS:
                        fmt_writer.writerow((discogs_id, full))
                        counters["formats"] += 1
                        bytes_written += len(full) + 12

                    if new_writer is not None and discogs_id > since_id:
                        row = _parse_release(elem, dump_date)
                        if row is not None:
                            # row["format_type"] уже полный: _parse_release
                            # зовёт derive_format, который с 2026-08 отдаёт все
                            # описания. Новым строкам side-таблица не нужна.
                            # artist_ids и is_unofficial обычно приезжают
                            # отдельным проходом (extract_discogs_artist_map →
                            # load_artist_map). Без artist_ids строка не видна
                            # на экране артиста — фильтр там по GIN artist_ids,
                            # — поэтому тащим их в том же проходе.
                            new_writer.writerow((
                                row["discogs_id"], row["master_id"], row["artist"],
                                row["title"], row["year"], row["country"],
                                row["format_type"], row["label"],
                                row["barcode_norm"], row["catalog_norm"],
                                ";".join(_artist_ids(elem)),
                                1 if _is_unofficial(elem) else 0,
                            ))
                            counters["new"] += 1

                    if genres_writer is not None and discogs_id in wanted_ids:
                        genre = _joined(elem, "genres/genre")
                        style = _joined(elem, "styles/style")
                        if genre or style:
                            genres_writer.writerow((discogs_id, genre or "", style or ""))
                            counters["genres"] += 1

                    now = time.time()
                    if now - last_report >= 30:
                        rate = counters["seen"] / (now - started)
                        logger.info(
                            "seen=%d formats=%d new=%d genres=%d rate=%.0f/s est_table=%.0fMB",
                            counters["seen"], counters["formats"], counters["new"],
                            counters["genres"], rate,
                            (bytes_written + counters["formats"] * 40) / 1e6,
                        )
                        last_report = now

                    if limit and counters["seen"] >= limit:
                        logger.info("limit %d — останов", limit)
                        break
                finally:
                    # Без очистки lxml держит всё дерево: 10 ГБ дампа в RAM.
                    elem.clear()
                    parent = elem.getparent()
                    if parent is not None:
                        while elem.getprevious() is not None:
                            del parent[0]
    finally:
        if new_file is not None:
            new_file.close()
        if genres_file is not None:
            genres_file.close()

    # Досюда дошли — поток дочитан до конца, файлы можно считать готовыми.
    formats_tmp.rename(formats_path)
    if new_file is not None:
        new_tmp.rename(new_path)
    if genres_file is not None:
        genres_tmp.rename(genres_path)

    # Дамп 2026-08 содержит ~19M релизов. Сильно меньше — почти наверняка
    # обрезанный файл, который iterparse дочитал «успешно» (gzip-поток кончился
    # на границе члена). Не падаем, но кричим: залить такое на прод нельзя.
    if not limit and counters["seen"] < 15_000_000:
        logger.warning(
            "ПОДОЗРИТЕЛЬНО МАЛО релизов: %d (ожидается ~19M). "
            "Проверь sha256 дампа против CHECKSUM.txt — вероятно обрыв загрузки.",
            counters["seen"],
        )

    elapsed = time.time() - started
    logger.info(
        "ГОТОВО за %.0f мин: seen=%d formats=%d (%.1f%%) new=%d genres=%d",
        elapsed / 60, counters["seen"], counters["formats"],
        100 * counters["formats"] / max(counters["seen"], 1), counters["new"],
        counters["genres"],
    )
    logger.info("formats → %s (%.0f МБ)", formats_path, formats_path.stat().st_size / 1e6)
    logger.info(
        "оценка таблицы на проде: ~%.0f МБ heap + ~%.0f МБ PK",
        (bytes_written + counters["formats"] * 40) / 1e6,
        counters["formats"] * 30 / 1e6,
    )
    if new_file is not None:
        logger.info("new → %s (%.0f МБ)", new_path, new_path.stat().st_size / 1e6)
    if genres_file is not None:
        # Промах = id есть у нас, но в дампе его нет: релиз новее дампа либо
        # удалён из Discogs. Такие добираются живым API, их должно быть мало —
        # если доля большая, значит список id снят не с того окружения.
        missing = len(wanted_ids) - counters["genres"]
        logger.info(
            "genres → %s (%.1f МБ): нашли %d из %d запрошенных, не нашли %d",
            genres_path, genres_path.stat().st_size / 1e6,
            counters["genres"], len(wanted_ids), missing,
        )
    return counters


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--file", required=True, type=Path, help="путь к releases.xml.gz")
    parser.add_argument("--out-dir", default=Path("."), type=Path)
    parser.add_argument(
        "--dump-date", help="YYYY-MM-DD; по умолчанию выводится из имени файла",
    )
    parser.add_argument(
        "--since-id", type=int,
        help="max(discogs_id) на проде — включает выгрузку новых релизов",
    )
    parser.add_argument(
        "--ids-file", type=Path,
        help=(
            "файл со списком discogs_id (по одному в строке) — включает выгрузку "
            "genres_*.csv.gz с жанрами и стилями только для этих релизов"
        ),
    )
    parser.add_argument("--limit", type=int, help="остановиться после N релизов (тест)")
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

    wanted_ids = None
    if args.ids_file:
        if not args.ids_file.exists():
            parser.error(f"нет файла со списком id: {args.ids_file}")
        wanted_ids = load_wanted_ids(args.ids_file)
        if not wanted_ids:
            # Пустой список молча дал бы пустой CSV, загрузчик отработал бы «успешно»
            # и ноль строк — ровно тот класс тихих провалов, что уже стоил нам
            # 6M пропущенных релизов при ингесте дампа.
            parser.error(f"список id пуст: {args.ids_file}")
        logger.info("жанры запрошены для %d id", len(wanted_ids))

    extract(args.file, args.out_dir, dump_date, args.since_id, args.limit, wanted_ids)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
