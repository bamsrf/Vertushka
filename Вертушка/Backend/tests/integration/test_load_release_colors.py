"""Загрузчик цвета пресса — на живом Postgres.

SQL идёт на прод массовым UPDATE и пишет в JSONB, где легко снести соседние
ключи. Проверяем на настоящей базе: payload не теряется, известный цвет не
перетирается, счётчик --dry-run совпадает с боевым.
"""
import csv
import gzip
import uuid
from pathlib import Path

import pytest

from app.database import async_session_maker
from app.models.record import Record
from app.scripts.load_release_colors import load

pytestmark = pytest.mark.asyncio


def _csv(tmp_path: Path, rows: list[tuple]) -> Path:
    path = tmp_path / "colors_20260801.csv.gz"
    with gzip.open(path, "wt", newline="", encoding="utf-8") as fh:
        csv.writer(fh).writerows(rows)
    return path


async def _add(discogs_id: str, discogs_data) -> uuid.UUID:
    async with async_session_maker() as db:
        rec = Record(title="T", artist="A", source="discogs",
                     discogs_id=discogs_id, discogs_data=discogs_data)
        db.add(rec)
        await db.commit()
        return rec.id


async def _get(rid) -> Record:
    async with async_session_maker() as db:
        return await db.get(Record, rid)


async def test_fills_color_into_discogs_data(tmp_path):
    rid = await _add("910001", {})
    counters = await load(_csv(tmp_path, [(910001, "Red Translucent")]), dry_run=False)

    assert counters["updated"] == 1
    assert (await _get(rid)).discogs_data["vinyl_color_raw"] == "Red Translucent"


async def test_keeps_the_rest_of_the_payload(tmp_path):
    """JSONB-мерж, а не присваивание: рядом лежит весь payload релиза."""
    rid = await _add("910002", {"notes": "тест", "master_id": "42"})
    await load(_csv(tmp_path, [(910002, "Blue")]), dry_run=False)

    data = (await _get(rid)).discogs_data
    assert data["vinyl_color_raw"] == "Blue"
    assert data["notes"] == "тест" and data["master_id"] == "42"


async def test_null_payload_is_not_wiped(tmp_path):
    """`NULL || jsonb` молча даёт NULL — отсюда COALESCE в UPDATE."""
    rid = await _add("910003", None)
    await load(_csv(tmp_path, [(910003, "Green")]), dry_run=False)

    assert (await _get(rid)).discogs_data == {"vinyl_color_raw": "Green"}


async def test_known_color_is_not_overwritten(tmp_path):
    """Цвет из живого API свежее дампного — дамп месячный."""
    rid = await _add("910004", {"vinyl_color_raw": "Orange"})
    counters = await load(_csv(tmp_path, [(910004, "Blue")]), dry_run=False)

    assert counters["updated"] == 0
    assert (await _get(rid)).discogs_data["vinyl_color_raw"] == "Orange"


async def test_dry_run_counts_the_same_rows_it_would_change(tmp_path):
    rid = await _add("910005", {})
    dry = await load(_csv(tmp_path, [(910005, "White")]), dry_run=True)
    assert dry["updated"] == 1
    assert "vinyl_color_raw" not in ((await _get(rid)).discogs_data or {})

    real = await load(_csv(tmp_path, [(910005, "White")]), dry_run=False)
    assert real["updated"] == dry["updated"]


async def test_malformed_rows_are_counted_not_fatal(tmp_path):
    rid = await _add("910006", {})
    counters = await load(_csv(tmp_path, [
        ("nope", "Red"), (910006,), (910006, "  "), (910006, "Pink"),
    ]), dry_run=False)

    assert counters["bad"] == 3
    assert (await _get(rid)).discogs_data["vinyl_color_raw"] == "Pink"
