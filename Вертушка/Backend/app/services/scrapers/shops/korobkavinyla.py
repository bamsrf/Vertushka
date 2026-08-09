"""
Парсер Korobka Vinyla (korobkavinyla.ru) — магазин на Tilda.

WS1.4: переведён с постраничного обхода на Tilda store-API (см.
`_tilda_store.TildaStoreParser`). Было ~5950 запросов на каталог (sitemap-store.xml
→ фетч страницы на каждый товар), стало **60** (страницами по 100). Данные при
этом не потеряны — API отдаёт всё, что раньше выцарапывалось из HTML:

    sku       → EAN-13 (заполнен у 100% товаров, из них 95% валидный 8-14-значный)
    descr     → «Label: Ninja Tune – ZEN195<br />Format: 2×Vinyl, LP, Album, 180g
                 <br />Country: UK<br />Released: 27 Mar 2013…» — год, формат,
                 цвет, лейбл, каталожный номер
    quantity  → наличие ("0" = закончился)
    gallery   → обложка (раньше брали og:image)
    uid       → external_id, тот же что в URL /tproduct/{root}-{uid}-{slug}

Что изменилось по данным:
- `discogs_release_url` больше не ищем. Раньше звали `find_discogs_release_url`
  по всему HTML страницы, но ссылок на Discogs у магазина нет ни в API, ни на
  самих страницах товара (проверено на выборке) — поле всегда было None.
- Убран fallback «barcode из URL»: он брал второе число из
  /tproduct/{root}-{uid}-{slug}, а это **uid товара, а не EAN** — при пустом sku
  подставлялся мусорный штрихкод. sku в API есть всегда, fallback не нужен.

Особенности данных:
- title формата «Artist – Album (Clear Vinyl)», разделитель — en/em-dash.
- descr приходит как HTML с <br /> — разворачиваем в текст перед разбором.
- Нон-медиа товары (пины, плакаты, мерч) пропускаем.
- Магазин нового товара — condition всегда «Новый (Mint)».
"""
from __future__ import annotations

import re

from bs4 import BeautifulSoup

from app.services.scrapers.base import ListingDTO
from app.services.scrapers.extractors import (
    parse_price,
    parse_year,
    infer_format,
    infer_vinyl_color,
    normalize_barcode,
    normalize_catalog,
)
from app.services.scrapers.registry import register_parser
from app.services.scrapers.shops._tilda_store import TildaStoreParser


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
class KorobkaVinylaParser(TildaStoreParser):
    base_url = "https://korobkavinyla.ru"
    rate_limit_per_sec = 0.5  # 1 req per 2s — вежливо к Tilda
    rate_burst = 2
    requires_js = False

    # Из t_store_init('771567999', {... storepart:'974505268935' ...}) на /catalog.
    store_recid = "771567999"
    store_partuid = "974505268935"

    def parse_product(self, product: dict) -> ListingDTO | None:
        title = str(product.get("title") or "").strip()
        if not title:
            return None

        # Пропускаем аксессуары (пины, значки, плакаты и т.д.) — не носители звука
        if _ACCESSORY_RE.search(title):
            return None

        url = str(product.get("url") or "")

        # descr приходит HTML'ом с <br /> — разворачиваем в текст.
        descr_html = str(product.get("descr") or "")
        descr_text = (
            BeautifulSoup(descr_html, "lxml").get_text(" ", strip=True)
            if descr_html else ""
        )
        # URL slug добавляем для format detection: slug часто содержит формат
        # («-cd», «-box-set», «-cassette»). Если у товара пустой descr — slug
        # спасёт infer_format. Дефис → пробел чтобы \b в regex сработали.
        url_slug = url.rsplit("/", 1)[-1].replace("-", " ")
        full_text = f"{title}\n{descr_text}\n{url_slug}"

        artist, album = _split_artist_album(title)

        # SKU из store-API = как правило EAN-13. Кладём в barcode если 8-14 цифр,
        # иначе в catalog. Это критично для match_listing: без barcode он не идёт
        # в on-demand Discogs fetch, и листинг остаётся unmatched.
        sku_raw = str(product.get("sku") or "").strip() or None
        barcode = normalize_barcode(sku_raw)
        catalog_number = None if barcode else normalize_catalog(sku_raw)

        price = parse_price(str(product.get("price") or ""))
        price_old = parse_price(str(product.get("priceold") or ""))

        # Статус: ключевой сигнал — `quantity`. Tilda пишет "N" когда товар в
        # наличии, и "0"/пусто когда закончился. Это надёжнее regex по ключевым
        # словам — у out-of-stock товаров на странице часто нет фраз типа
        # «нет в наличии», просто скрыта кнопка «купить».
        qty_raw = product.get("quantity")
        try:
            qty = int(str(qty_raw)) if qty_raw not in (None, "") else 0
        except (ValueError, TypeError):
            qty = 0

        if _PREORDER_KW_RE.search(full_text):
            status = "preorder"
        elif qty > 0:
            status = "in_stock"
        elif _OUT_OF_STOCK_KW_RE.search(full_text):
            status = "out_of_stock"
        else:
            status = "out_of_stock"

        if price is None and status == "in_stock":
            status = "on_request"

        uid = product.get("uid")
        external_id = str(uid) if uid is not None else _uid_from_url(url)

        raw_payload: dict = {"tilda_uid": uid}
        if price_old is not None:
            raw_payload["price_old_rub"] = str(price_old)

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
            # Ссылок на Discogs у магазина нет — ни в API, ни на страницах товара.
            discogs_release_url=None,
            image_url=self.first_gallery_image(product),
            raw_payload=raw_payload,
        )


# ---- helpers ----------------------------------------------------------- #


def _split_artist_album(title: str) -> tuple[str | None, str]:
    """«Антоха МС – Родня» → ("Антоха МС", "Родня"). Если разделителя нет — артист None."""
    parts = _TITLE_SPLIT_RE.split(title, maxsplit=1)
    if len(parts) == 2:
        return parts[0].strip(), parts[1].strip()
    return None, title.strip()


def _uid_from_url(url: str) -> str:
    """Из «/catalog/tproduct/771567999-611248127497-slug» → «611248127497»."""
    m = re.search(r"/tproduct/(\d+)-(\d+)", url)
    if m:
        return m.group(2)
    return url.rstrip("/").rsplit("/", 1)[-1]
