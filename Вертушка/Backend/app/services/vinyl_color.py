"""
Нормализация «сырого» текста цвета винила → семья цвета.

Зачем: и у листинга (`store_listings.vinyl_color_raw`), и у записи
(`records.discogs_data->>'vinyl_color_raw'` = `formats[0].text` из Discogs)
строка цвета грязная и в разном написании. Discogs-сторона особенно мусорная —
мешает цвет с весом («180 Gram»), упаковкой («Jewel Case», «Gatefold»), заводом
(«Cinram GmbH»), даже битрейтом («256 kbps»). Поэтому для СРАВНЕНИЯ цвета
(exact-pressing vs album-level в offers) нельзя брать сырые строки — нужно
свести обе стороны к одной «семье» и сравнивать семьи.

`color_family()` возвращает каноническую семью (`black`/`red`/`green`/…) или
None, если в строке нет ни одного известного цветового слова (вес/упаковка →
None, и сравнение деградирует в «неизвестно», а не в ложный конфликт).

`sql_color_family()` / `sql_pressing_tier()` — зеркала той же логики в SQL, для
batch-summary endpoint, который считает агрегаты в Postgres, а не в Python.
Держать ОБА в синхроне: правишь семьи здесь — поправь и SQL-ветки.
"""
from __future__ import annotations

import re

# (семья, regex по EN+RU синонимам). Порядок = приоритет при мульти-цвете
# (напр. «Red/Blue» → red). Намеренно НЕ включаем неспецифичные токены
# (clear/marbled/splatter/translucent/coloured/цветной) — они не дают семью,
# не годятся для доказательства конфликта.
# EN-токены — по границе слова (\b), иначе «red» ловится внутри «colouRED»,
# «hundRED» и т.п. (главный источник ложного «red» в цвете оффера). RU-стемы
# оставлены как префиксы — там подстрочных коллизий на практике нет. teal/
# turquoise добавлены: без них «Teal [Translucent Electric Teal]» с Discogs
# давал family=None → конфликт с цветом оффера не доказывался.
# sql_color_family() транслирует \b → \y (граница слова в Postgres) — держать в
# синхроне.
_FAMILY_PATTERNS: list[tuple[str, str]] = [
    ("black", r"\bblack\b|чёрн|чорн"),
    ("white", r"\bwhite\b|бел"),
    ("teal", r"\bteal\b|бирюз"),
    ("turquoise", r"\bturquoise\b|тиркойз"),
    ("red", r"\bred\b|красн"),
    ("blue", r"\bblue\b|син|голуб"),
    ("green", r"\bgreen\b|зелён|зелен"),
    ("yellow", r"\byellow\b|жёлт|желт"),
    ("orange", r"\borange\b|оранж"),
    ("purple", r"\bpurple\b|фиолет"),
    ("pink", r"\bpink\b|розов"),
    ("gold", r"\bgold\b|золот"),
    ("silver", r"\bsilver\b|серебр"),
]

_COMPILED: list[tuple[str, re.Pattern[str]]] = [
    (fam, re.compile(pat, re.IGNORECASE)) for fam, pat in _FAMILY_PATTERNS
]


def color_family(raw: str | None) -> str | None:
    """Свести сырой текст цвета к канонической семье или None.

    None = нет ни одного известного цветового слова (вес/упаковка/мусор).
    """
    if not raw:
        return None
    for fam, rx in _COMPILED:
        if rx.search(raw):
            return fam
    return None


# ---- Цвет пресса из дампа Discogs --------------------------------------- #
#
# Discogs держит цвет винила в атрибуте `text` у формата: `<format name="Vinyl"
# text="Red Translucent">`. Поле необязательное и общего назначения — рядом с
# цветом пластинки туда пишут упаковку, вес и вообще что угодно. Замер по
# нашим 37 464 записям (дамп 2026-08): непустой text у 14 770, цвет
# распознаётся у 6 436, и 943 из них описывают НЕ пластинку:
#
#   «Metallic Silver Sleeve», «Gold Inner Sleeve», «Green Case»,
#   «White Embossed Cover», «Blue Labels», «Simple Black Sleeve»
#
# Возьми мы их — чёрная пластинка в золотом конверте приехала бы золотой.
# Поэтому куски со словами упаковки отбрасываются целиком, до поиска цвета.
_PACKAGING_RE = re.compile(
    r"sleeve|cover|case|jacket|box|insert|obi|booklet|poster|sticker|label|"
    r"card|slipcase|digipak|gatefold|envelope|конверт|чехол",
    re.IGNORECASE,
)


def vinyl_color_from_format_texts(texts: list[str] | None) -> str | None:
    """Цвет пластинки из значений `format@text` одного релиза.

    Возвращает исходную строку (например «Red Translucent»), а не семью:
    хранить лучше то, что написал Discogs, семью выведут потребители.
    Куски про упаковку игнорируются, из остальных берётся первый, где есть
    известное цветовое слово.
    """
    for text in texts or []:
        cleaned = (text or "").strip()
        if not cleaned or _PACKAGING_RE.search(cleaned):
            continue
        if color_family(cleaned):
            return cleaned
    return None


# ---- «Цветной ли винил» — вопрос, отдельный от семьи -------------------- #
#
# `color_family` отвечает «какой именно цвет» и нужна для ДОКАЗАТЕЛЬСТВА
# конфликта (чёрный листинг ↔ зелёная запись). Неспецифичные слова она
# намеренно не считает семьёй: «цветной» не конфликтует ни с чем.
#
# Но у фильтра Маркета вопрос другой — «цветной ли он вообще». И на складе это
# чаще всего написано ровно так, без уточнения: у plastinka_com 883 листинга с
# «(цветной винил)» в заголовке и ни одного конкретного цвета. Через семью этот
# вопрос не выразить, поэтому у него своя функция — и своё SQL-зеркало.
#: Неспецифичные признаки «это не обычный чёрный»: сам маркер «цветной», а
#: также прозрачность, разводы и брызги. Семьёй они не считаются намеренно
#: (конфликт ими не докажешь), но пластинку с «Clear & Black» или «Splatter»
#: чёрной называть нельзя. Набор совпадает с правилом счётчика цветных в
#: профиле (services/profile_stats) — одно определение «цветного» на оба места.
#:
#: Сюда приходит уже РАСПОЗНАННОЕ значение (канон «coloured» от
#: infer_vinyl_color или сырая строка магазина), а не произвольный текст, —
#: поэтому адъяцентность к носителю тут не нужна, её проверил парсер.
_COLORED_MARKER = (
    r"\bcolou?red\b|\bcolou?r\b|цветн|"
    r"translucen|transparent|\bclear\b|marbl|splatter|swirl|"
    r"picture disc|\bglow\b|прозрачн|мрамор"
)
_COLORED_MARKER_RE = re.compile(_COLORED_MARKER, re.IGNORECASE)


def is_colored_vinyl(raw: str | None) -> bool:
    """Цветной ли винил: есть ЛЮБОЕ не-чёрное цветовое слово ИЛИ общий маркер.

    Именно «любое», а не «семья по приоритету». `color_family` ставит black
    первым и на двухцветном прессе отдаёт именно его — а «Red/Black Splatter»,
    «Orange With Black Splatter», «Black and Purple Marbled» это ровно тот
    цветной винил, за которым и охотятся. В дампе таких 570 из 5 493 значений,
    12%: через семью они все считались бы чёрными.

    Приоритет семьи при этом не трогаем — он нужен там, где доказывается
    КОНФЛИКТ цвета листинга и записи, и там «первый по списку» осмыслен.
    """
    if not raw:
        return False
    for fam, rx in _COMPILED:
        if fam != "black" and rx.search(raw):
            return True
    return bool(_COLORED_MARKER_RE.search(raw))


def sql_is_colored_vinyl(col_expr: str) -> str:
    """SQL-зеркало is_colored_vinyl. Держать в синхроне с функцией выше.

    Проверяем НАЛИЧИЕ любого не-чёрного цветового слова, а не результат
    sql_color_family: у той black первый по приоритету и «Red/Black Splatter»
    вернулся бы чёрным.
    """
    nonblack = "|".join(
        pat.replace(chr(92) + "b", chr(92) + "y")
        for fam, pat in _FAMILY_PATTERNS
        if fam != "black"
    )
    marker = _COLORED_MARKER.replace(chr(92) + "b", chr(92) + "y")
    return (
        f"(lower({col_expr}) ~ '({nonblack})'"
        f" OR lower({col_expr}) ~ '{marker}')"
    )


# ---- SQL-зеркала (для batch summary endpoint) -------------------------- #


def sql_color_family(col_expr: str) -> str:
    """SQL CASE, эквивалент color_family(), над переданным text-выражением.

    `col_expr` подставляется как есть — передавай только доверенные имена
    колонок/выражений (не пользовательский ввод).
    """
    # Postgres ARE не знает \b — транслируем в \y (граница слова). RU-стемы без
    # \b проходят как есть.
    branches = "\n".join(
        f"      WHEN lower({col_expr}) ~ '({pat.replace(chr(92) + 'b', chr(92) + 'y')})' THEN '{fam}'"
        for fam, pat in _FAMILY_PATTERNS
    )
    return f"""CASE
      WHEN {col_expr} IS NULL THEN NULL
{branches}
      ELSE NULL END"""


# match_method'ы, идентифицирующие КОНКРЕТНЫЙ пресс (а не просто альбом):
# barcode/discogs_url — точные; catalog — каталожный № пресса; store_native /
# merged — цвет записи выведен из самого листинга, по построению верный.
_PRESSING_EXACT_METHODS = (
    "discogs_url",
    "barcode",
    "catalog",
    "store_native",
    "merged_from_store_native",
)


def sql_pressing_tier(
    *,
    method_col: str,
    confidence_col: str,
    listing_color_col: str,
    record_color_expr: str,
) -> str:
    """SQL-выражение → 'exact' | 'album'. Зеркало pressing_tier() в offers.py.

    Логика: конфликт семей цвета (обе известны и разные) → 'album' (перебивает
    всё). Иначе exact-методы → 'exact'; fuzzy → 'album'; остальные
    (dump_index/discogs_fetch) — по confidence ≥0.95.
    """
    lf = sql_color_family(listing_color_col)
    rf = sql_color_family(record_color_expr)
    methods = ", ".join(f"'{m}'" for m in _PRESSING_EXACT_METHODS)
    return f"""CASE
      WHEN ({lf}) IS NOT NULL AND ({rf}) IS NOT NULL AND ({lf}) <> ({rf}) THEN 'album'
      WHEN {method_col} IN ({methods}) THEN 'exact'
      WHEN {method_col} = 'fuzzy' THEN 'album'
      WHEN {confidence_col} >= 0.95 THEN 'exact'
      ELSE 'album' END"""


# Python-зеркало списка методов — для pressing_tier() в offers.py.
PRESSING_EXACT_METHODS = frozenset(_PRESSING_EXACT_METHODS)
