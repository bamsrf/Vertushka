"""Строка редкости на share-карточке ачивки.

Карточка уходит в публичные Stories, поэтому политика жёсткая: показываем
процент, только когда он читается как флекс. «87% уже открыли» на картинке
работает против юзера, а на базе из четырёх человек процент вообще ничего
не значит.
"""
from datetime import datetime

import pytest

from app.services.achievements.registry import all_definitions
from app.services.achievements.share_card import (
    RARITY_MIN_USERS,
    RARITY_SHARE_MAX_PCT,
    rarity_share_line,
    render_for_format,
)


@pytest.mark.parametrize(
    "pct,total,expected",
    [
        (0.003, 900, "Меньше 1% коллекционеров"),
        (0.024, 900, "Всего у 2.4% коллекционеров"),
        (0.03, 900, "Всего у 3% коллекционеров"),   # без хвостового «.0»
        (0.099, 900, "Всего у 9.9% коллекционеров"),
        (0.12, 900, "Всего у 12% коллекционеров"),
        (RARITY_SHARE_MAX_PCT, 900, "Всего у 25% коллекционеров"),
    ],
)
def test_rare_enough_gets_a_line(pct, total, expected):
    assert rarity_share_line(pct, total) == expected


@pytest.mark.parametrize(
    "pct,total",
    [
        (RARITY_SHARE_MAX_PCT + 0.01, 900),  # массовая — молчим
        (0.87, 900),
        (1.0, 900),
        (0.03, RARITY_MIN_USERS - 1),        # юзеров мало — процент это шум
        (0.0, 900),                          # никто не открыл: нечего хвалить
    ],
)
def test_not_rare_or_too_few_users_stays_silent(pct, total):
    assert rarity_share_line(pct, total) is None


def _first_definition():
    return next(d for d in all_definitions() if d.title_ru)


def test_card_renders_with_and_without_rarity():
    """Плашка не должна ломать рендер ни в одном из сочетаний с уликой."""
    defn = _first_definition()
    variants = [
        ("Radiohead — Kid A", "Всего у 2.4% коллекционеров"),
        (None, "Меньше 1% коллекционеров"),
        ("Radiohead — Kid A", None),
        (None, None),
    ]
    for evidence, rarity in variants:
        png = render_for_format(
            defn,
            username="vlad",
            unlocked_at=datetime(2026, 9, 7),
            fmt="stories",
            evidence_text=evidence,
            rarity_text=rarity,
        )
        assert png.startswith(b"\x89PNG"), (evidence, rarity)


def test_rarity_changes_the_pixels():
    """Защита от «параметр принят и потерян»: карточка обязана отличаться."""
    defn = _first_definition()
    common = dict(
        username="vlad",
        unlocked_at=datetime(2026, 9, 7),
        fmt="stories",
        evidence_text="Radiohead — Kid A",
    )
    with_rarity = render_for_format(defn, rarity_text="Меньше 1% коллекционеров", **common)
    without = render_for_format(defn, rarity_text=None, **common)
    assert with_rarity != without
