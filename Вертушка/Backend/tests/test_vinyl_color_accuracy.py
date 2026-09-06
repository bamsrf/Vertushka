"""WS-фикс 06.09: точность определения цвета винила.

Корпус «реальный вход → ожидаемый цвет» на обоих классах ошибок, которые
не ловил ни один прежний тест:
  (б) ложный цвет из ЛЕЙБЛА/жанра/артворка (Blue Note → blue, black metal → black);
  (а) нюансный цветной, схлопнутый в black (Translucent Black, Splatter).

Именно эти кейсы держат от регрессий — аудит 06.09 показал, что 67% blue у
plastinka были ложные (лейбл Blue Note), а «Translucent Black» прятался как
обычный чёрный.
"""
from app.services.scrapers.extractors import COLORED_UNSPECIFIED, infer_vinyl_color


# ---- (б) Ложные срабатывания: чёрный из свободного прохода не течёт ------- #

def test_black_metal_genre_not_color():
    # «black» из жанра без cue рядом — не цвет пресса
    assert infer_vinyl_color("The Black Dahlia Murder - Nightbringers") is None


def test_black_label_not_color():
    assert infer_vinyl_color("Lee Konitz At Storyville Лейбл: Black Lion") is None


def test_lone_black_word_dropped():
    assert infer_vinyl_color("Back In Black") is None


def test_black_vinyl_with_cue_still_detected():
    # но явный «black vinyl» (cue-проход №1) — остаётся чёрным
    assert infer_vinyl_color("Limited black vinyl") == "black"


# ---- (б) Ложный цвет из лейбла убирается через exclude ------------------- #

def test_blue_note_label_excluded():
    # Как зовёт plastinka: лейбл в exclude → синего винила нет
    text = "Hank Mobley A Slice Of The Top Лейбл: Blue Note 180 гр"
    assert infer_vinyl_color(text, exclude=["Hank Mobley", "A Slice Of The Top", "Blue Note"]) is None


def test_blue_note_without_exclude_would_leak():
    # контроль: без выреза лейбла — протекает (демонстрация корня бага)
    assert infer_vinyl_color("A Slice Of The Top Blue Note") == "blue"


# ---- (а) Нюансный цветной не прячется в black ---------------------------- #

def test_translucent_black_is_colored_not_black():
    c = infer_vinyl_color("Limited Translucent Black Vinyl")
    assert c and c != "black"          # clear/translucent → цветной


def test_splatter_with_black_is_colored():
    c = infer_vinyl_color("Clear With Yellow Splatter & Black")
    assert c in ("yellow", "splatter", "clear")   # первый не-чёрный сигнал
    assert c != "black"


def test_yellow_black_prefers_non_black():
    assert infer_vinyl_color("Yellow / Black marble") in ("yellow", "marble")


# ---- легитимные цвета сохраняются --------------------------------------- #

def test_cue_orange_kept():
    assert infer_vinyl_color("RSD26 Orange Vinyl") == "orange"


def test_generic_colored_marker_kept():
    assert infer_vinyl_color("Fear Of A Black Planet (цветной винил)") == COLORED_UNSPECIFIED


def test_free_pass_real_color_kept():
    assert infer_vinyl_color("Pressed on gorgeous red wax") == "red"
