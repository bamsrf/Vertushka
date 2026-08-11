"""Тесты разбора AJAX-каталога Stoprobot Vinyl (WS1.5)."""
import json
from decimal import Decimal

import pytest

from app.services.scrapers.base import TransientParserError
from app.services.scrapers.shops.stoprobotvinyl import StoprobotVinylParser


def _product(**over):
    base = {
        "id": 56099,
        "price": "5&nbsp;990 &#8381;",
        "album": "All Our Gods Have Abandoned Us",
        "format": ["LP"],
        "style": ["Metalcore"],
        "direction": "Rock",
        "in_stock": "1",
        "images": [{"src": "/upload/iblock/e35/x.png", "alt": "Architects"}],
        "url": "/vinyl/product/111254_architects_all_our_gods_have_abandoned_us_lp/",
        "name": "Architects",
        "label": {"name": "Epitaph"},
    }
    base.update(over)
    return base


@pytest.fixture
def parser():
    return StoprobotVinylParser(http=object())


def test_external_id_comes_from_url_not_ajax_id(parser):
    """Поле id (56099) — другая нумерация; подмена задвоила бы каталог."""
    dto = parser.parse_product(_product())
    assert dto.external_id == "111254"


def test_parse_product_basic(parser):
    dto = parser.parse_product(_product())
    assert dto.artist_raw == "Architects"
    assert dto.title_raw == "All Our Gods Have Abandoned Us"
    assert dto.price_rub == Decimal("5990")  # html-escaped «5&nbsp;990 &#8381;»
    assert dto.status == "in_stock"
    assert dto.format_raw == "LP"
    assert dto.url.startswith("https://stoprobotvinyl.ru/vinyl/product/")
    assert dto.image_url == "https://stoprobotvinyl.ru/upload/iblock/e35/x.png"
    assert dto.raw_payload["stoprobot_label"] == "Epitaph"
    assert dto.year_raw is None  # года в AJAX нет — осознанно


def test_colour_recovered_from_url_slug(parser):
    dto = parser.parse_product(_product(
        url="/vinyl/product/110967_djo_decide_lp_blue_swirl_transparent/",
        album="Decide", name="Djo",
    ))
    assert dto.vinyl_color_raw == "blue"


def test_colour_defaults_to_black_without_token(parser):
    """Нет цветового токена в слаге — пластинка чёрная (сверено 8/8)."""
    assert parser.parse_product(_product()).vinyl_color_raw == "black"


def test_multi_lp_format(parser):
    dto = parser.parse_product(_product(format=["2LP"], price="7&nbsp;790 &#8381;"))
    assert dto.format_raw == "2xLP"
    assert dto.price_rub == Decimal("7790")


@pytest.mark.parametrize("qty, expected", [
    ("1", "in_stock"), ("8", "in_stock"), ("0", "out_of_stock"), ("", "out_of_stock"),
])
def test_in_stock_is_a_quantity(parser, qty, expected):
    assert parser.parse_product(_product(in_stock=qty)).status == expected


def test_skips_product_without_url_or_album(parser):
    assert parser.parse_product(_product(url="/vinyl/")) is None
    assert parser.parse_product(_product(album="")) is None


class _FakeHttp:
    def __init__(self, pages, fail_on=None):
        self.pages, self.fail_on = pages, fail_on

    async def get_text(self, url, **kw):
        page = int(url.split("PAGEN_1=")[1])
        if self.fail_on == page:
            raise RuntimeError("network error")
        return json.dumps(self.pages.get(page, {"products": []}))


async def _collect(parser):
    return [d async for d in parser.crawl_full()]


@pytest.mark.asyncio
async def test_crawl_walks_all_pages():
    p1 = {"products": [_product()], "page_count": 2}
    p2 = {"products": [_product(url="/vinyl/product/222_b_c_lp/", album="C", name="B")],
          "page_count": 2}
    dtos = await _collect(StoprobotVinylParser(http=_FakeHttp({1: p1, 2: p2})))
    assert [d.external_id for d in dtos] == ["111254", "222"]


@pytest.mark.asyncio
async def test_single_bad_page_is_skipped_not_fatal():
    """Ночь 08-11: ReadTimeout на 2-й странице стоил 8 860 позиций из 8 956."""
    pages = {
        1: {"products": [_product()], "page_count": 3},
        3: {"products": [_product(url="/vinyl/product/333_c/")], "page_count": 3},
    }
    dtos = await _collect(StoprobotVinylParser(http=_FakeHttp(pages, fail_on=2)))
    assert [d.external_id for d in dtos] == ["111254", "333"]


@pytest.mark.asyncio
async def test_crawl_raises_when_site_is_down():
    """Сквозной обрыв должен долететь до runner'а, а не дать зелёный статус."""
    class _DeadHttp(_FakeHttp):
        async def get_text(self, url, **kw):
            page = int(url.split("PAGEN_1=")[1])
            if page == 1:
                return json.dumps(self.pages[1])
            raise RuntimeError("network error")

    http = _DeadHttp({1: {"products": [_product()], "page_count": 9}})
    with pytest.raises(TransientParserError, match="подряд"):
        await _collect(StoprobotVinylParser(http=http))


@pytest.mark.asyncio
async def test_crawl_dedupes_repeated_products():
    p1 = {"products": [_product(), _product()], "page_count": 1}
    dtos = await _collect(StoprobotVinylParser(http=_FakeHttp({1: p1})))
    assert len(dtos) == 1
