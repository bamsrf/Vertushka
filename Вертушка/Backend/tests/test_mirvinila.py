"""Тесты парсера «Пластиночная №1» (mirvinila.com, InSales collection-API).

Образцы — реальные товары витрины (снято 10.09.2026).
"""
import json
from decimal import Decimal

import pytest

from app.services.scrapers.shops.mirvinila import (
    MirvinilaParser,
    _characteristics,
    _split_artist_album,
)

# property_id → название; у живой витрины они именно такие, но парсер обязан
# ходить по НАЗВАНИЮ, поэтому в тестах ниже id местами намеренно другие.
_PROPS = [
    {"id": 58365978, "title": "Формат носителя"},
    {"id": 58365975, "title": "Год"},
    {"id": 58396019, "title": "Лейбл"},
    {"id": 58396020, "title": "Страна"},
    {"id": 58396018, "title": "Уникальный код"},
    {"id": 58365976, "title": "Состояние винила"},
    {"id": 58365977, "title": "Состояние конверта"},
]


def _p(**over) -> dict:
    base = {
        "id": 1916857505,
        "title": "Pink Floyd ‎– A Collection Of Great Dance Songs (Австралия 1981г.) T",
        "url": "/collection/novye-postupleniya/product/pink-floyd-a-collection",
        "available": True,
        "properties": list(_PROPS),
        "characteristics": [
            {"property_id": 58365978, "title": "LP"},
            {"property_id": 58365975, "title": "1981"},
            {"property_id": 58396019, "title": "Harvest"},
            {"property_id": 58396020, "title": "Австралия"},
            {"property_id": 58396018, "title": "SBP 237729"},
            {"property_id": 58365976, "title": "EX"},
            {"property_id": 58365977, "title": "NM"},
            {"property_id": -6, "title": "Хобби и развлечения/Коллекционирование"},
        ],
        "variants": [
            {"sku": "4356268053", "barcode": None, "quantity": 2, "price": "5400.0"}
        ],
        "first_image": {
            "url": "https://cdn.insales-shop.ru/images/products/1/1/1/thumb_IMG.jpg",
            "original_url": "https://cdn.insales-shop.ru/images/products/1/1/1/IMG.jpg",
            "large_url": "https://cdn.insales-shop.ru/images/products/1/1/1/large_IMG.jpg",
        },
    }
    base.update(over)
    return base


def _parse(**over):
    return MirvinilaParser.parse_product(MirvinilaParser.__new__(MirvinilaParser), _p(**over))


# ---- Разбор названия ---------------------------------------------------- #

def test_splits_artist_and_strips_country_year_tail():
    artist, album = _split_artist_album(
        "Pink Floyd ‎– A Collection Of Great Dance Songs (Австралия 1981г.) T"
    )
    assert artist == "Pink Floyd"
    # Скобочный хвост и одиночная буква-пометка не должны попасть в название:
    # страна и год лежат отдельными свойствами, а в records.title их нет.
    assert album == "A Collection Of Great Dance Songs"


def test_cd_prefix_dropped():
    artist, album = _split_artist_album("CD 10cc - Ten Out Of 10 (Япония 1991г.)")
    assert artist == "10cc"
    assert album == "Ten Out Of 10"


def test_hyphenated_artist_survives():
    artist, album = _split_artist_album("Jay-Z – The Blueprint")
    assert artist == "Jay-Z"
    assert album == "The Blueprint"


def test_disc_count_marker_stripped_before_parenthesis():
    """«… Nuotaka 2LP (СССР 1978г.)» — счётчик пластинок стоит ПЕРЕД скобкой.
    На проде такой хвост был у 15% названий."""
    artist, album = _split_artist_album("V. Ganelinas – Velnio Nuotaka 2LP (СССР 1978г.)")
    assert artist == "V. Ganelinas"
    assert album == "Velnio Nuotaka"


def test_format_marker_after_parenthesis_stripped():
    """«… (США 1997г.) EP» — а тут маркер ПОСЛЕ скобки, и скобка уже не в конце
    строки. Срезать надо оба, в любом порядке."""
    artist, album = _split_artist_album("Big Punisher – I'm Not A Player (США 1997г.) EP")
    assert artist == "Big Punisher"
    assert album == "I'm Not A Player"


def test_multi_disc_counts_stripped():
    _, album = _split_artist_album("Бетховен – 9 симфоний 9LP (СССР 1980г.)")
    assert album == "9 симфоний"


def test_year_range_album_survives_tail_strip():
    """«1962 - 1966 2LP»: срезаем только формат, диапазон лет остаётся."""
    artist, album = _split_artist_album("The Beatles ‎– 1962 - 1966 2LP (Япония 1973г.)")
    assert artist == "The Beatles"
    assert album == "1962 - 1966"


def test_colour_marker_after_parenthesis_stripped():
    """«(Европа 2026г.) Yellow» — цвет приезжает из свойства «Формат носителя»,
    в названии он лишний."""
    artist, album = _split_artist_album(
        "Various – The Platinum Connection 3LP (Европа 2026г.) Yellow"
    )
    assert artist == "Various"
    assert album == "The Platinum Connection"


def test_promo_marker_after_parenthesis_stripped():
    _, album = _split_artist_album("Сборник - The best of screen music (Япония) Promo")
    assert album == "The best of screen music"


def test_non_word_tails_after_parenthesis_stripped():
    """Хвост не всегда слово: встречаются «LP+» и «7"»."""
    _, a1 = _split_artist_album("Steel Pulse – Baggariddim (Европа 1985г.) LP+")
    assert a1 == "Baggariddim"
    _, a2 = _split_artist_album(
        'Duran Duran – Is There Something I Should Know? (Япония 1983г.) 7"'
    )
    assert a2 == "Is There Something I Should Know?"


def test_parenthesis_that_is_part_of_the_name_survives():
    """Предохранитель: у названия со скобкой, но без страны/года, слова после
    скобки отрезать нечем — цикл не должен съесть само название."""
    artist, album = _split_artist_album("Barrett Strong – Money (That's What I Want)")
    assert artist == "Barrett Strong"
    assert album == "Money"  # скобка-хвост срезана, но само название цело


def test_numeric_opus_survives():
    """«ор. 14» — часть названия, а не хвост."""
    _, album = _split_artist_album("Берлиоз - Фантастическая симфония ор. 14 (Япония)")
    assert album == "Фантастическая симфония ор. 14"


def test_title_made_entirely_of_tails_is_not_emptied():
    """Если срезать всё, матчеру уедет пустота — лучше оставить как есть."""
    _, album = _split_artist_album("Various – LP")
    assert album


def test_title_without_separator_keeps_whole_as_album():
    artist, album = _split_artist_album("Сборник Лучшее")
    assert artist is None
    assert album == "Сборник Лучшее"


# ---- Характеристики ----------------------------------------------------- #

def test_characteristics_resolved_by_property_name():
    ch = _characteristics(_p())
    assert ch["Формат носителя"] == "LP"
    assert ch["Лейбл"] == "Harvest"
    assert ch["Состояние винила"] == "EX"
    assert ch["Состояние конверта"] == "NM"


def test_characteristics_survive_renumbered_property_ids():
    """id принадлежат витрине и меняются при правках в админке — парсер обязан
    опираться на название свойства, а не на число."""
    product = _p(
        properties=[{"id": 777, "title": "Формат носителя"}],
        characteristics=[{"property_id": 777, "title": "2LP"}],
    )
    assert _characteristics(product)["Формат носителя"] == "2LP"


# ---- Товар целиком ------------------------------------------------------ #

def test_parses_full_listing():
    dto = _parse()
    assert dto is not None
    assert dto.artist_raw == "Pink Floyd"
    assert dto.title_raw == "A Collection Of Great Dance Songs"
    assert dto.year_raw == 1981
    assert dto.price_rub == Decimal("5400.0")
    assert dto.status == "in_stock"
    assert dto.condition == "EX"
    assert dto.catalog_number == "SBP237729"
    assert dto.url == "https://mirvinila.com/collection/novye-postupleniya/product/pink-floyd-a-collection"
    assert dto.external_id == "1916857505"
    assert dto.raw_payload["label"] == "Harvest"
    assert dto.raw_payload["country"] == "Австралия"
    assert dto.raw_payload["sleeve_condition"] == "NM"


def test_image_is_original_not_thumb():
    """`first_image.url` у InSales — это thumb_*. Апскейл миниатюр уже однажды
    сделал половину обложек в приложении пиксельными."""
    dto = _parse()
    assert dto.image_url == "https://cdn.insales-shop.ru/images/products/1/1/1/IMG.jpg"
    assert "thumb" not in dto.image_url


# ---- Отсев не-носителей ------------------------------------------------- #

def test_accessory_without_format_is_skipped():
    """У слипматов, щёток и усилителей Radiotehnika нет «Формата носителя» —
    проверено на разделах магазина: 39 из 39 и 8 из 8."""
    dto = _parse(
        title="Слипмат Evomat First Mat Черный",
        characteristics=[{"property_id": -6, "title": "Хобби и развлечения"}],
    )
    assert dto is None


def test_product_without_title_is_skipped():
    assert _parse(title="") is None


def test_product_without_url_is_skipped():
    assert _parse(url="") is None


# ---- Наличие и цена ----------------------------------------------------- #

def test_zero_quantity_is_out_of_stock():
    dto = _parse(variants=[{"quantity": 0, "price": "5400.0"}])
    assert dto.status == "out_of_stock"


def test_available_false_is_out_of_stock():
    """Хвост каталога — коллекция «ждём поступление»: флаг и остаток совпали
    на 700 товарах из 700."""
    dto = _parse(available=False, variants=[{"quantity": 0, "price": "5400.0"}])
    assert dto.status == "out_of_stock"


def test_no_price_is_on_request():
    dto = _parse(variants=[{"quantity": 2, "price": ""}])
    assert dto.status == "on_request"
    assert dto.price_rub is None


def test_max_price_across_variants_and_summed_quantity():
    dto = _parse(variants=[
        {"quantity": 1, "price": "3000.0"},
        {"quantity": 2, "price": "5400.0"},
    ])
    assert dto.price_rub == Decimal("5400.0")
    assert dto.raw_payload["quantity"] == 3


def test_barcode_normalized_when_present():
    dto = _parse(variants=[{"quantity": 1, "price": "100", "barcode": "5016919450015"}])
    assert dto.barcode == "5016919450015"


# ---- Обход каталога ----------------------------------------------------- #

class _FakeHttp:
    """Отдаёт заранее заготовленные страницы каталога."""

    def __init__(self, pages):
        self.pages = pages
        self.requested = []

    async def get_text(self, url, **kwargs):
        self.requested.append(url)
        page = int(url.split("page=")[1].split("&")[0])
        return json.dumps(self.pages[page - 1] if page <= len(self.pages) else {"products": []})


def _page(n_available, n_sold=0):
    prods = [_p(id=i, available=True) for i in range(n_available)]
    prods += [_p(id=1000 + i, available=False,
                 variants=[{"quantity": 0, "price": "100"}]) for i in range(n_sold)]
    return {"products": prods}


@pytest.mark.asyncio
async def test_crawl_stops_at_stock_boundary():
    """Каталог отсортирован стоком вперёд: 20.9k позиций, из них в наличии
    ~5.7k. Обход обязан останавливаться на границе, а не тащить 150 страниц
    распроданного архива."""
    parser = MirvinilaParser.__new__(MirvinilaParser)
    parser.http = _FakeHttp([
        _page(100),          # стр. 1 — весь сток
        _page(100),          # стр. 2 — весь сток
        _page(0, 100),       # стр. 3 — архив
        _page(0, 100),       # стр. 4 — архив, здесь обход и кончится
        _page(0, 100),       # стр. 5 — не должна быть запрошена
    ])
    got = [p async for p in parser._iter_products()]
    assert len(got) == 200
    assert len(parser.http.requested) == 4


@pytest.mark.asyncio
async def test_single_sold_page_does_not_end_crawl():
    """Одна аномальная страница не должна обрезать каталог — иначе смена
    сортировки на витрине молча урежет магазин до нескольких сотен позиций."""
    parser = MirvinilaParser.__new__(MirvinilaParser)
    parser.http = _FakeHttp([
        _page(100),
        _page(0, 100),       # провал в середине
        _page(100),          # сток продолжился
        _page(0, 100),
        _page(0, 100),       # только теперь конец
    ])
    got = [p async for p in parser._iter_products()]
    assert len(got) == 200


@pytest.mark.asyncio
async def test_crawl_stops_on_short_page():
    parser = MirvinilaParser.__new__(MirvinilaParser)
    parser.http = _FakeHttp([_page(10)])
    got = [p async for p in parser._iter_products()]
    assert len(got) == 10
    assert len(parser.http.requested) == 1
