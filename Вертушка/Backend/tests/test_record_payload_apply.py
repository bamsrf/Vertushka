"""Донос payload до колонок: format_description, qty, rarity-флаги.

Ловим регрессию, из-за которой полный Discogs-payload умирал в discogs_data
(JSON), а колонки, по которым считают ачивки (BX/FMT/C-серии), Маркет и
pricing, оставались пустыми/False. Живой БД нет: _apply_discogs_release ходит
в неё только commit/refresh — их глушит FakeDB.
"""
import pytest

from app.api.records import _apply_discogs_release
from app.models.record import Record
from app.services.achievements.media_format import BOX_SET, parse_media
from app.services.discogs import _prepend_qty


class FakeDB:
    async def commit(self):
        pass

    async def refresh(self, _obj):
        pass

    async def rollback(self):
        pass


def _record(**kwargs) -> Record:
    defaults = dict(
        discogs_id="123",
        title="T",
        artist="A",
        source="discogs",
        # cover есть и barcode пуст — CAA-fallback в сеть не пойдёт
        cover_image_url="http://example/c.jpg",
        barcode=None,
        is_limited=False,
        is_collectible=False,
        is_hot=False,
    )
    defaults.update(kwargs)
    return Record(**defaults)


# --- _prepend_qty / qty в описании формата -----------------------------------

def test_prepend_qty_formats_pattern_for_media_format():
    desc = _prepend_qty("Box Set, Limited Edition", "10")
    assert desc == "10× Box Set, Limited Edition"
    info = parse_media("Vinyl", desc)
    assert info.has(BOX_SET)
    assert info.qty == 10


def test_prepend_qty_ignores_single_and_garbage():
    assert _prepend_qty("LP", "1") == "LP"
    assert _prepend_qty("LP", None) == "LP"
    assert _prepend_qty("LP", "ten") == "LP"
    assert _prepend_qty(None, "3") == "3×"


# --- _apply_discogs_release ----------------------------------------------------

@pytest.mark.asyncio
async def test_apply_fills_format_description_and_flags():
    rec = _record(tracklist=[{"position": "A1", "title": "x", "duration": "1:00"}])
    data = {
        "format_description": "Box Set, Limited Edition",
        "is_limited": True,
        "is_collectible": True,
        "is_hot": False,
    }
    await _apply_discogs_release(rec, data, FakeDB())
    assert rec.format_description == "Box Set, Limited Edition"
    assert rec.is_limited is True
    assert rec.is_collectible is True
    assert rec.is_hot is False


@pytest.mark.asyncio
async def test_apply_does_not_clobber_existing_values():
    rec = _record(
        tracklist=[{"position": "A1", "title": "x", "duration": "1:00"}],
        format_description="уже есть",
        is_limited=True,
    )
    data = {"format_description": "новое", "is_limited": False}
    await _apply_discogs_release(rec, data, FakeDB())
    # Непустое описание не перезаписывается, True-флаг не сбрасывается.
    assert rec.format_description == "уже есть"
    assert rec.is_limited is True


# --- Кандидаты ночного sweep ---------------------------------------------------

def test_sweep_candidates_query_shape():
    from sqlalchemy.dialects import postgresql
    from app.tasks.discogs_tasks import _collection_payload_candidates_stmt

    sql = str(
        _collection_payload_candidates_stmt(400).compile(
            dialect=postgresql.dialect()
        )
    )
    # Только записи из коллекций, без ключа is_collectible в payload, с лимитом.
    assert "collection_items" in sql
    assert "discogs_data" in sql and "?" in sql  # jsonb has_key оператор
    assert "LIMIT" in sql
    assert "GROUP BY" in sql
