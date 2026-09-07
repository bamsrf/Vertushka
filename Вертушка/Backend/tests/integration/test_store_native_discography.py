"""План B (бэкенд-половина): store-native записи вливаются в дискографию артиста.

Тестируем ядро — `_store_native_masters_for_artist`: матч по нормализованному
имени, дедуп по названию против Discogs-мастеров, маркер master_id='s{uuid}'.
Таблицы дампа (discogs_artists/discogs_releases_index) вне ORM, поэтому полный
get_artist_masters_local покрыт живой сверкой на проде, а здесь — ядро на
таблице records.
"""
import uuid

import pytest

from app.models.record import Record
from app.services.discogs_index import _store_native_masters_for_artist

pytestmark = pytest.mark.asyncio


@pytest.fixture
def make_store_record(db):
    async def _make(artist: str, title: str, *, year: int | None = 2024,
                    source: str = "store", merged_into_id=None) -> Record:
        rec = Record(
            source=source, artist=artist, title=title, year=year,
            format_type="LP", cover_image_url="https://x/cover.jpg",
            merged_into_id=merged_into_id,
        )
        db.add(rec)
        await db.commit()
        await db.refresh(rec)
        return rec

    return _make


async def test_matches_by_normalized_name(db, make_store_record):
    name = f"Boulevard Depo {uuid.uuid4().hex[:6]}"
    rec = await make_store_record(f"  {name.lower()}  ", "Футуроархаика")
    out = await _store_native_masters_for_artist(db, name, set(), "https://cov", "desc")
    ids = [r.master_id for r in out]
    assert f"s{rec.id}" in ids                      # нашёлся, несмотря на регистр/пробелы
    got = next(r for r in out if r.master_id == f"s{rec.id}")
    assert got.title == "Футуроархаика"
    assert got.main_release_id == str(rec.id)
    assert got.artist == name


async def test_title_dedup_excludes_discogs_release(db, make_store_record):
    name = f"Artist {uuid.uuid4().hex[:6]}"
    await make_store_record(name, "Известный Альбом")
    out = await _store_native_masters_for_artist(
        db, name, {"известный альбом"}, "https://cov", "desc"
    )
    assert out == []                                # уже есть в Discogs → не дублируем


async def test_different_artist_not_matched(db, make_store_record):
    name = f"Artist {uuid.uuid4().hex[:6]}"
    await make_store_record("Совсем Другой", "Альбом")
    out = await _store_native_masters_for_artist(db, name, set(), "https://cov", "desc")
    assert out == []


async def test_merged_record_excluded(db, make_store_record):
    name = f"Artist {uuid.uuid4().hex[:6]}"
    other = await make_store_record(name, "Оригинал")
    await make_store_record(name, "Слитый дубль", merged_into_id=other.id)
    out = await _store_native_masters_for_artist(db, name, set(), "https://cov", "desc")
    titles = [r.title for r in out]
    assert "Оригинал" in titles
    assert "Слитый дубль" not in titles             # merged_into не показываем


async def test_discogs_source_not_matched(db, make_store_record):
    name = f"Artist {uuid.uuid4().hex[:6]}"
    await make_store_record(name, "Дискогс-релиз", source="discogs")
    out = await _store_native_masters_for_artist(db, name, set(), "https://cov", "desc")
    assert out == []                                # только source='store'
