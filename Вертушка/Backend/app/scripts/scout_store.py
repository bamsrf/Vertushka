"""Скрипт-разведчик нового магазина-кандидата (WS4.1, MARKET_STORES_SCALING §6).

Запуск:
    cd Backend && python -m app.scripts.scout_store <domain>
    # например: python -m app.scripts.scout_store long-play.ru

За 3–7 вежливых запросов (пауза ~1.2 с между ними, браузерный UA, таймауты)
собирает «паспорт» кандидата и печатает его в stdout:

  1. robots.txt — Disallow-паттерны; отдельно помечаются /*PAGEN*, широкий
     запрет query (`/*?*`) и запрет каталога целиком (урок long-play:
     PAGEN запрещён, а `?count=N` — нет).
  2. CMS по маркерам главной: bitrix/ → Bitrix; t_store_init / tildaapi →
     Tilda; /collection/ + insales → InSales; wa-data/ → Shop-Script;
     cdn.shopify → Shopify; иначе самопис/SPA.
  3. Если Tilda — дёргает store.tildaapi.com getproductslist с recid /
     storepartuid из HTML и проверяет total > 0 (урок domkultury: total=0 =
     лендинг без каталога).
  4. Фиды: /yml.xml, /yandex_market.xml, /export/yml.xml, /products.json —
     с детектом soft-404 (страница-200 с HTML вместо XML/JSON).
  5. sitemap.xml — индекс или плоский, сколько URL, паттерны путей. Размер
     по sitemap помечается «ненадёжно» (урок long-play: 16k → 2 627 → 4 453).

Никаких записей в БД. Никакой тяжёлой обвязки scrapers/http_client —
разведчику на один прогон не нужны токен-бакеты и брейкеры, хватает httpx
напрямую + пауз между запросами.
"""
from __future__ import annotations

import asyncio
import json
import re
import sys
import time
from collections import Counter
from dataclasses import dataclass, field
from urllib.parse import urlparse

import httpx

# ---------------------------------------------------------------------------
# Константы сети
# ---------------------------------------------------------------------------

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36"
)
HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept": (
        "text/html,application/xhtml+xml,application/xml;q=0.9,"
        "image/avif,image/webp,*/*;q=0.8"
    ),
    "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
}
REQUEST_TIMEOUT = 15.0
PAUSE_BETWEEN_REQUESTS = 1.2  # секунд; вежливость важнее скорости

TILDA_STORE_API = "https://store.tildaapi.com/api/getproductslist/"

FEED_PATHS_YML = ["/yml.xml", "/yandex_market.xml", "/export/yml.xml"]
FEED_PATH_PRODUCTS_JSON = "/products.json"


# ---------------------------------------------------------------------------
# Чистые функции разбора (покрыты tests/test_scout_store.py, без сети)
# ---------------------------------------------------------------------------


@dataclass
class RobotsReport:
    """Что интересного нашлось в robots.txt (для группы User-agent: *)."""

    disallow: list[str] = field(default_factory=list)
    sitemaps: list[str] = field(default_factory=list)
    pagen_blocked: bool = False       # /*PAGEN* — штатная пагинация закрыта
    query_blocked: bool = False       # /*?* — широкий запрет query-параметров
    catalog_blocked: bool = False     # /catalog|/shop|/store|/collection
    full_blocked: bool = False        # Disallow: / — весь сайт закрыт


def parse_robots(text: str) -> RobotsReport:
    """Разбирает robots.txt: правила берём из групп `User-agent: *`,
    Sitemap-директивы — отовсюду (по спеке они глобальные)."""
    report = RobotsReport()
    in_star_group = False
    for raw_line in text.splitlines():
        line = raw_line.split("#", 1)[0].strip()
        if not line or ":" not in line:
            continue
        key, _, value = line.partition(":")
        key = key.strip().lower()
        value = value.strip()
        if key == "user-agent":
            in_star_group = value == "*"
            continue
        if key == "sitemap" and value:
            report.sitemaps.append(value)
            continue
        if key == "disallow" and in_star_group and value:
            report.disallow.append(value)
    for pattern in report.disallow:
        upper = pattern.upper()
        if "PAGEN" in upper:
            report.pagen_blocked = True
        # Широкий запрет query: "/*?*", "/*?", "*?*" и т.п. — только
        # спецсимволы, без конкретного имени параметра.
        if "?" in pattern and not re.search(r"[A-Za-z0-9]", pattern):
            report.query_blocked = True
        if pattern == "/":
            report.full_blocked = True
        if re.match(r"^/(catalog|shop|store|collection)(/|\*|$)", pattern, re.I):
            report.catalog_blocked = True
    return report


CMS_BITRIX = "Bitrix"
CMS_TILDA = "Tilda"
CMS_INSALES = "InSales"
CMS_SHOPSCRIPT = "Shop-Script"
CMS_SHOPIFY = "Shopify"
CMS_UNKNOWN = "самопис/SPA"


def detect_cms(html: str) -> str:
    """CMS по маркерам главной страницы. Порядок проверок важен: маркеры
    Bitrix (`/bitrix/`) не встречаются на чужих CMS, а вот `/collection/`
    без insales — ещё ничего не значит."""
    low = html.lower()
    if "/bitrix/" in low:
        return CMS_BITRIX
    if "t_store_init" in low or "tildaapi" in low or "tildacdn" in low:
        return CMS_TILDA
    if "insales" in low and "/collection/" in low:
        return CMS_INSALES
    if "wa-data/" in low:
        return CMS_SHOPSCRIPT
    if "cdn.shopify" in low:
        return CMS_SHOPIFY
    return CMS_UNKNOWN


_TILDA_RECID_RE = re.compile(r"t_store_init\w*\(\s*['\"](\d+)['\"]")
_TILDA_STOREPART_RE = re.compile(r"storepart\w*['\"]?\s*[:=]\s*['\"](\d+)['\"]")


def extract_tilda_store_params(html: str) -> tuple[str, str] | None:
    """(recid, storepartuid) из вызова t_store_init('<recid>', {...
    storepart:'<uid>' ...}) в HTML витрины. None — store-блока нет вообще
    (Tilda-лендинг без каталога)."""
    recid_m = _TILDA_RECID_RE.search(html)
    if not recid_m:
        return None
    part_m = _TILDA_STOREPART_RE.search(html)
    return recid_m.group(1), part_m.group(1) if part_m else ""


def looks_like_html(content_type: str, body: str) -> bool:
    """Детект soft-404: ждали XML/JSON, а пришла HTML-страница с кодом 200.
    Урок newartstore.ru — «все пути отдают главную»."""
    if "text/html" in content_type.lower():
        return True
    head = body.lstrip()[:200].lower()
    return head.startswith(("<!doctype", "<html", "<head", "<body"))


_OFFER_RE = re.compile(r"<offer[\s>]", re.I)


def count_yml_offers(content_type: str, body: str) -> int | None:
    """Число <offer> в YML-фиде. None — это не YML (в т.ч. soft-404).
    Считаем findall'ом, не строками: фиды приходят и одной строкой."""
    if looks_like_html(content_type, body):
        return None
    low = body.lower()
    if "<yml_catalog" not in low and "<offers" not in low:
        return None
    return len(_OFFER_RE.findall(body))


def count_products_json(content_type: str, body: str) -> int | None:
    """Число товаров в /products.json (Shopify/InSales). None — не JSON
    с товарами (в т.ч. soft-404)."""
    if looks_like_html(content_type, body):
        return None
    try:
        data = json.loads(body)
    except (json.JSONDecodeError, ValueError):
        return None
    if isinstance(data, dict) and isinstance(data.get("products"), list):
        return len(data["products"])
    return None


@dataclass
class SitemapReport:
    kind: str = "none"  # "index" | "urlset" | "invalid" | "none"
    url_count: int = 0
    path_patterns: list[tuple[str, int]] = field(default_factory=list)
    children: list[str] = field(default_factory=list)  # для индекса
    urls: list[str] = field(default_factory=list)      # для urlset


_LOC_RE = re.compile(r"<loc>\s*([^<\s][^<]*?)\s*</loc>", re.I)


def parse_sitemap(content_type: str, body: str) -> SitemapReport:
    """Разбирает sitemap. Урок long-play: карты приходят одной строкой,
    поэтому только findall, никаких построчных grep -c."""
    if looks_like_html(content_type, body):
        return SitemapReport(kind="invalid")
    low = body.lower()
    locs = _LOC_RE.findall(body)
    if "<sitemapindex" in low:
        return SitemapReport(kind="index", url_count=len(locs), children=locs)
    if "<urlset" not in low:
        return SitemapReport(kind="invalid")
    patterns: Counter[str] = Counter()
    for loc in locs:
        path = urlparse(loc).path
        segments = [s for s in path.split("/") if s]
        patterns["/" + segments[0] + "/" if segments else "/"] += 1
    return SitemapReport(
        kind="urlset",
        url_count=len(locs),
        path_patterns=patterns.most_common(5),
        urls=locs,
    )


_CATALOG_HINT_RE = re.compile(
    r"vinyl|catalog|shop|store|market|plastin|collection", re.I
)


def pick_catalog_url(urls: list[str]) -> str | None:
    """URL, похожий на страницу каталога, из плоского sitemap. Нужен для
    Tilda-лендингов, у которых store-блок живёт не на главной, а на
    подстранице (found: pizza.foundmoscow.com/vinyl)."""
    for url in urls:
        path = urlparse(url).path
        if path in ("", "/"):
            continue
        if _CATALOG_HINT_RE.search(path):
            return url
    return None


# ---------------------------------------------------------------------------
# Паспорт и вердикт
# ---------------------------------------------------------------------------


@dataclass
class Passport:
    domain: str
    cms: str = CMS_UNKNOWN
    robots: RobotsReport = field(default_factory=RobotsReport)
    tilda_params: tuple[str, str] | None = None
    tilda_total: int | None = None
    tilda_catalog_url: str | None = None  # store-блок нашёлся не на главной
    yml_feed: tuple[str, int] | None = None       # (path, offers)
    products_json_count: int | None = None
    sitemap: SitemapReport = field(default_factory=SitemapReport)
    requests_made: int = 0
    elapsed_sec: float = 0.0
    errors: list[str] = field(default_factory=list)

    # заполняются classify()
    tier: str = "?"
    size_estimate: str = "неизвестен"
    access: str = "?"
    bypass_notes: list[str] = field(default_factory=list)
    disqualifiers: list[str] = field(default_factory=list)
    verdict: str = "🟡 сомнительно"
    verdict_reason: str = ""


def classify(p: Passport) -> Passport:
    """Тир доступа, оценка размера, дисквалификаторы и вердикт-подсказка.
    Вердикт — именно подсказка: ✅ значит «есть дешёвый машинный доступ»,
    чек-лист разбираемости (§4a) скрипт не заменяет."""
    # --- обходные параметры / грабли robots ---
    if p.robots.pagen_blocked:
        p.bypass_notes.append(
            "PAGEN запрещён в robots — штатная пагинация закрыта; "
            "пробовать ?count=N / SHOWALL_1 (сработало на long-play)"
        )
    if p.robots.query_blocked:
        p.bypass_notes.append(
            "robots запрещает все query-параметры (/*?*) — обходные "
            "параметры листинга недоступны, только чистые URL"
        )
    if p.robots.catalog_blocked:
        p.disqualifiers.append("robots закрывает каталог (Disallow /catalog|/shop|…)")
    if p.robots.full_blocked:
        p.disqualifiers.append("robots закрывает весь сайт (Disallow: /)")

    # --- размер ---
    if p.yml_feed:
        p.size_estimate = f"{p.yml_feed[1]} (по фиду, надёжно)"
    elif p.tilda_total is not None and p.tilda_total > 0:
        p.size_estimate = f"{p.tilda_total} (по Tilda API, надёжно)"
    elif p.products_json_count:
        p.size_estimate = f"{p.products_json_count}+ (первая страница products.json)"
    elif p.sitemap.kind == "urlset" and p.sitemap.url_count:
        p.size_estimate = (
            f"~{p.sitemap.url_count} URL по sitemap — ненадёжно, "
            "сверять с витриной (long-play: 16k → 2 627 → 4 453)"
        )
    elif p.sitemap.kind == "index":
        p.size_estimate = (
            f"sitemap-индекс из {p.sitemap.url_count} карт — размер "
            "не оценён, сверять с витриной"
        )

    # --- tier + вердикт ---
    if p.cms == CMS_TILDA and p.tilda_params is not None and not p.tilda_total:
        p.tier = "—"
        p.access = "Tilda store-API отвечает, но total=0"
        p.disqualifiers.append(
            "Tilda-блок пустой (total=0) — лендинг без онлайн-каталога "
            "(урок domkultury)"
        )
    elif p.cms == CMS_TILDA and p.tilda_params is None:
        p.tier = "—"
        p.access = "Tilda без store-блока (t_store_init не найден)"
        p.disqualifiers.append(
            "Tilda-store-блок не найден ни на главной, ни на странице "
            "каталога из sitemap — онлайн-каталога нет"
        )
    elif p.yml_feed:
        p.tier = "A (YML-фид)"
        p.access = f"YML-фид {p.yml_feed[0]}, {p.yml_feed[1]} offers"
    elif p.tilda_total:
        p.tier = "A (Tilda API)"
        where = f", витрина {p.tilda_catalog_url}" if p.tilda_catalog_url else ""
        p.access = (
            f"store.tildaapi.com getproductslist, total={p.tilda_total}, "
            f"recid={p.tilda_params[0]}{where}"
        )
    elif p.products_json_count:
        p.tier = "A (products.json)"
        p.access = f"{FEED_PATH_PRODUCTS_JSON}, {p.products_json_count} на страницу"
    elif p.sitemap.kind in ("urlset", "index"):
        p.tier = "B/C? (листинг или страница-на-товар — проверить руками)"
        p.access = (
            "фидов/API нет; смотреть листинг (цена+наличие в карточке?), "
            "JSON-LD и Network при скролле каталога"
        )
    else:
        p.tier = "D? (JS-only)"
        p.access = "ни фидов, ни API, ни sitemap — вероятно, рендер на клиенте"

    if p.disqualifiers:
        p.verdict = "🔴 мимо"
        p.verdict_reason = "; ".join(p.disqualifiers)
    elif p.tier.startswith("A"):
        p.verdict = "✅ кандидат"
        p.verdict_reason = "дешёвый машинный доступ найден; дальше чек-лист §4a"
    elif p.tier.startswith("D"):
        p.verdict = "🔴 мимо"
        p.verdict_reason = "похоже на requires_browser — брать только за уникальный сток"
    else:
        p.verdict = "🟡 сомнительно"
        p.verdict_reason = (
            "дешёвого доступа скрипт не нашёл — нужен ручной осмотр листинга"
        )
    return p


def render_passport(p: Passport) -> str:
    lines = [
        "=" * 64,
        f"ПАСПОРТ КАНДИДАТА: {p.domain}",
        "=" * 64,
        f"CMS:            {p.cms}",
        f"Tier доступа:   {p.tier}",
        f"Размер:         {p.size_estimate}",
        f"Доступ:         {p.access}",
    ]
    if p.robots.disallow:
        shown = ", ".join(p.robots.disallow[:8])
        extra = f" (+ ещё {len(p.robots.disallow) - 8})" if len(p.robots.disallow) > 8 else ""
        lines.append(f"robots.txt:     Disallow: {shown}{extra}")
    else:
        lines.append("robots.txt:     без Disallow для * (или нет файла)")
    if p.sitemap.kind == "urlset":
        pat = ", ".join(f"{path}×{n}" for path, n in p.sitemap.path_patterns)
        lines.append(f"sitemap:        плоский, {p.sitemap.url_count} URL; пути: {pat}")
    elif p.sitemap.kind == "index":
        names = ", ".join(c.rsplit("/", 1)[-1] for c in p.sitemap.children[:6])
        lines.append(f"sitemap:        индекс из {p.sitemap.url_count} карт ({names})")
    elif p.sitemap.kind == "invalid":
        lines.append("sitemap:        soft-404 / не XML")
    else:
        lines.append("sitemap:        не найден")
    for note in p.bypass_notes:
        lines.append(f"обход:          {note}")
    for d in p.disqualifiers:
        lines.append(f"дисквалификатор: {d}")
    for e in p.errors:
        lines.append(f"ошибка:         {e}")
    lines += [
        f"Вердикт:        {p.verdict} — {p.verdict_reason}",
        f"({p.requests_made} запросов, {p.elapsed_sec:.1f} c)",
        "",
        "Строка для таблицы §7b MARKET_STORES_SCALING.md:",
        render_markdown_row(p),
    ]
    return "\n".join(lines)


def render_markdown_row(p: Passport) -> str:
    """Готовая строка для таблицы §7b: | магазин | CMS | каталог | доступ | вердикт |"""
    size = p.size_estimate.split(" — ")[0].split(" (")[0]
    return f"| **{p.domain}** | {p.cms} | {size} | {p.access} | {p.verdict} |"


# ---------------------------------------------------------------------------
# Сетевая часть (в тестах не покрывается — только чистые функции выше)
# ---------------------------------------------------------------------------


class _PoliteFetcher:
    """GET с паузой между запросами и счётчиком. Ошибки сети не роняют
    разведку — возвращается None, факт пишется в passport.errors."""

    def __init__(self, client: httpx.AsyncClient, passport: Passport) -> None:
        self._client = client
        self._passport = passport
        self._first = True

    async def get(self, url: str) -> httpx.Response | None:
        if not self._first:
            await asyncio.sleep(PAUSE_BETWEEN_REQUESTS)
        self._first = False
        self._passport.requests_made += 1
        try:
            return await self._client.get(url)
        except httpx.HTTPError as exc:
            self._passport.errors.append(f"{url}: {type(exc).__name__}: {exc}")
            return None


async def scout(domain: str) -> Passport:
    domain = domain.strip().rstrip("/")
    domain = re.sub(r"^https?://", "", domain)
    base = f"https://{domain}"
    passport = Passport(domain=domain)
    started = time.monotonic()

    async with httpx.AsyncClient(
        headers=HEADERS, timeout=REQUEST_TIMEOUT, follow_redirects=True
    ) as client:
        fetch = _PoliteFetcher(client, passport)

        # 1. robots.txt
        resp = await fetch.get(f"{base}/robots.txt")
        if resp is not None and resp.status_code == 200 and not looks_like_html(
            resp.headers.get("content-type", ""), resp.text
        ):
            passport.robots = parse_robots(resp.text)

        # 2. Главная → CMS
        resp = await fetch.get(f"{base}/")
        home_html = ""
        if resp is not None and resp.status_code == 200:
            home_html = resp.text
            passport.cms = detect_cms(home_html)
        elif resp is not None:
            passport.errors.append(f"главная: HTTP {resp.status_code}")

        # 3. Tilda: recid/storepartuid с главной (если там нет — после
        # sitemap попробуем страницу каталога, см. шаг 5a)
        if passport.cms == CMS_TILDA:
            passport.tilda_params = extract_tilda_store_params(home_html)
            if passport.tilda_params is not None:
                await _probe_tilda_api(fetch, passport)

        # 4. Фиды — набор путей зависит от CMS, стоп на первом рабочем
        if passport.cms == CMS_TILDA:
            feed_paths: list[str] = []  # у Tilda фидов не бывает, есть API
        elif passport.cms in (CMS_SHOPIFY, CMS_INSALES):
            feed_paths = [FEED_PATH_PRODUCTS_JSON, *FEED_PATHS_YML[:1]]
        else:
            feed_paths = [*FEED_PATHS_YML, FEED_PATH_PRODUCTS_JSON]
        for path in feed_paths:
            resp = await fetch.get(base + path)
            if resp is None or resp.status_code != 200:
                continue
            ctype = resp.headers.get("content-type", "")
            if path == FEED_PATH_PRODUCTS_JSON:
                count = count_products_json(ctype, resp.text)
                if count:
                    passport.products_json_count = count
                    break
            else:
                offers = count_yml_offers(ctype, resp.text)
                if offers:
                    passport.yml_feed = (path, offers)
                    break

        # 5. sitemap: адрес из robots, иначе /sitemap.xml
        sitemap_url = (
            passport.robots.sitemaps[0]
            if passport.robots.sitemaps
            else f"{base}/sitemap.xml"
        )
        resp = await fetch.get(sitemap_url)
        if resp is not None and resp.status_code == 200:
            passport.sitemap = parse_sitemap(
                resp.headers.get("content-type", ""), resp.text
            )

        # 5a. Tilda-лендинг: store-блок бывает не на главной, а на
        # подстранице (found: /vinyl) — ищем её в sitemap
        if passport.cms == CMS_TILDA and passport.tilda_params is None:
            catalog_url = pick_catalog_url(passport.sitemap.urls)
            if catalog_url is not None:
                resp = await fetch.get(catalog_url)
                if resp is not None and resp.status_code == 200:
                    passport.tilda_params = extract_tilda_store_params(resp.text)
                    if passport.tilda_params is not None:
                        passport.tilda_catalog_url = catalog_url
                        await _probe_tilda_api(fetch, passport)

    passport.elapsed_sec = time.monotonic() - started
    return classify(passport)


async def _probe_tilda_api(fetch: _PoliteFetcher, passport: Passport) -> None:
    """Один запрос к store.tildaapi.com: живой ли каталог (total > 0)."""
    recid, partuid = passport.tilda_params  # type: ignore[misc]
    api_url = (
        f"{TILDA_STORE_API}?storepartuid={partuid or recid}"
        f"&recid={recid}&c={int(time.time())}"
        f"&getparts=true&slice=1&size=1"
    )
    resp = await fetch.get(api_url)
    if resp is not None and resp.status_code == 200:
        try:
            passport.tilda_total = int(resp.json().get("total") or 0)
        except (json.JSONDecodeError, ValueError, AttributeError):
            passport.errors.append("Tilda API: не-JSON ответ")


def main() -> None:
    if len(sys.argv) != 2:
        print("Использование: python -m app.scripts.scout_store <domain>")
        print("Пример:        python -m app.scripts.scout_store long-play.ru")
        raise SystemExit(2)
    passport = asyncio.run(scout(sys.argv[1]))
    print(render_passport(passport))


if __name__ == "__main__":
    main()
