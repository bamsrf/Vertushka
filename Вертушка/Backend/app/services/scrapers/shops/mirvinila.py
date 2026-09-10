"""Парсер «Пластиночная №1» (mirvinila.com) — InSales collection-API.

Найден и замерен глобальной разведкой 09–10.09 (MARKET_STORES_SCALING.md §7d).
Первый InSales-магазин в маркете; когда появится второй, ходилку по API стоит
поднять в общий `_insales_store.py` — как сделано для Tilda.

    GET /collection/all.json?page=<N>&per_page=100
    → {"status":"ok","count":20937,"products":[{...}]}

Три вещи, которые замер вскрыл и на которых легко ошибиться:

1. **Каталог отсортирован стоком вперёд.** В нём 20 937 позиций, но в наличии
   лишь ~5 700 (28.6%): хвост — коллекция «ждём поступление» с
   `available:false` и `quantity:0`. Поэтому обход идёт ДО ГРАНИЦЫ СТОКА
   (~57 страниц), а не по всему каталогу (210 страниц, 183 МБ). Граница
   определяется на лету: страница, где ни одного `available`, заканчивает
   обход. Флаг честный — на 700 товарах он совпал с `quantity:0` и коллекцией
   «ждём поступление» ровно 700 раз из 700.

2. **`per_page` жёстко ограничен сотней**, а `order` игнорируется — просили
   250 и сортировку по обновлению, получили 100 вперемешку. Инкремента у
   магазина нет: `crawl_incremental` = полный обход. Учитывая `quantity` 1–2
   (товар разлетается поштучно), это нормально — 57 запросов дёшево.

3. **`first_image.url` — это THUMB** (`thumb_IMG_1234.jpg`). Полноразмер лежит
   в `original_url`. Берём только его: апскейл миниатюр уже однажды сделал
   половину обложек в приложении пиксельными.

Метаданные у магазина уровня Discogs — `characteristics` ссылается на
`properties` по `property_id`, оттуда достаём «Лейбл», «Год», «Страна»,
«Уникальный код» (каталожный номер) и ОТДЕЛЬНО «Состояние винила» и
«Состояние конверта». Ключи ищем по НАЗВАНИЮ свойства, а не по числовому id:
id принадлежат конкретной витрине и переживут разве что до следующей правки
карточек в админке.

Не-носители (слипматы, щётки, фонокорректоры Radiotehnika, сертификаты)
отсекаются отсутствием «Формата носителя» — проверено на разделах
`aksessuary-dlya-vinila` (39 из 39 без формата) и `muzykalnoe-oborudovanie`
(8 из 8), при том что в `cd` формат есть у 35 из 36.

Названия имеют вид `Artist ‎– Album (Страна 1981г.) T`, у CD с префиксом
`CD `. Страна и год дублируют свойства, поэтому скобочный хвост срезаем —
иначе точного совпадения с `records.title` не будет никогда.
"""
from __future__ import annotations

import html as html_lib
import json
import logging
import re
from decimal import Decimal
from typing import AsyncIterator

from app.services.scrapers.base import BaseStoreParser, ListingDTO
from app.services.scrapers.extractors import (
    infer_format,
    infer_vinyl_color,
    normalize_barcode,
    normalize_catalog,
    parse_price,
    parse_year,
)
from app.services.scrapers.registry import register_parser

logger = logging.getLogger(__name__)

# Невидимые маркеры направления письма — рвут split и матчинг.
_BIDI_RE = re.compile(r"[‎‏‪-‮]")

# «Artist – Album»: en/em-dash, либо дефис ТОЛЬКО с пробелами с обеих сторон
# (иначе порвём «Jay-Z»).
_TITLE_SPLIT_RE = re.compile(r"\s*[–—]\s*|\s+-\s+")

# Хвост «(Австралия 1981г.)» — страна и год, они же лежат в свойствах.
_PAREN_TAIL_RE = re.compile(r"\s*\([^()]*\)\s*$")

# Одиночная буква-пометка в самом конце («… Great Dance Songs T»).
_LETTER_TAIL_RE = re.compile(r"\s+[A-ZА-Я]\s*$")

# Формат носителя у CD пишется в начало названия.
_CD_PREFIX_RE = re.compile(r"^(CD|LP|MC)\s+")

# Свойства, которые нас интересуют (ищем по названию, не по id).
_P_FORMAT = "Формат носителя"
_P_YEAR = "Год"
_P_LABEL = "Лейбл"
_P_COUNTRY = "Страна"
_P_CATNO = "Уникальный код"
_P_COND_VINYL = "Состояние винила"
_P_COND_SLEEVE = "Состояние конверта"
_P_BRAND = "Бренд"


def _clean(s) -> str:
    return _BIDI_RE.sub("", html_lib.unescape(str(s or ""))).strip()


def _characteristics(product: dict) -> dict[str, str]:
    """`properties` (id → название) + `characteristics` (property_id → значение)
    сводим в плоский словарь «название свойства» → «значение»."""
    names = {
        pr.get("id"): _clean(pr.get("title"))
        for pr in (product.get("properties") or [])
        if isinstance(pr, dict)
    }
    out: dict[str, str] = {}
    for ch in product.get("characteristics") or []:
        if not isinstance(ch, dict):
            continue
        name = names.get(ch.get("property_id"))
        value = _clean(ch.get("title"))
        if name and value:
            out.setdefault(name, value)
    return out


def _split_artist_album(title: str) -> tuple[str | None, str]:
    """`Artist ‎– Album (Страна Годг.) T` → ('Artist', 'Album')."""
    core = _CD_PREFIX_RE.sub("", _clean(title))
    prev = None
    while prev != core:
        prev = core
        core = _LETTER_TAIL_RE.sub("", _PAREN_TAIL_RE.sub("", core)).strip()
    parts = _TITLE_SPLIT_RE.split(core, maxsplit=1)
    if len(parts) == 2 and parts[0].strip() and parts[1].strip():
        return parts[0].strip(), parts[1].strip()
    return None, core or _clean(title)


def _variant_totals(product: dict) -> tuple[Decimal | None, int, str | None, str | None]:
    """Максимальная цена, суммарный остаток, sku и штрихкод первого варианта."""
    price: Decimal | None = None
    qty = 0
    sku = barcode = None
    for v in product.get("variants") or []:
        if not isinstance(v, dict):
            continue
        p = parse_price(str(v.get("price") or ""))
        if p is not None and (price is None or p > price):
            price = p
        try:
            qty += int(float(v.get("quantity") or 0))
        except (TypeError, ValueError):
            pass
        if sku is None and v.get("sku"):
            sku = _clean(v.get("sku"))
        if barcode is None and v.get("barcode"):
            barcode = normalize_barcode(str(v.get("barcode")))
    return price, qty, sku, barcode


@register_parser("mirvinila")
class MirvinilaParser(BaseStoreParser):
    base_url = "https://mirvinila.com"
    rate_limit_per_sec = 0.5
    rate_burst = 2
    requires_js = False

    # Каталог отдаёт цену и остаток вместе с обходом — точечный stock_refresh
    # тратил бы сотни запросов на то, что уже приехало ночью.
    stock_from_listing = True

    # per_page витрина клампит до 100, что бы мы ни просили.
    catalog_page_size: int = 100

    # Страховка от бесконечного цикла и от того, что витрина вдруг перестанет
    # сортировать сток вперёд: 210 страниц — это весь каталог целиком.
    max_pages: int = 210

    # Сколько подряд идущих страниц без единой позиции в наличии считаем концом
    # стока. Одна страница — рискованно: хватит одной аномалии в сортировке,
    # чтобы молча обрезать каталог. Две — компромисс между этим риском и тем,
    # чтобы не тащить 150 страниц распроданного архива.
    stock_tail_pages: int = 2

    # ---- InSales collection-API ----------------------------------------- #

    async def _iter_products(self) -> AsyncIterator[dict]:
        """Страницы каталога до границы стока. Yields product-dict'ы."""
        empty_streak = 0
        seen_available = False
        for page in range(1, self.max_pages + 1):
            url = (
                f"{self.base_url}/collection/all.json"
                f"?page={page}&per_page={self.catalog_page_size}"
            )
            # respect_robots=False: это data-API витрины, его дёргает сам фронт
            # магазина. Per-domain rate-limit из http_client остаётся.
            raw = await self.http.get_text(url, respect_robots=False)
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                logger.warning("[%s] страница %d — не JSON, обрываю", self.slug, page)
                return
            products = data.get("products") or []
            if not products:
                return

            available = [p for p in products if p.get("available")]
            for p in available:
                yield p

            if available:
                seen_available = True
                empty_streak = 0
            elif seen_available:
                empty_streak += 1
                if empty_streak >= self.stock_tail_pages:
                    logger.info(
                        "[%s] граница стока на странице %d — дальше архив, обход закончен",
                        self.slug, page,
                    )
                    return

            if len(products) < self.catalog_page_size:
                return
        logger.warning(
            "[%s] упёрлись в max_pages=%d, не найдя границы стока — "
            "витрина могла сменить сортировку", self.slug, self.max_pages,
        )

    # ---- Оркестрация ---------------------------------------------------- #

    async def crawl_full(self, limit: int | None = None) -> AsyncIterator[ListingDTO]:
        seen = 0
        async for p in self._iter_products():
            if limit is not None and seen >= limit:
                return
            try:
                dto = self.parse_product(p)
            except Exception:
                logger.debug("[%s] parse_product failed for id=%s",
                             self.slug, p.get("id"), exc_info=True)
                continue
            if dto is None:
                continue
            yield dto
            seen += 1

    async def refresh_urls(
        self, urls: list[str]
    ) -> AsyncIterator[tuple[str, ListingDTO | None]]:
        """Stock-refresh одним проходом каталога.

        Обход идёт только по стоку, поэтому отсутствие url в каталоге означает
        «больше не продаётся» — это ровно то, что должен увидеть вызывающий.
        """
        catalog: dict[str, dict] = {}
        async for p in self._iter_products():
            path = _clean(p.get("url"))
            if path:
                catalog[path] = p
        for url in urls:
            path = url[len(self.base_url):] if url.startswith(self.base_url) else url
            product = catalog.get(path)
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
        raise NotImplementedError(
            f"{type(self).__name__} работает каталогом через collection-API, не по URL"
        )

    # ---- Товар → DTO ---------------------------------------------------- #

    def parse_product(self, product: dict) -> ListingDTO | None:
        raw_title = _clean(product.get("title"))
        if not raw_title:
            return None

        ch = _characteristics(product)

        # Не-носитель: у слипматов, щёток и усилителей нет «Формата носителя».
        fmt_raw = ch.get(_P_FORMAT)
        if not fmt_raw:
            return None

        path = _clean(product.get("url"))
        if not path:
            return None

        artist, album = _split_artist_album(raw_title)
        price, qty, sku, barcode = _variant_totals(product)

        if price is None:
            status = "on_request"
        elif product.get("available") and qty > 0:
            status = "in_stock"
        else:
            status = "out_of_stock"

        # Цвет — из «Формата носителя» («3LP Yellow», «LP Promo»), а не из
        # названия: там страна и год, которые ловятся как ложные цвета.
        color = infer_vinyl_color(fmt_raw, exclude=[artist, album])

        image = None
        first = product.get("first_image")
        if isinstance(first, dict):
            # ТОЛЬКО original_url: `url` у InSales — это thumb_*.
            image = first.get("original_url") or None

        raw_payload: dict = {"insales_id": product.get("id")}
        for key, field in (
            (_P_LABEL, "label"),
            (_P_COUNTRY, "country"),
            (_P_COND_SLEEVE, "sleeve_condition"),
            (_P_BRAND, "brand"),
        ):
            if ch.get(key):
                raw_payload[field] = ch[key]
        if sku:
            raw_payload["store_sku"] = sku
        if qty:
            raw_payload["quantity"] = qty

        return ListingDTO(
            external_id=str(product.get("id") or path),
            url=self.base_url + path,
            title_raw=album,
            artist_raw=artist,
            year_raw=parse_year(ch.get(_P_YEAR)) or parse_year(raw_title),
            format_raw=infer_format(fmt_raw) or fmt_raw,
            vinyl_color_raw=color,
            condition=ch.get(_P_COND_VINYL),
            price_rub=price,
            price_currency="RUB",
            status=status,
            barcode=barcode,
            catalog_number=normalize_catalog(ch.get(_P_CATNO)),
            discogs_release_url=None,
            image_url=image,
            raw_payload=raw_payload,
        )
