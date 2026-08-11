"""
Парсер Rotary Records (rotaryrecords.store) — небольшой магазин б/у винила.
Каталог ~1 800 позиций (по состоянию на 2026-08-10).

Самый дешёвый магазин в маркете: **24 запроса на весь каталог**.

Витрина рендерится на клиенте (`/catalog-app.js`), в HTML товаров нет —
данные идут из собственного JSON-API магазина:

    GET /catalog-api.php?action=page&featured=all&offset=N&limit=80
    → {"ok":true,"total":1804,"has_more":true,"cards":[...]}

Карточка отдаёт всё, что нам нужно:

    id       «60740323-7a12-11f1-0a80-0da4000f0192» → external_id (uuid)
    url      «/record/{uuid}/various-smash-hits-the-80s»
    title    «Various - Smash Hits The 80s»          → артист и альбом
    subtitle «Rhino Records • 2017»                  → лейбл и год
    styles   «Pop Rock, Synth-pop, …»                → жанры в raw_payload
    price    «5 900 ₽»
    images   {thumb, base, jpeg_srcset, webp_srcset}

Почему НЕ ходим на страницу товара: она добавляет только формат и состояние,
а они у магазина константы. Проверено на 13 карточках из разных партий
каталога — везде «LP • Vinyl» и «> VG+». Это политика магазина («не хуже
VG+»), а не грейдинг конкретного экземпляра.

`limit` сервер обрезает до 80 независимо от запрошенного (пробовали 100/500/2000).

Наличия в ответе нет: магазин б/у, экземпляр один, проданное просто исчезает
из выдачи. Поэтому всё, что пришло, — `in_stock`, а пропажу ловит обычный
цикл (листинг перестал приходить → протухает по last_seen_at).

Обложки лежат в `/images/discogs_synced/` — магазин синхронизируется с Discogs,
но release id наружу не отдаёт: в поисковом индексе (`action=index`) есть
внутренний SKU «04103» и номер вида «2000000041674», который выглядит как EAN,
но это внутренняя нумерация (префикс 200000 — «для внутреннего использования»),
в barcode её писать нельзя. Матчинг идёт по artist+title.
"""
from __future__ import annotations

import json
import logging
import re
from typing import AsyncIterator

from app.services.scrapers.base import (
    BaseStoreParser,
    ListingDTO,
    PageErrorBudget,
    TransientParserError,
)
from app.services.scrapers.extractors import (
    parse_price,
    parse_year,
    infer_format,
    infer_vinyl_color,
)
from app.services.scrapers.registry import register_parser

logger = logging.getLogger(__name__)


_API_PATH = "/catalog-api.php"
# URL товара: /record/{uuid}/{slug}
_URL_ID_RE = re.compile(r"/record/([0-9a-f-]{16,})/", re.I)
# «Rhino Records • 2017» — лейбл и год через bullet.
_SUBTITLE_RE = re.compile(r"^(?P<label>.*?)\s*•\s*(?P<year>\d{4})\s*$")
# «Various - Smash Hits The 80s»: артист до первого « - ».
_TITLE_SPLIT_RE = re.compile(r"\s+[-–—]\s+")

# Состояние и формат у магазина одинаковые для всего каталога (13/13 в выборке).
_STORE_CONDITION = "> VG+"


@register_parser("rotaryrecords")
class RotaryRecordsParser(BaseStoreParser):
    base_url = "https://rotaryrecords.store"
    rate_limit_per_sec = 0.5  # 1 req per 2s — магазин маленький, не долбим
    rate_burst = 2
    requires_js = False
    sitemap_paths: list[str] = []  # витрина на JS, каталог только через API
    listing_url_pattern = r"/record/[0-9a-f-]{16,}/"
    stock_from_listing = True  # каталог = то, что в наличии

    # Сервер режет limit до 80 при любом запрошенном значении.
    catalog_page_size: int = 80
    # Потолок страниц: 1804/80 ≈ 23, берём кратный запас.
    max_pages: int = 200

    @property
    def slug(self) -> str:
        return "rotaryrecords"

    # ---- Обход каталога через JSON-API ----------------------------------- #

    async def crawl_full(self, limit: int | None = None) -> AsyncIterator[ListingDTO]:
        seen: set[str] = set()
        emitted = 0
        async for card in self._iter_cards():
            try:
                dto = self.parse_card(card)
            except Exception:
                logger.debug("[%s] parse_card failed for %s",
                             self.slug, card.get("url"), exc_info=True)
                continue
            if dto is None or dto.external_id in seen:
                continue
            seen.add(dto.external_id)
            yield dto
            emitted += 1
            if limit is not None and emitted >= limit:
                return
        logger.info("[%s] обход по API: %d товаров", self.slug, emitted)

    async def _iter_cards(self) -> AsyncIterator[dict]:
        """Постранично тянет каталог. Yields card-dict'ы."""
        offset = 0
        total: int | None = None
        budget = PageErrorBudget(self.slug)
        for _ in range(self.max_pages):
            url = (
                f"{self.base_url}{_API_PATH}?action=page&featured=all"
                f"&offset={offset}&limit={self.catalog_page_size}"
            )
            text = await self.fetch_page(
                url, budget, page_label=f"offset={offset}", respect_robots=False,
            )
            if text is None:
                # Пропуск ≠ конец каталога: сдвигаем окно и идём дальше.
                offset += self.catalog_page_size
                if total is not None and offset >= total:
                    break
                continue

            try:
                data = json.loads(text)
            except json.JSONDecodeError as e:
                raise TransientParserError(f"non-JSON ответ API на offset={offset}") from e

            cards = data.get("cards") or []
            if not cards:
                budget.log_summary()
                return

            if total is None:
                total = int(data.get("total") or 0)
                logger.info("[%s] каталог: %d позиций, ~%d запросов",
                            self.slug, total,
                            (total // self.catalog_page_size + 1) if total else 0)

            for c in cards:
                yield c

            if not data.get("has_more"):
                budget.log_summary()
                return
            offset += len(cards)

    async def refresh_urls(
        self, urls: list[str]
    ) -> AsyncIterator[tuple[str, ListingDTO | None]]:
        """Один проход каталога, ответ всем url'ам из памяти.

        Нет в каталоге → None (экземпляр продан). Страницы товара у магазина
        живут и после продажи, так что 404-детект бесполезен — судим по выдаче.
        """
        catalog: dict[str, dict] = {}
        async for card in self._iter_cards():
            ext_id = _extract_id_from_url(str(card.get("url") or ""))
            if ext_id:
                catalog[ext_id] = card

        for url in urls:
            ext_id = _extract_id_from_url(url)
            card = catalog.get(ext_id) if ext_id else None
            if card is None:
                yield url, None
                continue
            try:
                dto = self.parse_card(card)
            except Exception:
                logger.debug("[%s] refresh parse_card failed for %s",
                             self.slug, url, exc_info=True)
                continue
            if dto is not None:
                yield url, dto

    async def parse_listing(self, url: str) -> ListingDTO:
        # Каталог приходит из API целиком; страница товара не даёт ничего сверх.
        raise NotImplementedError(
            f"{type(self).__name__} parses via catalog API, not per-URL"
        )

    # ---- Разбор карточки -------------------------------------------------- #

    def parse_card(self, card: dict) -> ListingDTO | None:
        """Карточка из `cards[]` → ListingDTO. None = пропустить."""
        url_path = str(card.get("url") or "")
        external_id = str(card.get("id") or "").strip() or _extract_id_from_url(url_path)
        if not external_id or not url_path:
            return None

        raw_title = str(card.get("title") or "").strip()
        if not raw_title:
            return None
        artist, album = _split_artist_album(raw_title)

        label, year = _parse_subtitle(str(card.get("subtitle") or ""))
        styles = str(card.get("styles") or "").strip() or None

        price = parse_price(str(card.get("price") or ""))

        images = card.get("images") or {}
        image = images.get("base") or images.get("thumb") if isinstance(images, dict) else None
        if image and image.startswith("/"):
            image = f"{self.base_url}{image}"

        # Формат в карточке не приходит; у магазина весь каталог — LP (13/13
        # в выборке). Название всё же прогоняем: вдруг попадётся «(2LP)».
        format_raw = infer_format(raw_title) or "LP"

        return ListingDTO(
            external_id=external_id,
            url=f"{self.base_url}{url_path}" if url_path.startswith("/") else url_path,
            title_raw=album,
            artist_raw=artist,
            year_raw=year,
            format_raw=format_raw,
            vinyl_color_raw=infer_vinyl_color(raw_title, exclude=[artist, album]),
            # Константа магазина, а не грейдинг экземпляра — см. docstring.
            condition=_STORE_CONDITION,
            price_rub=price,
            price_currency="RUB",
            status="in_stock" if price is not None else "on_request",
            # Внутренняя нумерация магазина за EAN не выдаётся — см. docstring.
            barcode=None,
            catalog_number=None,
            discogs_release_url=None,
            image_url=image,
            raw_payload={
                "rotary_external_id": external_id,
                "label": label,
                "styles": styles,
            },
        )


# ---- helpers ------------------------------------------------------------- #


def _extract_id_from_url(url: str) -> str | None:
    m = _URL_ID_RE.search(url or "")
    return m.group(1) if m else None


def _split_artist_album(title: str) -> tuple[str | None, str]:
    """«Various - Smash Hits The 80s» → («Various», «Smash Hits The 80s»).

    Режем по ПЕРВОМУ разделителю: у магазина попадаются сплит-релизы вида
    «Dick Jordan/Jack Hammer - I Want Her Back/Twist In The Morning», где слэши
    есть и в артисте, и в альбоме, но дефис-разделитель один.
    """
    parts = _TITLE_SPLIT_RE.split(title, maxsplit=1)
    if len(parts) == 2 and parts[0].strip() and parts[1].strip():
        return parts[0].strip(), parts[1].strip()
    return None, title.strip()


def _parse_subtitle(subtitle: str) -> tuple[str | None, int | None]:
    """«Rhino Records • 2017» → («Rhino Records», 2017)."""
    m = _SUBTITLE_RE.match(subtitle.strip())
    if m:
        return (m.group("label").strip() or None), int(m.group("year"))
    return (subtitle.strip() or None), parse_year(subtitle)
