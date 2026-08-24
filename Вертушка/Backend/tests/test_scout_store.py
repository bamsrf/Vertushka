"""Тесты скрипта-разведчика (app/scripts/scout_store.py, WS4.1).

Покрываются только чистые функции разбора — на HTML/XML-фикстурах, без
единого сетевого вызова. Сетевая оркестрация (scout/_PoliteFetcher)
проверяется живым смоуком при онбординге, не здесь.

Сторожим уроки разведок 7a/7b:
  * long-play: PAGEN запрещён в robots, а ?count=N — нет;
  * long-play: sitemap приходит одной строкой и врёт о размере;
  * domkultury: «CMS = Tilda» ещё не значит «есть каталог» (total=0);
  * newartstore: soft-404 — страница-200 с HTML вместо фида.
"""
from app.scripts.scout_store import (
    CMS_BITRIX,
    CMS_INSALES,
    CMS_SHOPIFY,
    CMS_SHOPSCRIPT,
    CMS_TILDA,
    CMS_UNKNOWN,
    Passport,
    RobotsReport,
    SitemapReport,
    classify,
    count_products_json,
    count_yml_offers,
    detect_cms,
    extract_tilda_store_params,
    looks_like_html,
    parse_robots,
    parse_sitemap,
    pick_catalog_url,
    render_markdown_row,
)

# ---------------------------------------------------------------------------
# robots.txt
# ---------------------------------------------------------------------------

LONG_PLAY_LIKE_ROBOTS = """\
User-agent: *
Disallow: /bitrix/
Disallow: /*PAGEN
Disallow: /*?print=
Disallow: /auth/
Allow: /catalog/

User-agent: Yandex
Disallow: /*UTM

Sitemap: https://long-play.ru/sitemap.xml
"""


def test_parse_robots_pagen_and_sitemap():
    r = parse_robots(LONG_PLAY_LIKE_ROBOTS)
    assert r.pagen_blocked, "урок long-play: /*PAGEN должен подсвечиваться"
    assert "/bitrix/" in r.disallow
    assert r.sitemaps == ["https://long-play.ru/sitemap.xml"]
    # правила чужой группы (Yandex) не подмешиваются
    assert "/*UTM" not in r.disallow
    # /*?print= — конкретный параметр, это НЕ широкий запрет query
    assert not r.query_blocked
    assert not r.full_blocked
    assert not r.catalog_blocked


def test_parse_robots_broad_query_ban():
    r = parse_robots("User-agent: *\nDisallow: /*?*\n")
    assert r.query_blocked, "/*?* — обходные параметры вида ?count=N закрыты"


def test_parse_robots_full_and_catalog_ban():
    r = parse_robots("User-agent: *\nDisallow: /\n")
    assert r.full_blocked

    r = parse_robots("User-agent: *\nDisallow: /catalog/\n")
    assert r.catalog_blocked
    assert not r.full_blocked


def test_parse_robots_empty_and_garbage():
    assert parse_robots("").disallow == []
    r = parse_robots("# комментарий\nчто-то без двоеточия\nDisallow: /x\n")
    # Disallow вне группы User-agent: * игнорируется
    assert r.disallow == []


# ---------------------------------------------------------------------------
# CMS-детект
# ---------------------------------------------------------------------------


def test_detect_cms_bitrix():
    html = '<html><script src="/bitrix/js/main/core.js"></script></html>'
    assert detect_cms(html) == CMS_BITRIX


def test_detect_cms_tilda_by_store_init():
    html = "<script>t_store_init('452019122', {storepart:'928019163388'});</script>"
    assert detect_cms(html) == CMS_TILDA


def test_detect_cms_tilda_by_api_host():
    assert detect_cms('<script src="https://store.tildaapi.com/x.js">') == CMS_TILDA


def test_detect_cms_insales_requires_both_markers():
    both = '<a href="/collection/vinyl">..</a><script src="//assets.insales.ru/a.js">'
    assert detect_cms(both) == CMS_INSALES
    # /collection/ без insales-маркера — ещё не InSales
    assert detect_cms('<a href="/collection/vinyl">..</a>') == CMS_UNKNOWN


def test_detect_cms_shopscript_and_shopify():
    assert detect_cms('<img src="/wa-data/public/shop/img/1.jpg">') == CMS_SHOPSCRIPT
    assert detect_cms('<link href="https://cdn.shopify.com/a.css">') == CMS_SHOPIFY


def test_detect_cms_unknown():
    assert detect_cms("<html><body>привет</body></html>") == CMS_UNKNOWN


# ---------------------------------------------------------------------------
# Tilda: recid / storepartuid
# ---------------------------------------------------------------------------


def test_extract_tilda_params_domkultury_style():
    html = (
        "<div id='rec452019122'></div>"
        "<script>t_store_init('452019122', "
        "{'storepart':'928019163388','sort':'default'});</script>"
    )
    assert extract_tilda_store_params(html) == ("452019122", "928019163388")


def test_extract_tilda_params_no_storepart():
    html = "t_store_init(\"452019122\")"
    assert extract_tilda_store_params(html) == ("452019122", "")


def test_extract_tilda_params_absent():
    assert extract_tilda_store_params("<html>лендинг без магазина</html>") is None


# ---------------------------------------------------------------------------
# soft-404 и фиды
# ---------------------------------------------------------------------------

SOFT_404_BODY = "<!DOCTYPE html>\n<html><head><title>Главная</title></head></html>"

YML_FIXTURE = (
    '<?xml version="1.0" encoding="UTF-8"?>'
    '<yml_catalog date="2026-08-23"><shop><offers>'
    '<offer id="1" available="true"><name>LP один</name></offer>'
    '<offer id="2" available="false"><name>LP два</name></offer>'
    "</offers></shop></yml_catalog>"
)


def test_looks_like_html_detects_soft_404():
    assert looks_like_html("text/html; charset=utf-8", "{}")
    assert looks_like_html("application/xml", SOFT_404_BODY)
    assert not looks_like_html("application/xml", YML_FIXTURE)


def test_count_yml_offers_real_feed():
    assert count_yml_offers("application/xml", YML_FIXTURE) == 2


def test_count_yml_offers_rejects_soft_404():
    # урок newartstore.ru: 200 + HTML на любом пути
    assert count_yml_offers("text/html", SOFT_404_BODY) is None


def test_count_yml_offers_rejects_foreign_xml():
    rss = '<?xml version="1.0"?><rss><channel><item/></channel></rss>'
    assert count_yml_offers("application/xml", rss) is None


def test_count_products_json():
    body = '{"products": [{"id": 1}, {"id": 2}, {"id": 3}]}'
    assert count_products_json("application/json", body) == 3


def test_count_products_json_rejects_html_and_foreign_json():
    assert count_products_json("text/html", SOFT_404_BODY) is None
    assert count_products_json("application/json", '{"items": []}') is None
    assert count_products_json("application/json", "не json вовсе") is None


# ---------------------------------------------------------------------------
# sitemap
# ---------------------------------------------------------------------------


def test_parse_sitemap_flat_single_line():
    # Урок long-play: карта приходит ОДНОЙ строкой; построчный счёт вернул бы 1
    body = (
        '<?xml version="1.0"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
        + "".join(
            f"<url><loc>https://x.ru/catalog/rock/item{i}/</loc></url>" for i in range(7)
        )
        + "<url><loc>https://x.ru/about/</loc></url></urlset>"
    )
    r = parse_sitemap("application/xml", body)
    assert r.kind == "urlset"
    assert r.url_count == 8
    assert r.path_patterns[0] == ("/catalog/", 7)


def test_parse_sitemap_index():
    body = (
        "<sitemapindex>"
        "<sitemap><loc>https://x.ru/sitemap_iblock_4.xml</loc></sitemap>"
        "<sitemap><loc>https://x.ru/sitemap_iblock_14.xml</loc></sitemap>"
        "</sitemapindex>"
    )
    r = parse_sitemap("application/xml", body)
    assert r.kind == "index"
    assert r.url_count == 2
    assert r.children[1].endswith("sitemap_iblock_14.xml")


def test_pick_catalog_url_found_style():
    # found: store-блок живёт на /vinyl, а не на главной
    urls = [
        "https://pizza.foundmoscow.com/",
        "https://pizza.foundmoscow.com/restaurant/",
        "https://pizza.foundmoscow.com/vinyl/",
        "https://pizza.foundmoscow.com/feedbac/",
    ]
    assert pick_catalog_url(urls) == "https://pizza.foundmoscow.com/vinyl/"


def test_pick_catalog_url_nothing_catalogish():
    assert pick_catalog_url(["https://x.ru/", "https://x.ru/about/"]) is None
    assert pick_catalog_url([]) is None


def test_parse_sitemap_soft_404_and_garbage():
    assert parse_sitemap("text/html", SOFT_404_BODY).kind == "invalid"
    assert parse_sitemap("application/xml", "<foo/>").kind == "invalid"


# ---------------------------------------------------------------------------
# classify: tier, дисквалификаторы, вердикт
# ---------------------------------------------------------------------------


def test_classify_yml_feed_is_tier_a():
    p = classify(Passport(domain="x.ru", cms=CMS_BITRIX, yml_feed=("/yml.xml", 4453)))
    assert p.tier.startswith("A")
    assert p.verdict.startswith("✅")
    assert "4453" in p.size_estimate and "надёжно" in p.size_estimate


def test_classify_tilda_with_catalog():
    p = classify(
        Passport(
            domain="pizza.foundmoscow.com",
            cms=CMS_TILDA,
            tilda_params=("123", "456"),
            tilda_total=1600,
        )
    )
    assert p.tier == "A (Tilda API)"
    assert p.verdict.startswith("✅")


def test_classify_tilda_empty_store_is_disqualified():
    # урок domkultury: API отвечает, но total=0 — лендинг без каталога
    p = classify(
        Passport(
            domain="domkultury.store",
            cms=CMS_TILDA,
            tilda_params=("452019122", "928019163388"),
            tilda_total=0,
        )
    )
    assert p.verdict.startswith("🔴")
    assert any("total=0" in d for d in p.disqualifiers)


def test_classify_tilda_without_store_block():
    p = classify(Passport(domain="x.ru", cms=CMS_TILDA, tilda_params=None))
    assert p.verdict.startswith("🔴")


def test_classify_pagen_blocked_suggests_count_bypass():
    robots = RobotsReport(disallow=["/*PAGEN"], pagen_blocked=True)
    p = classify(
        Passport(
            domain="long-play.ru",
            cms=CMS_BITRIX,
            robots=robots,
            sitemap=SitemapReport(kind="urlset", url_count=2627),
        )
    )
    assert any("?count=N" in n for n in p.bypass_notes)
    assert "ненадёжно" in p.size_estimate  # sitemap-размер всегда с оговоркой


def test_classify_full_robots_ban_is_disqualifier():
    robots = RobotsReport(disallow=["/"], full_blocked=True)
    p = classify(Passport(domain="x.ru", robots=robots))
    assert p.verdict.startswith("🔴")


def test_classify_no_signals_is_js_only():
    p = classify(Passport(domain="x.ru", cms=CMS_UNKNOWN))
    assert p.tier.startswith("D?")
    assert p.verdict.startswith("🔴")


def test_classify_sitemap_only_is_questionable():
    p = classify(
        Passport(
            domain="x.ru",
            cms=CMS_BITRIX,
            sitemap=SitemapReport(kind="urlset", url_count=500),
        )
    )
    assert p.tier.startswith("B/C?")
    assert p.verdict.startswith("🟡")


def test_markdown_row_shape():
    p = classify(Passport(domain="x.ru", cms=CMS_BITRIX, yml_feed=("/yml.xml", 100)))
    row = render_markdown_row(p)
    # | магазин | CMS | каталог | доступ | вердикт | — 5 колонок таблицы §7b
    assert row.startswith("| **x.ru** | Bitrix | 100 |")
    assert row.count("|") == 6
    assert row.rstrip().endswith("|")
