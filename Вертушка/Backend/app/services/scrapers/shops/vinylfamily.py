"""Парсер Vinyl Family (vinylfamily.shop) — Tilda store-API.

Найден ресерчем 05.09. Всё новьё (цветные/юбилейные прессы, reissue), крен в
метал/рок с добавкой электроники/хип-хопа. Каталог плоский (одна партиция),
много распроданного (qty=0) — фильтруем по наличию.

Данные store-API (образец 05.09):
- title: «Artist - Album (LP)» — формат в хвостовой скобке, разделитель — дефис.
- **`text`** (не `descr`!): «Формат: виниловая пластинка<br />Количество
  носителей: 2<br />Лейбл: XL<br />Дата релиза: 27.06.1997<br />Номер по
  каталогу: 7248811<br /><br />Трек-лист: …» — **каталожный номер у 100%**,
  это сильнейший сигнал матчинга.
- sku — внутренний счётчик («3», «5»), НЕ каталожный номер (в отличие от
  Kultura); катномер берём только из text.
- quantity: число; gallery — JSON с обложкой.
"""
from __future__ import annotations

import html as html_lib
import re

from app.services.scrapers.base import ListingDTO
from app.services.scrapers.extractors import (
    infer_format,
    infer_vinyl_color,
    parse_price,
    parse_year,
)
from app.services.scrapers.registry import register_parser
from app.services.scrapers.shops._tilda_store import TildaStoreParser

_BR_RE = re.compile(r"<br\s*/?>", re.I)
_TITLE_SPLIT_RE = re.compile(r"\s*[–—]\s*|\s+-\s+")
# Хвостовая скобка формата: «... (LP)», «... (2LP, Coloured)».
_TRAILING_PAREN_RE = re.compile(r"\s*\(([^()]*)\)\s*$")
_PREORDER_KW_RE = re.compile(r"предзаказ|pre[\s\-]?order", re.I)

_NON_MEDIA_RE = re.compile(
    r"\b(?:сертификат|подарочн\w*|футболк\w*|майк\w*|толстовк\w*|худи|hoodie|"
    r"кружк\w*|значо?к\w*|пин\b|брелок\w*|стикер\w*|наклейк\w*|плакат\w*|"
    r"постер\w*|poster|сумк\w*|шопер\w*|шоппер\w*|tote|слипмат|slipmat)\b",
    re.I | re.UNICODE,
)


def _clean(s: str) -> str:
    return html_lib.unescape(s or "").replace("‎", "").replace("‏", "").strip()


def _text_kv(text: str) -> dict[str, str]:
    """«Лейбл: XL<br />Дата релиза: 1997» → {'лейбл': 'XL', ...} (ключ lower).

    Трек-лист (после пустого <br /><br />) не мешает: строки трек-листа —
    «A1. Smack My Bitch Up», двоеточия в них нет либо ключ мусорный, в нужные
    поля они не попадают.
    """
    out: dict[str, str] = {}
    for line in _BR_RE.split(text or ""):
        line = _clean(line)
        if ":" in line:
            k, _, v = line.partition(":")
            k, v = k.strip().lower(), v.strip()
            if k and v and k not in out:
                out[k] = v
    return out


def _split_artist_album(title: str) -> tuple[str | None, str]:
    # Отрезаем хвостовую скобку формата от album.
    fmt = ""
    m = _TRAILING_PAREN_RE.search(title)
    if m:
        fmt = m.group(1)
        title = title[: m.start()].strip()
    parts = _TITLE_SPLIT_RE.split(title, maxsplit=1)
    if len(parts) == 2 and parts[0].strip() and parts[1].strip():
        return parts[0].strip(), parts[1].strip(), fmt
    return None, title.strip(), fmt


@register_parser("vinylfamily")
class VinylFamilyParser(TildaStoreParser):
    base_url = "https://vinylfamily.shop"
    rate_limit_per_sec = 0.5
    rate_burst = 2
    requires_js = False

    # t_store_init('1866202431', {... storepart:'271951382371' ...}).
    store_recid = "1866202431"
    store_partuid = "271951382371"

    def parse_product(self, product: dict) -> ListingDTO | None:
        raw_title = _clean(str(product.get("title") or ""))
        if not raw_title:
            return None

        artist, album, fmt_tail = _split_artist_album(raw_title)

        if _NON_MEDIA_RE.search(f"{artist or ''} {album}"):
            return None

        text = str(product.get("text") or product.get("descr") or "")
        kv = _text_kv(text)
        full_text = f"{raw_title}\n{text}"

        # «Номер по каталогу» у vinylfamily заполнен всегда, но у части товаров
        # там 12–13-значный EAN, а не каталожный номер. Штрихкод — сильнейший
        # сигнал матчинга, поэтому разводим по полям: чистые 12–13 цифр → barcode,
        # всё остальное → catalog_number.
        catalog = barcode = None
        catno_raw = (kv.get("номер по каталогу") or "").strip()
        if catno_raw:
            digits = catno_raw.replace(" ", "").replace("-", "")
            if digits.isdigit() and len(digits) in (12, 13):
                barcode = digits
            else:
                catalog = catno_raw
        label = kv.get("лейбл") or None
        year = parse_year(kv.get("дата релиза", "")) or parse_year(full_text)

        # Формат: характеристики → хвостовая скобка title → эвристика.
        fmt_char = _characteristic(product, "формат")
        fmt_raw = infer_format(f"{fmt_char} {fmt_tail} {text}") or "LP"

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
            year_raw=year,
            format_raw=fmt_raw,
            vinyl_color_raw=infer_vinyl_color(
                f"{fmt_tail} {text}", exclude=[artist, album, label]
            ),
            condition="Новый (Mint)",
            price_rub=price,
            price_currency="RUB",
            status=status,
            barcode=barcode,
            catalog_number=catalog,
            discogs_release_url=None,
            image_url=self.first_gallery_image(product),
            raw_payload=raw_payload,
        )


def _characteristic(product: dict, key: str) -> str:
    """Значение из characteristics=[{'title':'Формат','value':'...'}]."""
    import json

    raw = product.get("characteristics")
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except json.JSONDecodeError:
            return ""
    if isinstance(raw, list):
        for c in raw:
            if isinstance(c, dict) and str(c.get("title", "")).strip().lower() == key:
                return str(c.get("value") or "")
    return ""
