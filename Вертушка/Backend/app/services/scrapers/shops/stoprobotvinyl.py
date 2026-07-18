"""
Парсер Stoprobot Vinyl — МСК-магазин на Bitrix CMS, **только винил** (LP/2LP/EP/7"/Box Set).
Каталог ~8 900 товаров (по состоянию на 2026-05-19).

Особенности:
- Sitemap-индекс существует, но НЕ обновлялся с 2024-10-09 — пропускает свежие
  поступления. Поэтому используем не sitemap, а **собственный AJAX-endpoint**
  магазина: `POST /ajax/catalog.php` с `action=get-products&iblock=vinyl&PAGEN_1=N`.
  GET тоже работает. Endpoint возвращает JSON со всеми товарами в порядке Bitrix.
  Discovery: пагинируем PAGEN_1=1..page_count, yield-им `url` из каждого `products[]`.
- Per-listing HTML рендерится сервером целиком (без JS-гидрации) — достаточно
  `bs4.lxml` + `dl.product-characteristics`-блок (dt/dd термины/значения).
- Title: `[{ID}] {Artist} - {Album} ({Format})` — fallback если dl-блок неполный.
- Каталожный номер на странице (`2000000{ID}`) — внутренний Bitrix SKU, НЕ реальный
  EAN/catalog. НЕ пишем в `catalog_number` (создаст ложные матчи). Матчер пойдёт
  через `_try_discogs_fetch_by_text` (artist+title).
- In-stock detect: `<div class="product-stock">В наличии</div>` →
  `class="product-stock product-stock--no...">Нет в наличии</div>` → out_of_stock.
  Предзаказ — текст «Предзаказ» в этом же блоке.
- Обложка: `data-image` атрибут `<div class="ya-share2" ...>` (CDN
  stoprobotvinyl.ru:443/upload/iblock/...).
- Жанр/стиль/страна/лейбл в dl-блоке — складываем в raw_payload для аналитики.
"""
from __future__ import annotations

import json
import logging
import re
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


# URL: /vinyl/product/{ID}_{slug}/  где ID — Bitrix product id (короткий int)
_URL_ID_RE = re.compile(r"/vinyl/product/(\d+)_")

# Title: «[105086] L'Imperatrice - Tako Tsubo (2LP)»
_TITLE_RE = re.compile(
    r"\[\d+\]\s+(?P<artist>.+?)\s+[-–—]\s+(?P<album>.+?)\s+\((?P<format>[^)]+)\)\s*$"
)

# AJAX-endpoint магазина
_AJAX_URL = "https://stoprobotvinyl.ru/ajax/catalog.php"
_AJAX_QUERY = "action=get-products&iblock=vinyl&PAGEN_1={page}"

# Маркер предзаказа в product-stock блоке
_PREORDER_RE = re.compile(r"предзаказ|pre[\s\-]?order", re.I)


@register_parser("stoprobotvinyl")
class StoprobotVinylParser(BaseStoreParser):
    base_url = "https://stoprobotvinyl.ru"
    rate_limit_per_sec = 0.5  # 1 req per 2s — Bitrix-сайт средней нагрузки
    rate_burst = 2
    requires_js = False
    # Sitemap здесь fallback, но т.к. он не обновлялся с 2024-10 — используем
    # discover_urls() override через AJAX-endpoint магазина (см. ниже).
    sitemap_paths: list[str] = []
    listing_url_pattern = r"/vinyl/product/\d+_"

    @property
    def slug(self) -> str:
        return "stoprobotvinyl"

    # ---- Discovery через AJAX-endpoint ---------------------------------- #

    async def discover_urls(self) -> AsyncIterator[str]:
        """Пагинируем /ajax/catalog.php → 93+ страницы × 96 товаров.

        AJAX отвечает JSON: `{products:[{url,...}], page_count, page_current}`.
        respect_robots=False — robots.txt блокирует `/*PAGEN_1=` (это правило
        предназначено для SEO-индексации обычных страниц, не для backend AJAX).
        """
        page = 1
        max_page: int | None = None
        seen: set[str] = set()
        while True:
            url = f"{_AJAX_URL}?{_AJAX_QUERY.format(page=page)}"
            try:
                # respect_robots=False: robots.txt запрещает PAGEN_1= для всех
                # путей (анти-SEO-дублирование), но это backend-API, не страница.
                text = await self.http.get_text(url, respect_robots=False)
            except Exception:
                logger.debug("[%s] AJAX page %d failed", self.slug, page, exc_info=True)
                break

            try:
                data = json.loads(text)
            except json.JSONDecodeError:
                logger.warning("[%s] non-JSON response on page %d", self.slug, page)
                break

            products = data.get("products") or []
            if not products:
                break

            if max_page is None:
                max_page = int(data.get("page_count") or 1)
                logger.info("[%s] AJAX discover: %d страниц × ~%d товаров",
                            self.slug, max_page, len(products))

            for p in products:
                u = p.get("url")
                if not u:
                    continue
                if not u.startswith("http"):
                    u = self.base_url.rstrip("/") + u
                if u not in seen:
                    seen.add(u)
                    yield u

            page += 1
            if max_page and page > max_page:
                break

    # ---- Parsing per-listing -------------------------------------------- #

    async def parse_listing(self, url: str) -> ListingDTO:
        html = await self.http.get_text(url)
        soup = BeautifulSoup(html, "lxml")

        external_id = _extract_id_from_url(url)
        if not external_id:
            raise ParserError(f"no external_id in URL {url}")

        # === Title parse ===
        title_tag = soup.title.get_text(strip=True) if soup.title else ""
        m = _TITLE_RE.search(title_tag)
        artist_from_title = album_from_title = format_from_title = None
        if m:
            artist_from_title = m.group("artist").strip()
            album_from_title = m.group("album").strip()
            format_from_title = m.group("format").strip()

        # === Характеристики (dl.product-characteristics) ===
        chars = _extract_characteristics(soup)
        artist = chars.get("Исполнитель") or artist_from_title
        album = chars.get("Альбом") or album_from_title
        if not album:
            raise ParserError(f"no album at {url}")

        # === Price ===
        # Приоритет: HTML class="product-price__item" > характеристики «Цена» > None.
        price = None
        price_node = soup.find("div", class_="product-price__item")
        if price_node:
            price = parse_price(price_node.get_text(strip=True))
        if price is None and chars.get("Цена"):
            price = parse_price(chars["Цена"])

        # === Year ===
        # «Год релиза» = год пресса (для матчинга важнее), fallback «Год выхода» = оригинал.
        year = None
        for key in ("Год релиза", "Год выхода"):
            if chars.get(key):
                try:
                    year = int(chars[key].strip())
                    break
                except ValueError:
                    continue
        if year is None:
            year = parse_year(title_tag)

        # === Format ===
        # Приоритет: явное «Формат» из характеристик → infer_format нормализует
        # («2LP»→«2xLP», «Box»→«Box Set»). Fallback на парсинг из title в скобках.
        # Дефолт «LP» — магазин позиционируется как vinyl-only.
        format_src = chars.get("Формат") or format_from_title or ""
        format_raw = (
            (infer_format(format_src) if format_src else None)
            or format_src
            or infer_format(title_tag)
            or "LP"
        )

        # === Vinyl color ===
        # Поле «Цвет» в характеристиках — самое надёжное (например «Purple translucent»).
        # Чёрный НЕ обнуляем: он нужен матчингу офферов, чтобы конфликт семьи
        # цвета (чёрный листинг ↔ цветная запись) понижал пресс до 'album'
        # (см. offers.pressing_tier). Скрытие бейджа чёрного — на отдаче (_to_response).
        color_raw = chars.get("Цвет")
        vinyl_color = color_raw or infer_vinyl_color(title_tag)

        # === Status ===
        stock_node = soup.find("div", class_="product-stock")
        stock_text = stock_node.get_text(strip=True) if stock_node else ""
        if _PREORDER_RE.search(stock_text):
            status = "preorder"
        elif stock_node and "product-stock--no" in (stock_node.get("class") or []):
            status = "out_of_stock"
        elif stock_text and "наличии" in stock_text.lower() and "нет" not in stock_text.lower():
            status = "in_stock"
        elif price is None:
            status = "on_request"
        else:
            status = "out_of_stock"

        # === Condition ===
        condition_raw = chars.get("Состояние")
        # «New» → новинка из коробки; в нашей системе condition нужен только для used.
        # Если New — оставляем None (=новый). Если что-то другое (M/NM/VG+) — пишем.
        condition = None if (condition_raw or "").lower() in ("", "new") else condition_raw

        # === Cover ===
        # og:image на этом сайте нет, но есть data-image у блока ya-share2.
        cover = None
        share_node = soup.find("div", class_="ya-share2")
        if share_node and share_node.get("data-image"):
            cover = share_node["data-image"]

        # === Label (для raw_payload) ===
        label = chars.get("Лейбл")
        country = chars.get("Страна")

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
            # Stoprobot не публикует реального barcode/EAN/Discogs-ссылки.
            # «Каталожный номер» на сайте = `2000000{ID}` = внутренний SKU Bitrix,
            # НЕ пишем — создал бы ложные матчи через normalize_catalog.
            barcode=None,
            catalog_number=None,
            discogs_release_url=None,
            image_url=cover,
            raw_payload={
                "stoprobot_external_id": external_id,
                "stoprobot_label": label,
                "stoprobot_country": country,
            },
        )


# ---- helpers ----------------------------------------------------------- #


def _extract_id_from_url(url: str) -> str | None:
    m = _URL_ID_RE.search(url)
    return m.group(1) if m else None


def _extract_characteristics(soup: BeautifulSoup) -> dict[str, str]:
    """Парсим `<dl class="product-characteristics"><dt>…</dt><dd>…</dd>…</dl>`.

    Возвращает dict {term: value}. Если внутри <dd> анкор-ссылка
    (`<a>microqlima</a>`) — берём её текст (это лейбл/исполнитель в Bitrix как
    кликабельные фильтры). Пропускаем пустые значения.
    """
    out: dict[str, str] = {}
    dl = soup.find("dl", class_="product-characteristics")
    if not dl:
        return out
    terms = dl.find_all("dt", class_="product-characteristics__term")
    descs = dl.find_all("dd", class_="product-characteristics__desc")
    for dt, dd in zip(terms, descs):
        key = dt.get_text(strip=True)
        # Если внутри dd есть <a> — берём её текст (анкор это лейбл/исполнитель)
        a = dd.find("a")
        value = a.get_text(strip=True) if a else dd.get_text(strip=True)
        # Срезаем мусорные whitespace-окружения (Bitrix щедр на табуляции)
        value = re.sub(r"\s+", " ", value).strip()
        if value:
            out[key] = value
    return out
