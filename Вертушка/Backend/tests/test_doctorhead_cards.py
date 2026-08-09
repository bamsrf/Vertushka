"""Тесты разбора карточек листинга Dr.Head (WS1.2 — обход без страниц товара)."""
from decimal import Decimal

import pytest
from bs4 import BeautifulSoup

from app.services.scrapers.shops.doctorhead import _extract_cards, _parse_card

BASE = "https://doctorhead.ru"


def _card_html(
    *,
    pid="102300",
    price="3290",
    href="/product/kino-nachalnik-kamchatki/",
    alt="Виниловая пластинка Кино - Начальник Камчатки LP",
    artist="Кино",
    status="В наличии",
    img="/upload/resize_cache/iblock/384/242_247_1/177.jpg",
):
    artist_block = (
        f'<div class="characteristic">Исполнитель: {artist}</div>' if artist else ""
    )
    return f"""
    <div class="catalog-list__item product js-product-container">
      <a href="{href}"><img src="{img}" alt="{alt}"></a>
      {artist_block}
      <div class="characteristic">Жанр: Rock</div>
      <div data-price="{price}" data-id="{pid}" class="js-product-price product-price"></div>
      <div class="product-status v1"><span>{status}</span></div>
    </div>
    """


def _parse(html):
    cards = _extract_cards(html)
    assert len(cards) == 1
    return _parse_card(cards[0], BASE)


def test_parse_card_basic():
    dto = _parse(_card_html())
    assert dto.external_id == "102300"
    assert dto.url == BASE + "/product/kino-nachalnik-kamchatki/"
    assert dto.artist_raw == "Кино"
    assert dto.title_raw == "Начальник Камчатки"
    assert dto.price_rub == Decimal("3290")
    assert dto.status == "in_stock"
    assert dto.format_raw == "LP"
    assert dto.condition == "Новый (Mint)"
    assert dto.year_raw is None
    # resize_cache-сегмент срезан до полноразмерной картинки
    assert dto.image_url == BASE + "/upload/iblock/384/177.jpg"


def test_parse_card_price_trailing_zero_normalized():
    """data-price=«4990.0» должен дать ту же цену, что и страница товара."""
    dto = _parse(_card_html(price="4990.0"))
    assert dto.price_rub == Decimal("4990")
    assert str(dto.price_rub) == "4990"


def test_parse_card_artist_without_dash_in_title():
    """«Rammstein Rosenrot LP» — разделителя нет, артист только из характеристики."""
    dto = _parse(_card_html(alt="Виниловая пластинка Rammstein Rosenrot LP", artist="Rammstein"))
    assert dto.artist_raw == "Rammstein"
    assert dto.title_raw == "Rosenrot"


def test_parse_card_falls_back_to_dash_split_without_characteristic():
    dto = _parse(_card_html(artist=None))
    assert dto.artist_raw == "Кино"
    assert dto.title_raw == "Начальник Камчатки"


def test_parse_card_multi_lp_format():
    dto = _parse(_card_html(alt="Виниловая пластинка Daft Punk – Random Access Memories 2LP",
                            artist="Daft Punk"))
    assert dto.format_raw == "2xLP"
    assert dto.title_raw == "Random Access Memories"


def test_parse_card_colour_from_trailing_paren():
    dto = _parse(_card_html(alt="Виниловая пластинка Кишлак – СХИК2 (Coloured Red Black) LP",
                            artist="Кишлак"))
    assert dto.vinyl_color_raw == "red"
    assert dto.title_raw == "СХИК2"


def test_parse_card_category_prefix_sets_format():
    """Нет суффикса в названии — формат берётся из подписи раздела."""
    dto = _parse(_card_html(alt="Кассета Кино - Начальник Камчатки", artist="Кино"))
    assert dto.format_raw == "Cassette"


@pytest.mark.parametrize("status, expected", [
    ("В наличии", "in_stock"),
    ("На заказ", "on_request"),
    ("Нет в наличии", "out_of_stock"),
    ("Предзаказ", "preorder"),
])
def test_parse_card_status(status, expected):
    assert _parse(_card_html(status=status)).status == expected


def test_parse_card_without_price_is_on_request():
    dto = _parse(_card_html(price=""))
    assert dto.price_rub is None
    assert dto.status == "on_request"


def test_parse_card_skips_card_without_price_node():
    html = '<div class="js-product-container"><a href="/product/x/">x</a></div>'
    cards = _extract_cards(html)
    assert _parse_card(cards[0], BASE) is None


def test_extract_cards_finds_all():
    soup = BeautifulSoup(_card_html() + _card_html(pid="99999"), "lxml")
    assert len(_extract_cards(str(soup))) == 2
