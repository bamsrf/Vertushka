"""Лестница уровней бэкенда обязана совпадать с клиентской.

Расхождение = push объявляет «Волна», а в hero юзер видит «Эхо». Парсим
Mobile/lib/archetype.ts регуляркой (тянуть node в тесты не хочется) и
сверяем ключи, лейблы и пороги.
"""
import re
from pathlib import Path

import pytest

from app.services.achievements.levels import (
    LEVELS,
    TIER_WEIGHT,
    counts_toward_level,
    level_index_for_score,
    resolve_definition,
    weight_for_code,
)

ARCHETYPE_TS = (
    Path(__file__).resolve().parents[2] / "Mobile" / "lib" / "archetype.ts"
)


def _parse_mobile_levels() -> list[tuple[str, str, int]]:
    src = ARCHETYPE_TS.read_text(encoding="utf-8")
    ladder = src.split("export const LEVELS")[1]
    blocks = re.findall(
        r"key:\s*'([^']+)',\s*\n\s*label:\s*'([^']+)',\s*\n\s*threshold:\s*(\d+)",
        ladder,
    )
    return [(key, label, int(threshold)) for key, label, threshold in blocks]


def _parse_mobile_weights() -> dict[str, int]:
    src = ARCHETYPE_TS.read_text(encoding="utf-8")
    block = src.split("TIER_WEIGHT")[1].split("}")[0]
    return {k: int(v) for k, v in re.findall(r"(\w+):\s*(\d+)", block)}


@pytest.mark.skipif(not ARCHETYPE_TS.exists(), reason="Mobile не в этом чекауте")
def test_levels_match_mobile():
    mobile = _parse_mobile_levels()
    backend = [(lv.key, lv.label, lv.threshold) for lv in LEVELS]
    assert backend == mobile


@pytest.mark.skipif(not ARCHETYPE_TS.exists(), reason="Mobile не в этом чекауте")
def test_tier_weights_match_mobile():
    assert TIER_WEIGHT == _parse_mobile_weights()


def test_thresholds_are_strictly_increasing():
    thresholds = [lv.threshold for lv in LEVELS]
    assert thresholds == sorted(thresholds)
    assert len(set(thresholds)) == len(thresholds)
    assert thresholds[0] == 0


@pytest.mark.parametrize(
    "score,expected",
    [
        (0, 0),
        (6, 0),
        (7, 1),
        (14, 1),
        (15, 2),
        (24, 2),
        (25, 3),
        (49, 3),
        (1049, 8),
        (1050, 9),
        (99999, 9),
    ],
)
def test_level_index_for_score(score: int, expected: int):
    assert level_index_for_score(score) == expected


# --- Динамические коды -------------------------------------------------------
#
# Ачивки серии «Полная дискография» хранятся в БД как `H2:king-crimson`, но в
# реестре зарегистрированы под именем `H2_artist_studio_full`. Прямой поиск по
# коду их не находит, и без резолва по префиксу они молча стоили бы 0 XP —
# именно это и произошло при первом прогоне миграции.


@pytest.mark.parametrize("code,expected_def", [
    ("H2:king-crimson", "H2_artist_studio_full"),
    ("H4:some-master", "H4_master_pressings_5"),
    ("H5:blue-note", "H5_label_x20"),
])
def test_dynamic_code_resolves_to_definition(code, expected_def):
    defn = resolve_definition(code)
    assert defn is not None, f"{code} не разрешился в определение"
    assert defn.code == expected_def


@pytest.mark.parametrize("code", ["H2:king-crimson", "H4:x", "H5:blue-note"])
def test_dynamic_code_has_weight(code):
    assert weight_for_code(code) > 0
    assert counts_toward_level(code) is True


def test_unknown_dynamic_code_is_harmless():
    assert resolve_definition("ZZ:nonsense") is None
    assert weight_for_code("ZZ:nonsense") == 0
    assert counts_toward_level("ZZ:nonsense") is False
