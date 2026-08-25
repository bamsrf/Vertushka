"""Выгрузка жанров из masters-дампа.

Появилась потому, что releases-дамп (10.4 ГБ) не качается: data.discogs.com не
поддерживает Range, и восемь попыток подряд легли с обрывом в случайных точках.
Masters — 593 МБ и берётся с первой попытки, а жанр у мастера тот же, что у его
прессов. Покрывает записи с discogs_master_id — на проде это 80%.
"""
import csv
import gzip
from datetime import date
from pathlib import Path
from xml.sax.saxutils import escape

import pytest

from app.scripts.extract_master_genres import extract


def _master(mid: int, genres: list[str], styles: list[str]) -> str:
    g = "".join(f"<genre>{escape(x)}</genre>" for x in genres)
    st = "".join(f"<style>{escape(x)}</style>" for x in styles)
    return (
        f'<master id="{mid}">'
        f"<main_release>{mid * 10}</main_release>"
        f"<title>Album {mid}</title>"
        f"<genres>{g}</genres><styles>{st}</styles>"
        f"</master>"
    )


@pytest.fixture
def dump(tmp_path: Path) -> Path:
    path = tmp_path / "discogs_20260801_masters.xml.gz"
    body = "".join([
        _master(501, ["Rock"], ["Indie Rock"]),
        _master(502, ["Folk, World, & Country"], ["Ballad"]),
        _master(503, ["Jazz"], ["Bebop"]),
        _master(504, [], []),
    ])
    with gzip.open(path, "wt", encoding="utf-8") as fh:
        fh.write(f"<masters>{body}</masters>")
    return path


def _run(dump: Path, tmp_path: Path, ids: set[int]) -> dict[int, tuple[str, str]]:
    extract(dump, tmp_path, date(2026, 8, 1), ids)
    out = tmp_path / "genres_masters_20260801.csv.gz"
    with gzip.open(out, "rt", encoding="utf-8") as fh:
        return {int(r[0]): (r[1], r[2]) for r in csv.reader(fh)}


def test_writes_requested_masters(dump, tmp_path):
    rows = _run(dump, tmp_path, {501, 502})
    assert rows[501] == ("Rock", "Indie Rock")
    assert rows[502][0] == "Folk, World, & Country"
    assert 503 not in rows


def test_master_without_genres_is_skipped(dump, tmp_path):
    assert _run(dump, tmp_path, {504}) == {}


def test_counters_report_hits(dump, tmp_path):
    counters = extract(dump, tmp_path, date(2026, 8, 1), {501, 503, 999})
    assert counters["seen"] == 4       # прочитали весь дамп
    assert counters["written"] == 2    # 999 в дампе нет
