"""
Базовый интерфейс парсера магазина.

Каждый магазин = подкласс BaseStoreParser в `shops/<slug>.py`.
"""
from __future__ import annotations

import asyncio
import logging
import math
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


# ---- Бюджет ошибок постраничного обхода --------------------------------- #

class PageErrorBudget:
    """Позволяет пропустить единичную сбойную страницу, но не потерять каталог.

    До 08-11 любая ошибка фетча рвала весь обход: один HTTP 500 на 29-й
    странице из 114 стоил doctorhead'у суток данных (взято 812 из 3548).
    Обратный вариант — глушить ошибки — ещё хуже: обход молча заканчивается
    на середине, а магазин помечается успешным (инцидент 08-10).

    Компромисс: пропускаем страницу, но считаем пропуски. Рвём обход, если
      * `max_consecutive` страниц подряд не отдались — сайт лёг, дальше
        долбить бессмысленно;
      * доля пропусков превысила `max_error_ratio` от пройденных страниц
        (но не раньше `min_allowance` — на коротких каталогах ratio слишком
        нервный: 3% от 24 страниц rotaryrecords это ноль).
    """

    def __init__(
        self,
        label: str,
        *,
        max_error_ratio: float = 0.05,
        min_allowance: int = 3,
        max_consecutive: int = 3,
    ) -> None:
        self.label = label
        self.max_error_ratio = max_error_ratio
        self.min_allowance = min_allowance
        self.max_consecutive = max_consecutive
        self.attempted = 0
        self.failed = 0
        self.consecutive = 0
        self.skipped_pages: list[str] = []

    @property
    def allowance(self) -> int:
        """Сколько пропусков допустимо при текущем числе пройденных страниц."""
        return max(self.min_allowance, math.ceil(self.attempted * self.max_error_ratio))

    def record_success(self) -> None:
        self.attempted += 1
        self.consecutive = 0

    def record_failure(self, page_label: str, exc: BaseException) -> None:
        """Учесть сбойную страницу. Бросает TransientParserError при исчерпании."""
        self.attempted += 1
        self.failed += 1
        self.consecutive += 1
        self.skipped_pages.append(page_label)

        if self.consecutive >= self.max_consecutive:
            raise TransientParserError(
                f"{self.label}: {self.consecutive} страниц подряд не отдались "
                f"(последняя — {page_label}): {exc}"
            ) from exc
        if self.failed > self.allowance:
            raise TransientParserError(
                f"{self.label}: пропущено {self.failed} страниц из {self.attempted} "
                f"при лимите {self.allowance} (последняя — {page_label}): {exc}"
            ) from exc

        logger.warning(
            "[%s] страница пропущена (%d/%d в бюджете): %s — %s",
            self.label, self.failed, self.allowance, page_label, exc,
        )

    def log_summary(self) -> None:
        if self.failed:
            logger.warning(
                "[%s] обход завершён с пропусками: %d из %d страниц (%s)",
                self.label, self.failed, self.attempted,
                ", ".join(self.skipped_pages[:10]),
            )


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

    # Потолок на ОДНУ страницу каталога, секунды. Клиентский таймаут (90 с)
    # перемножается с ретраями, поэтому без этой отсечки страница может держать
    # обход десять минут (stoprobotvinyl, 08-12). 120 с — щедро: самая тяжёлая
    # страница в маркете (plastinka, 200 карточек, ~317 KB) отдаётся за секунды.
    #
    # Цена решения: при HTTP 429 клиент честно спит по Retry-After (до 300 с), и
    # дедлайн такую паузу оборвёт — страница уйдёт в пропуск вместо вежливого
    # ожидания. Осознанно: за 72 ч логов в маркете ни одного 429/503, а
    # per-domain token bucket (0.5 req/s) и так не даёт нам долбить магазин.
    # Если 429 появятся — поднимать здесь, а не убирать дедлайн.
    page_deadline_sec: float = 120.0

    # Потолок на весь обход магазина, секунды. Ночное окно 3 часа делится между
    # магазинами, и один тормозящий не должен съесть его целиком.
    #
    # Замер 08-12: самый долгий обход в маркете — skifmusic, 688 страниц,
    # 1372 c (22.9 мин). Час даёт запас 2.6× — магазин может вырасти в два с
    # половиной раза, прежде чем упрётся. Следующий кандидат на пересмотр
    # именно skifmusic: если его каталог перевалит за ~50 000 позиций, потолок
    # поднимать (и сверяться с elapsed_sec в логах, а не с этим комментарием).
    max_crawl_seconds: float = 3600.0

    def __init__(self, http: ScraperHttpClient, browser: BrowserPool | None = None) -> None:
        if not self.slug or not self.base_url:
            raise RuntimeError(f"{type(self).__name__}: slug/base_url must be set")
        self.http = http
        self.browser = browser

    # ---- Постраничный фетч с бюджетом ошибок ---------------------------- #

    async def fetch_page(
        self,
        url: str,
        budget: PageErrorBudget,
        *,
        page_label: str,
        respect_robots: bool = True,
        retries: int = 3,
        second_chance_delay: float = 5.0,
        deadline_sec: float | None = None,
    ) -> str | None:
        """GET страницы каталога. Возвращает None, если страницу решено пропустить.

        Две ступени защиты от флака:
          1. `retries` внутри http_client — быстрые попытки с backoff 1/2/4 c;
          2. вторая попытка через `second_chance_delay` — Bitrix-овые 500 на
             doctorhead отпускают за секунды, а первая серия ретраев успевает
             уложиться в 7 с и упереться в ту же ошибку.

        Обе ступени ограничены `deadline_sec` (по умолчанию `page_deadline_sec`
        класса). Без потолка ретраи перемножаются с 90-секундным таймаутом
        клиента: в ночь 08-12 одна AJAX-страница stoprobotvinyl держала обход
        ~10 минут. Дедлайн ставим на КАЖДУЮ ступень, а не на весь метод: иначе
        вторая попытка получала бы остаток времени первой и была бы бесполезна.

        ParserBlocked/ParserNeedsBrowser не пропускаем: это не флак, а смена
        режима доступа, её должен увидеть runner.
        """
        limit = self.page_deadline_sec if deadline_sec is None else deadline_sec

        for is_second_chance in (False, True):
            try:
                text = await asyncio.wait_for(
                    self.http.get_text(
                        url, respect_robots=respect_robots, retries=retries
                    ),
                    timeout=limit,
                )
                budget.record_success()
                return text
            except ParserBlocked:
                raise
            except Exception as e:
                if isinstance(e, asyncio.TimeoutError):
                    e = TransientParserError(f"страница не уложилась в {limit:.0f} c")
                if not is_second_chance:
                    logger.debug(
                        "[%s] %s не отдалась, вторая попытка через %.0f c: %s",
                        self.slug, page_label, second_chance_delay, e,
                    )
                    await asyncio.sleep(second_chance_delay)
                    continue
                budget.record_failure(page_label, e)
                return None
        return None

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
