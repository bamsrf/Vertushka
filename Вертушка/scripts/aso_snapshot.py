#!/usr/bin/env python3
"""
ASO-замер по App Store: автоподсказки + выдача по ключам.

Зачем: docs/plans/APPSTORE_ASO_KIT.md §3 построен на этих данных. Выдача
меняется, поэтому замер надо повторять перед каждым сабмитом и сравнивать
с предыдущим снапшотом.

Два источника:
  1. MZSearchHints — тот же эндпоинт, что кормит строку поиска в App Store.
     Подсказка есть => у запроса есть заметный объём. Подсказок нет => объём
     около нуля. Абсолютных цифр эндпоинт не даёт.
  2. itunes.apple.com/search — кто стоит в выдаче и сколько у них оценок.
     ВАЖНО: порядок здесь НЕ равен ранжированию в самом App Store (движок
     другой). Показателен состав приложений и число оценок, не позиции.

Запуск:
    python3 scripts/aso_snapshot.py                    # текст в stdout
    python3 scripts/aso_snapshot.py --json out.json    # сырые данные
    python3 scripts/aso_snapshot.py --country us       # другой сторфронт
"""
import argparse
import json
import plistlib
import sys
import time
import urllib.parse
import urllib.request

# Сторфронты для заголовка X-Apple-Store-Front (нужен только подсказкам).
STOREFRONTS = {"ru": "143469", "us": "143441", "gb": "143444", "ua": "143492"}
UA = "iTunes-iPhone/12.0 (5; 16GB)"
PAUSE = 0.5  # сек между запросами, чтобы не долбить Apple

# Префиксы для автоподсказок: короткие куски слов, как их набирает человек.
PREFIXES = [
    "вин", "вини", "винил", "виниловые", "плас", "пласт", "пластин",
    "пластинки", "грампласт", "колл", "коллек", "коллекция", "коллекция вин",
    "каталог", "каталог пласт", "учет коллек", "скан", "сканер",
    "сканер вин", "штрих", "штрихкод", "мело", "меломан", "музыкальная колл",
    "альбом", "дискогр", "вишлист", "список желаний", "оценк", "оценка пласт",
    "стоим", "стоимость колл", "цена пласт", "подар", "подарок мело",
    "полка", "магазин вин", "купить вин", "редк", "раритет", "обложк",
    "проигрыват", "вертушк", "lp",
    "vinyl", "vinyl coll", "record", "record coll", "lp addict", "album",
    "collect", "catalog", "barcode", "wantlist", "shelf", "crate", "discog",
]

# Ключи, по которым смотрим выдачу и силу конкурентов.
TERMS = [
    "винил", "виниловые пластинки", "коллекция винила", "каталог пластинок",
    "пластинки", "сканер винила", "сканер пластинок", "штрихкод пластинки",
    "стоимость коллекции", "оценка пластинок", "цена винила", "вишлист",
    "меломан", "музыкальная коллекция", "дискография", "магазин винила",
    "купить винил", "подарок меломану",
    "vinyl collection", "record collection", "vinyl scanner",
]


def _get(url, headers=None, timeout=25):
    req = urllib.request.Request(url, headers=headers or {})
    return urllib.request.urlopen(req, timeout=timeout).read()


def hints(term, storefront):
    """Автоподсказки App Store по префиксу."""
    url = ("https://search.itunes.apple.com/WebObjects/MZSearchHints.woa/wa/hints"
           "?clientApplication=Software&term=" + urllib.parse.quote(term))
    try:
        raw = _get(url, {"X-Apple-Store-Front": "%s-16,29" % storefront,
                         "User-Agent": UA})
        return [h.get("term", "") for h in plistlib.loads(raw).get("hints", [])]
    except Exception as e:
        return {"error": str(e)}


def ranking(term, country):
    """Кто в выдаче по ключу и сколько у них оценок."""
    url = "https://itunes.apple.com/search?" + urllib.parse.urlencode({
        "term": term, "country": country, "entity": "software", "limit": 10})
    try:
        d = json.loads(_get(url))
    except Exception as e:
        return {"error": str(e)}
    return [{"name": a["trackName"], "seller": a.get("sellerName", ""),
             "rating": a.get("averageUserRating"),
             "count": a.get("userRatingCount", 0)} for a in d.get("results", [])]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--country", default="ru", choices=sorted(STOREFRONTS))
    ap.add_argument("--json", metavar="FILE", help="сохранить сырые данные")
    args = ap.parse_args()
    sf = STOREFRONTS[args.country]

    out = {"country": args.country, "hints": {}, "ranking": {}}

    print("=== АВТОПОДСКАЗКИ (%s) ===" % args.country.upper())
    for p in PREFIXES:
        h = out["hints"][p] = hints(p, sf)
        shown = "ОШИБКА: %s" % h["error"] if isinstance(h, dict) else (
            " · ".join(h) if h else "—ПУСТО— (объём около нуля)")
        print("%-18s | %s" % (p, shown))
        time.sleep(PAUSE)

    print("\n=== ВЫДАЧА И СИЛА КОНКУРЕНТОВ ===")
    print("%-22s %3s  %-38s %s" % ("ключ", "n", "лидер выдачи", "макс.оценок"))
    for t in TERMS:
        apps = out["ranking"][t] = ranking(t, args.country)
        if isinstance(apps, dict):
            print("%-22s ОШИБКА: %s" % (t, apps["error"]))
        else:
            top = apps[0]["name"][:38] if apps else "—"
            mx = max([a["count"] for a in apps], default=0)
            print("%-22s %3d  %-38s %d" % (t, len(apps), top, mx))
        time.sleep(PAUSE)

    if args.json:
        with open(args.json, "w") as f:
            json.dump(out, f, ensure_ascii=False, indent=1)
        print("\nСырые данные: %s" % args.json, file=sys.stderr)


if __name__ == "__main__":
    main()
