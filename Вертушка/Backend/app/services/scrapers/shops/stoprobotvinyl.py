"""
Парсер Stoprobot Vinyl — МСК-магазин на Bitrix CMS, **только винил** (LP/2LP/EP/7"/Box Set).
Каталог ~8 900 товаров (по состоянию на 2026-05-19).

WS1.5: обход переведён со страниц товара на сам AJAX-ответ. Было
94 запроса discovery + ~8 900 страниц товара (≈5 часов — в ночное окно не
влезало, и магазин с 08-08 не досчитывался ни разу), стало **94 запроса**
(≈3 минуты). В `products[]` уже лежит всё, кроме года:

    url «/vinyl/product/111254_architects_..._lp/» → external_id 111254
    name «Architects» / album «All Our Gods...»    → артист и альбом
    format ["2LP"] · price «7&nbsp;790 &#8381;»    → формат и цена
    in_stock «1»/«0»                               → наличие (это количество)
    images[0].src · label.name · style · direction

Чего в AJAX нет:
- **Год пресса** («Год выпуска пластинки» на странице). Потеря осознанная:
  альтернатива — пятичасовой обход, который сейчас не доходит до конца вообще.
  Матчинг у магазина и так идёт по artist+title (barcode/catno нет).
  Вернуть можно после WS3.4 (COALESCE-upsert) недельным глубоким проходом.
- **Цвет винила** — но он восстанавливается из хвоста URL-слага
  (`..._lp_blue_swirl_transparent`), а при отсутствии цветового токена
  пластинка чёрная. Сверено на 8 товарах со страницами: 8/8.

ВАЖНО: `external_id` берём из URL (111254), а НЕ из поля `id` AJAX-ответа
(56099) — это разные нумерации, и подмена задвоила бы весь каталог.

Особенности:
- Sitemap-индекс существует, но НЕ обновлялся с 2024-10-09 — пропускает свежие
  поступления. Поэтому используем не sitemap, а **собственный AJAX-endpoint**
  магазина: `POST /ajax/catalog.php` с `action=get-products&iblock=vinyl&PAGEN_1=N`.
  GET тоже работает. Endpoint возвращает JSON со всеми товарами в порядке Bitrix.
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

import html as html_lib
import json
import logging
import re
from decimal import Decimal
from typing import AsyncIterator

from bs4 import BeautifulSoup

from app.services.scrapers.base import (
    BaseStoreParser,
    ListingDTO,
    ParserError,
    PageErrorBudget,
)
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
    stock_from_listing = True  # in_stock приходит в AJAX-ответе
    listing_url_pattern = r"/vinyl/product/\d+_"

    @property
    def slug(self) -> str:
        return "stoprobotvinyl"

    # ---- Обход каталога прямо по AJAX-ответу ----------------------------- #

    async def crawl_full(self, limit: int | None = None) -> AsyncIterator[ListingDTO]:
        """Пагинируем AJAX и строим DTO из самих products[], без захода на товар."""
        seen: set[str] = set()
        emitted = 0
        async for product in self._iter_products():
            try:
                dto = self.parse_product(product)
            except Exception:
                logger.debug("[%s] parse_product failed for %s",
                             self.slug, product.get("url"), exc_info=True)
                continue
            if dto is None or dto.external_id in seen:
                continue
            seen.add(dto.external_id)
            yield dto
            emitted += 1
            if limit is not None and emitted >= limit:
                return
        logger.info("[%s] обход по AJAX: %d товаров", self.slug, emitted)

    async def _iter_products(self) -> AsyncIterator[dict]:
        """Постранично тянет AJAX-каталог. Yields product-dict'ы."""
        page = 1
        max_page: int | None = None
        budget = PageErrorBudget(self.slug)
        while True:
            url = f"{_AJAX_URL}?{_AJAX_QUERY.format(page=page)}"
            # respect_robots=False: robots.txt запрещает PAGEN_1= для всех
            # путей (анти-SEO-дублирование), но это backend-API, не страница.
            text = await self.fetch_page(
                url, budget,
                page_label=f"AJAX стр. {page} из {max_page or '?'}",
                respect_robots=False,
            )
            if text is None:
                # Пропуск ≠ конец каталога: теряем ~96 позиций, идём дальше.
                page += 1
                if max_page is not None and page > max_page:
                    break
                continue

            try:
                data = json.loads(text)
            except json.JSONDecodeError as e:
                raise ParserError(f"non-JSON ответ AJAX на странице {page}") from e

            products = data.get("products") or []
            if not products:
                budget.log_summary()
                return

            if max_page is None:
                max_page = int(data.get("page_count") or 1)
                logger.info("[%s] AJAX: %d страниц × ~%d товаров",
                            self.slug, max_page, len(products))

            for p in products:
                yield p

            page += 1
            if max_page and page > max_page:
                budget.log_summary()
                return

    def parse_product(self, product: dict) -> ListingDTO | None:
        """Элемент `products[]` из AJAX → ListingDTO. None = пропустить."""
        url_path = str(product.get("url") or "")
        external_id = _extract_id_from_url(url_path)
        if not external_id:
            return None

        album = str(product.get("album") or "").strip()
        artist = str(product.get("name") or "").strip() or None
        if not album:
            return None

        # price приходит html-escaped: «7&nbsp;790 &#8381;».
        price = parse_price(html_lib.unescape(str(product.get("price") or "")))

        # in_stock — это количество строкой («0» = нет).
        try:
            qty = int(str(product.get("in_stock") or "0").strip() or 0)
        except (TypeError, ValueError):
            qty = 0

        fmt_list = product.get("format") or []
        fmt_src = " ".join(str(f) for f in fmt_list) if isinstance(fmt_list, list) else str(fmt_list)

        # Хвост слага несёт цвет: «..._lp_blue_swirl_transparent». Нет токена
        # цвета — пластинка чёрная (сверено со страницами товара, 8/8).
        slug = url_path.rstrip("/").rsplit("/", 1)[-1].replace("_", " ")
        vinyl_color = infer_vinyl_color(slug, exclude=[artist, album]) or "black"

        full_text = f"{album} {fmt_src} {slug}"
        if _PREORDER_RE.search(full_text):
            status = "preorder"
        elif qty > 0:
            status = "in_stock"
        else:
            status = "out_of_stock"
        if price is None and status == "in_stock":
            status = "on_request"

        label = product.get("label") or {}
        label_name = label.get("name") if isinstance(label, dict) else str(label or "") or None

        images = product.get("images") or []
        image = None
        if isinstance(images, list) and images and isinstance(images[0], dict):
            src = images[0].get("src")
            image = f"{self.base_url}{src}" if src and src.startswith("/") else src

        return ListingDTO(
            external_id=external_id,
            url=f"{self.base_url}{url_path}" if url_path.startswith("/") else url_path,
            title_raw=album,
            artist_raw=artist,
            # Год есть только на странице товара, куда мы больше не ходим.
            year_raw=None,
            format_raw=infer_format(fmt_src) or fmt_src or "LP",
            vinyl_color_raw=vinyl_color,
            condition=None,  # магазин нового товара
            price_rub=price,
            price_currency="RUB",
            status=status,
            barcode=None,
            catalog_number=None,
            discogs_release_url=None,
            image_url=image,
            raw_payload={
                "stoprobot_external_id": external_id,
                "stoprobot_label": label_name,
                "stoprobot_style": product.get("style"),
                "stoprobot_direction": product.get("direction"),
            },
        )

    # ---- Discovery через AJAX-endpoint (для sitemap-совместимости) -------- #

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
        vinyl_color = color_raw or infer_vinyl_color(title_tag, exclude=[artist, album])

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
