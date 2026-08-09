"""
Парсер Plastinka.com — крупный российский магазин винила (СПб, доставка по РФ).

WS1.1: обход переведён со страниц товара на карточки листинга `/lp?page=N`
(200 товаров на страницу). Было 7 653 запроса (≈4.2 часа), стало **39**
(≈80 секунд). Карточка `.products-grid-item` отдаёт всё:

    data-id="377288"                     → external_id
    data-artist-name="System Of A Down"  → артист (без разбора title!)
    itemprop=name «Toxicity '01»         → альбом + год оригинала
    descr «Европа / American | Инди | Переиздание'18 | SS/SS»
                                         → страна, лейбл, жанр, год пресса, состояние
    itemprop=price / availability        → цена и наличие

Побочно чинится баг разбора артиста: title-регексп резал «A-ha - Analogue»
по дефису внутри имени и давал artist='A', album='ha - Analogue'.
`data-artist-name` этой проблемы лишён.

Год: если в описании есть «Переиздание'NN» — берём его (это год пресса, как
и раньше из title), иначе «'NN» из названия (оригинал).

Обложка в карточке — `.webp` того же пути, что и `.jpg` из og:image.

`parse_listing()` (разбор страницы товара) сохранён — его использует
`refresh_urls()` для точечной перепроверки и детекта 404 → removed.

Особенности:
- Собственная CMS на PHP, sitemap.xml в корне: 12 898 URL, из них
  7 653 — `/lp/item/` (CD в sitemap нет).
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
from datetime import datetime
from decimal import Decimal
from typing import AsyncIterator

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

# Хвост «'01» / «'25» в названии карточки и в «Переиздание'18».
_APOSTROPHE_YEAR_RE = re.compile(r"\s*'(\d{2})\s*$")
_REISSUE_RE = re.compile(r"переиздан", re.I)
# Грейдинг в последней строке описания: «SS/SS», «M/M», «EX+/EX», «VG+/VG».
_CONDITION_RE = re.compile(r"[A-Z]{1,2}\+?-?(?:/[A-Z]{1,2}\+?-?)?")


@register_parser("plastinka_com")
class PlastinkaComParser(BaseStoreParser):
    base_url = "https://plastinka.com"
    rate_limit_per_sec = 0.5  # 1 req per 2s — вежливо, страница тяжёлая (~317 KB)
    rate_burst = 2
    requires_js = False
    sitemap_paths = ["/sitemap.xml"]
    # Фильтр для discover_urls: берём только LP-страницы, без /cd/, /acc/, категорий
    listing_url_pattern = r"/lp/item/\d+"

    # Листинг LP: 200 товаров на страницу, `?page=N`. Пустая страница = конец
    # (проверено: page 39 отдаёт 53 товара, page 40 — ноль, итого 7 653).
    catalog_path = "/lp"
    catalog_page_size = 200
    max_pages = 200

    @property
    def slug(self) -> str:  # читаемое имя из registry
        return "plastinka_com"

    # ---- Обход по карточкам листинга ------------------------------------- #

    async def crawl_full(self, limit: int | None = None) -> AsyncIterator[ListingDTO]:
        """Пагинируем `/lp?page=N` и разбираем карточки, без захода на товар.

        Rate-limit держит per-domain token bucket в http_client, поэтому
        дополнительный sleep как в `BaseStoreParser.crawl_full` не нужен.
        """
        seen: set[str] = set()
        emitted = 0

        for page in range(1, self.max_pages + 1):
            url = f"{self.base_url}{self.catalog_path}"
            if page > 1:
                url = f"{url}?page={page}"
            try:
                html = await self.http.get_text(url)
            except Exception:
                logger.debug("[%s] listing page %d failed", self.slug, page, exc_info=True)
                return

            cards = _extract_cards(html)
            if not cards:
                logger.info("[%s] каталог кончился на page %d (%d товаров)",
                            self.slug, page, emitted)
                return

            fresh = 0
            for card in cards:
                try:
                    dto = _parse_card(card, self.base_url)
                except Exception:
                    logger.debug("[%s] card parse failed on page %d",
                                 self.slug, page, exc_info=True)
                    continue
                if dto is None or dto.external_id in seen:
                    continue
                seen.add(dto.external_id)
                fresh += 1
                yield dto
                emitted += 1
                if limit is not None and emitted >= limit:
                    return

            if fresh == 0:
                return
            if len(cards) < self.catalog_page_size:
                logger.info("[%s] последняя страница %d, всего %d товаров",
                            self.slug, page, emitted)
                return

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


def _extract_cards(html: str) -> list:
    """Карточки товара со страницы листинга (`.products-grid-item`)."""
    soup = BeautifulSoup(html, "lxml")
    return soup.find_all("div", class_="products-grid-item")


def _year_from_apostrophe(value: str | None) -> int | None:
    """«'01» → 2001, «'67» → 1967. Двузначный год: > текущего → прошлый век."""
    if not value:
        return None
    m = _APOSTROPHE_YEAR_RE.search(value)
    if not m:
        return None
    nn = int(m.group(1))
    century_cut = (datetime.utcnow().year % 100)
    return 2000 + nn if nn <= century_cut else 1900 + nn


def _parse_card(card, base_url: str) -> ListingDTO | None:
    """Карточка листинга → ListingDTO. None — карточка без id/ссылки."""
    external_id = (card.get("data-id") or "").strip()
    link = card.find("a", href=True)
    if not external_id or not link:
        return None

    name_el = card.find(attrs={"itemprop": "name"})
    raw_name = name_el.get_text(" ", strip=True) if name_el else ""
    if not raw_name:
        return None

    # «Toxicity '01» → альбом «Toxicity» + год оригинала 2001.
    year_original = _year_from_apostrophe(raw_name)
    album = _APOSTROPHE_YEAR_RE.sub("", raw_name).strip(" ,")

    # data-artist-name надёжнее разбора title: он не ломается на «A-ha».
    artist = (card.get("data-artist-name") or "").strip() or None

    descr_el = card.find(attrs={"itemprop": "description"})
    descr_lines = (
        [ln.strip() for ln in descr_el.get_text("\n", strip=True).split("\n") if ln.strip()]
        if descr_el else []
    )
    descr_text = " ".join(descr_lines)
    # Последняя строка описания — грейдинг («SS/SS», «M/M», «EX+/EX»).
    condition = None
    if descr_lines and _CONDITION_RE.fullmatch(descr_lines[-1]):
        condition = descr_lines[-1]

    # Год пресса: «Переиздание'18» → 2018; иначе год оригинала из названия.
    reissue = next((ln for ln in descr_lines if _REISSUE_RE.search(ln)), None)
    year = _year_from_apostrophe(reissue) or year_original

    price_el = card.find(attrs={"itemprop": "price"})
    price = parse_price(
        (price_el.get("content") if price_el else None)
        or (price_el.get_text(strip=True) if price_el else None)
    )

    avail_el = card.find(attrs={"itemprop": "availability"})
    avail = (avail_el.get("href") or avail_el.get("content") or "") if avail_el else ""

    full_text = f"{raw_name}\n{descr_text}"
    if _PREORDER_KW_RE.search(full_text):
        status = "preorder"
    elif "OutOfStock" in avail or "SoldOut" in avail:
        status = "out_of_stock"
    elif "InStock" in avail and price is not None:
        status = "in_stock"
    elif price is None:
        status = "on_request"
    else:
        status = "in_stock"

    img = card.find("img")
    image = img.get("src") if img else None

    label = descr_lines[1] if len(descr_lines) > 1 else None
    return ListingDTO(
        external_id=external_id,
        url=base_url + link["href"].split("?")[0],
        title_raw=album,
        artist_raw=artist,
        year_raw=year,
        format_raw=infer_format(full_text) or "LP",
        vinyl_color_raw=infer_vinyl_color(full_text, exclude=[artist, album]),
        condition=condition,
        price_rub=price,
        price_currency="RUB",
        status=status,
        # Plastinka не публикует barcode/catalog/Discogs-ссылки
        barcode=None,
        catalog_number=None,
        discogs_release_url=None,
        image_url=image,
        raw_payload={
            "plastinka_external_id": external_id,
            "label": label,
        },
    )


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
