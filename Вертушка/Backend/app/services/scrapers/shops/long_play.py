"""
Парсер Long Play (long-play.ru) — московский магазин б/у винила,
~2 600 позиций (по состоянию на 2026-08-16).

Самый дешёвый обход в маркете: **16 запросов на весь каталог**
(1 на корень `/catalog/` + по одному на каждый из 15 жанровых разделов).

Как так вышло. Витрина — Bitrix с обычной пагинацией по 20 товаров на
страницу, это дало бы ~132 запроса. Но:

  1. `PAGEN` у магазина **запрещён в robots.txt** (`Disallow: /*PAGEN`),
     так что штатный путь doctorhead'а здесь закрыт;
  2. компонент каталога принимает `?count=N` — размер выдачи, и его robots
     не запрещает. `?count=2000` отдаёт весь раздел одним ответом
     (самый большой, rock, — 971 товар, ~1 МБ, 9 c).

`SIZEN_1` / `SHOWALL_1` магазин игнорирует, `count` — единственный рабочий.

Разделы НЕ захардкожены: берём ссылки со страницы `/catalog/`. Sitemap
(`sitemap_iblock_4.xml`) для этого не годится — там `non-music`, а на сайте
раздел называется `non_music`, и товаров в карте сайта меньше, чем на витрине
(845 против 971 в rock): она отстаёт.

Витрина отдаёт ДВЕ панели в одном ответе — плитку (`#display-cells`) и список
(`#display-list`), переключаются на клиенте. Плитка беднее, поэтому разбираем
список: он несёт всё, кроме года и каталожного номера.

    a.list-item@href      «/catalog/blues/eleven/»      → url + external_id
    h3.list-item-title    «Harry Connick, Jr.»          → артист (отдельным полем!)
    p.item-title          «Eleven»                      → альбом
    div.item-price        «1 500.-»                     → цена
    img@src               resize_cache/300_300_1/…      → обложка (режем ресайз)
    ul.list-item-list li  [лейбл, жанр, формат, состояние, <пусто>]

Пятый `<li>` пуст у всех 2 600 товаров — видимо, зарезервирован под поле,
которое магазин не заполняет. Позиции слотов проверены на четырёх разделах
(2 600 карточек): длина списка всегда 5, слоты 0–3 всегда заполнены.

**Состояние приезжает с листингом** — и это редкость: грейды дискогсовские
(«Very Good Plus (VG+)», «Near Mint (NM or M-)», «Mint (M)»), у каждого
экземпляра свой. Пишем строку как есть, не нормализуя.

Чего в листинге НЕТ: год, каталожный номер, страна, состояние конверта и
полный формат. Всё это лежит на странице товара (`parse_listing`), но ходить
туда за каждым товаром — 2 600 запросов (~87 мин), что не влезает в часовой
потолок обхода. Поэтому по умолчанию каталог берём только с витрины, а
`parse_listing` остаётся для точечной перепроверки и как задел под будущее
обогащение новинок (см. WS5.6 в MARKET_STORES_SCALING.md).

Формат в листинге усечён до первого токена дискогсовской строки: у 765 из 971
товаров rock это просто «Vinyl» (на странице товара — «Vinyl, LP, Album,
Reissue»). То есть LP от 7"/12" по листингу не отличить, `infer_format` вернёт
для них LP. Осознанный компромисс: 16 запросов против 2 600.

Наличия в выдаче нет — магазин б/у, экземпляр один, проданное просто исчезает
из витрины. Всё, что пришло, помечаем `in_stock`, а пропажу ловит общий цикл
(`daily_retire_vanished_listings` по `last_seen_at`).
"""
from __future__ import annotations

import logging
import re
from typing import AsyncIterator
from urllib.parse import urlparse

from bs4 import BeautifulSoup

from app.services.scrapers.base import (
    BaseStoreParser,
    ListingDTO,
    PageErrorBudget,
    ParserError,
    TransientParserError,
)
from app.services.scrapers.extractors import (
    infer_format,
    infer_vinyl_color,
    parse_price,
    parse_year,
)
from app.services.scrapers.registry import register_parser

logger = logging.getLogger(__name__)

_CATALOG_ROOT = "/catalog/"
# Раздел каталога: `/catalog/folk_world_country/`. Товар — на уровень глубже.
_SECTION_HREF_RE = re.compile(r"^/catalog/([a-z0-9_-]+)/$")
_PRODUCT_HREF_RE = re.compile(r"^/catalog/([a-z0-9_-]+/[^/?#]+)/$")

# Размер выдачи раздела. Самый большой раздел — rock, 971 товар; 2000 даёт
# двойной запас. Если раздел всё же перерастёт лимит, витрина покажет
# пагинатор — тогда повторяем запрос с удвоенным count (см. `_fetch_section`).
_SECTION_PAGE_SIZE = 2000
_SECTION_PAGE_SIZE_MAX = 16000

# Слоты `ul.list-item-list li` — порядок стабилен на всех разделах.
_SLOT_LABEL, _SLOT_GENRE, _SLOT_FORMAT, _SLOT_CONDITION = 0, 1, 2, 3

# Дискогсовский грейд: «Very Good Plus (VG+)», «Near Mint (NM or M-)», «Mint (M)».
# Держим отдельно от позиции слота — если магазин перетасует поля, состояние
# всё равно найдётся, а не подменится жанром.
_CONDITION_RE = re.compile(
    r"\b(?:mint|near\s+mint|very\s+good(?:\s+plus)?|good(?:\s+plus)?|fair|poor)\b"
    r"|\((?:M|NM|VG\+?|G\+?|F|P)(?:\s+or\s+M-)?\)",
    re.I,
)

# `/upload/resize_cache/iblock/e02/300_300_1/x.jpeg` → `/upload/iblock/e02/x.jpeg`
_RESIZE_CACHE_RE = re.compile(r"resize_cache/(.*?)/\d+_\d+_\d+/")

# Магазин торгует б/у: пришедшее в выдаче — то, что лежит на полке.
_DEFAULT_STATUS = "in_stock"


@register_parser("long_play")
class LongPlayParser(BaseStoreParser):
    base_url = "https://long-play.ru"
    rate_limit_per_sec = 0.5  # 1 req / 2 c — обход и так 16 запросов
    rate_burst = 2
    requires_js = False
    sitemap_paths: list[str] = []  # витрина полнее карты сайта, см. docstring
    listing_url_pattern = r"/catalog/[a-z0-9_-]+/[^/]+/$"
    stock_from_listing = True  # цена приезжает с обходом каталога

    @property
    def slug(self) -> str:
        return "long_play"

    # ---- Обход каталога по карточкам витрины ----------------------------- #

    async def crawl_full(self, limit: int | None = None) -> AsyncIterator[ListingDTO]:
        budget = PageErrorBudget(self.slug)

        sections = await self._discover_sections(budget)
        if not sections:
            raise TransientParserError(f"{self.slug}: разделы каталога не найдены")

        seen: set[str] = set()
        emitted = 0

        for section in sections:
            html = await self._fetch_section(section, budget)
            if html is None:
                continue

            cards = _extract_cards(html)
            logger.info("[%s] %s: %d карточек", self.slug, section, len(cards))

            for card in cards:
                try:
                    dto = _parse_card(card, self.base_url)
                except Exception:
                    logger.debug(
                        "[%s] карточка не разобралась в %s", self.slug, section,
                        exc_info=True,
                    )
                    continue
                if dto is None or dto.external_id in seen:
                    continue
                seen.add(dto.external_id)
                yield dto
                emitted += 1
                if limit is not None and emitted >= limit:
                    return

        budget.log_summary()
        logger.info(
            "[%s] обход по витрине: %d товаров из %d разделов",
            self.slug, emitted, len(sections),
        )

    async def _discover_sections(self, budget: PageErrorBudget) -> list[str]:
        """Жанровые разделы со страницы `/catalog/`, в порядке появления."""
        html = await self.fetch_page(
            f"{self.base_url}{_CATALOG_ROOT}", budget, page_label="корень каталога",
        )
        if html is None:
            return []

        soup = BeautifulSoup(html, "lxml")
        out: list[str] = []
        for a in soup.find_all("a", href=True):
            m = _SECTION_HREF_RE.match(a["href"].split("?")[0])
            if m and m.group(1) not in out:
                out.append(m.group(1))
        logger.info("[%s] разделов каталога: %d", self.slug, len(out))
        return out

    async def _fetch_section(self, section: str, budget: PageErrorBudget) -> str | None:
        """Раздел целиком одним запросом.

        Пагинатор в ответе означает, что `count` не покрыл раздел, — тогда
        удваиваем и берём заново. Молча отдать первые N товаров нельзя:
        обход выглядел бы успешным, а хвост каталога тихо ушёл бы в
        `daily_retire_vanished_listings` как «пропавший».
        """
        count = _SECTION_PAGE_SIZE
        while count <= _SECTION_PAGE_SIZE_MAX:
            url = f"{self.base_url}{_CATALOG_ROOT}{section}/?count={count}"
            html = await self.fetch_page(
                url, budget, page_label=f"раздел {section} (count={count})",
            )
            if html is None:
                return None
            if not _has_pagination(html):
                return html
            logger.warning(
                "[%s] раздел %s не уместился в count=%d — повторяем с %d",
                self.slug, section, count, count * 2,
            )
            count *= 2

        raise TransientParserError(
            f"{self.slug}: раздел {section} не уместился даже в count={_SECTION_PAGE_SIZE_MAX}"
        )

    # ---- Discovery (для отладки и точечной перепроверки) ----------------- #

    async def discover_urls(self) -> AsyncIterator[str]:
        budget = PageErrorBudget(self.slug)
        for section in await self._discover_sections(budget):
            html = await self._fetch_section(section, budget)
            if html is None:
                continue
            for card in _extract_cards(html):
                href = card.get("href", "").split("?")[0]
                if _PRODUCT_HREF_RE.match(href):
                    yield self.base_url + href

    # ---- Парсинг страницы товара ----------------------------------------- #

    async def parse_listing(self, url: str) -> ListingDTO:
        """Страница товара: то же, что в карточке, плюс год и каталожный номер.

        В ночном обходе не участвует (см. docstring модуля) — нужна для
        точечной перепроверки и детекта 404 → removed.
        """
        html = await self.http.get_text(url)
        soup = BeautifulSoup(html, "lxml")

        props = _extract_properties(soup)
        # `h2.product-title` — артист (ссылка на `/ispolniteli/<id>/`),
        # `h1.product-subtitle` — альбом. Первый `h1` на странице принадлежит
        # шапке заказа, а не товару, поэтому селектор именно по классу.
        artist = _text(soup.select_one("h2.product-title"))
        title = _text(soup.select_one("h1.product-subtitle"))
        if not title:
            raise ParserError(f"no title at {url}")

        price = parse_price(_text(soup.select_one(".item-price")))
        fmt_raw = props.get("Формат") or ""
        color_source = " ".join(filter(None, (fmt_raw, props.get("Стиль"))))

        raw_payload: dict = {}
        for key, prop in (("label", "Лейбл"), ("genre", "Жанр"),
                          ("style", "Стиль"), ("country", "Страна"),
                          ("sleeve_condition", "Состояние конверта")):
            if props.get(prop):
                raw_payload[key] = props[prop]

        external_id = _external_id(url)
        if not external_id:
            raise ParserError(f"не разобрался URL товара: {url}")

        return ListingDTO(
            external_id=external_id,
            url=url,
            title_raw=title,
            artist_raw=artist or None,
            year_raw=parse_year(props.get("Год")),
            format_raw=infer_format(fmt_raw),
            vinyl_color_raw=infer_vinyl_color(color_source, exclude=[artist, title]),
            condition=props.get("Состояние"),
            price_rub=price,
            price_currency="RUB",
            status=_DEFAULT_STATUS if price is not None else "on_request",
            barcode=None,
            catalog_number=props.get("Кат. номер"),
            discogs_release_url=None,
            image_url=_full_size_image(soup, self.base_url),
            raw_payload=raw_payload,
        )


# ---- helpers ------------------------------------------------------------ #


def _extract_cards(html: str) -> list:
    """Карточки панели-списка (`#display-list a.list-item`)."""
    soup = BeautifulSoup(html, "lxml")
    return soup.select("#display-list a.list-item")


def _has_pagination(html: str) -> bool:
    """Пагинатор в ответе = выдача обрезана размером `count`."""
    soup = BeautifulSoup(html, "lxml")
    block = soup.select_one(".pagination")
    return bool(block and block.find("a", href=True))


def _parse_card(card, base_url: str) -> ListingDTO | None:
    """Карточка витрины → ListingDTO. None — карточка без ссылки или названия."""
    href = (card.get("href") or "").split("?")[0]
    external_id = _external_id(href)
    if not external_id:
        return None

    artist = _text(card.select_one(".list-item-title"))
    title = _text(card.select_one(".item-title"))
    if not title:
        return None

    slots = [_text(li) for li in card.select("ul.list-item-list li")]
    label = _slot(slots, _SLOT_LABEL)
    genre = _slot(slots, _SLOT_GENRE)
    fmt = _slot(slots, _SLOT_FORMAT)
    condition = _find_condition(slots)

    price = parse_price(_text(card.select_one(".item-price")))

    raw_payload: dict = {}
    if label:
        raw_payload["label"] = label
    if genre:
        raw_payload["genre"] = genre

    img = card.find("img")
    image = None
    if img and img.get("src"):
        image = base_url + _RESIZE_CACHE_RE.sub(r"\1/", img["src"])

    return ListingDTO(
        external_id=external_id,
        url=base_url + href,
        title_raw=title,
        artist_raw=artist or None,
        year_raw=None,  # года в витрине нет, он только на странице товара
        format_raw=infer_format(fmt),
        # Цвет ищем только в формате: название у б/у переизданий регулярно
        # содержит цвет как слово («Green River», «Красный Свет»).
        vinyl_color_raw=infer_vinyl_color(fmt, exclude=[artist, title]),
        condition=condition,
        price_rub=price,
        price_currency="RUB",
        status=_DEFAULT_STATUS if price is not None else "on_request",
        barcode=None,
        catalog_number=None,
        discogs_release_url=None,
        image_url=image,
        raw_payload=raw_payload,
    )


def _external_id(href: str) -> str | None:
    """`/catalog/blues/eleven/` → `blues/eleven`.

    Числового id в витрине нет (в карте сайта он есть, но она отстаёт), а слаг
    Bitrix при коллизии дополняет самим id (`…-n_1164206`), так что пара
    «раздел + слаг» уникальна внутри магазина.

    Принимает и относительный href (обход витрины), и абсолютный URL
    (`parse_listing`): иначе один и тот же товар получал бы разные
    `external_id` на двух путях и задваивался бы в БД.
    """
    path = urlparse(href or "").path
    m = _PRODUCT_HREF_RE.match(path)
    return m.group(1) if m else None


def _slot(slots: list[str], index: int) -> str | None:
    return slots[index] if index < len(slots) and slots[index] else None


def _find_condition(slots: list[str]) -> str | None:
    """Состояние по грейду, а не по позиции — см. `_CONDITION_RE`."""
    for value in slots:
        if value and _CONDITION_RE.search(value):
            return value
    return None


def _extract_properties(soup: BeautifulSoup) -> dict[str, str]:
    """Характеристики страницы товара → {«Год»: «1992», «Кат. номер»: …}.

    Разметка — не таблица: `.product-info-item` с заголовком в `h3` и значением
    в соседней колонке. Мультизначные поля («Стиль») лежат ссылками через
    запятую, `_text` склеивает их в « Big Band , Swing » — запятые чистим.
    """
    out: dict[str, str] = {}
    for item in soup.select(".product-info-item"):
        key_node = item.select_one("h3")
        value_node = item.select_one(".col-xs-9")
        if not key_node or not value_node:
            continue
        key = _text(key_node).rstrip(":")
        value = re.sub(r"\s+,", ",", _text(value_node))
        if key and value and key not in out:
            out[key] = value
    return out


def _full_size_image(soup: BeautifulSoup, base_url: str) -> str | None:
    """Страница товара отдаёт оригинал (`/upload/iblock/…`), но ресайз всё
    равно срезаем — на случай если шаблон когда-нибудь начнёт его подставлять."""
    img = soup.select_one(".pic-wrap img, .pic-wrapper img, img.pic")
    src = img.get("src") if img else None
    if not src:
        og = soup.find("meta", property="og:image")
        src = og.get("content") if og else None
    if not src:
        return None
    src = _RESIZE_CACHE_RE.sub(r"\1/", src.strip())
    return src if src.startswith("http") else base_url + src


def _text(node) -> str:
    if node is None:
        return ""
    return re.sub(r"\s+", " ", node.get_text(" ", strip=True)).strip()
