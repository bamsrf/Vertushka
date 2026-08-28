"""SQL-зеркало «семьи носителя» не должно расходиться с Python.

Зачем зеркало: `rematch_format_conflicts_batch` искала конфликты фильтром в
Python, а из базы брала 500 строк по `matched_at ASC`. У чистой строки
`matched_at` не меняется, поэтому она никогда не покидала окно — джоба каждую
ночь разглядывала одни и те же 500 майских листингов. Замер 28.08: 2 конфликта
в окне при 750 на проде. Предикат в SQL делает `LIMIT` лимитом на конфликты.

Цена зеркала — риск расхождения. Поэтому оно не пишется руками, а генерируется
из `_FORMAT_MAP`; тесты фиксируют, что генерация не врёт.
"""
import pytest

from app.services.listing_matcher import _format_family
from app.services.scrapers.extractors import (
    _FORMAT_MAP,
    FORMAT_FAMILY,
    infer_format,
    sql_format_family,
)

#: Реальные значения `store_listings.format_raw` и `records.format_type` с прода
#: (277 различных на 28.08) — здесь характерная выборка, включая пограничные.
REAL_VALUES = [
    "LP", "2xLP", "3xLP", "EP", "Single", "Box Set", "Vinyl", "Vinyl, LP",
    "CD", "2CD", "CDr", "SACD", "Cassette", "Cassette, Album", "CD, Album",
    "CD, Compilation", "CD, Single", "Vinyl, 12\"", "12\"", "10\"", "7\"",
    "Acetate", "Flexi-disc", "Shellac", "Lathe Cut", "File", "File, FLAC",
    "Blu-ray", "DVD", "VHS", "Laserdisc", "Minidisc", "Reel-To-Reel",
    "8-Track Cartridge", "All Media", "Hybrid", "PictureDisc", "винил",
    "кассета", "коробочное издание", "бокс-сет", "double LP", "2 x Vinyl",
]


def test_sql_mirror_covers_every_pattern():
    """Веток CASE ровно столько, сколько паттернов — ни одна не потерялась."""
    sql = sql_format_family("v")
    assert sql.count("WHEN ") == len(_FORMAT_MAP)


def test_generated_sql_has_no_colons():
    """Двоеточие в SQL ломает `text()`: SQLAlchemy читает `:имя` как bind.

    Ровно на этом падал первый вариант: паттерн «(?:lp|vinyl)» требовал
    параметр `lp` и запрос не собирался. Инвариант дешевле, чем ловить это
    ночью в проде.
    """
    assert ":" not in sql_format_family("sl.format_raw")


def test_box_set_has_no_family_in_both_paths():
    """Бокс бывает и виниловый, и CD — семьи у него нет, конфликт не доказуем.

    В SQL это ветка `THEN NULL`, а не отсутствие ветки: CASE обязан
    остановиться на боксе, иначе «Vinyl Box Set» провалился бы в ветку LP и
    получил семью, которой у него в Python нет.
    """
    assert infer_format("Box Set") == "Box Set"
    assert "Box Set" not in FORMAT_FAMILY
    assert _format_family("Vinyl Box Set") is None
    assert "THEN NULL" in sql_format_family("v")


def test_python_family_comes_from_the_shared_table():
    for fmt, family in FORMAT_FAMILY.items():
        # Формат из таблицы обязан быть тем, что реально отдаёт infer_format,
        # иначе таблица тихо перестанет применяться.
        assert any(f == fmt for _pattern, f in _FORMAT_MAP), fmt
        assert family in ("VINYL", "CD", "CASSETTE")


@pytest.mark.parametrize("value", REAL_VALUES)
def test_family_is_defined_for_real_values(value):
    """Функция не падает и отдаёт либо известную семью, либо None."""
    assert _format_family(value) in (None, "VINYL", "CD", "CASSETTE")
