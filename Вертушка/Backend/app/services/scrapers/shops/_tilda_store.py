"""
Базовый парсер магазина на Tilda — «новый принцип» harvest'а каталога.

В отличие от sitemap-парсеров (korobkavinyla и т.п.), которые тянут по одной
HTTP-странице на товар (N запросов на N товаров), Tilda-магазины отдают весь
каталог через store-API одним эндпоинтом:

    GET https://store.tildaapi.com/api/getproductslist/
        ?storepartuid=<storepart>&recid=<recid>&getparts=true&slice=<page>&size=<n>

Ответ — JSON `{"total": N, "products": [{uid,title,price,priceold,quantity,
gallery,url,sku,...}, ...]}`. Каталог из ~1.6к товаров = ~17 запросов вместо
~1.6к. Вежливее к магазину, быстрее, и данные приходят структурированными.

Параметры магазина (`store_recid`, `store_partuid`) лежат в исходном HTML
витрины в вызове `t_store_init('<recid>', {... storepart:'<storepart>' ...})`.

Подкласс обязан:
  1. Объявить `slug`, `base_url`, `store_recid`, `store_partuid`.
  2. Реализовать `parse_product(p)` — словарь товара → ListingDTO (или None,
     если товар надо пропустить, напр. нон-медиа аксессуар).
"""
from __future__ import annotations

import json
import logging
import re
from datetime import datetime
from typing import AsyncIterator

from app.services.scrapers.base import BaseStoreParser, ListingDTO

logger = logging.getLogger(__name__)

_STORE_API = "https://store.tildaapi.com/api/getproductslist/"
_UID_FROM_URL_RE = re.compile(r"/tproduct/\d+-(\d+)-")


class TildaStoreParser(BaseStoreParser):
    """Парсер каталога Tilda-магазина через store-API."""

    # Должны быть переопределены в подклассе:
    store_recid: str = ""
    store_partuid: str = ""

    # Размер страницы store-API. 100 — комфортный батч (≈135 КБ JSON).
    stock_from_listing = True  # каталог store-API отдаёт quantity

    catalog_page_size: int = 100
    # Жёсткий потолок страниц на всякий случай (защита от бесконечного цикла,
    # если API внезапно начнёт игнорировать slice).
    max_pages: int = 200

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        if not self.store_recid or not self.store_partuid:
            raise RuntimeError(
                f"{type(self).__name__}: store_recid/store_partuid must be set"
            )

    # ---- Tilda store-API ------------------------------------------------ #

    async def _iter_products(self) -> AsyncIterator[dict]:
        """Постранично тянет весь каталог. Yields product-dict'ы."""
        size = self.catalog_page_size
        emitted = 0
        for page in range(1, self.max_pages + 1):
            params = (
                f"?storepartuid={self.store_partuid}&recid={self.store_recid}"
                f"&c={int(datetime.utcnow().timestamp())}"
                f"&getparts=true&slice={page}&size={size}"
            )
            # respect_robots=False: это data-API витрины (не страница для
            # индексации), его дёргает сам фронт магазина. Per-domain rate-limit
            # из http_client остаётся.
            raw = await self.http.get_text(_STORE_API + params, respect_robots=False)
            data = json.loads(raw)
            products = data.get("products") or []
            total = int(data.get("total") or 0)
            if not products:
                return
            for p in products:
                yield p
                emitted += 1
            if len(products) < size or (total and emitted >= total):
                return

    async def _load_catalog_by_uid(self) -> dict[str, dict]:
        """Весь каталог одним проходом → {uid(str): product-dict}."""
        out: dict[str, dict] = {}
        async for p in self._iter_products():
            uid = p.get("uid")
            if uid is not None:
                out[str(uid)] = p
        return out

    # ---- Оркестрация (оверрайд базовых sitemap-методов) ----------------- #

    async def crawl_full(self, limit: int | None = None) -> AsyncIterator[ListingDTO]:
        """Весь каталог через store-API → parse_product(). Без пер-URL фетча."""
        seen = 0
        async for p in self._iter_products():
            if limit is not None and seen >= limit:
                return
            try:
                dto = self.parse_product(p)
            except Exception:
                logger.debug("[%s] parse_product failed for uid=%s",
                             self.slug, p.get("uid"), exc_info=True)
                continue
            if dto is None:
                continue
            yield dto
            seen += 1

    async def refresh_urls(
        self, urls: list[str]
    ) -> AsyncIterator[tuple[str, ListingDTO | None]]:
        """Stock-refresh: один проход каталога, ответ всем url'ам из памяти.

        uid берём из самого url (`/tproduct/<root>-<uid>-<slug>`). Нет в
        каталоге → None (товар снят). Отфильтрованный parse_product'ом товар
        не трогаем (не yield'им).
        """
        catalog = await self._load_catalog_by_uid()
        for url in urls:
            uid = self._uid_from_url(url)
            product = catalog.get(uid) if uid else None
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
        # Tilda-парсер работает каталогом, пер-URL парсинг не используется
        # (crawl_full и refresh_urls переопределены).
        raise NotImplementedError(
            f"{type(self).__name__} parses via store-API catalog, not per-URL"
        )

    # ---- Подкласс реализует --------------------------------------------- #

    def parse_product(self, product: dict) -> ListingDTO | None:
        """Словарь товара из store-API → ListingDTO. None = пропустить товар."""
        raise NotImplementedError

    # ---- helpers -------------------------------------------------------- #

    @staticmethod
    def _uid_from_url(url: str) -> str | None:
        m = _UID_FROM_URL_RE.search(url)
        return m.group(1) if m else None

    @staticmethod
    def first_gallery_image(product: dict) -> str | None:
        """gallery — JSON-строка `[{"img":"https://..."}]`. Вернуть первый img."""
        raw = product.get("gallery")
        if not raw:
            return None
        try:
            arr = json.loads(raw) if isinstance(raw, str) else raw
        except json.JSONDecodeError:
            return None
        if isinstance(arr, list) and arr and isinstance(arr[0], dict):
            return arr[0].get("img") or None
        return None
