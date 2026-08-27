"""Катномер-канал обложек: нормализация-зеркало, коллизии, консерватизм.

Канал матчит Discogs-релизы с CAA по (каталожный номер, лейбл) — ключу
слабее штрихкода. Всё, что защищает от ложных обложек, живёт в трёх местах:
зеркальная нормализация (ключи обязаны совпадать байт в байт с Discogs-
стороной), выбрасывание неоднозначных ключей (_resolve_key) и правило
года при применении. Эти тесты фиксируют все три.
"""
import re

from app.scripts.ingest_discogs_dump import _norm_catalog
from app.scripts.ingest_mb_catno_covers import (
    _MAX_YEAR_DIFF,
    _APPLY_SQL,
    _VALIDATE_SQL,
    _catno_ok,
    _norm_key,
    _resolve_key,
)


def test_normalization_mirrors_discogs_side():
    """Ключ обязан совпадать с catalog_norm из ingest_discogs_dump.

    Если нормализации разойдутся, канал не упадёт — он молча перестанет
    матчить (или начнёт матчить не то). Сверяем на реальных формах записи
    катномеров.
    """
    samples = [
        "AIRAC-1347", "airac 1347", "TMO 10858", "VK 43.", "wabb-133",
        "  b 004 ", "С 60—28837",  # кириллица и длинное тире — как есть
    ]
    for raw in samples:
        assert _norm_key(raw) == _norm_catalog(raw), raw


def test_junk_catnos_are_rejected():
    assert not _catno_ok(_norm_key("none"))
    assert not _catno_ok(_norm_key("[none]"))  # реальная MB-заглушка из release_label
    assert not _catno_ok(_norm_key("N/A".replace("/", "")))  # NA
    assert not _catno_ok(_norm_key("07"))    # короче 3 — шум
    assert not _catno_ok(None)
    assert _catno_ok(_norm_key("B-004"))
    assert _catno_ok(_norm_key("1600"))


def test_resolve_key_single_album_takes_earliest_press():
    """Один альбом (release group) → берём самый ранний датированный пресс."""
    got = _resolve_key([
        ("mbid-reissue", 10, 2015),
        ("mbid-orig", 10, 1971),
        ("mbid-undated", 10, None),
    ])
    assert got == ("mbid-orig", 10, 1971)


def test_resolve_key_drops_ambiguous_albums():
    """Два разных альбома под одним ключом — ключ выбрасывается ЦЕЛИКОМ.

    Это главный предохранитель канала: лейблы переиспользуют катномера,
    и «хоть какая-то обложка» здесь означала бы чужой альбом на карточке —
    ровно инцидент с подменёнными обложками, только массовый.
    """
    assert _resolve_key([("a", 10, 1971), ("b", 20, 1971)]) is None
    assert _resolve_key([]) is None


def test_resolve_key_undated_single_album_is_kept():
    """Без дат, но альбом один — берём детерминированно первый mbid."""
    got = _resolve_key([("zzz", 10, None), ("aaa", 10, None)])
    assert got == ("aaa", 10, None)


def test_apply_sql_is_conservative():
    """Применение: только пустые строки, год с обеих сторон, |Δ| <= 2."""
    assert "cover_image_url IS NULL" in _APPLY_SQL
    assert "d.year IS NOT NULL AND m.year IS NOT NULL" in _APPLY_SQL
    assert f"abs(d.year - m.year) <= {_MAX_YEAR_DIFF}" in _APPLY_SQL
    # Валидация обязана мерить ровно тот джойн, который применяется.
    for cond in ("m.catno_norm = d.catalog_norm", "d.year IS NOT NULL"):
        assert cond in _VALIDATE_SQL and cond in _APPLY_SQL


def test_sql_has_no_bindparam_cast_trap():
    """`:param::type` ломает SQLAlchemy/asyncpg молча — сторожим и тут."""
    bad = re.compile(r":\w+::")
    assert not bad.search(_VALIDATE_SQL)
    assert not bad.search(_APPLY_SQL)
