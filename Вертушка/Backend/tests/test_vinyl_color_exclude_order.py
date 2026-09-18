"""Вырезка артиста/альбома перед поиском цвета: порядок и пометки в скобках."""
from app.services.scrapers.extractors import COLORED_UNSPECIFIED, infer_vinyl_color


def test_artist_inside_album_does_not_leak_album_colour():
    """Прод, plastinka: «Красная» из названия альбома уезжала цветом red."""
    artist = "Голубые Гитары"
    album = "Красная Шапочка, Серый Волк И Голубые Гитары"
    text = f"{artist} - {album} Лейбл: Мелодия"
    assert infer_vinyl_color(text, exclude=[artist, album, "Мелодия"]) is None


def test_order_of_exclude_does_not_matter():
    artist, album = "Roy Fox", "Golden Age Of Roy Fox"
    text = f"{artist} - {album}"
    assert infer_vinyl_color(text, exclude=[artist, album]) is None
    assert infer_vinyl_color(text, exclude=[album, artist]) is None


def test_shop_note_in_album_brackets_survives():
    """plastinka кладёт «(цветной винил)» в название — это цвет, не название."""
    artist, album = "Weezer", "Weezer (цветной винил)"
    text = f"{artist} - {album}"
    assert infer_vinyl_color(text, exclude=[artist, album]) == COLORED_UNSPECIFIED


def test_bracketed_colour_in_album_survives():
    artist, album = "Beirut", "A Study of Losses (Blue Vinyl)"
    assert infer_vinyl_color(f"{artist} - {album}", exclude=[artist, album]) == "blue"


import pytest

#: Реальные входы с прода (прогон парсеров 18.09, 17 834 вызова).
@pytest.mark.parametrize("text,exclude,expected", [
    # скобка — часть названия, цвет из неё не берём
    ("Bullion - Funnybones / Payroll (Paul White's Clean Dub)",
     ["Bullion", "Funnybones / Payroll (Paul White's Clean Dub)"], None),
    ("King Gizzard – Murder Of The Universe (Live At Red Rocks 2022)",
     ["King Gizzard", "Murder Of The Universe (Live At Red Rocks 2022)"], None),
    ("Борис Бужор - Аудиоспектакль (сказка) - Золотой ключик, или Приключения Буратино LP",
     ["Борис Бужор", "Аудиоспектакль (сказка) - Золотой ключик, или Приключения Буратино"], None),
    ("Miles Davis - Kind Of Blue LP", ["Miles Davis", "Kind Of Blue"], None),
    # скобка/хвост — пометка о прессе, цвет берём
    ("Peggy Gou - I Hear You (Blue Edition)", ["Peggy Gou", "I Hear You (Blue Edition)"], "blue"),
    ("RSD26 Sex Pistols - Jubilee (pink) (RSD26) LP", ["Sex Pistols", "Jubilee (pink)"], "pink"),
    ("Muse - Muscle Museum - (RSD26) Green LP", ["Muse", "Muscle Museum - (RSD26) Green"], "green"),
    ("Deep Purple – Deep Purple In Rock Coloured Purple LP",
     ["Deep Purple", "Deep Purple In Rock Coloured Purple"], "purple"),
    ("Cerrone – Cerrone 3 - Supernature - Green LP",
     ["Cerrone", "Cerrone 3 - Supernature - Green"], "green"),
    # цвет перед выделкой главнее выделки
    ("Coldplay – Moon Music (Red Translucent Vinyl)",
     ["Coldplay", "Moon Music (Red Translucent Vinyl)"], "red"),
    ("Moon Music (голубой прозрачный винил, + буклет)",
     ["Coldplay", "Moon Music (голубой прозрачный винил, + буклет)"], "blue"),
])
def test_real_prod_inputs(text, exclude, expected):
    assert infer_vinyl_color(text, exclude=exclude) == expected
