"""
Парсер Skifmusic — крупный магазин муз. инструментов, винил — одна из категорий.
Каталог винила ~20 600 товаров (по состоянию на 2026-08-09).

Особенности — это «дешёвый» магазин по принципу found/stoprobotvinyl:
- Каталог берём НЕ из sitemap. `sitemaps/product*.xml` — это ВЕСЬ магазин
  (инструменты, пульты, струны), 30 000 URL в каждом файле из семи. Виниловую
  категорию оттуда не отфильтровать по URL — `/product/{id}-{slug}` одинаков
  для гитары и для пластинки. Поэтому идём пагинацией категории 617.
- На каждой странице категории лежит **JSON-LD `ItemList`** (schema.org) со
  ВСЕМИ нужными полями: `name`, `url`, `image`, `offers.price`,
  `offers.availability`, `offers.itemCondition`. Заход на страницу товара не
  нужен ни для цены, ни для наличия → 688 запросов на весь каталог вместо
  20 600. Поэтому оверрайдим `crawl_full`/`refresh_urls` (как TildaStoreParser).
- Пагинация: `/catalog/vinilovyie-plastinki-617/page{N}`, 30 товаров на страницу.
  Последняя страница (688) отдаёт неполный ItemList, дальше (page700) ItemList
  пропадает вовсе → это и есть условие остановки.
- `numberOfItems` в ItemList = размер всей категории (20617), а не страницы —
  используем как sanity-логу, не как счётчик.
- Name всегда с префиксом «Виниловая пластинка {Artist} – {Album} (…)».
  Разделитель — en-dash «–», реже дефис. Хвост в скобках — формат («LP») либо
  цвет («Blue Vinyl», «Purple Vinyl»). У сборников артиста может не быть
  вовсе («Виниловая пластинка Забытые Вальсы») → artist=None, матчер пойдёт
  по названию.
- `brand` в JSON-LD — всегда литерал «Виниловая пластинка» (категория, не
  лейбл). Бесполезен, не парсим.
- **Нет barcode/каталожного номера** ни в JSON-LD, ни в карточке листинга.
  Матчинг пойдёт через artist+title (шаг 5b в listing_matcher).
- `itemCondition` = New/Used — у магазина есть винтажный сток, `UsedCondition`
  прокидываем в `condition`, иначе None (новый).
"""
from __future__ import annotations

import json
import logging
import re
from decimal import Decimal
from typing import AsyncIterator

from app.services.scrapers.base import BaseStoreParser, ListingDTO, PageErrorBudget
from app.services.scrapers.extractors import (
    parse_price,
    infer_format,
    infer_vinyl_color,
)
from app.services.scrapers.registry import register_parser

logger = logging.getLogger(__name__)


_CATALOG_PATH = "/catalog/vinilovyie-plastinki-617"

# URL товара: /product/784099-led-zeppelin-i-lp → external_id «784099»
_URL_ID_RE = re.compile(r"/product/(\d+)-")

# JSON-LD блоки обёрнуты в CDATA-комментарии.
_LD_RE = re.compile(r'application/ld\+json[^>]*>(.*?)</script>', re.S)
_CDATA_RE = re.compile(r'/\*\s*<!\[CDATA\[\s*\*/|/\*\s*\]\]>\s*\*/')

# «Виниловая пластинка {Artist} – {Album}». Разделитель — en-dash (основной),
# em-dash или дефис в пробелах. Первое вхождение = граница артиста: в названиях
# вида «Led Zeppelin – Led Zeppelin – Remastered by Jimmy Page» второй дефис
# принадлежит альбому.
_NAME_PREFIX_RE = re.compile(r"^\s*Виниловая\s+пластинка\s+", re.I)
_ARTIST_ALBUM_RE = re.compile(r"^(?P<artist>.+?)\s+[–—-]\s+(?P<album>.+)$")

# Хвост в скобках: «(LP)», «(2LP)», «(Blue Vinyl)», «(vol.9)».
_TRAILING_PAREN_RE = re.compile(r"\s*\(([^()]*)\)\s*$")


@register_parser("skifmusic")
class SkifmusicParser(BaseStoreParser):
    base_url = "https://skifmusic.ru"
    rate_limit_per_sec = 0.5  # 1 req per 2s — крупный магазин, но мы и так дешёвые
    rate_burst = 2
    requires_js = False
    # Sitemap не используем осознанно (см. docstring) — каталог только пагинацией.
    sitemap_paths: list[str] = []
    listing_url_pattern = r"/product/\d+-"

    # Размер страницы фиксирован магазином.
    stock_from_listing = True  # availability приезжает с JSON-LD листинга

    catalog_page_size: int = 30
    # Потолок страниц — защита от бесконечного цикла, если пагинация начнёт
    # зацикливаться. 20617/30 ≈ 688, берём двойной запас.
    max_pages: int = 1400

    @property
    def slug(self) -> str:
        return "skifmusic"

    # ---- Обход каталога -------------------------------------------------- #

    def _page_url(self, page: int) -> str:
        base = self.base_url.rstrip("/") + _CATALOG_PATH
        if page > 1:
            base = f"{base}/page{page}"
        # sort=name — стабильный порядок. По умолчанию выдача идёт «по новизне»,
        # и за 25 минут обхода 688 страниц она разъезжается: товары попадают на
        # две страницы подряд, а часть проскакивает мимо окна. В ночь 08-10 из
        # 20 617 позиций так дошло только 13 927 при 20 621 «upserted».
        return f"{base}?sort=name"

    async def _iter_products(self) -> AsyncIterator[dict]:
        """Постранично тянет категорию винила. Yields item-dict'ы из JSON-LD.

        Останавливаемся, когда на странице нет ItemList или он пуст: у магазина
        за последней страницей (688) JSON-LD категории просто исчезает.
        """
        total_expected: int | None = None
        seen_ids: set[str] = set()
        emitted = 0
        budget = PageErrorBudget(self.slug)
        for page in range(1, self.max_pages + 1):
            url = self._page_url(page)
            html = await self.fetch_page(url, budget, page_label=f"стр. {page}")
            if html is None:
                # Пропуск страницы ≠ конец каталога: теряем ~30 позиций из 20k,
                # обход продолжается. Сквозной обрыв ловит сам бюджет.
                continue

            item_list = _extract_item_list(html)
            if item_list is None:
                budget.log_summary()
                _log_coverage(self.slug, page, emitted, total_expected)
                return

            if total_expected is None:
                total = item_list.get("numberOfItems")
                total_expected = int(total) if total else 0
                logger.info("[%s] категория винила: %s товаров, ~%s страниц",
                            self.slug, total,
                            (total_expected // self.catalog_page_size + 1) if total_expected else "?")

            products = [
                el["item"] for el in item_list.get("itemListElement") or []
                if isinstance(el, dict) and isinstance(el.get("item"), dict)
            ]
            if not products:
                return

            fresh = 0
            for p in products:
                # Дедуп по external_id: даже при sort=name страницы могут
                # перекрываться, если каталог пополнился во время обхода.
                ext_id = _extract_id_from_url(p.get("url") or "")
                if not ext_id or ext_id in seen_ids:
                    continue
                seen_ids.add(ext_id)
                fresh += 1
                yield p
                emitted += 1

            # Неполная страница = последняя.
            if len(products) < self.catalog_page_size:
                budget.log_summary()
                _log_coverage(self.slug, page, emitted, total_expected)
                return
            if fresh == 0:
                budget.log_summary()
                logger.warning("[%s] страница %d без новых товаров — стоп", self.slug, page)
                return

    async def _load_catalog_by_id(self) -> dict[str, dict]:
        """Весь каталог одним проходом → {external_id: item-dict}."""
        out: dict[str, dict] = {}
        async for p in self._iter_products():
            ext_id = _extract_id_from_url(p.get("url") or "")
            if ext_id:
                out[ext_id] = p
        return out

    # ---- Оркестрация (оверрайд базовых sitemap-методов) ------------------ #

    async def crawl_full(self, limit: int | None = None) -> AsyncIterator[ListingDTO]:
        """Вся категория через JSON-LD листингов. Без пер-URL фетча."""
        seen = 0
        async for p in self._iter_products():
            if limit is not None and seen >= limit:
                return
            try:
                dto = self.parse_product(p)
            except Exception:
                logger.debug("[%s] parse_product failed for %s",
                             self.slug, p.get("url"), exc_info=True)
                continue
            if dto is None:
                continue
            yield dto
            seen += 1

    async def refresh_urls(
        self, urls: list[str]
    ) -> AsyncIterator[tuple[str, ListingDTO | None]]:
        """Stock-refresh: один проход каталога, ответ всем url'ам из памяти.

        Нет в каталоге → None (товар снят). Наличие и так приезжает с листинга,
        поэтому для этого магазина `stock_refresh_active` избыточен — см.
        WS2.2 в docs/plans/MARKET_STORES_SCALING.md.
        """
        catalog = await self._load_catalog_by_id()
        for url in urls:
            ext_id = _extract_id_from_url(url)
            product = catalog.get(ext_id) if ext_id else None
            if product is None:
                yield url, None
                continue
            try:
                dto = self.parse_product(product)
            except Exception:
                logger.debug("[%s] refresh parse_product failed for %s",
                             self.slug, url, exc_info=True)
                continue
            if dto is None:
                continue
            yield url, dto

    async def parse_listing(self, url: str) -> ListingDTO:
        # Парсер работает каталогом (crawl_full и refresh_urls переопределены),
        # пер-URL разбор страницы товара не нужен: цена и наличие есть в листинге.
        raise NotImplementedError(
            f"{type(self).__name__} parses via category JSON-LD, not per-URL"
        )

    # ---- Разбор одного товара -------------------------------------------- #

    def parse_product(self, product: dict) -> ListingDTO | None:
        """JSON-LD Product из ItemList → ListingDTO. None = пропустить товар."""
        url = product.get("url") or ""
        external_id = _extract_id_from_url(url)
        if not external_id:
            return None

        name = (product.get("name") or "").strip()
        if not name:
            return None

        artist, album, paren_tail = _split_name(name)
        if not album:
            return None

        offers = product.get("offers") or {}

        # === Price ===
        price: Decimal | None = parse_price(offers.get("price"))

        # === Status ===
        # availability — единственный надёжный источник, HTML-карточку не трогаем.
        availability = (offers.get("availability") or "").rsplit("/", 1)[-1].lower()
        if availability == "instock":
            status = "in_stock"
        elif availability in ("outofstock", "soldout", "discontinued"):
            status = "out_of_stock"
        elif availability in ("preorder", "presale"):
            status = "preorder"
        elif price is None:
            status = "on_request"
        else:
            status = "in_stock"

        # === Condition ===
        # NewCondition → None (новый — дефолт нашей системы). UsedCondition
        # прокидываем: у магазина есть винтажный сток без грейдинга VG+/NM,
        # поэтому пишем обобщённое «Used».
        condition_raw = (offers.get("itemCondition") or "").rsplit("/", 1)[-1].lower()
        condition = "Used" if condition_raw == "usedcondition" else None

        # === Format ===
        # Хвост в скобках — это либо формат («LP», «2LP»), либо цвет
        # («Blue Vinyl»), либо мусор («vol.9»). infer_format вернёт None на
        # не-формате. Дефолт «LP» — категория чисто виниловая.
        format_raw = infer_format(paren_tail) or infer_format(name) or "LP"

        # === Vinyl color ===
        # exclude=artist/album — иначе «Deep Purple» или «Красный Свет» в
        # названии прочитается как цвет пресса (см. infer_vinyl_color).
        vinyl_color = infer_vinyl_color(name, exclude=[artist, album])

        return ListingDTO(
            external_id=external_id,
            url=url,
            title_raw=album,
            artist_raw=artist,
            # Год в листинге не публикуется — только на странице товара, куда мы
            # осознанно не ходим. Матчер обойдётся artist+title.
            year_raw=None,
            format_raw=format_raw,
            vinyl_color_raw=vinyl_color,
            condition=condition,
            price_rub=price,
            price_currency=offers.get("priceCurrency") or "RUB",
            status=status,
            # Ни barcode, ни каталожного номера магазин не публикует.
            barcode=None,
            catalog_number=None,
            discogs_release_url=None,
            image_url=product.get("image") or None,
            raw_payload={
                "skifmusic_external_id": external_id,
                "skifmusic_name_raw": name,
            },
        )


# ---- helpers ------------------------------------------------------------- #


def _log_coverage(slug: str, page: int, emitted: int, expected: int | None) -> None:
    """Итог обхода + предупреждение, если собрали заметно меньше заявленного.

    `numberOfItems` из ItemList — размер всей категории, так что расхождение
    сразу видно в логах, а не всплывает потом в БД.
    """
    if expected and emitted < expected * 0.9:
        logger.warning(
            "[%s] обход закончился на page %d: %d товаров из %d заявленных (%.0f%%)",
            slug, page, emitted, expected, 100.0 * emitted / expected,
        )
    else:
        logger.info("[%s] обход закончился на page %d: %d товаров", slug, page, emitted)


def _extract_id_from_url(url: str) -> str | None:
    m = _URL_ID_RE.search(url or "")
    return m.group(1) if m else None


def _extract_item_list(html: str) -> dict | None:
    """Достать JSON-LD блок `@type: ItemList` со страницы категории.

    На странице несколько ld+json (есть ещё BreadcrumbList), поэтому идём по
    всем и берём первый ItemList. Блоки обёрнуты в CDATA-комментарии.
    """
    for raw in _LD_RE.findall(html):
        payload = _CDATA_RE.sub("", raw).strip()
        if not payload:
            continue
        try:
            data = json.loads(payload)
        except json.JSONDecodeError:
            continue
        if isinstance(data, dict) and data.get("@type") == "ItemList":
            return data
    return None


def _split_name(name: str) -> tuple[str | None, str | None, str | None]:
    """«Виниловая пластинка Artist – Album (LP)» → (artist, album, «LP»).

    Возвращает (artist|None, album|None, paren_tail|None). Артиста может не
    быть («Виниловая пластинка Забытые Вальсы») — тогда всё уходит в album.
    Скобочный хвост срезаем из album и отдаём отдельно: он нужен для формата и
    цвета, но в названии релиза только мешает матчингу.
    """
    body = _NAME_PREFIX_RE.sub("", name).strip()
    if not body:
        return None, None, None

    paren_tail = None
    m_paren = _TRAILING_PAREN_RE.search(body)
    if m_paren:
        paren_tail = m_paren.group(1).strip() or None
        body = _TRAILING_PAREN_RE.sub("", body).strip()

    m = _ARTIST_ALBUM_RE.match(body)
    if not m:
        return None, body or None, paren_tail

    artist = m.group("artist").strip() or None
    album = m.group("album").strip() or None
    if not album:
        return None, artist, paren_tail
    return artist, album, paren_tail
