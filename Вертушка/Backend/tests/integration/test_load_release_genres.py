"""Загрузчик жанров из дампа — на живом Postgres.

SQL этого скрипта уезжает на прод и трогает `records` массовым UPDATE, поэтому
проверяем его настоящей базой, а не моками: COALESCE-политику (живой Discogs
точнее дампа и не затирается), фильтр «обновлять только то, что меняется» (на
прод-диске каждая лишняя версия строки — мёртвый кортеж) и --dry-run.
"""
import csv
import gzip
import uuid
from pathlib import Path

import pytest
import pytest_asyncio
from sqlalchemy import select

from app.database import async_session_maker
from app.models.record import Record
from app.scripts.load_release_genres import load

pytestmark = pytest.mark.asyncio


def _csv(tmp_path: Path, rows: list[tuple]) -> Path:
    path = tmp_path / "genres_20260801.csv.gz"
    with gzip.open(path, "wt", newline="", encoding="utf-8") as fh:
        csv.writer(fh).writerows(rows)
    return path


async def _add(**kwargs) -> uuid.UUID:
    async with async_session_maker() as db:
        rec = Record(
            title=kwargs.pop("title", "Title"),
            artist=kwargs.pop("artist", "Artist"),
            source="discogs",
            **kwargs,
        )
        db.add(rec)
        await db.commit()
        return rec.id


async def _get(record_id: uuid.UUID) -> Record:
    async with async_session_maker() as db:
        return await db.get(Record, record_id)


@pytest_asyncio.fixture
async def empty_record():
    return await _add(discogs_id="777001")


async def test_fills_empty_genre_and_style(tmp_path, empty_record):
    path = _csv(tmp_path, [(777001, "Rock", "Indie Rock, Shoegaze")])
    counters = await load(path, dry_run=False)

    assert counters["updated"] == 1
    rec = await _get(empty_record)
    assert rec.genre == "Rock"
    assert rec.style == "Indie Rock, Shoegaze"


async def test_does_not_overwrite_live_discogs_values(tmp_path):
    # Жанр из живого API свежее дампного — дамп месячный, релиз могли
    # переклассифицировать.
    rid = await _add(discogs_id="777002", genre="Electronic", style="Techno")
    path = _csv(tmp_path, [(777002, "Rock", "Indie Rock")])
    await load(path, dry_run=False)

    rec = await _get(rid)
    assert rec.genre == "Electronic"
    assert rec.style == "Techno"


async def test_fills_only_the_empty_half(tmp_path):
    rid = await _add(discogs_id="777003", genre="Jazz")
    path = _csv(tmp_path, [(777003, "Rock", "Bebop")])
    counters = await load(path, dry_run=False)

    assert counters["updated"] == 1
    rec = await _get(rid)
    assert rec.genre == "Jazz"        # своё сохранили
    assert rec.style == "Bebop"       # пустое добрали


async def test_record_with_nothing_to_change_is_not_rewritten(tmp_path):
    """Ключевое для прод-диска: no-op строки не должны плодить версии."""
    await _add(discogs_id="777004", genre="Rock", style="Indie Rock")
    path = _csv(tmp_path, [(777004, "Rock", "Indie Rock")])
    counters = await load(path, dry_run=False)

    assert counters["updated"] == 0


async def test_merged_records_are_skipped(tmp_path):
    survivor = await _add(discogs_id="777005")
    merged = await _add(discogs_id="777006", merged_into_id=survivor)
    path = _csv(tmp_path, [(777006, "Rock", "Indie Rock")])
    counters = await load(path, dry_run=False)

    assert counters["updated"] == 0
    assert (await _get(merged)).genre is None


async def test_unknown_ids_are_ignored(tmp_path, empty_record):
    path = _csv(tmp_path, [(999999, "Rock", "Indie Rock")])
    counters = await load(path, dry_run=False)

    assert counters["updated"] == 0
    assert (await _get(empty_record)).genre is None


async def test_dry_run_counts_but_changes_nothing(tmp_path, empty_record):
    path = _csv(tmp_path, [(777001, "Rock", "Indie Rock")])
    counters = await load(path, dry_run=True)

    assert counters["updated"] == 1
    assert (await _get(empty_record)).genre is None


async def test_malformed_rows_are_counted_not_fatal(tmp_path, empty_record):
    path = _csv(tmp_path, [
        ("not-an-id", "Rock", "Indie Rock"),
        (777001,),
        (777001, "", ""),
        (777001, "Rock", "Indie Rock"),
    ])
    counters = await load(path, dry_run=False)

    assert counters["bad"] == 3
    assert counters["updated"] == 1
