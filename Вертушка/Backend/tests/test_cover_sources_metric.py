"""Источники обложек в метрике покрытия: считаем ОБЕ таблицы, не одну.

Регрессия, которую сторожит файл. Метрика `cover_sources` считала хосты только
по `discogs_releases_index` и показывала «Deezer 632». Реально Deezer добыл
443 905 обложек — просто бэкфиллы (`app/scripts/backfill_covers_deezer.py`,
`backfill_covers.py`) пишут в `discogs_master_covers`, другую таблицу.

Цена ошибки не косметическая: free_pct выходил 74% вместо 82%, а именно по этой
цифре принимается решение «можно ли выпилить Discogs из лестницы мастеров».
Решение по заниженной на 8 п.п. метрике — решение вслепую.
"""
from app.tasks.cover_coverage_tasks import _FREE, _HOSTS, _source_filters, _tally

# Живые цифры прода на 2026-08-16 — они же служат примером, который метрика
# обязана воспроизводить.
_RELEASES_ROW = {
    "caa": 1_278_689, "deezer": 632, "itunes": 50,
    "discogs": 432_285, "other": 15_598,
}
_MASTERS_ROW = {
    "caa": 413_379, "deezer": 443_905, "itunes": 0,
    "discogs": 4_742, "other": 4_166,
}


def test_tally_total_matches_sum_of_sources():
    """`total` — сумма источников, а не отдельный COUNT.

    Так он всегда сходится с `count(*) FILTER (WHERE cover_image_url IS NOT
    NULL)` из того же запроса; расхождение означало бы дырку в классификации
    хостов (URL, не попавший ни в один бакет, включая `other`).
    """
    t = _tally(_RELEASES_ROW)
    assert t["total"] == 1_727_254 == sum(_RELEASES_ROW.values())


def test_discogs_is_not_free():
    """Discogs не бесплатный источник — иначе метрика теряет весь смысл.

    Их правила: ~1000 картинок в сутки и запрет хранить дольше необходимого.
    Постоянное зеркало им противоречит, поэтому доля Discogs — это и есть
    размер зависимости, от которой уходим.
    """
    assert "discogs" not in _FREE
    t = _tally(_RELEASES_ROW)
    assert t["free"] == 1_278_689 + 632 + 50
    assert t["free_pct"] == 0.7407  # 74.1% — по одной таблице картина хуже


def test_masters_are_almost_entirely_free():
    """Мастера закрыты бесплатными источниками на ~99%.

    Это и есть цифра, которой не хватало: на уровне мастеров зависимость от
    Discogs — 4 742 обложки из 866 тыс., то есть уже почти ноль.
    """
    t = _tally(_MASTERS_ROW)
    assert t["total"] == 866_192
    assert t["free_pct"] > 0.98


def test_combined_free_pct_beats_release_only_view():
    """Сводная доля по двум таблицам выше, чем по одной release-таблице.

    Ровно тот разрыв, из-за которого метрику и переписали.
    """
    rel, mst = _tally(_RELEASES_ROW), _tally(_MASTERS_ROW)
    combined = (rel["free"] + mst["free"]) / (rel["total"] + mst["total"])
    assert round(combined, 4) == 0.8239
    assert combined > rel["free_pct"] + 0.08


def test_source_filters_covers_every_host_plus_other():
    """Одно выражение на обе таблицы: по бакету на хост и `other` в конце.

    `other` обязан исключать ВСЕ известные хосты — иначе store-native обложки
    посчитались бы дважды (и в своём бакете, и в other), а total разъехался бы
    с with_cover.
    """
    sql = _source_filters()
    for key, host in _HOSTS.items():
        assert f"AS {key}" in sql
        assert f"LIKE '%{host}%'" in sql
        assert f"NOT LIKE '%{host}%'" in sql
    assert sql.count("AS other") == 1
