"""
Парсер Plastinka.com — крупный российский магазин винила (СПб, доставка по РФ).

Особенности:
- Собственная CMS на PHP, sitemap.xml в корне (~50k+ URL включая страницы CD/LP).
- URL товара: /lp/item/{external_id}-{slug} (LP) или /cd/item/{external_id}-{slug} (CD).
- Полное Schema.org microdata: itemprop="price"/"availability"/"name"/"brand".
- ВАЖНО: на странице **много** Product-blocks (рекомендации, похожие, корзина).
  Главный товар — первый <div itemtype="https://schema.org/Product"> на странице.
- Title формата `Пластинка {Artist} - {Album}, {Year}, {Condition}, арт. {ID}`.
- НЕТ barcode/EAN/каталога/Discogs-ссылок — на странице только Альбом/Размер
  диска/Страна/Тип. Matcher без on-demand-by-barcode не сработает; нужен
  artist+title search-fallback в listing_matcher._try_discogs_fetch.

Что НЕ парсим: CD (`/cd/item/...`) и аксессуары (`/acc/...`) — только LP.
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


# URL: /lp/item/{id}-{slug} — id это external_id магазина (375285)
_URL_ID_RE = re.compile(r"/lp/item/(\d+)(?:-[^/?#]+)?/?$")

# Title формат: «Пластинка Grover Washington Jr. - Best Is Yet To Come, 1982, EX+/EX+, арт. 375285»
# Captures: 1=artist, 2=album, 3=year (опц), 4=condition (опц)
_TITLE_RE = re.compile(
    r"^Пластинка\s+(?P<artist>.+?)\s*[-–—]\s*(?P<album>.+?)"
    r"(?:,\s*(?P<year>\d{4}))?"
    r"(?:,\s*(?P<condition>[A-Z][A-Z+/\-\s]+?))?"
    r",\s*арт\.?\s*\d+",
    re.IGNORECASE,
)

_PREORDER_KW_RE = re.compile(r"предзаказ|pre[\s\-]?order", re.I)


@register_parser("plastinka_com")
class PlastinkaComParser(BaseStoreParser):
    base_url = "https://plastinka.com"
    rate_limit_per_sec = 0.5  # 1 req per 2s — вежливо, страница тяжёлая (~317 KB)
    rate_burst = 2
    requires_js = False
    sitemap_paths = ["/sitemap.xml"]
    # Фильтр для discover_urls: берём только LP-страницы, без /cd/, /acc/, категорий
    listing_url_pattern = r"/lp/item/\d+"

    @property
    def slug(self) -> str:  # читаемое имя из registry
        return "plastinka_com"

    async def parse_listing(self, url: str) -> ListingDTO:
        html = await self.http.get_text(url)
        soup = BeautifulSoup(html, "lxml")

        external_id = _extract_id_from_url(url)
        if not external_id:
            raise ParserError(f"no external_id in URL {url}")

        # MAIN PRODUCT scope: первый <div itemtype="*Product*"> — это товар-герой.
        # У Plastinka.com внутри одной страницы много Product-блоков (рекомендации,
        # похожие, корзина), но главный всегда первый — рендерится сверху.
        main = _find_main_product(soup, external_id)
        if main is None:
            # Fallback на og:title если scope не нашёлся (редкий случай)
            main = soup

        # === Цена ===
        price_el = main.find(attrs={"itemprop": "price"})
        price_str = (price_el.get("content") if price_el else None) or (
            price_el.get_text(strip=True) if price_el else None
        )
        price = parse_price(price_str) if price_str else None

        # === Доступность через schema.org ===
        avail_el = main.find(attrs={"itemprop": "availability"})
        avail_url = (avail_el.get("href") or avail_el.get("content") or "") if avail_el else ""

        # === Артист/альбом из title (надёжнее чем парсить itemprop="name" в куче рекомендаций) ===
        og_title = _meta_content(soup, "og:title", attr="property")  # «Artist - Album»
        title_tag = soup.title.get_text(strip=True) if soup.title else ""
        artist, album, year_from_title, condition = _parse_title(title_tag)
        if not album:
            # Fallback на og:title (без префикса «Пластинка »)
            if og_title and " - " in og_title:
                artist, album = og_title.split(" - ", 1)
            elif og_title:
                album = og_title
            else:
                raise ParserError(f"no album title at {url}")

        # === Год ===
        year = year_from_title or parse_year(title_tag) or parse_year(html[:5000])

        # === Status ===
        if _PREORDER_KW_RE.search(title_tag):
            status = "preorder"
        elif "OutOfStock" in avail_url or "SoldOut" in avail_url:
            status = "out_of_stock"
        elif "InStock" in avail_url and price is not None:
            status = "in_stock"
        elif price is None:
            status = "on_request"
        else:
            # availability не размечена явно но цена есть — оптимистично
            status = "in_stock"

        # === Обложка ===
        cover = _meta_content(soup, "og:image", attr="property")

        # === Формат / цвет винила — из описания если есть ===
        descr_meta = _meta_content(soup, "og:description", attr="property") or ""
        full_text = f"{title_tag}\n{descr_meta}"
        format_raw = infer_format(full_text) or "LP"
        vinyl_color = infer_vinyl_color(full_text, exclude=[artist, album])

        return ListingDTO(
            external_id=external_id,
            url=url,
            title_raw=album,
            artist_raw=artist,
            year_raw=year,
            format_raw=format_raw,
            vinyl_color_raw=vinyl_color,
            condition=condition,
            price_rub=price,
            price_currency="RUB",
            status=status,
            # Plastinka не публикует barcode/catalog/Discogs-ссылки
            barcode=None,
            catalog_number=None,
            discogs_release_url=None,
            image_url=cover,
            raw_payload={
                "plastinka_external_id": external_id,
                "og_title": og_title,
            },
        )


# ---- helpers ----------------------------------------------------------- #


def _extract_id_from_url(url: str) -> str | None:
    m = _URL_ID_RE.search(url)
    return m.group(1) if m else None


def _find_main_product(soup: BeautifulSoup, external_id: str):
    """
    Главный товар-герой = первый <div itemtype="*Product*">.
    Plastinka.com обычно ставит его в начале body, до блоков «Похожие».
    """
    return soup.find(attrs={"itemtype": re.compile(r"schema\.org/Product$")})


def _meta_content(soup: BeautifulSoup, key: str, *, attr: str = "name") -> str | None:
    el = soup.find("meta", attrs={attr: key})
    return el.get("content") if el and el.get("content") else None


def _parse_title(title: str) -> tuple[str | None, str | None, int | None, str | None]:
    """
    «Пластинка Grover Washington Jr. - Best Is Yet To Come, 1982, EX+/EX+, арт. 375285»
    → ('Grover Washington Jr.', 'Best Is Yet To Come', 1982, 'EX+/EX+')

    Условие (EX+/EX+) — vinyl/sleeve grade по Goldmine. Опционально.
    """
    if not title:
        return None, None, None, None
    m = _TITLE_RE.search(title)
    if not m:
        return None, None, None, None
    year_str = m.group("year")
    year = int(year_str) if year_str else None
    cond = m.group("condition")
    cond = cond.strip() if cond else None
    # Иногда condition не grade а текст типа «Limited Edition» — фильтруем по
    # формату Goldmine (короткие 2-7 символов с заглавными)
    if cond and not re.match(r"^[A-Z][A-Z+/\-\s]{1,15}$", cond):
        cond = None
    return m.group("artist").strip(), m.group("album").strip(), year, cond
