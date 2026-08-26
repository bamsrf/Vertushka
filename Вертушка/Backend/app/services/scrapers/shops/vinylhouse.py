"""Парсер «Дом Винила» (vinylhouse.ru) — CS-Cart, б/у оригиналы, СПб.

Найден ресерчем 26.08 (скрипт-разведчик + ручной осмотр). Особенности:

- ~10 000 товаров по sitemap; артист, ГОД и альбом лежат в структурированном
  тайтле карточки листинга: «AC/DC – 1976 – Dirty Deeds Done Dirt Cheap –
  Atlantic — Виниловая пластинка» (en-dash между полями, em-dash перед
  форматом). Год в карточке — редкость для маркета и главный сигнал для
  store-native gate.
- robots.txt запрещает ВСЕ query-параметры (`/*?*`) — никакой `?count=N`.
  Пагинация только путём `/page-N/` (штатная для CS-Cart), последняя страница
  видна в пагинаторе первой же страницы, поэтому за конец каталога (404) мы
  не заходим вовсе.
- WAF отдаёт 403 на «голые» не-браузерные запросы — наш ua_pool проходит.
- Б/у: проданное исчезает с витрины → `stock_from_listing = True`, судьбу
  пропавших решает `daily_retire_vanished_listings`.
- `external_id` — числовой product_id CS-Cart (виден в каждой карточке).
  Товар может быть в нескольких категориях под разными URL — по product_id
  дедуп надёжен, URL для этого НЕ годится (перенос в другую категорию =
  другой URL, тот же product_id).
- Грейды Discogs-словаря («Состояние: конверт Near Mint пластинки Near Mint»)
  — только на странице товара; ночной обход туда не ходит (паттерн WS5.6,
  как год у long-play). `parse_listing` написан и готов к дообогащению.
"""
from __future__ import annotations

import logging
import re
from decimal import Decimal, InvalidOperation
from typing import AsyncIterator

from bs4 import BeautifulSoup, Tag

from app.services.scrapers.base import (
    BaseStoreParser,
    ListingDTO,
    PageErrorBudget,
    ParserError,
    TransientParserError,
)
from app.services.scrapers.registry import register_parser

logger = logging.getLogger(__name__)

# Категории верхнего меню, которые не являются музыкой.
# memorabilia — сувениры/мерч; dom-vinyla — витрина бренда без товаров
# (осмотр 26.08: ноль карточек), держим в блэклисте, чтобы не жечь запрос.
_EXCLUDED_CATEGORIES = {"memorabilia", "dom-vinyla"}

# /category/ или /category/subcategory/ — относительный путь без домена.
_CATEGORY_PATH_RE = re.compile(r"^/([a-z0-9-]+)(?:/([a-z0-9-]+))?/$")

# Ссылки пагинации CS-Cart: .../page-7/
_PAGE_HREF_RE = re.compile(r"/page-(\d+)/")

# product_id из формы карточки: product_data[29959][product_id]
_PRODUCT_ID_RE = re.compile(r"product_data\[(\d+)\]")

# Превью 150×150 → полноразмер: убираем /thumbnails/<w>/<h>
_THUMBNAIL_RE = re.compile(r"/thumbnails/\d+/\d+")

# Тайтл: «Артист – 1976 – Альбом [– Издание] — Формат».
# Поля разделены en-dash с пробелами (дефисы внутри «AC/DC», «Jay-Z» не
# страдают), формат отделён em-dash.
_FIELD_SEP = " – "     # en dash
_FORMAT_SEP = " — "    # em dash
_YEAR_RE = re.compile(r"^(1[89]\d{2}|20\d{2})$")

# Хвост тайтла, который подтверждает «это носитель, а не мерч».
_MEDIA_TAIL_RE = re.compile(r"пластинк|сингл|винил|дюйм|\bLP\b|\bEP\b", re.I)

_MAX_PAGES_PER_CATEGORY = 200  # предохранитель: 200 × 12 = 2 400 позиций


def _parse_title(raw: str) -> tuple[str | None, int | None, str | None, str | None]:
    """(artist, year, album, format_tail) из тайтла карточки.

    «1989 Australian Rocks – 1989 — Виниловая пластинка» — артист с цифрами
    в имени и без альбома: год распознаём только как ОТДЕЛЬНОЕ поле.
    """
    head, _, tail = raw.partition(_FORMAT_SEP)
    format_tail = tail.strip() or None

    parts = [p.strip() for p in head.split(_FIELD_SEP) if p.strip()]
    if not parts:
        return None, None, None, format_tail

    artist: str | None = parts[0]
    year: int | None = None
    album: str | None = None

    if len(parts) >= 2 and _YEAR_RE.match(parts[1]):
        year = int(parts[1])
        album = _FIELD_SEP.join(parts[2:]) or None
    elif len(parts) >= 2:
        album = _FIELD_SEP.join(parts[1:])

    return artist, year, album, format_tail


def _clean_price(text: str) -> Decimal | None:
    digits = re.sub(r"[^\d.]", "", text.replace("\xa0", "").replace(" ", ""))
    if not digits:
        return None
    try:
        price = Decimal(digits)
    except InvalidOperation:
        return None
    return price if price > 0 else None


def _full_image(src: str | None) -> str | None:
    if not src:
        return None
    return _THUMBNAIL_RE.sub("", src)


def _extract_cards(soup: BeautifulSoup) -> list[Tag]:
    return soup.find_all("div", class_="ty-grid-list__item")


def _parse_card(card: Tag) -> ListingDTO | None:
    link = card.find("a", class_="product-title")
    if link is None or not link.get("href"):
        return None
    title_raw = link.get_text(strip=True)
    if not title_raw:
        return None

    m = _PRODUCT_ID_RE.search(str(card))
    if not m:
        # Без product_id карточка бесполезна: URL-фолбэк наплодил бы дубли
        # при переносе товара между категориями.
        return None
    external_id = m.group(1)

    artist, year, album, format_tail = _parse_title(title_raw)

    # Мерч-фильтр: явный не-носитель пропускаем, отсутствие хвоста прощаем.
    if format_tail and not _MEDIA_TAIL_RE.search(format_tail):
        return None

    price: Decimal | None = None
    for span in card.find_all("span", class_="ty-price-num"):
        price = _clean_price(span.get_text())
        if price is not None:
            break

    img = card.find("img", class_="ty-pict")

    return ListingDTO(
        external_id=external_id,
        url=link["href"],
        title_raw=title_raw,
        artist_raw=artist,
        year_raw=year,
        format_raw=format_tail,
        price_rub=price,
        status="in_stock" if price is not None else "on_request",
        image_url=_full_image(img.get("src") if img else None),
        raw_payload={"album": album} if album else {},
    )


def _max_page(html: str) -> int:
    pages = [int(n) for n in _PAGE_HREF_RE.findall(html)]
    return max(pages) if pages else 1


def _category_paths(anchors) -> list[str]:
    """Относительные пути категорий из набора <a>-тегов."""
    out: list[str] = []
    for a in anchors:
        href = a.get("href") or ""
        path = href.split("vinylhouse.ru", 1)[-1] if "vinylhouse.ru" in href else href
        m = _CATEGORY_PATH_RE.match(path)
        if not m:
            continue
        if m.group(1) in _EXCLUDED_CATEGORIES:
            continue
        if path not in out:
            out.append(path)
    return out


@register_parser("vinylhouse")
class VinylhouseParser(BaseStoreParser):
    slug = "vinylhouse"
    base_url = "https://vinylhouse.ru"
    stock_from_listing = True
    listing_url_pattern = r"/[a-z0-9-]+/[a-z0-9-]+/$"

    # ---- Обход каталога --------------------------------------------------- #

    async def crawl_full(self, limit: int | None = None) -> AsyncIterator[ListingDTO]:
        budget = PageErrorBudget(self.slug)

        queue = await self._discover_categories(budget)
        if not queue:
            raise TransientParserError(f"{self.slug}: категории каталога не найдены")

        seen: set[str] = set()
        visited: set[str] = set()
        emitted = 0

        while queue:
            path = queue.pop(0)
            if path in visited:
                continue
            visited.add(path)

            page = 1
            last_page = 1
            while page <= last_page and page <= _MAX_PAGES_PER_CATEGORY:
                suffix = "" if page == 1 else f"page-{page}/"
                html = await self.fetch_page(
                    f"{self.base_url}{path}{suffix}", budget,
                    page_label=f"{path} стр. {page}",
                )
                if html is None:
                    page += 1
                    continue

                last_page = max(last_page, _max_page(html))
                soup = BeautifulSoup(html, "lxml")

                if page == 1:
                    # Подкатегории (Beatles → соло-разделы): родительская
                    # страница CS-Cart их товары НЕ показывает. Разметка:
                    # <ul class="subcategories"><li class="ty-subcategories__item"><a …>
                    # Селектор по контейнеру: первый прогон 26.08 промахнулся
                    # мимо префикса ty- на <li> и потерял 3.5k позиций.
                    subs = soup.select("ul.subcategories a[href]")
                    for sub in _category_paths(subs):
                        if sub not in visited:
                            queue.append(sub)

                cards = _extract_cards(soup)
                for card in cards:
                    try:
                        dto = _parse_card(card)
                    except Exception:
                        logger.debug(
                            "[%s] карточка не разобралась на %s стр. %d",
                            self.slug, path, page, exc_info=True,
                        )
                        continue
                    if dto is None or dto.external_id in seen:
                        continue
                    seen.add(dto.external_id)
                    yield dto
                    emitted += 1
                    if limit is not None and emitted >= limit:
                        return
                page += 1

        budget.log_summary()
        logger.info(
            "[%s] обход по витрине: %d товаров из %d категорий",
            self.slug, emitted, len(visited),
        )

    async def _discover_categories(self, budget: PageErrorBudget) -> list[str]:
        """Категории верхнего меню с главной страницы."""
        html = await self.fetch_page(
            f"{self.base_url}/", budget, page_label="главная (меню категорий)",
        )
        if html is None:
            return []
        soup = BeautifulSoup(html, "lxml")
        cats = _category_paths(soup.find_all("a", class_="ty-menu__item-link"))
        logger.info("[%s] категорий в меню: %d", self.slug, len(cats))
        return cats

    # ---- Страница товара (для дообогащения, в ночном обходе не участвует) - #

    _CONDITION_RE = re.compile(
        r"Состояни[ея]\s*:?\s*конверт[а]?\s*[—:-]?\s*(?P<sleeve>[^,<]+?)"
        r"\s+пластинки?\s*[—:-]?\s*(?P<media>[A-Za-z+ -]+)",
        re.I,
    )

    async def parse_listing(self, url: str) -> ListingDTO:
        budget = PageErrorBudget(self.slug)
        html = await self.fetch_page(url, budget, page_label=f"товар {url}")
        if html is None:
            raise TransientParserError(f"{self.slug}: страница товара не отдалась: {url}")

        soup = BeautifulSoup(html, "lxml")

        title_el = soup.find("h1")
        title_raw = title_el.get_text(strip=True) if title_el else ""
        if not title_raw:
            raise ParserError(f"{self.slug}: нет тайтла на {url}")

        m = _PRODUCT_ID_RE.search(html)
        if not m:
            raise ParserError(f"{self.slug}: нет product_id на {url}")

        artist, year, album, format_tail = _parse_title(title_raw)

        price: Decimal | None = None
        for span in soup.find_all("span", class_="ty-price-num"):
            price = _clean_price(span.get_text())
            if price is not None:
                break

        condition: str | None = None
        cm = self._CONDITION_RE.search(soup.get_text(" ", strip=True))
        if cm:
            condition = (
                f"пластинка {cm.group('media').strip()} / "
                f"конверт {cm.group('sleeve').strip()}"
            )

        # «В наличии» — точный span (id="in_stock_info_<pid>"); строка
        # «Нет в наличии» на живой странице встречается только в JS-словаре
        # темы (text_out_of_stock), по тексту страницы судить нельзя.
        in_stock = soup.find("span", class_="ty-qty-in-stock") is not None

        img = soup.find("img", class_="ty-pict")

        return ListingDTO(
            external_id=m.group(1),
            url=url,
            title_raw=title_raw,
            artist_raw=artist,
            year_raw=year,
            format_raw=format_tail,
            condition=condition,
            price_rub=price,
            status="in_stock" if (in_stock and price is not None) else "out_of_stock",
            image_url=_full_image(img.get("src") if img else None),
            raw_payload={"album": album} if album else {},
        )
