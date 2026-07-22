"""
Парсер Korobka Vinyla (korobkavinyla.ru) — магазин на Tilda.

Особенности:
- sitemap-store.xml — sitemap-index → 6 part-файлов с ~3500 товаров
- товарные URL: /catalog/tproduct/<rootpart>-<uid>-<slug>
- JSON-LD нет, но есть:
    * <meta itemprop="sku" content="..."> — microdata (часто = EAN-13 штрихкод)
    * <h1> title в формате "Artist – Album"
    * og:image — обложка
    * JS-объект `var product = {...}` с полным payload (title, descr, prices)
- описание (descr) часто содержит: год, формат, цвет винила, лейбл, страну
"""
from __future__ import annotations

import json
import re
from decimal import Decimal

from bs4 import BeautifulSoup

from app.services.scrapers.base import BaseStoreParser, ListingDTO, ParserError
from app.services.scrapers.extractors import (
    parse_price,
    parse_year,
    infer_format,
    infer_vinyl_color,
    normalize_barcode,
    normalize_catalog,
    find_discogs_release_url,
)
from app.services.scrapers.registry import register_parser


_PRODUCT_VAR_RE = re.compile(r"var\s+product\s*=\s*(\{.*?\});", re.DOTALL)
_TITLE_SPLIT_RE = re.compile(r"\s+[–—-]\s+")  # разделители артист–альбом
_PREORDER_KW_RE = re.compile(r"предзаказ|pre[\s\-]?order", re.I)
_OUT_OF_STOCK_KW_RE = re.compile(r"нет в наличии|sold\s*out|раскуплен|закончил", re.I)

# Аксессуары и нон-медиа товары — пропускать при парсинге.
# Пины, значки, брелоки, плакаты, одежда — всё что не является носителем звука.
_ACCESSORY_RE = re.compile(
    r"\b(?:"
    r"пин[ыа]?|pin[s]?|значо?к[и]?|брошь|брелок[и]?|"
    r"плакат[ы]?|poster[s]?|"
    r"футболк[аи]|майк[аи]|толстовк[аи]|hoodie|t-shirt|"
    r"кружк[аи]|mug[s]?|"
    r"патч[и]?|patch(?:es)?|нашивк[аи]?|"
    r"стикер[ы]?|sticker[s]?|наклейк[аи]?"
    r")\b",
    re.I | re.UNICODE,
)


@register_parser("korobkavinyla")
class KorobkaVinylaParser(BaseStoreParser):
    base_url = "https://korobkavinyla.ru"
    rate_limit_per_sec = 0.5  # 1 req per 2s — вежливо к Tilda
    rate_burst = 2
    requires_js = False
    # Tilda: основной sitemap пуст, продуктовый — sitemap-store.xml (sitemap-index)
    sitemap_paths = ["/sitemap-store.xml"]
    listing_url_pattern = r"/tproduct/"

    async def parse_listing(self, url: str) -> ListingDTO:
        html = await self.http.get_text(url)
        soup = BeautifulSoup(html, "lxml")

        # 1) Tilda var product = {...} — основной источник, тут всё что надо
        product = _extract_tilda_product(html)

        # 2) Падбэки на DOM
        title = (
            (product.get("title") if product else None)
            or _meta_content(soup, "og:title", attr="property")
            or (soup.h1.get_text(strip=True) if soup.h1 else "")
        )
        if not title:
            raise ParserError(f"no title at {url}")

        # Пропускаем аксессуары (пины, значки, плакаты и т.д.) — не носители звука
        if _ACCESSORY_RE.search(title):
            raise ParserError(f"accessory item, skip: {title!r}")

        descr_html = (product.get("descr") if product else "") or ""
        descr_text = BeautifulSoup(descr_html, "lxml").get_text(" ", strip=True) if descr_html else ""
        meta_descr = _meta_content(soup, "og:description", attr="property") or ""
        # URL slug добавляем для format detection: URL формата
        # /tproduct/{rootpartid}-{barcode}-{slug}, где slug часто содержит формат
        # («-cd», «-box-set», «-cassette»). Если у товара пустой descr — slug
        # спасёт infer_format. Дефис → пробел чтобы \b в regex сработали.
        url_slug = url.rsplit("/", 1)[-1].replace("-", " ")
        full_text = f"{title}\n{descr_text}\n{meta_descr}\n{url_slug}"

        artist, album = _split_artist_album(title)

        # SKU из microdata = часто EAN-13. Класть в barcode если 8-14 цифр, иначе catalog.
        # Fallback: URL Tilda имеет формат /tproduct/{rootpartid}-{EAN}-{slug} —
        # если product.sku и meta itemprop="sku" пусты, EAN скорее всего там.
        # Это критично для match_listing: без barcode он не идёт в on-demand
        # Discogs fetch, и листинг остаётся unmatched.
        sku_raw = (
            (product.get("sku") if product else None)
            or _itemprop(soup, "sku")
            or _extract_barcode_from_url(url)
        )
        barcode = normalize_barcode(sku_raw)
        catalog_number = None if barcode else normalize_catalog(sku_raw)

        # Цена: priceMinprefix → price из product → fallback meta itemprop="price"
        price = None
        if product:
            price = parse_price(str(product.get("price") or product.get("priceMin") or ""))
        if price is None:
            price = parse_price(_itemprop(soup, "price"))

        # Статус: ключевой сигнал — `product.quantity` из Tilda JSON-объекта.
        # Tilda пишет "quantity":"N" когда товар в наличии, и пропускает поле
        # (или ставит "0") когда товар закончился. Это надёжнее, чем regex по
        # ключевым словам — у out-of-stock товаров часто на странице нет фраз
        # типа «нет в наличии», просто скрыта кнопка «купить».
        qty_raw = product.get("quantity") if product else None
        try:
            qty = int(str(qty_raw)) if qty_raw is not None and str(qty_raw).strip() != "" else 0
        except (ValueError, TypeError):
            qty = 0

        if _PREORDER_KW_RE.search(title) or _PREORDER_KW_RE.search(full_text):
            status = "preorder"
        elif qty > 0:
            status = "in_stock"
        elif _OUT_OF_STOCK_KW_RE.search(full_text):
            status = "out_of_stock"
        elif product is None:
            # Tilda product объект не найден на странице — нет данных о наличии,
            # фолбэк на старую эвристику (цена есть → on_request, иначе out_of_stock)
            status = "on_request" if price is not None else "out_of_stock"
        else:
            # product есть, но quantity нет / 0 — товар закончился
            status = "out_of_stock"

        if price is None and status == "in_stock":
            status = "on_request"

        external_id = (
            str(product.get("uid")) if product and product.get("uid")
            else _extract_uid_from_url(url)
        )

        return ListingDTO(
            external_id=external_id,
            url=url,
            title_raw=album or title,
            artist_raw=artist,
            year_raw=parse_year(full_text),
            format_raw=infer_format(full_text) or "LP",
            vinyl_color_raw=infer_vinyl_color(full_text, exclude=[artist, album]),
            # Магазин нового товара — состояние всегда запечатанный нов.
            condition="Новый (Mint)",
            price_rub=price,
            price_currency="RUB",
            status=status,
            barcode=barcode,
            catalog_number=catalog_number,
            discogs_release_url=find_discogs_release_url(html),
            image_url=_meta_content(soup, "og:image", attr="property"),
            raw_payload={
                "tilda_uid": product.get("uid") if product else None,
                "tilda_rootpartid": product.get("rootpartid") if product else None,
            },
        )


# ---- helpers ----------------------------------------------------------- #


def _extract_tilda_product(html: str) -> dict | None:
    """Найти `var product = {...};` и распарсить как JSON."""
    m = _PRODUCT_VAR_RE.search(html)
    if not m:
        return None
    raw = m.group(1)
    # Tilda иногда вставляет одиночные кавычки или trailing-запятые — пробуем
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        # Лёгкая sanitize: trailing запятые в JSON
        sanitized = re.sub(r",\s*([}\]])", r"\1", raw)
        try:
            return json.loads(sanitized)
        except json.JSONDecodeError:
            return None


def _meta_content(soup: BeautifulSoup, key: str, *, attr: str = "name") -> str | None:
    el = soup.find("meta", attrs={attr: key})
    return el.get("content") if el and el.get("content") else None


def _itemprop(soup: BeautifulSoup, prop: str) -> str | None:
    el = soup.find(attrs={"itemprop": prop})
    if not el:
        return None
    return (el.get("content") or el.get_text(strip=True)) or None


def _split_artist_album(title: str) -> tuple[str | None, str]:
    """«Антоха МС – Родня» → ("Антоха МС", "Родня"). Если разделителя нет — артист None."""
    parts = _TITLE_SPLIT_RE.split(title, maxsplit=1)
    if len(parts) == 2:
        return parts[0].strip(), parts[1].strip()
    return None, title.strip()


def _extract_uid_from_url(url: str) -> str:
    """Из «/catalog/tproduct/769281620-646599740242-slug» → «646599740242»."""
    m = re.search(r"/tproduct/(\d+)-(\d+)", url)
    if m:
        return m.group(2)
    return url.rstrip("/").rsplit("/", 1)[-1]


def _extract_barcode_from_url(url: str) -> str | None:
    """
    Fallback для barcode когда microdata пустая.
    Tilda URL формата /tproduct/{rootpartid}-{barcode}-{slug} — второе число
    часто EAN-12/13. Возвращаем только если длина 8-14 (фильтр через
    normalize_barcode выше).
    """
    m = re.search(r"/tproduct/\d+-(\d{8,14})-", url)
    return m.group(1) if m else None
