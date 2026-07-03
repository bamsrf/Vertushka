"""CLI: извлечение artist-данных из Discogs XML-дампов → CSV (stdlib-only).

Запускается ЛОКАЛЬНО (не на сервере): стримит XML.gz, память константная.
Результат — два сжатых CSV, которые едут на сервер и грузятся
app/scripts/load_artist_map.py:

  1. artists.csv.gz      : artist_id,name           (из artists-дампа, ~9M строк)
  2. release_artists.csv.gz : release_id,artist_ids  (';'-joined, из releases-дампа)

Берутся только ОСНОВНЫЕ артисты релиза (<artists>), НЕ <extraartists>
(сессионные музыканты/продюсеры — они раздули бы дискографию).

Использование:
  python3 Backend/app/scripts/extract_discogs_artist_map.py \
    --artists-xml ~/discogs-dumps/discogs_20260701_artists.xml.gz \
    --releases-xml ~/discogs-dumps/discogs_20260701_releases.xml.gz \
    --out-dir ~/discogs-dumps

Releases-дамп ~12.5 GB gz — проход занимает ~30-60 минут (ElementTree).
"""
from __future__ import annotations

import argparse
import csv
import gzip
import logging
import sys
import time
import xml.etree.ElementTree as ET
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger("artist_extract")


def extract_artists(xml_path: Path, out_path: Path) -> None:
    """artists-дамп → CSV (artist_id, name).

    Только прямые дети <artist> верхнего уровня: у <members>/<aliases>
    внутри тоже бывают <id>/<name> — их отсекаем по глубине.
    """
    started = time.monotonic()
    total = 0
    with gzip.open(xml_path, "rb") as fh, gzip.open(out_path, "wt", newline="") as out:
        writer = csv.writer(out)
        depth = 0
        root: ET.Element | None = None
        artist_id: str | None = None
        artist_name: str | None = None
        for event, elem in ET.iterparse(fh, events=("start", "end")):
            if event == "start":
                depth += 1
                if depth == 1:
                    root = elem
                elif depth == 2 and elem.tag == "artist":
                    artist_id = None
                    artist_name = None
                continue
            # end
            if depth == 3 and artist_id is None and elem.tag == "id":
                artist_id = (elem.text or "").strip()
            elif depth == 3 and artist_name is None and elem.tag == "name":
                artist_name = (elem.text or "").strip()
            elif depth == 2 and elem.tag == "artist":
                if artist_id and artist_id.isdigit() and artist_name:
                    writer.writerow((artist_id, artist_name))
                    total += 1
                    if total % 1_000_000 == 0:
                        logger.info("artists: %dM", total // 1_000_000)
                # clear() у root, не у elem: иначе root копит миллионы пустых
                # детей (~1 GB RAM на полном дампе).
                if root is not None:
                    root.clear()
            depth -= 1
    logger.info("artists ГОТОВО: %d → %s за %.0fs", total, out_path, time.monotonic() - started)


def extract_release_artists(xml_path: Path, out_path: Path) -> None:
    """releases-дамп → CSV (release_id, 'id1;id2;...').

    Структура: <releases><release id="N"><artists><artist><id>M</id>...
    <extraartists> игнорируется. Порядок артистов сохраняется (первый =
    основной для отображения).
    """
    started = time.monotonic()
    total = 0
    with gzip.open(xml_path, "rb") as fh, gzip.open(out_path, "wt", newline="") as out:
        writer = csv.writer(out)
        path: list[str] = []
        root: ET.Element | None = None
        release_id: str | None = None
        artist_ids: list[str] = []
        for event, elem in ET.iterparse(fh, events=("start", "end")):
            if event == "start":
                path.append(elem.tag)
                if len(path) == 1:
                    root = elem
                elif len(path) == 2 and elem.tag == "release":
                    release_id = elem.get("id")
                    artist_ids = []
                continue
            # end
            if (
                len(path) == 5
                and elem.tag == "id"
                and path[2] == "artists"
                and path[3] == "artist"
            ):
                aid = (elem.text or "").strip()
                if aid.isdigit():
                    artist_ids.append(aid)
            elif len(path) == 2 and elem.tag == "release":
                if release_id and release_id.isdigit() and artist_ids:
                    writer.writerow((release_id, ";".join(artist_ids)))
                    total += 1
                    if total % 1_000_000 == 0:
                        logger.info(
                            "releases: %dM (%.0f мин)",
                            total // 1_000_000, (time.monotonic() - started) / 60,
                        )
                if root is not None:
                    root.clear()
            path.pop()
    logger.info(
        "release_artists ГОТОВО: %d → %s за %.0f мин",
        total, out_path, (time.monotonic() - started) / 60,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artists-xml", help="discogs_YYYYMMDD_artists.xml.gz")
    parser.add_argument("--releases-xml", help="discogs_YYYYMMDD_releases.xml.gz")
    parser.add_argument("--out-dir", required=True)
    args = parser.parse_args()

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    if not args.artists_xml and not args.releases_xml:
        raise SystemExit("Укажи --artists-xml и/или --releases-xml")
    if args.artists_xml:
        extract_artists(Path(args.artists_xml), out_dir / "artists.csv.gz")
    if args.releases_xml:
        extract_release_artists(Path(args.releases_xml), out_dir / "release_artists.csv.gz")


if __name__ == "__main__":
    main()
