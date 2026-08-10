"""Тесты разбора листингов skifmusic (JSON-LD категории)."""
import pytest

from app.services.scrapers.shops.skifmusic import (
    SkifmusicParser,
    _extract_id_from_url,
    _extract_item_list,
    _split_name,
)


@pytest.mark.parametrize("name, artist, album, tail", [
    ("Виниловая пластинка Adriano Celentano – Golden Hits (LP)",
     "Adriano Celentano", "Golden Hits", "LP"),
    # Второй дефис принадлежит альбому, граница артиста — первый.
    ("Виниловая пластинка Led Zeppelin – Led Zeppelin – Remastered by Jimmy Page (LP)",
     "Led Zeppelin", "Led Zeppelin – Remastered by Jimmy Page", "LP"),
    # Обычный дефис вместо en-dash.
    ("Виниловая пластинка Louis Armstrong - Platinum Collection (3LP)",
     "Louis Armstrong", "Platinum Collection", "3LP"),
    # Хвост — цвет, а не формат.
    ("Виниловая пластинка C.C.Catch – Golden Disco Hits (Blue Vinyl)",
     "C.C.Catch", "Golden Disco Hits", "Blue Vinyl"),
    # Сборник без артиста.
    ("Виниловая пластинка Забытые Вальсы", None, "Забытые Вальсы", None),
    # Без скобочного хвоста.
    ("Виниловая пластинка Electric Light Orchestra – Time",
     "Electric Light Orchestra", "Time", None),
])
def test_split_name(name, artist, album, tail):
    assert _split_name(name) == (artist, album, tail)


def test_extract_id_from_url():
    assert _extract_id_from_url("https://skifmusic.ru/product/784099-led-zeppelin-i-lp") == "784099"
    assert _extract_id_from_url("https://skifmusic.ru/catalog/vinilovyie-plastinki-617") is None


def _product(**over):
    base = {
        "@type": "Product",
        "name": "Виниловая пластинка Moby – Play (2LP)",
        "url": "https://skifmusic.ru/product/123456-moby-play",
        "image": "https://skifmusic.ru/thumbs/x.webp",
        "offers": {
            "price": "3490",
            "priceCurrency": "RUB",
            "itemCondition": "https://schema.org/NewCondition",
            "availability": "https://schema.org/InStock",
        },
    }
    base["offers"].update(over.pop("offers", {}))
    base.update(over)
    return base


@pytest.fixture
def parser():
    return SkifmusicParser(http=object())


def test_parse_product_basic(parser):
    dto = parser.parse_product(_product())
    assert dto.external_id == "123456"
    assert dto.artist_raw == "Moby"
    assert dto.title_raw == "Play"
    assert int(dto.price_rub) == 3490
    assert dto.status == "in_stock"
    assert dto.format_raw == "2xLP"
    assert dto.condition is None
    assert dto.barcode is None and dto.catalog_number is None


def test_parse_product_out_of_stock_and_used(parser):
    dto = parser.parse_product(_product(offers={
        "availability": "https://schema.org/OutOfStock",
        "itemCondition": "https://schema.org/UsedCondition",
    }))
    assert dto.status == "out_of_stock"
    assert dto.condition == "Used"


def test_parse_product_colored_vinyl(parser):
    dto = parser.parse_product(_product(
        name="Виниловая пластинка Black Sabbath – Paranoia (Purple Vinyl)",
    ))
    assert dto.vinyl_color_raw == "purple"


def test_parse_product_skips_garbage(parser):
    assert parser.parse_product(_product(url="https://skifmusic.ru/about")) is None
    assert parser.parse_product(_product(name="")) is None


def test_extract_item_list_picks_itemlist_over_breadcrumbs():
    html = """
    <script type="application/ld+json">/*<![CDATA[*/
      {"@context":"https://schema.org","@type":"BreadcrumbList","itemListElement":[]}
    /*]]>*/</script>
    <script type="application/ld+json">/*<![CDATA[*/
      {"@context":"https://schema.org/","@type":"ItemList","numberOfItems":2,
       "itemListElement":[{"@type":"ListItem","position":1,"item":{"name":"x"}}]}
    /*]]>*/</script>
    """
    data = _extract_item_list(html)
    assert data is not None
    assert data["numberOfItems"] == 2


def test_extract_item_list_absent():
    assert _extract_item_list("<html><body>нет каталога</body></html>") is None


# ---- Обход каталога: дедуп, стабильная сортировка, обрыв ---------------- #

def _page(items, total=90):
    """Страница категории с JSON-LD ItemList из переданных (id, name)."""
    els = ",".join(
        f'{{"@type":"ListItem","position":{i+1},"item":{{"@type":"Product",'
        f'"name":"Виниловая пластинка {n}","url":"https://skifmusic.ru/product/{pid}-x",'
        f'"offers":{{"price":"100","availability":"https://schema.org/InStock"}}}}}}'
        for i, (pid, n) in enumerate(items)
    )
    return (
        '<script type="application/ld+json">/*<![CDATA[*/'
        f'{{"@context":"https://schema.org/","@type":"ItemList","name":"x",'
        f'"numberOfItems":{total},"itemListElement":[{els}]}}'
        '/*]]>*/</script>'
    )


class _FakeHttp:
    def __init__(self, pages, fail_on=None):
        self.pages, self.fail_on, self.urls = pages, fail_on, []

    async def get_text(self, url, **kw):
        self.urls.append(url)
        page = 1 if "/page" not in url else int(url.split("/page")[1].split("?")[0])
        if self.fail_on == page:
            raise RuntimeError("network error")
        return self.pages.get(page, "<html>пусто</html>")


async def _collect(parser):
    return [d async for d in parser.crawl_full()]


@pytest.mark.asyncio
async def test_crawl_uses_stable_sort_order():
    http = _FakeHttp({1: _page([("1", "A - B")], total=1)})
    await _collect(SkifmusicParser(http=http))
    assert all("sort=name" in u for u in http.urls)


@pytest.mark.asyncio
async def test_crawl_dedupes_overlapping_pages():
    """Товар, попавший на две страницы, отдаётся один раз."""
    full = [(str(i), f"Artist {i} - Album") for i in range(30)]
    overlap = [("29", "Artist 29 - Album")] + [(str(i), f"Artist {i} - Album")
                                               for i in range(30, 59)]
    http = _FakeHttp({1: _page(full), 2: _page(overlap)})
    dtos = await _collect(SkifmusicParser(http=http))
    ids = [d.external_id for d in dtos]
    assert len(ids) == len(set(ids)) == 59


@pytest.mark.asyncio
async def test_crawl_raises_on_interrupted_page():
    """Обрыв не должен молча дать неполный каталог: runner обязан узнать."""
    from app.services.scrapers.base import TransientParserError
    http = _FakeHttp({1: _page([(str(i), f"A{i} - B") for i in range(30)])}, fail_on=2)
    with pytest.raises(TransientParserError, match="обход прерван"):
        await _collect(SkifmusicParser(http=http))


@pytest.mark.asyncio
async def test_crawl_stops_on_page_without_itemlist():
    http = _FakeHttp({1: _page([(str(i), f"A{i} - B") for i in range(30)])})
    dtos = await _collect(SkifmusicParser(http=http))
    assert len(dtos) == 30
