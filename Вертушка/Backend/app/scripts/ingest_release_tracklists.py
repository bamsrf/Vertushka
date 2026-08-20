r"""Tier 2: парсер треклистов из Discogs releases dump (main-release мастеров).

Slim-дамп треклист не несёт → деталь версии тянула его live (MB/Deezer/Discogs).
Этот скрипт извлекает треклисты целевых релизов (~2.3M main-release мастеров) из
полного releases-дампа → CSV → сервер грузит в discogs_release_tracklists →
деталь версии мгновенна, ноль внешних вызовов.

Только stdlib — запускается на Mac (парс тяжёлый, дамп ~12GB gz / ~100GB XML).

Пайплайн:
  1. Экспорт целевых id с прода:
     ssh deploy@... 'cd .../Backend && docker compose -f docker-compose.prod.yml exec -T db \
       sh -c "psql -tA -U \$POSTGRES_USER -d vertushka -c \
       \"SELECT MIN(discogs_id) FROM discogs_releases_index WHERE master_id IS NOT NULL AND master_id<>0 GROUP BY master_id\""' \
       > target_ids.txt
  2. Скачать дамп ТОЛЬКО через data.discogs.com/?download=... (S3 напрямую = 403):
     https://data.discogs.com/  →  discogs_YYYYMMDD_releases.xml.gz
  3. Парс:
     python -m app.scripts.ingest_release_tracklists \
       --dump discogs_YYYYMMDD_releases.xml.gz --ids target_ids.txt --out tracklists.csv
  4. Загрузка на сервере (см. функцию print_load_help / низ файла).
"""
import argparse
import csv
import gzip
import json
import sys
import xml.etree.ElementTree as ET


def _load_ids(path: str) -> set[int]:
    ids: set[int] = set()
    with open(path) as f:
        for line in f:
            s = line.strip()
            if s.isdigit():
                ids.add(int(s))
    return ids


def parse(dump: str, ids_path: str, out: str) -> None:
    ids = _load_ids(ids_path)
    sys.stderr.write(f"target ids: {len(ids):,}\n")
    opener = gzip.open if dump.endswith(".gz") else open

    written = seen = 0
    with opener(dump, "rb") as fh, open(out, "w", newline="") as fout:
        w = csv.writer(fout)  # QUOTE_MINIMAL — JSON-поле квотится корректно
        # start/end + захват root для root.clear() — иначе ~GB утечка на 20M
        # элементов (урок mb_discogs_map / iterparse).
        ctx = ET.iterparse(fh, events=("start", "end"))
        _, root = next(ctx)
        for event, elem in ctx:
            if event != "end" or elem.tag != "release":
                continue
            seen += 1
            rid = elem.get("id")
            if rid and rid.isdigit() and int(rid) in ids:
                tl = []
                tlist = elem.find("tracklist")
                if tlist is not None:
                    for tr in tlist.findall("track"):
                        title = (tr.findtext("title") or "").strip()
                        if not title:
                            continue
                        pos = (tr.findtext("position") or "").strip()
                        dur = (tr.findtext("duration") or "").strip()
                        # Heading-строка (заголовок стороны/секции): ни позиции,
                        # ни длительности. Это не трек — пасхалка «Спрятанный
                        # трек» ловила бы её как ненумерованный скрытый.
                        if not pos and not dur:
                            continue
                        tl.append({"position": pos, "title": title, "duration": dur or None})
                if tl:
                    w.writerow([rid, json.dumps(tl, ensure_ascii=False)])
                    written += 1
            root.clear()  # критично: снять накопленные дети root
            if seen % 500000 == 0:
                sys.stderr.write(f"  seen={seen:,} written={written:,}\n")
    sys.stderr.write(f"DONE seen={seen:,} written={written:,}\n")


_LOAD_HELP = """\
=== Загрузка CSV на сервере ===
1. Скопировать CSV в контейнер БД:
   docker compose -f docker-compose.prod.yml cp tracklists.csv db:/tmp/tracklists.csv
2. COPY (FORMAT csv — квотирование JSON корректно):
   docker compose -f docker-compose.prod.yml exec -T db \\
     psql -U "$POSTGRES_USER" -d vertushka -c \\
     "\\copy discogs_release_tracklists(discogs_id,tracklist) FROM '/tmp/tracklists.csv' WITH (FORMAT csv)"
3. Проверка:
   ... -c "SELECT count(*) FROM discogs_release_tracklists;"
4. Удалить временный CSV из контейнера.
"""


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dump", help="Путь к discogs_*_releases.xml(.gz)")
    ap.add_argument("--ids", help="Файл целевых discogs_id (по одному в строке)")
    ap.add_argument("--out", default="tracklists.csv")
    ap.add_argument("--load-help", action="store_true", help="Показать инструкцию загрузки")
    args = ap.parse_args()

    if args.load_help or not (args.dump and args.ids):
        print(_LOAD_HELP)
        return
    parse(args.dump, args.ids, args.out)


if __name__ == "__main__":
    main()
