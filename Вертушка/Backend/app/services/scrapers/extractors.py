"""
Универсальные экстракторы полей из HTML-страницы товара.

Стратегия: пробуем JSON-LD (schema.org/Product) → microdata → OpenGraph →
обычные мета-теги. Per-shop парсер сверху может добавлять CSS-фолбэки.
"""
from __future__ import annotations

import json
import logging
import re
from decimal import Decimal, InvalidOperation
from typing import Any

from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)


# ---- JSON-LD ------------------------------------------------------------ #


def extract_jsonld_product(html: str) -> dict | None:
    """Найти первый JSON-LD блок типа Product. Возвращает dict либо None."""
    soup = BeautifulSoup(html, "lxml")
    for tag in soup.find_all("script", type="application/ld+json"):
        try:
            payload = json.loads(tag.string or "")
        except (json.JSONDecodeError, TypeError):
            continue
        product = _find_product(payload)
        if product:
            return product
    return None


def _find_product(node: Any) -> dict | None:
    if isinstance(node, dict):
        t = node.get("@type")
        if t == "Product" or (isinstance(t, list) and "Product" in t):
            return node
        # @graph контейнер
        if "@graph" in node:
            return _find_product(node["@graph"])
        # вложенные структуры
        for v in node.values():
            found = _find_product(v)
            if found:
                return found
    elif isinstance(node, list):
        for item in node:
            found = _find_product(item)
            if found:
                return found
    return None


def jsonld_price(product: dict) -> Decimal | None:
    """Из JSON-LD Product достать цену (offers.price)."""
    offers = product.get("offers")
    if not offers:
        return None
    if isinstance(offers, list):
        offers = offers[0] if offers else {}
    if not isinstance(offers, dict):
        return None
    price = offers.get("price") or offers.get("lowPrice")
    return parse_price(str(price)) if price is not None else None


def jsonld_availability(product: dict) -> str:
    """schema.org availability → наш ListingStatus enum."""
    offers = product.get("offers")
    if isinstance(offers, list):
        offers = offers[0] if offers else {}
    avail = (offers or {}).get("availability", "") if isinstance(offers, dict) else ""
    avail_lower = str(avail).lower()
    if "instock" in avail_lower:
        return "in_stock"
    if "outofstock" in avail_lower or "soldout" in avail_lower:
        return "out_of_stock"
    if "preorder" in avail_lower:
        return "preorder"
    if "discontinued" in avail_lower:
        return "removed"
    return "in_stock"


# ---- Парсинг цены ------------------------------------------------------- #


_PRICE_CLEAN = re.compile(r"[^\d,.]")
_PRICE_THOUSANDS_SEP = re.compile(r"[   ]")


def parse_price(value: str | None) -> Decimal | None:
    """«1 990 ₽», «1 990,00», «по запросу», «—» → Decimal | None."""
    if value is None:
        return None
    s = str(value).strip()
    if not s:
        return None
    s_lower = s.lower()
    if any(stop in s_lower for stop in ("запрос", "уточн", "договор", "недоступ", "снят")):
        return None
    s = _PRICE_THOUSANDS_SEP.sub("", s)
    s = _PRICE_CLEAN.sub("", s)
    if not s:
        return None
    # Заменяем русскую запятую-разделитель дробной части
    if s.count(",") == 1 and s.count(".") == 0:
        s = s.replace(",", ".")
    elif s.count(",") and s.count("."):
        s = s.replace(",", "")
    try:
        d = Decimal(s)
        if d <= 0 or d > Decimal("9999999"):
            return None
        return d
    except InvalidOperation:
        return None


# ---- Парсинг года ------------------------------------------------------- #


_YEAR_RE = re.compile(r"\b(19[5-9]\d|20[0-3]\d)\b")


def parse_year(value: str | None) -> int | None:
    if not value:
        return None
    m = _YEAR_RE.search(str(value))
    return int(m.group(1)) if m else None


# ---- Формат пластинки --------------------------------------------------- #


_FORMAT_MAP: list[tuple[re.Pattern, str]] = [
    # Box Set: «box set» / «box-set» / «boxset» / «бокс-сет» / «коробочное издание»
    # / просто «box» как самостоятельный токен (Bitrix-категория `/format/box/`).
    # Порядок важен — Box Set должен выиграть у «vinyl box set» где есть и LP-сигнал.
    # \bbox\b ловит ТОЛЬКО изолированное «Box» (не «Boxer», «Boxset» — для них
    # отдельные ветки выше). Это нужно для коротких маркеров типа «формат Box».
    (re.compile(r"\bbox[\-\s_]*set\b|\bboxset\b|\bбокс[\-\s_]?сет\b|\bкоробочн|\bbox\b", re.I), "Box Set"),
    # NxLP / NxVinyl: «2xLP», «3 LP», «4xVinyl», «double LP», «дабл-LP» — мультидисковые
    # пресс-сеты не-Box. Захватываем число → нормализуем в «2xLP» (количество в format_raw
    # сохраняем сырое, для матчинга достаточно знать что это набор LP)
    (re.compile(r"\b\d+\s*x?\s*[\-]?\s*(?:lp|vinyl)\b|\bdouble\s*lp\b|\bдабл[\s\-]?lp\b", re.I), "2xLP"),
    # Single LP / 12" — основной винил
    (re.compile(r"\blp\b|\bвинил\b|\bvinyl\b|12['']{1,2}|12\"", re.I), "LP"),
    # EP — extended play / 10"
    (re.compile(r"\bep\b|\b10['']{1,2}|10\"", re.I), "EP"),
    # 7" сингл
    (re.compile(r"\bsingle\b|\bсингл\b|7['']{1,2}|7\"", re.I), "Single"),
    # CD — compact disc. \bcd\b — границы слов чтобы не сматчить acdc-band
    (re.compile(r"\bcd\b", re.I), "CD"),
    # Кассета. «tape» убран — слишком много false positives (sticky tape в описании
    # клеящихся стрипов, например). Если нужно — «cassette tape» как пара слов.
    (re.compile(r"\bкассет(?:а|ы)?\b|\bcassette\b", re.I), "Cassette"),
    # Hybrid / SACD — реже но встречается в premium-изданиях
    (re.compile(r"\bsacd\b|\bhybrid\s*sacd\b", re.I), "SACD"),
]


def infer_format(value: str | None) -> str | None:
    if not value:
        return None
    for pattern, fmt in _FORMAT_MAP:
        if pattern.search(value):
            return fmt
    return None


# ---- Идентификаторы релиза ---------------------------------------------- #


_BARCODE_CLEAN = re.compile(r"[^\d]")
_DISCOGS_RELEASE_RE = re.compile(r"discogs\.com/(?:[\w\-]+/)?release/(\d+)", re.I)
_DISCOGS_MASTER_RE = re.compile(r"discogs\.com/(?:[\w\-]+/)?master/(\d+)", re.I)


def normalize_barcode(value: str | None) -> str | None:
    """Очистить штрихкод до 8-14 цифр.

    §A WS-A4: магазины часто паддят SKU лидирующими нулями (Tilda даёт
    '000'+EAN, напр. '000720642453612' для In Utero). Раньше это >14 цифр →
    отбрасывалось → листинг терял barcode → fuzzy-коллизия на чужой пресс.
    Теперь при >14 снимаем лидирующие нули (паддинг), затем — если всё ещё
    >14 — берём правые 14 (хвост несёт код). UPC↔EAN-13 эквивалентность
    разрешается на этапе матча через barcode_variants(), а не здесь.
    """
    if not value:
        return None
    cleaned = _BARCODE_CLEAN.sub("", str(value))
    if len(cleaned) > 14:
        cleaned = cleaned.lstrip("0")
        if len(cleaned) > 14:
            cleaned = cleaned[-14:]
    return cleaned if 8 <= len(cleaned) <= 14 else None


def barcode_variants(barcode: str | None) -> list[str]:
    """Эквивалентные формы штрихкода для матча (UPC-A ↔ EAN-13 + паддинг).

    Discogs-дамп хранит один и тот же товар то как UPC-A (12 цифр,
    '720642453612'), то как EAN-13 ('0'+UPC). ~20% записей дампа с лидирующим
    нулём. Чтобы матч не зависел от формы, при lookup'е пробуем набор:
    сам barcode, без лидирующих нулей, и UPC↔EAN-13 конверсию. Все кандидаты
    отфильтрованы по длине 8-14.
    """
    if not barcode:
        return []
    out = {barcode}
    stripped = barcode.lstrip("0")
    if stripped:
        out.add(stripped)
    if len(barcode) == 12:
        out.add("0" + barcode)  # UPC-A → EAN-13
    elif len(barcode) == 13 and barcode.startswith("0"):
        out.add(barcode[1:])  # EAN-13 → UPC-A
    return [b for b in out if 8 <= len(b) <= 14]


def normalize_catalog(value: str | None) -> str | None:
    """Catalog number: убираем пробелы/дефисы, в верхний регистр."""
    if not value:
        return None
    cleaned = re.sub(r"[\s\-_/.]", "", str(value)).upper()
    return cleaned or None


def find_discogs_release_url(html: str) -> str | None:
    m = _DISCOGS_RELEASE_RE.search(html)
    if m:
        return f"https://www.discogs.com/release/{m.group(1)}"
    m = _DISCOGS_MASTER_RE.search(html)
    if m:
        return f"https://www.discogs.com/master/{m.group(1)}"
    return None


# ---- Цвет винила ------------------------------------------------------- #


_COLOR_KEYWORDS = [
    "black", "чёрный", "чорный", "white", "белый", "red", "красный",
    "blue", "синий", "голубой", "green", "зелёный", "зеленый",
    "yellow", "жёлтый", "желтый", "orange", "оранжевый",
    "purple", "фиолетовый", "pink", "розовый", "clear", "прозрачный",
    "splatter", "брызги", "marbled", "мрамор", "splash",
    "translucent", "transparent", "gold", "золотой", "silver", "серебряный",
    "coloured", "color", "цветной",
]


def infer_vinyl_color(text: str | None) -> str | None:
    if not text:
        return None
    text_lower = text.lower()
    for kw in _COLOR_KEYWORDS:
        if kw in text_lower:
            # вернём найденное слово (как пользователь видит на сайте)
            idx = text_lower.find(kw)
            return text[idx:idx + len(kw)]
    return None
