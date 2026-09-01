"""Выгрузка жанров из releases-дампа (`extract_release_formats --ids-file`).

Жанр в Маркете берётся из `records.genre`, а туда он попадал только живым
вызовом Discogs API — то есть у записей, которые кто-то открыл руками. Склад
магазинов матчер создаёт из дампа, где колонок genre/style нет вовсе, поэтому
на 25.08 жанр был у ~390 карточек из ~30 тысяч.

Эти тесты фиксируют контракт выгрузки: формат склейки совпадает с живым путём,
`Folk, World, & Country` не разваливается, длинные списки стилей не рвут
`String(255)`, и в CSV попадают только запрошенные id.
"""
import csv
import gzip
from xml.sax.saxutils import escape
from datetime import date
from pathlib import Path

import pytest

from app.scripts.extract_release_formats import extract, load_wanted_ids


def _release(rid: int, genres: list[str], styles: list[str]) -> str:
    # escape() — не украшение: «Folk, World, & Country» содержит амперсанд, и
    # без экранирования lxml роняет разбор на xmlParseEntityRef. В настоящем
    # дампе Discogs он приезжает как &amp;.
    g = "".join(f"<genre>{escape(x)}</genre>" for x in genres)
    st = "".join(f"<style>{escape(x)}</style>" for x in styles)
    return (
        f'<release id="{rid}" status="Accepted">'
        f"<artists><artist><id>1</id><name>Artist {rid}</name></artist></artists>"
        f"<title>Title {rid}</title>"
        f"<formats><format name=\"Vinyl\" qty=\"1\"><descriptions>"
        f"<description>LP</description><description>Album</description>"
        f"</descriptions></format></formats>"
        f"<genres>{g}</genres><styles>{st}</styles>"
        f"</release>"
    )


@pytest.fixture
def dump(tmp_path: Path) -> Path:
    path = tmp_path / "discogs_20260801_releases.xml.gz"
    body = "".join([
        _release(101, ["Rock"], ["Indie Rock", "Shoegaze"]),
        _release(102, ["Electronic", "Rock"], ["Synth-pop"]),
        # Единственное имя словаря Discogs с запятыми внутри.
        _release(103, ["Folk, World, & Country"], ["Ballad"]),
        # Не в списке запрошенных — не должен попасть в выгрузку.
        _release(104, ["Jazz"], ["Bebop"]),
        # Жанра нет вовсе — писать нечего.
        _release(105, [], []),
        # Стилей на километр — проверяем обрезку под String(255).
        _release(106, ["Electronic"], [f"Style Number {i}" for i in range(40)]),
    ])
    with gzip.open(path, "wt", encoding="utf-8") as fh:
        fh.write(f"<releases>{body}</releases>")
    return path


def _run(dump: Path, tmp_path: Path, ids: list[int]) -> dict[int, tuple[str, str]]:
    ids_file = tmp_path / "ids.txt"
    ids_file.write_text("\n".join(str(i) for i in ids))
    extract(
        dump, tmp_path, date(2026, 8, 1),
        since_id=None, limit=None, wanted_ids=load_wanted_ids(ids_file),
    )
    out = tmp_path / "genres_20260801.csv.gz"
    with gzip.open(out, "rt", encoding="utf-8") as fh:
        return {int(row[0]): (row[1], row[2]) for row in csv.reader(fh)}


def test_joins_genres_exactly_like_the_live_discogs_path(dump, tmp_path):
    # services/discogs.py склеивает через ", " — разойдись формат, одна и та же
    # колонка заполнялась бы двумя путями по-разному.
    rows = _run(dump, tmp_path, [101, 102])
    assert rows[101] == ("Rock", "Indie Rock, Shoegaze")
    assert rows[102][0] == "Electronic, Rock"


def test_folk_world_country_survives_as_one_value(dump, tmp_path):
    rows = _run(dump, tmp_path, [103])
    assert rows[103][0] == "Folk, World, & Country"


def test_only_requested_ids_are_written(dump, tmp_path):
    rows = _run(dump, tmp_path, [101, 103])
    assert set(rows) == {101, 103}


def test_release_without_genres_is_skipped(dump, tmp_path):
    rows = _run(dump, tmp_path, [105])
    assert rows == {}


def test_long_style_list_is_truncated_on_a_value_boundary(dump, tmp_path):
    # records.style — String(255). Обрезка идёт по границе элемента: огрызок
    # вроде «Style Numb» матчился бы ILIKE-паттернами как попало.
    _genre, style = _run(dump, tmp_path, [106])[106]
    assert len(style) <= 255
    assert not style.endswith(",")
    assert all(part.strip().startswith("Style Number") for part in style.split(","))


def test_ids_file_ignores_blank_and_garbage_lines(tmp_path):
    f = tmp_path / "ids.txt"
    f.write_text("101\n\n  \nnot-an-id\n102\n")
    assert load_wanted_ids(f) == {101, 102}
