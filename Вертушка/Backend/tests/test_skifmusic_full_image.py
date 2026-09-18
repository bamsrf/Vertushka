"""skifmusic: в каталоге — миниатюра, а нужен оригинал.

18.09.2026. skifmusic оказался главным источником мелких обложек: из 11 099
зеркал мельче 500px 7 224 пришли от него. JSON-LD каталога отдаёт
`/thumbs/{aa}/{bb}/270x270_1_normal_{hash}.webp`, а по тому же пути у магазина
лежит весь ряд; «x» — оригинал без ограничения. Замер: 270x180 → 1600x1065.
"""
from app.scripts.upgrade_skifmusic_covers import _PG_PATTERN, thumb_floor
from app.services.scrapers.shops.skifmusic import SkifmusicParser, full_size_image

BASE = "https://skifmusic.ru/thumbs/a5/5e/{}_1_normal_ec7e4729d4f83e9371822853ca2d.webp"


def test_thumbnail_becomes_original():
    assert full_size_image(BASE.format("270x270")) == BASE.format("x")


def test_every_size_token_maps_to_original():
    for token in ("270x270", "348x", "600x600", "1200x1200"):
        assert full_size_image(BASE.format(token)) == BASE.format("x"), token


def test_original_is_left_as_is():
    assert full_size_image(BASE.format("x")) == BASE.format("x")


def test_foreign_urls_pass_through():
    """Хуже, чем было, не станет: не узнали форму — отдаём как есть."""
    other = "https://skifmusic.ru/assets/32b94dd3/img/content/manager-photo.webp"
    assert full_size_image(other) == other


def test_list_and_empty_values():
    assert full_size_image([BASE.format("270x270"), "second"]) == BASE.format("x")
    assert full_size_image(None) is None
    assert full_size_image([]) is None
    assert full_size_image("") is None


def test_parser_emits_original():
    """Сквозь parse_product: в листинг должен уйти оригинал, не миниатюра."""
    product = {
        "name": "Виниловая пластинка Led Zeppelin – I (LP)",
        "url": "https://skifmusic.ru/product/784099-led-zeppelin-i-lp",
        "image": BASE.format("270x270"),
        "offers": {"price": "3990", "priceCurrency": "RUB",
                   "availability": "https://schema.org/InStock"},
    }
    dto = SkifmusicParser.__new__(SkifmusicParser).parse_product(product)
    assert dto is not None
    assert dto.image_url == BASE.format("x")


def test_floor_from_thumbnail_address():
    """Пол для замены файла мастера: он скачан с миниатюры, крупнее не бывает."""
    assert thumb_floor(BASE.format("270x270")) == 270
    assert thumb_floor(BASE.format("348x")) == 348
    assert thumb_floor(BASE.format("x")) is None
    assert thumb_floor(None) is None


def test_sql_pattern_is_the_same_rule():
    """Шаблон для Postgres обязан совпадать с парсерным (проверен и на проде)."""
    import re
    py = re.sub(_PG_PATTERN, r"\1x\2", BASE.format("270x270"))
    assert py == BASE.format("x")
