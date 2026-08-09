"""Тесты разбора карточек листинга Plastinka.com (WS1.1)."""
from decimal import Decimal

import pytest

from app.services.scrapers.shops.plastinka_com import (
    _extract_cards,
    _parse_card,
    _year_from_apostrophe,
)

BASE = "https://plastinka.com"


def _card_html(
    *,
    pid="377288",
    artist="System Of A Down",
    name="Toxicity '01",
    descr_lines=("Европа /", "American", "Инди / Альтернатива", "Переиздание'18", "SS/SS"),
    price="3192",
    availability="http://schema.org/InStock",
    href="/lp/item/377288-system-of-a-down-toxicity",
):
    descr = "<br/>".join(descr_lines)
    avail = f'<link href="{availability}" itemprop="availability"/>' if availability else ""
    return f"""
    <div class="products-grid-item" data-artist-name="{artist}" data-id="{pid}"
         itemscope itemtype="https://schema.org/Product">
      <a href="{href}"><img itemprop="image" src="{BASE}/photo/lp/{pid}/x.webp"/></a>
      <div class="products-grid-item__title"><span itemprop="name">{name}</span></div>
      <div class="products-grid-item__params" itemprop="description">{descr}</div>
      <div class="products-grid-item__price">
        <span itemprop="offers" itemscope itemtype="https://schema.org/Offer">
          <meta content="{price}" itemprop="price"/>
          {avail}
        </span>
      </div>
    </div>
    """


def _parse(html):
    cards = _extract_cards(html)
    assert len(cards) == 1
    return _parse_card(cards[0], BASE)


def test_parse_card_basic():
    dto = _parse(_card_html())
    assert dto.external_id == "377288"
    assert dto.artist_raw == "System Of A Down"
    assert dto.title_raw == "Toxicity"
    assert dto.price_rub == Decimal("3192")
    assert dto.status == "in_stock"
    assert dto.condition == "SS/SS"
    assert dto.format_raw == "LP"
    assert dto.url == BASE + "/lp/item/377288-system-of-a-down-toxicity"
    assert dto.raw_payload["label"] == "American"


def test_year_prefers_reissue_over_original():
    """«Toxicity '01» + «Переиздание'18» → 2018 (год пресса, как на странице)."""
    assert _parse(_card_html()).year_raw == 2018


def test_year_falls_back_to_original_when_not_reissue():
    dto = _parse(_card_html(
        name="Saving Grace '25",
        descr_lines=("Европа /", "Nonesuch", "Хард Рок", "Оригинал", "SS/SS"),
    ))
    assert dto.year_raw == 2025
    assert dto.title_raw == "Saving Grace"


@pytest.mark.parametrize("raw, expected", [
    ("Toxicity '01", 2001),
    ("Strange Days '67", 1967),
    ("Переиздание'09", 2009),
    ("без года", None),
])
def test_year_from_apostrophe(raw, expected):
    assert _year_from_apostrophe(raw) == expected


def test_artist_with_hyphen_not_split():
    """Регрессия: title-регексп резал «A-ha - Analogue» и давал artist='A'."""
    dto = _parse(_card_html(
        artist="A-ha", name="Analogue (2LP) '20",
        descr_lines=("Европа /", "Поп", "Переиздание'26", "SS/SS"),
    ))
    assert dto.artist_raw == "A-ha"
    assert dto.title_raw == "Analogue (2LP)"
    assert dto.format_raw == "2xLP"


def test_out_of_stock():
    dto = _parse(_card_html(availability="http://schema.org/OutOfStock"))
    assert dto.status == "out_of_stock"


def test_no_price_is_on_request():
    dto = _parse(_card_html(price="", availability=""))
    assert dto.price_rub is None
    assert dto.status == "on_request"


def test_condition_only_from_grading_line():
    """Последняя строка не грейдинг — condition пустой, а не «Оригинал»."""
    dto = _parse(_card_html(descr_lines=("Европа /", "American", "Рок", "Оригинал")))
    assert dto.condition is None


def test_card_without_id_skipped():
    html = '<div class="products-grid-item"><a href="/lp/item/1-x">x</a></div>'
    assert _parse_card(_extract_cards(html)[0], BASE) is None
