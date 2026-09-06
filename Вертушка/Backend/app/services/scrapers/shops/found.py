"""
Парсер Found (pizza.foundmoscow.com/vinyl) — магазин винила на Tilda.

«Новый принцип»: весь каталог тянем через Tilda store-API одним проходом
(см. _tilda_store.TildaStoreParser), без пер-страничного фетча.

Особенности данных:
- sku / characteristics пусты → barcode/catalog нет, матчинг по artist+title
  (fuzzy + on-demand Discogs).
- title богатый и структурированный:
    «Виниловая пластинка {Artist} – {Album} ({формат, цвет, год}) [{Лейбл}, {год}] Style: {жанры}»
  префикс «Виниловая пластинка» есть не у всех (часть — просто «{Artist} – {Album}»).
- quantity: "1"=в наличии, "0"/пусто=нет.
- price «6900.0000», priceold — старая цена (скидка), кладём в raw_payload.
- gallery — JSON-строка с обложкой.
- Нон-медиа товары (сертификаты, пледы, мерч) — пропускаем.
"""
from __future__ import annotations

import html as html_lib
import re
from decimal import Decimal

from app.services.scrapers.base import ListingDTO
from app.services.scrapers.extractors import (
    parse_price,
    parse_year,
    infer_format,
    infer_vinyl_color,
)
from app.services.scrapers.registry import register_parser
from app.services.scrapers.shops._tilda_store import TildaStoreParser

# Префикс «Виниловая пластинка» / «Винил» в начале title.
_VINYL_PREFIX_RE = re.compile(r"^\s*винил(?:овая)?(?:\s*пластинка)?\s*[:\-–—]?\s*", re.I)
# Хвост «Style: Rock, Folk» — жанры.
_STYLE_RE = re.compile(r"\bstyle\s*:\s*(.+)$", re.I)
# Скобка [Лейбл, год] и (формат, цвет, год).
_SQUARE_RE = re.compile(r"\[([^\]]*)\]")
_PAREN_RE = re.compile(r"\(([^)]*)\)")
# artist – album: en/em-dash с любыми пробелами вокруг, либо дефис ТОЛЬКО с
# пробелами с обеих сторон (иначе порвём «Jay-Z», «P!nk-style» имена).
_TITLE_SPLIT_RE = re.compile(r"\s*[–—]\s*|\s+-\s+")
_PREORDER_KW_RE = re.compile(r"предзаказ|pre[\s\-]?order", re.I)

# Нон-медиа товары — не носители звука, пропускаем.
_NON_MEDIA_RE = re.compile(
    r"\b(?:"
    r"сертификат|подарочн\w*\s+сертификат|"
    r"плед|плэд|"
    r"футболк\w*|майк\w*|толстовк\w*|худи|hoodie|t-shirt|"
    r"кружк\w*|термокружк\w*|mug|стакан|бокал|"
    r"значо?к\w*|пин\b|pin[s]?\b|брелок\w*|брошь|"
    r"стикер\w*|наклейк\w*|sticker[s]?|"
    r"открытк\w*|плакат\w*|poster[s]?|постер\w*|"
    r"сумк\w*|шопер\w*|шоппер\w*|пакет\b|tote|"
    r"носки|чехол|коврик|slipmat|слипмат"
    r")\b",
    re.I | re.UNICODE,
)


@register_parser("found")
class FoundParser(TildaStoreParser):
    base_url = "https://pizza.foundmoscow.com"
    rate_limit_per_sec = 0.5
    rate_burst = 2
    requires_js = False

    # Из t_store_init('569036136', {... storepart:'852116833861' ...}) на /vinyl.
    store_recid = "569036136"
    store_partuid = "852116833861"

    def parse_product(self, product: dict) -> ListingDTO | None:
        raw_title = html_lib.unescape(str(product.get("title") or "")).strip()
        if not raw_title:
            return None

        artist, album, year, label, fmt_src = _parse_title(raw_title)

        # Нон-медиа фильтр — по ядру (artist+album), а НЕ по сырому title:
        # винил может комплектоваться постером/наклейкой («... Poster, 2LP»),
        # и эти слова в скобке не должны выкидывать пластинку из каталога.
        core = f"{artist or ''} {album}"
        if _NON_MEDIA_RE.search(core):
            return None

        # Текст для format/color/year — title + скобка-формат + descr.
        descr = html_lib.unescape(str(product.get("descr") or product.get("text") or ""))
        full_text = f"{raw_title}\n{fmt_src}\n{descr}"

        price = parse_price(str(product.get("price") or ""))
        price_old = parse_price(str(product.get("priceold") or ""))

        qty_raw = product.get("quantity")
        try:
            qty = int(str(qty_raw)) if qty_raw not in (None, "") else 0
        except (ValueError, TypeError):
            qty = 0

        if _PREORDER_KW_RE.search(full_text):
            status = "preorder"
        elif qty > 0:
            status = "in_stock"
        else:
            status = "out_of_stock"
        if price is None and status == "in_stock":
            status = "on_request"

        uid = product.get("uid")
        external_id = str(uid) if uid is not None else (product.get("url") or raw_title)

        raw_payload: dict = {"tilda_uid": uid}
        if price_old is not None:
            raw_payload["price_old_rub"] = str(price_old)
        if label:
            raw_payload["label"] = label

        return ListingDTO(
            external_id=external_id,
            url=str(product.get("url") or ""),
            title_raw=album or raw_title,
            artist_raw=artist,
            year_raw=year or parse_year(full_text),
            format_raw=infer_format(full_text) or "LP",
            vinyl_color_raw=(
                infer_vinyl_color(fmt_src, exclude=[artist, album, label])
                or infer_vinyl_color(full_text, exclude=[artist, album, label])
            ),
            condition="Новый (Mint)",
            price_rub=price,
            price_currency="RUB",
            status=status,
            barcode=None,
            catalog_number=None,
            discogs_release_url=None,
            image_url=self.first_gallery_image(product),
            raw_payload=raw_payload,
        )


# ---- helpers ----------------------------------------------------------- #


def _parse_title(raw: str) -> tuple[str | None, str, int | None, str | None, str]:
    """Разбор Found-title.

    «Виниловая пластинка Tyler – Call Me (Gatefold, 2LP, 2022) [Columbia, 2022] Style: Rap»
      → ("Tyler", "Call Me", 2022, "Columbia", "Gatefold, 2LP, 2022")

    Возвращает (artist, album, year, label, fmt_src). fmt_src — содержимое
    круглой скобки (формат/цвет/год) для infer_format/infer_vinyl_color.
    """
    t = _VINYL_PREFIX_RE.sub("", raw).strip()

    # Хвост Style: ... — отрезаем, для матчинга не нужен.
    m = _STYLE_RE.search(t)
    if m:
        t = t[: m.start()].strip()

    # [Лейбл, год]
    label: str | None = None
    year: int | None = None
    ms = _SQUARE_RE.search(t)
    if ms:
        bracket = ms.group(1)
        year = parse_year(bracket)
        label = (re.split(r",", bracket)[0].strip() or None)
        t = (t[: ms.start()] + " " + t[ms.end():]).strip()

    # (формат, цвет, год)
    fmt_src = ""
    mp = _PAREN_RE.search(t)
    if mp:
        fmt_src = mp.group(1)
        if year is None:
            year = parse_year(fmt_src)
        t = (t[: mp.start()] + " " + t[mp.end():]).strip()

    t = re.sub(r"\s+", " ", t).strip(" .–—-")
    artist, album = _split_artist_album(t)
    return artist, album, year, label, fmt_src


def _split_artist_album(title: str) -> tuple[str | None, str]:
    """«Antoha MC – Rodnya» → ("Antoha MC", "Rodnya"). Нет разделителя → (None, title)."""
    parts = _TITLE_SPLIT_RE.split(title, maxsplit=1)
    if len(parts) == 2 and parts[0].strip() and parts[1].strip():
        return parts[0].strip(), parts[1].strip()
    return None, title.strip()
