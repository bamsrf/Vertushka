"""
Парсер Dr.Head (doctorhead.ru) — московский аудио-ритейлер, раздел «Музыка».

Каталог `/catalog/muzyka/`: винил (~3.3k товаров, 115 страниц), CD, кассеты,
магнитные ленты. Книги и сувенирку не берём — не носители звука.

WS1.2: обход переведён со страниц товара на карточки листинга. Было
~121 страница категорий + ~3500 запросов на страницы товара (≈2 часа),
стало **121 запрос** (≈4 минуты) — карточка отдаёт всё нужное:

    data-id="102300"                    → external_id (= sku из JSON-LD, сверено)
    data-price="3290"                   → цена
    .product-status → «В наличии»       → статус
    img@alt «Виниловая пластинка Кино - Начальник Камчатки LP» → раздел + title
    «Исполнитель: Кино»                 → артист (есть у 29/29 карточек)

Единственное, чего в карточке нет — характеристика «Тип издания» («Цветной
винил»). Она участвовала только в определении цвета, и лишь как второй источник
после скобки в названии, откуда цвет и берётся в подавляющем большинстве
случаев. A/B листинг против страницы товара на 12 товарах: 12/12 совпало по
артисту, названию, цене, формату, цвету и обложке.

`parse_listing()` (разбор страницы товара) сохранён — его использует
`refresh_urls()` для точечной перепроверки и детекта 404 → removed.

Особенности:
- Bitrix. Общий `/sitemap/sitemap-iblock-2.xml` содержит ВЕСЬ каталог магазина
  (наушники, усилители, гейминг) без признака раздела — поэтому идём
  category-walk по `/catalog/muzyka/<раздел>/?PAGEN_1=N` (29 товаров на
  страницу, размер страницы не настраивается: SIZEN_1/count игнорируются).
  robots.txt PAGEN_1 не запрещает.
- На странице товара чистый JSON-LD Product: name / sku / offers.price /
  offers.availability / image.
- Артист лежит в характеристике «Исполнитель» — это надёжнее, чем резать
  title по дефису (в title попадаются «Kanye West - Ye», «Кишлак – СХИК2»,
  но и артисты с дефисом внутри имени).
- **Нет barcode / каталожного номера / года издания.** Характеристика
  «Приход» = 202405 — это год+неделя поступления на склад, НЕ год релиза,
  поэтому year_raw оставляем пустым; матчинг идёт по artist+title
  (fuzzy + on-demand Discogs), как у found.
- Формат — суффикс title («... 2LP», «... LP»), цвет — характеристика
  «Тип издания» = «Цветной винил» + скобка в title («(Coloured Red Black)»).
- Обложка: JSON-LD image[0] отдаёт thumbnail из `resize_cache/.../112_76_1/`,
  режем этот сегмент до полноразмерной картинки; фолбэк — og:image.
"""
from __future__ import annotations

import logging
import re
from decimal import Decimal
from typing import AsyncIterator

from bs4 import BeautifulSoup

from app.services.scrapers.base import (
    BaseStoreParser,
    ListingDTO,
    PageErrorBudget,
    ParserError,
)
from app.services.scrapers.extractors import (
    extract_jsonld_product,
    infer_format,
    infer_vinyl_color,
    jsonld_availability,
    jsonld_price,
    parse_price,
)
from app.services.scrapers.registry import register_parser

logger = logging.getLogger(__name__)

# Разделы `/catalog/muzyka/`, которые являются носителями звука. `knigi` и
# `suvenirnaya_produktsiya` сознательно исключены (книги, мерч, аксессуары).
_MEDIA_CATEGORIES = (
    "vinilovye-plastinki",
    "cd-diski",
    "kassety",
    "magnitnye_lenty",
)

_CATALOG_ROOT = "/catalog/muzyka"
# Страховка от бесконечной пагинации, если сайт начнёт отдавать одну и ту же
# страницу на любой PAGEN_1 (у винила сейчас 115 страниц).
_MAX_PAGES_PER_CATEGORY = 400

# Подпись раздела над h1 («Виниловая пластинка», «CD-диск», «Кассета»,
# «Магнитная лента») — фолбэк формата, когда в title нет суффикса
# («Kanye West - Ye»). infer_format её не ловит: «Виниловая» ≠ \bвинил\b.
_CATEGORY_FORMAT = {
    "виниловая пластинка": "LP",
    "cd-диск": "CD",
    "кассета": "Cassette",
    "магнитная лента": "Reel-to-Reel",
}

_PRODUCT_HREF_RE = re.compile(r"^/product/[^/]+/?$")
_PAGEN_RE = re.compile(r"PAGEN_1=(\d+)")

# «Aphex Twin – Richard D. James Album LP» → артист отрезаем по характеристике,
# а хвост-формат («LP», «2LP», «3LP», «CD», «Box Set», «7\"») режем отдельно.
_FORMAT_TAIL_RE = re.compile(
    r"[\s,–—-]*\b(?:\d+\s*x?\s*(?:LP|CD|Vinyl)|LP|CD|EP|SACD|Box\s*Set|"
    r"\d+\s*[\"″'']|Cassette|Кассета)\s*$",
    re.I,
)
# Хвостовая скобка с описанием издания: «(Coloured Red Black)», «(Deluxe)».
_EDITION_PAREN_RE = re.compile(r"\(([^()]*)\)\s*$")
_DASH_SPLIT_RE = re.compile(r"\s*[–—]\s*|\s+-\s+")
_PREORDER_KW_RE = re.compile(r"предзаказ|pre[\s\-]?order", re.I)
# Статус в карточке листинга: «В наличии» / «На заказ» / «Нет в наличии».
# Порядок проверки важен: «нет в наличии» содержит в себе «в наличии».
_CARD_OUT_OF_STOCK_RE = re.compile(r"нет\s+в\s+наличии|раскуплен|закончил", re.I)
_CARD_IN_STOCK_RE = re.compile(r"в\s+наличии", re.I)
_CARD_ON_ORDER_RE = re.compile(r"на\s+заказ|под\s+заказ", re.I)
# `/upload/.../resize_cache/iblock/997/112_76_1/x.webp` → полноразмерный оригинал.
_RESIZE_CACHE_RE = re.compile(r"resize_cache/(.*?)/\d+_\d+_\d+/")


@register_parser("doctorhead")
class DoctorHeadParser(BaseStoreParser):
    base_url = "https://doctorhead.ru"
    rate_limit_per_sec = 0.5  # 1 req / 2 c — крупный Bitrix, не долбим
    rate_burst = 2
    requires_js = False
    sitemap_paths: list[str] = []  # discovery через category-walk, см. ниже
    listing_url_pattern = r"/product/[^/]+/?$"
    stock_from_listing = True  # статус есть в карточке листинга

    @property
    def slug(self) -> str:
        return "doctorhead"

    # ---- Обход каталога по карточкам листинга ---------------------------- #

    async def crawl_full(self, limit: int | None = None) -> AsyncIterator[ListingDTO]:
        """Пагинируем медиа-разделы и разбираем карточки, без захода на товар.

        Rate-limit держит per-domain token bucket в http_client (его настраивает
        runner из `rate_limit_per_sec`), поэтому дополнительный sleep как в
        `BaseStoreParser.crawl_full` здесь не нужен.
        """
        seen: set[str] = set()
        emitted = 0
        # Бюджет общий на все категории: сайт лежит целиком, а не по разделам.
        budget = PageErrorBudget(self.slug)

        for category in _MEDIA_CATEGORIES:
            base = f"{self.base_url}{_CATALOG_ROOT}/{category}/"
            max_page: int | None = None
            page = 1

            while page <= _MAX_PAGES_PER_CATEGORY:
                url = base if page == 1 else f"{base}?PAGEN_1={page}"
                html = await self.fetch_page(
                    url, budget,
                    page_label=f"{category} стр. {page} из {max_page or '?'}",
                )
                if html is None:
                    # Страница в бюджете пропусков: теряем ~30 карточек, но не
                    # весь каталог. Сквозной обрыв ловит сам бюджет.
                    page += 1
                    continue

                if max_page is None:
                    max_page = _detect_max_page(html)
                    logger.info("[%s] %s: %s страниц", self.slug, category, max_page or "?")

                fresh = 0
                for card in _extract_cards(html):
                    try:
                        dto = _parse_card(card, self.base_url)
                    except Exception:
                        logger.debug("[%s] card parse failed on %s", self.slug, url, exc_info=True)
                        continue
                    if dto is None or dto.external_id in seen:
                        continue
                    seen.add(dto.external_id)
                    fresh += 1
                    yield dto
                    emitted += 1
                    if limit is not None and emitted >= limit:
                        return

                # Bitrix на PAGEN_1 за пределами диапазона отдаёт последнюю
                # страницу, а не 404 — поэтому останавливаемся по «ни одного
                # нового товара», а не по коду ответа.
                if fresh == 0:
                    break
                if max_page is not None and page >= max_page:
                    break
                page += 1

        budget.log_summary()
        logger.info("[%s] обход по карточкам: %d товаров", self.slug, emitted)

    # ---- Discovery (для sitemap-совместимости и отладки) ----------------- #

    async def discover_urls(self) -> AsyncIterator[str]:
        """Пагинируем каждый медиа-раздел `/catalog/muzyka/<cat>/?PAGEN_1=N`.

        Останавливаем раздел, когда страница не дала ни одного НОВОГО товара
        (Bitrix на PAGEN_1 за пределами диапазона отдаёт последнюю страницу,
        а не 404) либо когда дошли до максимума пагинатора со страницы 1.
        """
        seen: set[str] = set()

        for category in _MEDIA_CATEGORIES:
            base = f"{self.base_url}{_CATALOG_ROOT}/{category}/"
            max_page: int | None = None
            page = 1

            while page <= _MAX_PAGES_PER_CATEGORY:
                url = base if page == 1 else f"{base}?PAGEN_1={page}"
                try:
                    html = await self.http.get_text(url)
                except Exception:
                    logger.debug("[%s] category page failed: %s", self.slug, url, exc_info=True)
                    break

                if max_page is None:
                    max_page = _detect_max_page(html)

                fresh = 0
                for product_url in _extract_product_urls(html):
                    absolute = f"{self.base_url}{product_url}"
                    if absolute in seen:
                        continue
                    seen.add(absolute)
                    fresh += 1
                    yield absolute

                if fresh == 0:
                    break
                if max_page is not None and page >= max_page:
                    break
                page += 1

            logger.info("[%s] %s: %d urls total", self.slug, category, len(seen))

    # ---- Парсинг листинга ----------------------------------------------- #

    async def parse_listing(self, url: str) -> ListingDTO:
        html = await self.http.get_text(url)
        soup = BeautifulSoup(html, "lxml")

        product = extract_jsonld_product(html) or {}
        chars = _extract_characteristics(soup)

        raw_title = str(product.get("name") or "").strip() or _h1_title(soup)
        if not raw_title:
            raise ParserError(f"no title at {url}")

        artist = chars.get("Исполнитель") or None
        album, edition = _strip_artist_and_format(raw_title, artist)
        if artist is None:
            artist, album = _split_artist_album(album)

        label = chars.get("Лейбл") or chars.get("Бренд") or None
        edition_kind = chars.get("Тип издания") or ""
        # Суффикс title («2LP», «3CD») точнее всего; подпись раздела в h1 —
        # фолбэк, когда суффикса нет.
        category = _category_label(soup)
        format_text = f"{raw_title} {category} {edition_kind}"

        price = jsonld_price(product)
        status = jsonld_availability(product)
        if _PREORDER_KW_RE.search(f"{raw_title} {edition_kind}"):
            status = "preorder"
        if price is None and status == "in_stock":
            status = "on_request"

        external_id = str(product.get("sku") or "").strip() or url.rstrip("/").rsplit("/", 1)[-1]

        raw_payload: dict = {}
        if label:
            raw_payload["label"] = label
        if edition_kind:
            raw_payload["edition_kind"] = edition_kind
        if chars.get("Жанр"):
            raw_payload["genre"] = chars["Жанр"]

        color_source = " ".join(filter(None, (edition, edition_kind)))
        return ListingDTO(
            external_id=external_id,
            url=url,
            title_raw=album or raw_title,
            artist_raw=artist,
            year_raw=None,  # «Приход» — неделя поступления, не год релиза
            format_raw=infer_format(format_text) or _CATEGORY_FORMAT.get(category.lower()),
            vinyl_color_raw=(
                infer_vinyl_color(color_source, exclude=[artist, album])
                or infer_vinyl_color(raw_title, exclude=[artist, album])
            ),
            condition="Новый (Mint)",
            price_rub=price,
            price_currency="RUB",
            status=status,
            barcode=None,
            catalog_number=None,
            discogs_release_url=None,
            image_url=_pick_image(product, soup),
            raw_payload=raw_payload,
        )


# ---- helpers ------------------------------------------------------------ #


def _extract_cards(html: str) -> list:
    """Карточки товара со страницы категории (`.js-product-container`)."""
    soup = BeautifulSoup(html, "lxml")
    return soup.find_all("div", class_="js-product-container")


def _card_field(text: str, name: str) -> str | None:
    """«… | Исполнитель: Кино | Жанр: Rock | …» → значение поля по имени."""
    m = re.search(rf"{name}:\s*\|?\s*([^|]+)", text)
    return _clean(m.group(1)) if m else None


def _parse_card(card, base_url: str) -> ListingDTO | None:
    """Карточка листинга → ListingDTO. None — карточка без цены/ссылки."""
    price_node = card.find("div", class_="js-product-price")
    link = card.find("a", href=_PRODUCT_HREF_RE)
    if not price_node or not link:
        return None

    external_id = (price_node.get("data-id") or "").strip()
    if not external_id:
        return None

    text = card.get_text(" | ", strip=True)
    img = card.find("img")

    # img@alt — единственное место в карточке, где название идёт вместе с
    # подписью раздела («Виниловая пластинка …»), а она нужна как фолбэк формата.
    raw_title = _clean(img.get("alt") or "") if img else ""
    category = ""
    for label in _CATEGORY_FORMAT:
        if raw_title.lower().startswith(label):
            category = label
            raw_title = raw_title[len(label):].strip()
            break
    if not raw_title:
        return None

    artist = _card_field(text, "Исполнитель")
    album, edition = _strip_artist_and_format(raw_title, artist)
    if artist is None:
        artist, album = _split_artist_album(album)

    # data-price приходит как «4990.0» — срезаем хвостовой ноль, чтобы значение
    # совпадало с ценой со страницы товара и не плодило записей в price_history.
    price = parse_price(price_node.get("data-price"))
    if price is not None and price == price.to_integral_value():
        price = price.quantize(Decimal(1))

    status_node = card.find("div", class_="product-status")
    status_text = status_node.get_text(" ", strip=True) if status_node else ""
    if _PREORDER_KW_RE.search(f"{status_text} {raw_title} {edition}"):
        status = "preorder"
    elif _CARD_OUT_OF_STOCK_RE.search(status_text):
        status = "out_of_stock"
    elif _CARD_IN_STOCK_RE.search(status_text):
        status = "in_stock"
    elif _CARD_ON_ORDER_RE.search(status_text):
        status = "on_request"
    elif status_text:
        status = "out_of_stock"
    else:
        status = "in_stock" if price is not None else "out_of_stock"
    if price is None and status == "in_stock":
        status = "on_request"

    raw_payload: dict = {}
    genre = _card_field(text, "Жанр")
    if genre:
        raw_payload["genre"] = genre

    image = None
    if img and img.get("src"):
        image = base_url + _RESIZE_CACHE_RE.sub(r"\1/", img["src"])

    return ListingDTO(
        external_id=external_id,
        url=base_url + link["href"].split("?")[0],
        title_raw=album or raw_title,
        artist_raw=artist,
        year_raw=None,  # «Приход» — неделя поступления, не год релиза
        format_raw=infer_format(f"{raw_title} {category}") or _CATEGORY_FORMAT.get(category),
        # «Тип издания» есть только на странице товара; в карточке цвет живёт
        # в хвостовой скобке названия — она и так основной источник.
        vinyl_color_raw=infer_vinyl_color(
            " ".join(filter(None, (edition, raw_title))), exclude=[artist, album]
        ),
        condition="Новый (Mint)",
        price_rub=price,
        price_currency="RUB",
        status=status,
        barcode=None,
        catalog_number=None,
        discogs_release_url=None,
        image_url=image,
        raw_payload=raw_payload,
    )


def _extract_product_urls(html: str) -> list[str]:
    """Все `/product/<slug>/` со страницы категории, в порядке появления."""
    soup = BeautifulSoup(html, "lxml")
    urls: list[str] = []
    seen: set[str] = set()
    for a in soup.find_all("a", href=True):
        href = a["href"].split("?")[0].split("#")[0]
        if _PRODUCT_HREF_RE.match(href) and href not in seen:
            seen.add(href)
            urls.append(href)
    return urls


def _detect_max_page(html: str) -> int | None:
    """Максимальный номер из ссылок пагинатора `?PAGEN_1=N`."""
    pages = [int(n) for n in _PAGEN_RE.findall(html)]
    return max(pages) if pages else None


def _extract_characteristics(soup: BeautifulSoup) -> dict[str, str]:
    """Блоки `.characteristic` → {«Исполнитель»: «Aphex Twin», ...}."""
    out: dict[str, str] = {}
    for block in soup.select(".characteristic"):
        label_node = block.select_one(".characteristic__label")
        value_node = block.select_one(".characteristic__value")
        if not label_node or not value_node:
            continue
        key = _clean(label_node.get_text(" ", strip=True))
        value = _clean(value_node.get_text(" ", strip=True))
        if key and value:
            out[key] = value
    return out


def _h1_title(soup: BeautifulSoup) -> str:
    node = soup.select_one(".product-main-info__title")
    return _clean(node.get_text(" ", strip=True)) if node else ""


def _category_label(soup: BeautifulSoup) -> str:
    node = soup.select_one(".product-main-info__category")
    return _clean(node.get_text(" ", strip=True)) if node else ""


def _strip_artist_and_format(raw_title: str, artist: str | None) -> tuple[str, str]:
    """«Кишлак – СХИК2 (Coloured Red Black) LP» + «Кишлак» → («СХИК2», «Coloured Red Black»).

    Возвращает (album, edition) — edition это содержимое хвостовой скобки
    (описание издания/цвета), нужное для infer_vinyl_color.
    """
    title = _clean(raw_title)

    if artist:
        # Артист + разделитель в начале title — срезаем ровно этот префикс.
        prefix = re.compile(rf"^\s*{re.escape(artist)}\s*(?:[–—]|\s-\s)?\s*", re.I)
        title = prefix.sub("", title, count=1).strip()

    title = _FORMAT_TAIL_RE.sub("", title).strip()

    edition = ""
    m = _EDITION_PAREN_RE.search(title)
    if m:
        edition = m.group(1).strip()
        title = title[: m.start()].strip()
        # Формат мог стоять до скобки: «... LP (Coloured)».
        title = _FORMAT_TAIL_RE.sub("", title).strip()

    return title.strip(" .,–—-"), edition


def _split_artist_album(title: str) -> tuple[str | None, str]:
    """Фолбэк, когда характеристики «Исполнитель» нет: режем по дефису."""
    parts = _DASH_SPLIT_RE.split(title, maxsplit=1)
    if len(parts) == 2 and parts[0].strip() and parts[1].strip():
        return parts[0].strip(), parts[1].strip()
    return None, title.strip()


def _pick_image(product: dict, soup: BeautifulSoup) -> str | None:
    """JSON-LD image[0] без resize_cache-сегмента, фолбэк — og:image."""
    image = product.get("image")
    if isinstance(image, list):
        image = image[0] if image else None
    if isinstance(image, str) and image.strip():
        return _RESIZE_CACHE_RE.sub(r"\1/", image.strip())

    og = soup.find("meta", property="og:image")
    content = og.get("content") if og else None
    return content.strip() if content else None


def _clean(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip()
