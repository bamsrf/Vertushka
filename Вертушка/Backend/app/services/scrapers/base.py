"""
Базовый интерфейс парсера магазина.

Каждый магазин = подкласс BaseStoreParser в `shops/<slug>.py`.
"""
from __future__ import annotations

import asyncio
import logging
import random
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import AsyncIterator

from app.services.scrapers.http_client import ParserError_404, ScraperHttpClient
from app.services.scrapers.browser import BrowserPool

logger = logging.getLogger(__name__)


# ---- DTO ---------------------------------------------------------------- #

@dataclass
class ListingDTO:
    """Сырой листинг с сайта магазина — то, что парсер вернул."""
    external_id: str
    url: str
    title_raw: str
    artist_raw: str | None = None
    year_raw: int | None = None
    format_raw: str | None = None
    vinyl_color_raw: str | None = None
    condition: str | None = None
    price_rub: Decimal | None = None
    price_currency: str = "RUB"
    status: str = "in_stock"
    barcode: str | None = None
    catalog_number: str | None = None
    discogs_release_url: str | None = None
    image_url: str | None = None
    raw_payload: dict = field(default_factory=dict)
    variants: list["ListingDTO"] = field(default_factory=list)


# ---- Исключения --------------------------------------------------------- #

class ParserError(Exception):
    """База для всех ошибок парсера."""


class ParserBlocked(ParserError):
    """403/Cloudflare-challenge — нас заблокировали."""


class ParserNeedsBrowser(ParserBlocked):
    """Сайт требует JS-исполнения — выставит Store.requires_browser=True."""


class TransientParserError(ParserError):
    """5xx/network/таймаут — стоит ретраить, и инкрементить circuit-breaker."""


# ---- Базовый класс парсера ---------------------------------------------- #

class BaseStoreParser:
    """Базовый класс парсера магазина.

    Per-shop класс должен:
      1. Объявить `slug`, `base_url`.
      2. Реализовать `parse_listing(url)`.
      3. Опционально переопределить `discover_urls()` или положиться на дефолт
         (`sitemap.xml` + `yml.xml` + `feed.xml`).
      4. Опционально переопределить `crawl_incremental(since)` — например, для
         YML-фидов с lastmod.
    """

    # Должны быть переопределены в подклассе:
    slug: str = ""
    base_url: str = ""

    # Параметры с дефолтами:
    rate_limit_per_sec: float = 0.5         # 1 req per 2s
    rate_burst: int = 2                      # token bucket capacity
    requires_js: bool = False                # принудительно через Playwright
    sitemap_paths: list[str] = ["/sitemap.xml", "/yml.xml", "/feed.xml", "/sitemap_index.xml"]
    listing_url_pattern: str | None = None   # regex для фильтра sitemap-URL
    respect_robots: bool = True
    # True — цена и наличие приезжают вместе с обходом каталога, поэтому
    # точечный `stock_refresh_active` для магазина избыточен: он тратит по
    # 800 запросов в сутки на то, что и так обновилось ночью.
    stock_from_listing: bool = False

    def __init__(self, http: ScraperHttpClient, browser: BrowserPool | None = None) -> None:
        if not self.slug or not self.base_url:
            raise RuntimeError(f"{type(self).__name__}: slug/base_url must be set")
        self.http = http
        self.browser = browser

    # ---- Discovery ------------------------------------------------------ #

    async def discover_urls(self) -> AsyncIterator[str]:
        """Дефолтная стратегия — пробуем sitemap-style фиды по очереди."""
        from app.services.scrapers.sitemap import iter_sitemap_urls

        for path in self.sitemap_paths:
            url = self.base_url.rstrip("/") + path
            try:
                count = 0
                async for u in iter_sitemap_urls(self.http, url, self.listing_url_pattern):
                    count += 1
                    yield u
                if count:
                    logger.info("[%s] discover via %s: %d urls", self.slug, path, count)
                    return
            except Exception:
                logger.debug("[%s] sitemap %s failed", self.slug, path, exc_info=True)
                continue

        logger.warning("[%s] no usable sitemap; subclass must override discover_urls()", self.slug)

    # ---- Парсинг листинга ----------------------------------------------- #

    async def parse_listing(self, url: str) -> ListingDTO:
        """Загрузить страницу товара и извлечь поля. Подкласс ОБЯЗАН реализовать."""
        raise NotImplementedError

    # ---- Оркестрация ---------------------------------------------------- #

    async def crawl_full(self, limit: int | None = None) -> AsyncIterator[ListingDTO]:
        """Полный обход: все URL из discover_urls() → parse_listing().

        Между запросами — sleep(1/rate) ± jitter. ParserError-подклассы пропускаем.
        """
        delay = 1.0 / max(self.rate_limit_per_sec, 0.01)
        seen = 0
        async for url in self.discover_urls():
            if limit is not None and seen >= limit:
                return
            try:
                yield await self.parse_listing(url)
                seen += 1
            except ParserBlocked:
                # http_client уже выставил Store.requires_browser=True если нужно
                logger.warning("[%s] blocked at %s — stopping crawl", self.slug, url)
                return
            except (TransientParserError, ParserError):
                continue
            await asyncio.sleep(delay + random.uniform(0.0, delay * 0.5))

    async def refresh_urls(self, urls: list[str]) -> AsyncIterator[tuple[str, ListingDTO | None]]:
        """Точечная перепроверка известных URL (stock-refresh).

        Yields (url, dto). dto=None — товар удалён (404/410), листинг надо
        пометить removed. ParserBlocked останавливает обход магазина.
        """
        delay = 1.0 / max(self.rate_limit_per_sec, 0.01)
        for url in urls:
            try:
                yield url, await self.parse_listing(url)
            except ParserBlocked:
                logger.warning("[%s] blocked at %s — stopping refresh", self.slug, url)
                return
            except ParserError_404:
                yield url, None
            except (TransientParserError, ParserError):
                continue
            await asyncio.sleep(delay + random.uniform(0.0, delay * 0.5))

    async def crawl_incremental(self, since: datetime, limit: int | None = None) -> AsyncIterator[ListingDTO]:
        """Только новинки/изменённые с `since`. Дефолт — то же что full.

        Подклассы могут оверрайднуть: например, YML-фид с `<offer>...<modifiedTime>`.
        """
        async for dto in self.crawl_full(limit=limit):
            yield dto
