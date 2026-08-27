"""Катномер-канал обложек: нормализация-зеркало, коллизии, оборона в глубину.

Канал матчит Discogs-релизы с CAA по (каталожный номер, лейбл) — ключу
слабее штрихкода. После adversarial-ревью защита многослойная: зеркальная
нормализация, неоднозначность по ВСЕМУ MB (включая релизы без арта),
junk-фильтры катномеров И лейблов, потолок веерности, Python-сверка лейбла
как решающая, гейт --apply по непокрытой популяции. Тесты фиксируют каждый
слой — это ровно те места, чья тихая деградация кладёт чужую обложку на
карточку пользователя.
"""
import re

from app.scripts.ingest_discogs_dump import _norm_catalog
from app.scripts.ingest_mb_catno_covers import (
    _GATE_MIN_RG_KNOWN,
    _GATE_MIN_SAME_GROUP,
    _MAX_KEY_FANOUT,
    _MAX_YEAR_DIFF,
    _SQL_NORM_PATTERN,
    _catno_ok,
    _label_ok,
    _norm_key,
    _resolve_key,
    _validate_sql,
)


def test_normalization_mirrors_discogs_side():
    """Ключ обязан совпадать с catalog_norm из ingest_discogs_dump.

    Разъехавшиеся нормализации не падают — они молча перестают матчить.
    """
    samples = [
        "AIRAC-1347", "airac 1347", "TMO 10858", "VK 43.", "wabb-133",
        "  b 004 ", "С 60—28837",  # кириллица и длинное тире — как есть
    ]
    for raw in samples:
        assert _norm_key(raw) == _norm_catalog(raw), raw


def test_nbsp_is_stripped_on_both_sides():
    """NBSP: Python \\s его ест, а PG [[:space:]] — нет.

    Поэтому NBSP явно вписан в ОБА класса; иначе лейбл из копипасты
    (Blue\\xa0Note) молча терял бы матчи.
    """
    assert _norm_key("Blue\xa0Note") == "BLUENOTE"
    assert "\xa0" in _SQL_NORM_PATTERN


def test_junk_catnos_are_rejected():
    assert not _catno_ok(_norm_key("none"))
    assert not _catno_ok(_norm_key("[none]"))   # реальная MB-заглушка
    assert not _catno_ok(_norm_key("no number"))
    assert not _catno_ok(_norm_key("07"))       # короче 3 — шум
    assert not _catno_ok(None)
    assert _catno_ok(_norm_key("B-004"))
    assert _catno_ok(_norm_key("1600"))


def test_junk_labels_are_rejected():
    """Самиздат-вёдра: один «лейбл» на сотни несвязанных релизов."""
    for raw in ("Not On Label", "No Label", "White Label", "Self-Released", "[no label]"):
        assert not _label_ok(_norm_key(raw)), raw
    assert _label_ok(_norm_key("Мелодия"))
    assert _label_ok(_norm_key("Blue Note"))


def test_resolve_key_ambiguity_counts_artless_releases():
    """Неоднозначность — по ВСЕМУ MB, не только по релизам с обложкой.

    Альбом B без арта не становится кандидатом, но обязан ЗАПРЕЩАТЬ ключ:
    Discogs-строка под этим ключом может быть именно альбомом B, и обложка
    альбома A на ней — тот самый инцидент с подменёнными обложками.
    """
    # кандидат один (у B нет арта), но групп две → ключ выбрасывается
    assert _resolve_key([("a", 10, 1971)], {10, 20}) is None
    # обе группы с артом → тоже выбрасывается
    assert _resolve_key([("a", 10, 1971), ("b", 20, 1971)], {10, 20}) is None
    assert _resolve_key([], {10}) is None


def test_resolve_key_single_album_takes_earliest_press():
    got = _resolve_key(
        [("mbid-reissue", 10, 2015), ("mbid-orig", 10, 1971), ("mbid-x", 10, None)],
        {10},
    )
    assert got == ("mbid-orig", 10, 1971)


def test_resolve_key_undated_single_album_is_deterministic():
    assert _resolve_key([("zzz", 10, None), ("aaa", 10, None)], {10}) == ("aaa", 10, None)


def test_validate_sql_covers_both_populations():
    """Валидация обязана отдельно мерить непокрытую популяцию.

    Покрытые строки — курируемые релизы; --apply пишет в тёмный хвост.
    Мерить одно и применять к другому — дыра, найденная ревью.
    """
    assert "cover_image_url IS NULL" in _validate_sql(True)
    assert "cover_image_url IS NULL" not in _validate_sql(False)
    # rg берётся из независимой mb_mbid_rg, не из проверяемой таблицы
    assert "mb_mbid_rg" in _validate_sql(False)
    # условия матча идентичны в обеих популяциях
    for cond in ("m.catno_norm = d.catalog_norm", "d.year IS NOT NULL",
                 f"abs(d.year - m.year) <= {_MAX_YEAR_DIFF}"):
        assert cond in _validate_sql(True) and cond in _validate_sql(False)


def test_gate_and_fanout_constants_hold_the_line():
    """Пороги — часть контракта безопасности канала."""
    assert _GATE_MIN_SAME_GROUP >= 0.97
    assert _GATE_MIN_RG_KNOWN >= 500
    assert _MAX_KEY_FANOUT <= 5


def test_sql_has_no_bindparam_cast_trap():
    bad = re.compile(r":\w+::")
    assert not bad.search(_validate_sql(True))
    assert not bad.search(_validate_sql(False))
