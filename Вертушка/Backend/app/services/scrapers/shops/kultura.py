"""Парсер Kultura Record Store (kulturarecordstore.ru) — Tilda store-API.

Найден ресерчем 05.09. Главная ценность — жанровое РАЗНООБРАЗИЕ, которого
нет у текущих магазинов (крен в рок/поп/б-у): у Kultura 19 жанров, из них
Ambient/Experimental 640, House/Deep House 475, Electronic/IDM 239,
Hip-Hop 191, Drum&Bass 147, Jazz 166, Funk/Soul 113 — электроника,
эксперимент, хип-хоп, world.

Данные store-API (образец 05.09):
- title: «Artist - Album», разделитель — обычный дефис, часто с невидимым
  LTR-маркером `‎` (\\u200e) перед ним; встречается алиас-форма
  «박혜진 = Park Hye Jin - Before I Die» (нативное = латиница) — берём латиницу.
- sku: НАСТОЯЩИЙ каталожный номер (`TRP028RP`, `ZEN277`, `WARPLP288`), но не
  у всех — сильный сигнал для матчинга, когда есть.
- descr: «Лейбл: трип ‎– TRP028RP<br />Формат: 2 × 12"<br />Дата выхода:
  2023<br />Стиль: Techno» — год, лейбл, формат, жанр.
- quantity: число в наличии; gallery — JSON с обложкой.
- Нон-музыка вынесена в отдельные партиции (Книги/Сертификаты/Мерч/KURS
  Radio) — отсекаем по `partuids`, плюс страховочный regex по title.
"""
from __future__ import annotations

import html as html_lib
import json
import re
from decimal import Decimal

from app.services.scrapers.base import ListingDTO
from app.services.scrapers.extractors import (
    infer_format,
    infer_vinyl_color,
    parse_price,
    parse_year,
)
from app.services.scrapers.registry import register_parser
from app.services.scrapers.shops._tilda_store import TildaStoreParser

# Партиции витрины, которые НЕ музыка (uid из getparts=true, 05.09).
# Товар выкидываем, только если ВСЕ его партиции здесь: винил из «Новинки»
# лежит и в музыкальной партиции, а книга — только в «Аксессуары / Книги».
_NON_MUSIC_PARTS = {
    "249075337969",  # Аксессуары / Книги
    "782751268808",  # Сертификаты / Подписки
    "129621941950",  # Мерч
    "647226802572",  # KURS Radio
}

# Невидимые маркеры направления письма в title/descr — рвут split и матчинг.
_BIDI_RE = re.compile(r"[‎‏‪-‮]")

# artist – album: en/em-dash с пробелами, либо дефис ТОЛЬКО с пробелами с обеих
# сторон (иначе порвём «Jay-Z», «AC/DC» не трогаем — там нет пробелов).
_TITLE_SPLIT_RE = re.compile(r"\s*[–—]\s*|\s+-\s+")

# Алиас Discogs-вида «박혜진 = Park Hye Jin» → берём латинизированную часть.
_ALIAS_RE = re.compile(r"\s*=\s*")

# descr — строки «Ключ: значение», разделённые <br />.
_BR_RE = re.compile(r"<br\s*/?>", re.I)

# Каталожный номер: буква+цифра, 4–20 символов (TRP028RP, WARPLP288, ZEN277).
# Отсекаем внутренние счётчики vinylfamily-вида «3», «11».
_CATNO_RE = re.compile(r"^(?=.*\d)(?=.*[A-Za-z])[A-Za-z0-9][A-Za-z0-9 .\-]{2,19}$")

_NON_MEDIA_RE = re.compile(
    r"\b(?:сертификат|подпис\w*|"
    r"футболк\w*|майк\w*|толстовк\w*|худи|hoodie|t-shirt|"
    r"кружк\w*|значо?к\w*|пин\b|брелок\w*|стикер\w*|наклейк\w*|"
    r"плакат\w*|постер\w*|poster|сумк\w*|шопер\w*|шоппер\w*|tote|"
    r"слипмат|slipmat|книга|book)\b",
    re.I | re.UNICODE,
)


def _clean(s: str) -> str:
    return _BIDI_RE.sub("", html_lib.unescape(s or "")).strip()


def _partuids(product: dict) -> set[str]:
    """partuids приходит JSON-строкой `"[249075337969]"` (как gallery), а не
    списком — распарсить, иначе итерация идёт по символам."""
    raw = product.get("partuids")
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except json.JSONDecodeError:
            return set()
    if not isinstance(raw, list):
        return set()
    return {str(u) for u in raw}


def _descr_kv(descr: str) -> dict[str, str]:
    """«Лейбл: X<br />Формат: Y» → {'лейбл': 'X', 'формат': 'Y'} (ключ в lower)."""
    out: dict[str, str] = {}
    for line in _BR_RE.split(descr or ""):
        line = _clean(line)
        if ":" in line:
            k, _, v = line.partition(":")
            k = k.strip().lower()
            v = v.strip()
            if k and v:
                out[k] = v
    return out


def _split_artist_album(title: str) -> tuple[str | None, str]:
    parts = _TITLE_SPLIT_RE.split(title, maxsplit=1)
    if len(parts) == 2 and parts[0].strip() and parts[1].strip():
        artist = parts[0].strip()
        # «Нативное = Latin» — оставляем латиницу, она ближе к records.artist.
        if _ALIAS_RE.search(artist):
            artist = _ALIAS_RE.split(artist)[-1].strip() or artist
        return artist, parts[1].strip()
    return None, title.strip()


@register_parser("kultura")
class KulturaParser(TildaStoreParser):
    base_url = "https://kulturarecordstore.ru"
    rate_limit_per_sec = 0.5
    rate_burst = 2
    requires_js = False

    # t_store_init('197833805', {... storepart:'794705076345' ...}) на /store.
    store_recid = "197833805"
    store_partuid = "794705076345"

    def parse_product(self, product: dict) -> ListingDTO | None:
        raw_title = _clean(str(product.get("title") or ""))
        if not raw_title:
            return None

        # Отсекаем не-музыку по партициям: пропускаем, только если товар живёт
        # ИСКЛЮЧИТЕЛЬНО в нон-музыкальных разделах.
        partuids = _partuids(product)
        if partuids and partuids <= _NON_MUSIC_PARTS:
            return None

        artist, album = _split_artist_album(raw_title)

        # Страховка: явная не-музыка по ядру (сертификат/книга без партиции).
        if _NON_MEDIA_RE.search(f"{artist or ''} {album}"):
            return None

        kv = _descr_kv(str(product.get("descr") or product.get("text") or ""))
        full_text = f"{raw_title}\n{product.get('descr') or ''}"

        # Каталожный номер: сперва sku (там реальный катномер), иначе — из
        # «Лейбл: трип – TRP028RP» (хвост после дефиса).
        catalog = None
        sku = _clean(str(product.get("sku") or ""))
        if sku and _CATNO_RE.match(sku):
            catalog = sku
        elif kv.get("лейбл"):
            tail = _TITLE_SPLIT_RE.split(kv["лейбл"])
            if len(tail) > 1 and _CATNO_RE.match(tail[-1].strip()):
                catalog = tail[-1].strip()

        label = None
        if kv.get("лейбл"):
            label = _TITLE_SPLIT_RE.split(kv["лейбл"])[0].strip() or None

        year = parse_year(kv.get("дата выхода", "")) or parse_year(full_text)
        fmt_src = kv.get("формат", "")

        price = parse_price(str(product.get("price") or ""))
        price_old = parse_price(str(product.get("priceold") or ""))

        qty_raw = product.get("quantity")
        try:
            qty = int(str(qty_raw)) if qty_raw not in (None, "") else 0
        except (ValueError, TypeError):
            qty = 0

        is_preorder = bool(_PREORDER_KW_RE.search(full_text))
        if is_preorder:
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
        if kv.get("стиль"):
            raw_payload["genre"] = kv["стиль"]

        return ListingDTO(
            external_id=external_id,
            url=str(product.get("url") or ""),
            title_raw=album or raw_title,
            artist_raw=artist,
            year_raw=year,
            format_raw=infer_format(f"{fmt_src} {full_text}") or "LP",
            vinyl_color_raw=infer_vinyl_color(full_text, exclude=[artist, album]),
            condition="Новый (Mint)",
            price_rub=price,
            price_currency="RUB",
            status=status,
            barcode=None,
            catalog_number=catalog,
            discogs_release_url=None,
            image_url=self.first_gallery_image(product),
            raw_payload=raw_payload,
        )


_PREORDER_KW_RE = re.compile(r"предзаказ|pre[\s\-]?order", re.I)
