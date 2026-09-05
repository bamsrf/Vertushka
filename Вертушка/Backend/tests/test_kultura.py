"""Тесты парсера Kultura Record Store (kulturarecordstore.ru).

Образцы — реальные товары Tilda store-API (снято 05.09.2026).
"""
from decimal import Decimal

from app.services.scrapers.shops.kultura import (
    KulturaParser,
    _descr_kv,
    _split_artist_album,
)

MUSIC = "339869322140"      # Пластинки / Кассеты / CD
BOOKS = "249075337969"      # Аксессуары / Книги
CERTS = "782751268808"      # Сертификаты / Подписки


def _p(**over) -> dict:
    base = {
        "uid": "674100098223",
        "title": "Aleksi Perala ‎- Resonance",
        "price": "4300.0000",
        "priceold": "",
        "quantity": "2",
        "sku": "TRP028RP",
        "url": "https://kulturarecordstore.ru/store/tproduct/197833805-674100098223-x",
        "descr": 'Лейбл: трип ‎– TRP028RP<br />Формат: 2 × 12"<br />Дата выхода: 2023<br />Стиль: Techno',
        "partuids": f"[{MUSIC}]",  # живой API отдаёт JSON-СТРОКОЙ, не списком
        "gallery": '[{"img":"https://static.tildacdn.com/x/cover.jpg"}]',
    }
    base.update(over)
    return base


def _parse(**over):
    return KulturaParser.parse_product(KulturaParser.__new__(KulturaParser), _p(**over))


# ---- Разбор title -------------------------------------------------------- #

def test_title_strips_bidi_and_splits():
    a, al = _split_artist_album("Aleksi Perala ‎- Resonance".replace("‎", ""))
    assert a == "Aleksi Perala"
    assert al == "Resonance"


def test_alias_prefers_latin():
    a, al = _split_artist_album("박혜진 = Park Hye Jin - Before I Die")
    assert a == "Park Hye Jin"
    assert al == "Before I Die"


def test_hyphenated_artist_survives():
    a, al = _split_artist_album("Jay-Z - The Blueprint")
    assert a == "Jay-Z"
    assert al == "The Blueprint"


def test_acdc_no_space_hyphen_not_split():
    # «AC/DC» без пробелов вокруг слэша не трогаем; разделитель — ` - `
    a, al = _split_artist_album("AC/DC - Back In Black")
    assert a == "AC/DC"
    assert al == "Back In Black"


# ---- descr kv ------------------------------------------------------------ #

def test_descr_kv_parses_fields():
    kv = _descr_kv('Лейбл: трип ‎– TRP028RP<br />Формат: 2 × 12"<br />Дата выхода: 2023<br />Стиль: Techno')
    assert kv["формат"].startswith("2")
    assert kv["дата выхода"] == "2023"
    assert kv["стиль"] == "Techno"


# ---- parse_product ------------------------------------------------------- #

def test_full_product():
    dto = _parse()
    assert dto is not None
    assert dto.artist_raw == "Aleksi Perala"
    assert dto.title_raw == "Resonance"       # чистый альбом
    assert dto.year_raw == 2023
    assert dto.catalog_number == "TRP028RP"   # из sku
    assert dto.price_rub == Decimal("4300")
    assert dto.status == "in_stock"
    assert dto.raw_payload["label"] == "трип"
    assert dto.raw_payload["genre"] == "Techno"
    assert dto.image_url.endswith("cover.jpg")


def test_catalog_from_label_tail_when_sku_empty():
    dto = _parse(sku="")
    assert dto.catalog_number == "TRP028RP"    # хвост «Лейбл: трип – TRP028RP»


def test_internal_counter_sku_is_not_catalog():
    dto = _parse(sku="3", descr="Формат: LP")
    assert dto.catalog_number is None          # «3» — не катномер


def test_out_of_stock_zero_qty():
    dto = _parse(quantity="0")
    assert dto.status == "out_of_stock"


def test_preorder_detected():
    dto = _parse(title="Aphex Twin - Blackbox (предзаказ)", quantity="0")
    assert dto.status == "preorder"


def test_book_only_partition_is_skipped():
    dto = _parse(title="Рэндалл М. Музыка побега. История Radiohead",
                 partuids=f"[{BOOKS}]", sku="")
    assert dto is None


def test_certificate_partition_skipped():
    dto = _parse(title="Подарочный сертификат (2000)", partuids=f"[{CERTS}]", sku="")
    assert dto is None


def test_vinyl_in_two_partitions_kept():
    # Винил из «Новинки» + музыкальной партиции — остаётся
    dto = _parse(partuids=f"[893420959164, {MUSIC}]")
    assert dto is not None
    assert dto.artist_raw == "Aleksi Perala"


def test_book_by_title_without_partition_skipped():
    # Партиций нет, но «книга» в названии — страховочный regex
    dto = _parse(title="Книга: История джаза", partuids="[]", sku="")
    assert dto is None
