"""
Парсер Vinyl.ru — большой РФ-магазин винила и **смежных форматов**:
LP, 2LP/3LP/4LP, CD, 2CD, Box Set, LP+CD, EP, 7", Maxi Single, Подарочные наборы.
Каталог ~64 500 товаров (по состоянию на 2026-05-19), не только vinyl.

Особенности:
- Bitrix CMS, sitemap-index `/sitemap.xml` → `sitemap_part_detail.xml` со всеми
  товарами (URL `/catalog/item/{slug}-{ID}/`).
- Title очень структурированный: «Виниловая пластинка {Artist} - альбом {Album},
  цена {Price} ₽. , лейбл {Label}, формат {Format}». Префикс «Виниловая пластинка»
  для ВСЕХ товаров (даже CD/cassette) — это маркетинговый шаблон Bitrix, реальный
  формат в поле «формат».
- **Нет barcode/EAN/Discogs-ссылок**, но есть «Артикул производителя: {Label} –
  {Catno}» → парсим catno (шаг 3 catalog в matcher). Если catno не дал матча —
  fallback на artist+title Discogs fetch (шаг 5b в listing_matcher).
- Цена и наличие — ТОЛЬКО из главного блока `div.card-controls`: у in-stock там
  кнопка «купить за {N} ₽» (`.js_add2basket.buy-btn`), у out-of-stock блок пустой,
  а в `.seller-info` — «Товар закончился». ВАЖНО: на странице есть карусели
  «Другие пластинки» (`.album_footer` со своими `.price_current` + `.js_add2basket`)
  — это ЧУЖИЕ товары; парсить цену/наличие по всему html нельзя (брали рандом).
  title/og-цена устаревшая (видели «1 ₽» / «3 500» при реальных ценах) — не юзаем.
- Год выпуска: «Год выпуска пластинки: {YYYY}» в тексте товарной страницы.
- Обложка: og:image (CDN vinyl.ru/upload/resizeImg/...).
"""
from __future__ import annotations

import logging
import re
from decimal import Decimal

from bs4 import BeautifulSoup

from app.services.scrapers.base import BaseStoreParser, ListingDTO, ParserError
from app.services.scrapers.extractors import (
    parse_price,
    parse_year,
    infer_format,
    infer_vinyl_color,
)
from app.services.scrapers.registry import register_parser

logger = logging.getLogger(__name__)


# URL: /catalog/item/{slug}-{ID}/  где ID формата «00-00000372»
_URL_ID_RE = re.compile(r"/catalog/item/[^/]*?-(\d{2}-\d{8})/?$")

# Title regex: «Виниловая пластинка {Artist} - альбом {Album}, цена {N} ₽. , лейбл {Label}, формат {Format}»
# Берём через жадные/нежадные группы — между разделителями « - альбом », «, цена », «, лейбл », «, формат ».
_TITLE_RE = re.compile(
    r"Виниловая\s+пластинка\s+(?P<artist>.+?)\s*[-–—]\s*альбом\s+"
    r"(?P<album>.+?)"
    r"(?=\s*,\s*цена\s|\s*[.,]\s*[,]?\s*лейбл\s|\s*,\s*формат\s|\s*$)"
    r"(?:\s*,\s*цена\s+(?P<price>[\d\s ]+)\s*[₽])?"
    r"(?:[\s.,]+лейбл\s+(?P<label>.+?)(?=\s*,\s*формат\s|\s*$))?"
    r"(?:\s*,\s*формат\s+(?P<format>\S+))?",
    re.IGNORECASE,
)

_PREORDER_KW_RE = re.compile(r"предзаказ|pre[\s\-]?order", re.I)

# Год выпуска: «Год выпуска пластинки: 2014»
_YEAR_RELEASE_RE = re.compile(r"Год\s+выпуска\s+пластинки\s*:?\s*(\d{4})", re.I)

# Цена/наличие берём ТОЛЬКО из главного блока товара `div.card-controls`.
# Там у in-stock лежит кнопка «купить за {N} ₽» (`.js_add2basket.buy-btn`),
# у out-of-stock блок пустой, а в `.seller-info` — «Товар закончился».
# Карусели «Другие пластинки» (`.album_footer` с собственными `.price_current`
# и `.js_add2basket`) — ЧУЖИЕ товары, их не трогаем: раньше regex по всему html
# хватал первый price_current/js_add2basket из карусели и проставлял рандомную
# цену + ложный in_stock. BeautifulSoup декодит `&#8381;` → `₽`, поэтому
# работаем по тексту узла, а не по сырому html.
_BUY_PRICE_RE = re.compile(r"за\s+([\d\s  ]+)\s*[₽]", re.I)
_SOLD_OUT_RE = re.compile(r"закончил|нет\s+в\s+налич|снят\s+с\s+прода", re.I)

# «Артикул производителя: {Лейбл} – {Catno} (alt)» в карточке товара.
# Формат vinyl.ru: лейбл, en-dash «\u2013» в пробелах, затем catno (внутри catno —
# обычный дефис «-»). Иногда хвост с альтернативным catno в скобках. Берём catno
# без лейбла и без скобок, чтобы normalize_catalog в matcher'е совпал с Discogs.
_CATALOG_RE = re.compile(r"Артикул\s+производителя\s*:\s*([^<\n]+)", re.I)


@register_parser("vinyl_ru")
class VinylRuParser(BaseStoreParser):
    base_url = "https://vinyl.ru"
    rate_limit_per_sec = 0.5  # 1 req per 2s — Bitrix-сайт средней нагрузки
    rate_burst = 2
    requires_js = False
    # У vinyl.ru sitemap-индекс ссылается на sitemap_part_detail.xml — он содержит
    # все товары /catalog/item/. iter_sitemap_urls автоматически развернёт индекс.
    sitemap_paths = ["/sitemap.xml"]
    listing_url_pattern = r"/catalog/item/.+-\d{2}-\d{8}/?$"

    @property
    def slug(self) -> str:
        return "vinyl_ru"

    async def parse_listing(self, url: str) -> ListingDTO:
        html = await self.http.get_text(url)
        soup = BeautifulSoup(html, "lxml")

        external_id = _extract_id_from_url(url)
        if not external_id:
            raise ParserError(f"no external_id in URL {url}")

        # === Title parse ===
        title_tag = soup.title.get_text(strip=True) if soup.title else ""
        og_title = _meta_content(soup, "og:title", attr="property") or ""

        m = _TITLE_RE.search(title_tag)
        artist = album = label = format_from_title = None
        if m:
            artist = m.group("artist").strip()
            album = m.group("album").strip()
            label = (m.group("label") or "").strip() or None
            format_from_title = (m.group("format") or "").strip() or None

        # Fallback на og:title если main regex не сработал
        if not album and og_title:
            if " - " in og_title:
                artist, album = og_title.split(" - ", 1)
            else:
                album = og_title
        if not album:
            raise ParserError(f"no title at {url}")

        # === Price + наличие (главный блок div.card-controls) ===
        # Цена и наличие — ТОЛЬКО из кнопки покупки основного товара, а не из
        # title/og (стале: видели 3 500 в мете при реальных 6 500) и не из
        # каруселей .album_footer (чужие товары). У in-stock в .card-controls
        # есть «купить за {N} ₽», у out-of-stock блок пустой.
        controls = soup.select_one(".card-controls")
        seller_node = soup.select_one(".seller-info")
        seller_text = seller_node.get_text(" ", strip=True) if seller_node else ""
        buy_text = controls.get_text(" ", strip=True) if controls else ""
        has_buy_btn = bool(controls and controls.select_one(".js_add2basket, .buy-btn"))

        price = None
        bm = _BUY_PRICE_RE.search(buy_text)
        if bm:
            price = parse_price(bm.group(1))

        # === Year ===
        # Берём первый «Год выпуска пластинки» — на странице может быть и «Год релиза
        # альбома» (год оригинального релиза мастера), но нам нужен год пресса.
        year = None
        ym = _YEAR_RELEASE_RE.search(html)
        if ym:
            try:
                year = int(ym.group(1))
            except ValueError:
                year = None
        if year is None:
            year = parse_year(title_tag)

        # === Format ===
        # Приоритет: явное поле «формат X» из title, нормализованное через
        # infer_format (чтобы «Box»→«Box Set», «2lp»→«2xLP», и т.п. — для
        # консистентности с другими магазинами). Если infer_format ничего не
        # узнал в format_from_title — оставляем raw. Fallback на infer_format
        # по всему HTML, дефолт — «LP» для vinyl-магазина.
        full_text = f"{title_tag}\n{format_from_title or ''}\n{html[:5000]}"
        format_raw = (
            (infer_format(format_from_title) if format_from_title else None)
            or format_from_title
            or infer_format(full_text)
            or "LP"
        )

        # === Vinyl color ===
        vinyl_color = infer_vinyl_color(title_tag) or infer_vinyl_color(html[:5000])

        # === Status ===
        if _PREORDER_KW_RE.search(title_tag) or _PREORDER_KW_RE.search(buy_text):
            status = "preorder"
        elif has_buy_btn:
            status = "in_stock"
        elif _SOLD_OUT_RE.search(seller_text):
            status = "out_of_stock"
        elif price is None:
            status = "on_request"
        else:
            status = "out_of_stock"

        # === Cover ===
        cover = _meta_content(soup, "og:image", attr="property")

        # === Catalog number ===
        catalog = _extract_catalog(html)

        return ListingDTO(
            external_id=external_id,
            url=url,
            title_raw=album,
            artist_raw=artist,
            year_raw=year,
            format_raw=format_raw,
            vinyl_color_raw=vinyl_color,
            # Магазин нового товара — состояние всегда запечатанный нов.
            condition="Новый (Mint)",
            price_rub=price,
            price_currency="RUB",
            status=status,
            # Barcode/Discogs-ссылок нет, но есть «Артикул производителя» → catalog.
            # Matcher пробует catalog (шаг 3), иначе artist+title Discogs fetch.
            barcode=None,
            catalog_number=catalog,
            discogs_release_url=None,
            image_url=cover,
            raw_payload={
                "vinyl_ru_external_id": external_id,
                "vinyl_ru_label": label,
                "catalog_number": catalog,
            },
        )


# ---- helpers ----------------------------------------------------------- #


def _extract_id_from_url(url: str) -> str | None:
    m = _URL_ID_RE.search(url)
    return m.group(1) if m else None


def _extract_catalog(html: str) -> str | None:
    """«Mute \u2013 STUMM64» → «STUMM64»; «Capitol \u2013 32 439-2 (1C ...)» → «32 439-2»."""
    m = _CATALOG_RE.search(html)
    if not m:
        return None
    raw = m.group(1).strip()
    # Отрезаем лейбл слева (до en-dash в пробелах).
    sep = " \u2013 "
    if sep in raw:
        raw = raw.split(sep, 1)[1]
    # Отрезаем альтернативный catno в скобках.
    raw = re.sub(r"\s*\(.*$", "", raw).strip()
    return raw or None


def _meta_content(soup: BeautifulSoup, key: str, *, attr: str = "name") -> str | None:
    el = soup.find("meta", attrs={attr: key})
    return el.get("content") if el and el.get("content") else None
