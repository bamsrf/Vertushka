"""Тесты парсера Long Play (long-play.ru) — б/у винил, обход по витрине.

Ключевые инварианты, которые тут сторожатся:
  * карточка витрины отдаёт состояние — у б/у магазина оно у каждого
    экземпляра своё, потерять его нельзя;
  * `external_id` одинаков на обоих путях (витрина и страница товара),
    иначе один товар задвоится в `store_listings`;
  * пагинатор в ответе = выдача обрезана `count`, это НЕ успешный обход.
"""
import asyncio
from decimal import Decimal

import pytest

from app.services.scrapers.base import ParserError
from app.services.scrapers.shops.long_play import (
    LongPlayParser,
    _extract_cards,
    _external_id,
    _has_pagination,
    _parse_card,
)

BASE = "https://long-play.ru"


def _card_html(
    *,
    href="/catalog/blues/eleven/",
    artist="Harry Connick, Jr.",
    title="Eleven",
    price="1 500.-",
    label="Columbia",
    genre="Blues",
    fmt="Vinyl",
    condition="Near Mint (NM or M-)",
    img="/upload/resize_cache/iblock/e02/300_300_1/ffzx9ihpnsv8ewz1sba56vsg62fx9pqu.jpeg",
):
    return f"""
    <div id="display-list"><div class="list-items">
      <a href="{href}" class="list-item"><div class="row"><div class="col-xs-8">
        <img src="{img}" alt="" class="pic">
        <div class="ov">
          <h3 class="list-item-title">{artist}</h3>
          <p class="item-title">{title}</p>
          <ul class="list-item-list">
            <li><span>{label}</span></li><li>{genre}</li>
            <li>{fmt}</li><li>{condition}</li><li></li>
          </ul>
        </div></div>
        <div class="col-xs-2"><div class="item-price">{price}</div></div>
      </div></a>
    </div></div>
    """


def _parse(html):
    cards = _extract_cards(html)
    assert len(cards) == 1
    return _parse_card(cards[0], BASE)


def test_parse_card_basic():
    dto = _parse(_card_html())
    assert dto.external_id == "blues/eleven"
    assert dto.url == BASE + "/catalog/blues/eleven/"
    assert dto.artist_raw == "Harry Connick, Jr."
    assert dto.title_raw == "Eleven"
    assert dto.price_rub == Decimal("1500")
    assert dto.format_raw == "LP"
    assert dto.status == "in_stock"
    assert dto.raw_payload == {"label": "Columbia", "genre": "Blues"}
    # resize_cache-сегмент срезан до оригинала
    assert dto.image_url == BASE + "/upload/iblock/e02/ffzx9ihpnsv8ewz1sba56vsg62fx9pqu.jpeg"


def test_card_carries_per_item_condition():
    """Главная ценность магазина: грейд у каждого экземпляра свой."""
    assert _parse(_card_html(condition="Very Good Plus (VG+)")).condition == "Very Good Plus (VG+)"
    assert _parse(_card_html(condition="Mint (M)")).condition == "Mint (M)"


def test_condition_found_even_if_slots_reordered():
    """Состояние ищем по грейду, а не по позиции: перестановка полей в
    шаблоне не должна подсунуть в `condition` жанр."""
    html = _card_html().replace(
        "<li>Vinyl</li><li>Near Mint (NM or M-)</li>",
        "<li>Near Mint (NM or M-)</li><li>Vinyl</li>",
    )
    assert _parse(html).condition == "Near Mint (NM or M-)"


def test_price_with_space_separator_and_dash_suffix():
    assert _parse(_card_html(price="10 000.-")).price_rub == Decimal("10000")


def test_cassette_and_single_formats():
    assert _parse(_card_html(fmt="Cassette")).format_raw == "Cassette"
    assert _parse(_card_html(fmt='7"')).format_raw == "Single"


def test_unknown_format_stays_none():
    """«Album»/«Lathe Cut» — дискогсовский дескриптор, а не носитель.

    0,7% каталога. Пустой формат честнее выдуманного: матчер штрафует
    несовпадение формата, и ложный LP хуже отсутствующего.
    """
    assert _parse(_card_html(fmt="Album")).format_raw is None
    assert _parse(_card_html(fmt="Lathe Cut")).format_raw is None


def test_color_not_taken_from_title():
    """«Green River» — не зелёный винил."""
    assert _parse(_card_html(title="Green River", fmt="Vinyl")).vinyl_color_raw is None


def test_card_without_product_href_skipped():
    assert _parse(_card_html(href="/catalog/blues/")) is None


def test_card_without_title_skipped():
    assert _parse(_card_html(title="")) is None


# ---- external_id: один товар — один id на обоих путях ------------------- #


def test_external_id_matches_for_relative_and_absolute_url():
    assert _external_id("/catalog/blues/eleven/") == "blues/eleven"
    assert _external_id(BASE + "/catalog/blues/eleven/") == "blues/eleven"


def test_external_id_keeps_bitrix_collision_suffix():
    """Bitrix при коллизии слага дописывает id — это разные пластинки."""
    a = _external_id("/catalog/blues/tynis-myagi-i-myuzik-seyf/")
    b = _external_id("/catalog/blues/tynis-myagi-i-myuzik-seyf_1077921/")
    assert a != b


def test_external_id_rejects_non_product_paths():
    assert _external_id("/catalog/blues/") is None
    assert _external_id("/references/detail.php?ID=5570") is None


# ---- Пагинатор = обрезанная выдача -------------------------------------- #


def test_pagination_detected_when_count_too_small():
    assert _has_pagination('<div class="pagination"><a href="?PAGEN_1=2">2</a></div>')


def test_empty_pagination_block_is_not_pagination():
    assert not _has_pagination('<div class="pagination"></div>')


def test_section_refetched_with_bigger_count_when_paginated():
    """Раздел перерос `count` → повторяем с удвоенным, а не молча теряем хвост."""
    from app.services.scrapers import shops

    calls: list[str] = []
    paginated = '<div class="pagination"><a href="?PAGEN_1=2">2</a></div>'

    class _Parser(LongPlayParser):
        async def fetch_page(self, url, budget, *, page_label, **kw):
            calls.append(url)
            return paginated if len(calls) < 3 else _card_html()

    parser = _Parser(http=None)
    html = asyncio.run(parser._fetch_section("rock", _budget()))
    assert not _has_pagination(html)
    counts = [int(u.split("count=")[1]) for u in calls]
    assert counts == [2000, 4000, 8000], counts


def _budget():
    from app.services.scrapers.base import PageErrorBudget

    return PageErrorBudget("long_play")


# ---- Страница товара ----------------------------------------------------- #


_ITEM_HTML = """
<h1 class="page-order__heading">Eleven</h1>
<div class="pic-wrap"><img src="/upload/iblock/e02/x.jpeg" alt="" class="pic"></div>
<h2 class="product-title"><a href="/ispolniteli/1167931/">Harry Connick, Jr.</a></h2>
<h1 class="product-subtitle">Eleven</h1>
<div class="item-price">1 500.-</div>
<div class="product-info-list">
  <div class="product-info-item"><div class="row">
    <div class="col-xs-3"><h3>Жанр</h3></div><div class="col-xs-9"><span>Blues</span></div></div></div>
  <div class="product-info-item"><div class="row">
    <div class="col-xs-3"><h3>Стиль</h3></div>
    <div class="col-xs-9"><span><a href="#">Big Band</a>, <a href="#">Swing</a></span></div></div></div>
  <div class="product-info-item"><div class="row">
    <div class="col-xs-3"><h3>Год</h3></div><div class="col-xs-9"><span>1992</span></div></div></div>
  <div class="product-info-item"><div class="row">
    <div class="col-xs-3"><h3>Состояние</h3></div>
    <div class="col-xs-9"><span>Near Mint (NM or M-)</span></div></div></div>
  <div class="product-info-item"><div class="row">
    <div class="col-xs-3"><h3>Кат. номер</h3></div>
    <div class="col-xs-9"><span>COL 472808 1</span></div></div></div>
  <div class="product-info-item"><div class="row">
    <div class="col-xs-3"><h3>Формат</h3></div>
    <div class="col-xs-9"><span>Vinyl, LP, Album, Reissue</span></div></div></div>
</div>
"""


class _FakeHttp:
    def __init__(self, html):
        self.html = html

    async def get_text(self, url, **kw):
        return self.html


def _parse_item(html=_ITEM_HTML, url=BASE + "/catalog/blues/eleven/"):
    return asyncio.run(LongPlayParser(http=_FakeHttp(html)).parse_listing(url))


def test_parse_listing_adds_year_and_catalog_number():
    """То, чего нет в витрине, — ради чего страница товара вообще нужна."""
    dto = _parse_item()
    assert dto.year_raw == 1992
    assert dto.catalog_number == "COL 472808 1"
    assert dto.format_raw == "LP"


def test_parse_listing_takes_artist_from_product_title_not_page_heading():
    """Первый `h1` на странице принадлежит шапке заказа, а не товару."""
    dto = _parse_item()
    assert dto.artist_raw == "Harry Connick, Jr."
    assert dto.title_raw == "Eleven"


def test_parse_listing_external_id_matches_card():
    """Тот же товар с витрины и со страницы — один и тот же `external_id`."""
    assert _parse_item().external_id == _parse(_card_html()).external_id


def test_parse_listing_multivalue_property_cleaned():
    assert _parse_item().raw_payload["style"] == "Big Band, Swing"


def test_parse_listing_without_title_raises():
    with pytest.raises(ParserError):
        _parse_item(html="<h1 class='page-order__heading'>Заказ</h1>")


def test_parser_is_registered():
    from app.services.scrapers.registry import get_parser

    assert get_parser("long_play") is LongPlayParser


def test_stock_arrives_with_catalog_crawl():
    """`stock_from_listing` выключает точечный stock-refresh: цена и так
    приезжает с ночным обходом, а он стоит 16 запросов."""
    assert LongPlayParser.stock_from_listing is True
