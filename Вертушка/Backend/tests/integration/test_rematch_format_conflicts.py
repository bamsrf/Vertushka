"""Разбор конфликтов носителя — на живом Postgres.

Джоба брала 500 листингов по `matched_at ASC` и искала конфликт в Python. У
чистой строки `matched_at` не меняется, поэтому окно не двигалось: каждую ночь
джоба разглядывала одни и те же 500 майских листингов (2 конфликта из 500 при
750 на проде) и разбирала примерно два конфликта в сутки.

Здесь проверяется главное: конфликт находится независимо от того, как глубоко
он лежит по `matched_at`, — и что SQL-зеркало семьи совпадает с Python на живом
Postgres (регулярки у Python и ARE разные, `\\b` против `\\y`).
"""
import uuid
from datetime import datetime, timedelta

import pytest
import pytest_asyncio
from sqlalchemy import text

from app.database import async_session_maker
from app.models.record import Record
from app.models.store import Store
from app.models.store_listing import StoreListing
from app.services.listing_matcher import _format_family, rematch_format_conflicts_batch
from app.services.scrapers.extractors import sql_format_family

pytestmark = pytest.mark.asyncio

#: Реальные значения format_raw / format_type с прода (сверка 28.08 прошла на
#: всех 277 различных без единого расхождения).
CORPUS = [
    "LP", "2xLP", "3xLP", "EP", "Single", "Box Set", "Vinyl Box Set", "Vinyl",
    "Vinyl, LP", "CD", "2CD", "CDr", "SACD", "Cassette", "Cassette, Album",
    "CD, Album", "CD, Compilation", "Vinyl, 12\"", "12\"", "10\"", "7\"",
    "Acetate", "Flexi-disc", "Shellac", "File, FLAC", "Blu-ray", "DVD", "VHS",
    "Minidisc", "All Media", "винил", "кассета", "бокс-сет", "double LP",
]


async def test_sql_mirror_matches_python_on_live_postgres():
    """Зеркало обязано совпадать с Python значение в значение.

    Это не формальность: Python и Postgres — разные движки регулярок, и
    генератор переводит `\\b` в `\\y` вслепую. Разъедься они — джоба начнёт
    сбрасывать корректные привязки, а листинг уйдёт в unmatched до следующего
    часового прогона.
    """
    expr = sql_format_family("v")
    async with async_session_maker() as db:
        rows = (await db.execute(
            text(f"SELECT v, {expr} AS fam FROM unnest(CAST(:vals AS text[])) AS v"),
            {"vals": CORPUS},
        )).all()

    mismatches = [(v, _format_family(v), fam) for v, fam in rows if _format_family(v) != fam]
    assert not mismatches, mismatches


@pytest_asyncio.fixture
async def store():
    async with async_session_maker() as db:
        suffix = uuid.uuid4().hex[:8]
        st = Store(
            name="Test Store", slug=f"test-{suffix}",
            domain=f"test-{suffix}.example",
            base_url=f"https://test-{suffix}.example",
            parser_class="TestParser", is_active=True,
        )
        db.add(st)
        await db.commit()
        return st.id


async def _listing(store_id, fmt_raw: str, record_fmt: str, matched_at: datetime) -> uuid.UUID:
    async with async_session_maker() as db:
        rec = Record(title="T", artist="A", source="discogs",
                     discogs_id=str(uuid.uuid4().int)[:8], format_type=record_fmt)
        db.add(rec)
        await db.flush()
        listing = StoreListing(
            store_id=store_id, external_id=uuid.uuid4().hex, url="http://x",
            title_raw="T", format_raw=fmt_raw, status="in_stock",
            matched_record_id=rec.id, match_method="fuzzy", matched_at=matched_at,
        )
        db.add(listing)
        await db.commit()
        return listing.id


async def test_conflict_is_found_even_when_buried_deep(store):
    """Регрессия на застрявшее окно.

    Раньше при batch_size=1 джоба видела только самый старый листинг; если он
    чистый — не находила ничего и завтра смотрела бы его же. Теперь `LIMIT`
    ограничивает конфликты, а не просмотренные строки.
    """
    old = datetime.utcnow() - timedelta(days=90)
    clean = await _listing(store, "LP", "Vinyl, LP", old)                 # чистый, самый старый
    conflict = await _listing(store, "LP", "CD, Album", old + timedelta(days=30))

    counters = await rematch_format_conflicts_batch(batch_size=1)

    assert counters["conflicts_reset"] == 1
    async with async_session_maker() as db:
        assert (await db.get(StoreListing, conflict)).matched_record_id is None
        assert (await db.get(StoreListing, clean)).matched_record_id is not None


async def test_box_set_is_not_a_conflict(store):
    """Бокс без семьи — сбрасывать нечего, даже если вторая сторона CD."""
    await _listing(store, "Box Set", "CD, Album", datetime.utcnow())

    counters = await rematch_format_conflicts_batch(batch_size=50)

    assert counters["conflicts_reset"] == 0


async def test_store_native_listings_are_left_alone(store):
    """У store-native format_type записи выведен из самого листинга — сброс
    сломал бы merge-цепочку."""
    async with async_session_maker() as db:
        rec = Record(title="T", artist="A", source="store", format_type="CD, Album")
        db.add(rec)
        await db.flush()
        db.add(StoreListing(
            store_id=store, external_id=uuid.uuid4().hex, url="http://x",
            title_raw="T", format_raw="LP", status="in_stock",
            matched_record_id=rec.id, match_method="store_native",
            matched_at=datetime.utcnow(),
        ))
        await db.commit()

    counters = await rematch_format_conflicts_batch(batch_size=50)

    assert counters["conflicts_reset"] == 0
