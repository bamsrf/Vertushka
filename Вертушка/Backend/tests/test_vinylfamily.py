"""Тесты парсера Vinyl Family (vinylfamily.shop).

Образцы — реальные товары Tilda store-API (снято 05.09.2026).
"""
from decimal import Decimal

from app.services.scrapers.shops.vinylfamily import (
    VinylFamilyParser,
    _split_artist_album,
    _text_kv,
)


def _p(**over) -> dict:
    base = {
        "uid": "1866202431-5",
        "title": "The Prodigy - The Fat Of The Land (LP)",
        "price": "5180.0000",
        "priceold": "",
        "quantity": "1",
        "sku": "5",
        "url": "https://vinylfamily.shop/tproduct/1866202431-5-x",
        "text": (
            "Формат: виниловая пластинка <br />Количество носителей: 2 <br />"
            "Лейбл: XL <br />Дата релиза: 27.06.1997 <br />"
            "Номер по каталогу: 7248811 <br /><br />Трек-лист: <br />"
            "A1. Smack My Bitch Up <br />A2. Breathe"
        ),
        "descr": "",
        "characteristics": [
            {"title": "Жанр", "value": "Электроника"},
            {"title": "Формат", "value": "Виниловая пластинка"},
        ],
        "gallery": '[{"img":"https://static.tildacdn.com/x/cover.jpg"}]',
    }
    base.update(over)
    return base


def _parse(**over):
    return VinylFamilyParser.parse_product(
        VinylFamilyParser.__new__(VinylFamilyParser), _p(**over)
    )


def test_split_strips_trailing_format_paren():
    a, al, fmt = _split_artist_album("The Prodigy - The Fat Of The Land (LP)")
    assert a == "The Prodigy"
    assert al == "The Fat Of The Land"
    assert fmt == "LP"


def test_split_acdc_hyphen():
    a, al, fmt = _split_artist_album("AC/DC - Back In Black (LP)")
    assert a == "AC/DC"
    assert al == "Back In Black"


def test_hyphenated_artist_survives():
    a, al, _ = _split_artist_album("Jay-Z - The Blueprint (2LP)")
    assert a == "Jay-Z"
    assert al == "The Blueprint"


def test_text_kv_ignores_tracklist():
    kv = _text_kv(_p()["text"])
    assert kv["лейбл"] == "XL"
    assert kv["номер по каталогу"] == "7248811"
    assert kv["дата релиза"] == "27.06.1997"


def test_full_product():
    dto = _parse()
    assert dto is not None
    assert dto.artist_raw == "The Prodigy"
    assert dto.title_raw == "The Fat Of The Land"
    assert dto.year_raw == 1997
    assert dto.catalog_number == "7248811"     # из text, не из sku="5"
    assert dto.price_rub == Decimal("5180")
    assert dto.status == "in_stock"
    assert dto.raw_payload["label"] == "XL"
    assert dto.image_url.endswith("cover.jpg")


def test_13digit_catno_routed_to_barcode():
    dto = _parse(text="Лейбл: EMI <br />Номер по каталогу: 5099902988313")
    assert dto.barcode == "5099902988313"
    assert dto.catalog_number is None


def test_alnum_catno_stays_catalog():
    dto = _parse(text="Лейбл: Aeon <br />Номер по каталогу: AEON017")
    assert dto.catalog_number == "AEON017"
    assert dto.barcode is None


def test_internal_sku_not_used_as_catalog():
    # даже если текст без катномера — sku="5" не должен стать каталогом
    dto = _parse(text="Формат: виниловая пластинка", sku="5")
    assert dto.catalog_number is None


def test_out_of_stock_zero_qty():
    dto = _parse(quantity="0")
    assert dto.status == "out_of_stock"


def test_preorder_detected():
    dto = _parse(title="Behemoth - The Satanist (LP) предзаказ", quantity="0")
    assert dto.status == "preorder"


def test_merch_by_title_skipped():
    dto = _parse(title="Vinyl Family - Футболка с логотипом")
    assert dto is None


def test_format_from_characteristics():
    dto = _parse()
    assert dto.format_raw  # infer_format нашёл винил
