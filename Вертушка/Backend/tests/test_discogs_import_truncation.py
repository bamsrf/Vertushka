"""Обрезка импорта по лимиту не должна быть молчаливой.

Кейс из прода (records2303, 16.09.2026): wantlist 3157, хардкод max_items=3000,
скачали 3000 — и диалог показал «из 3000», неотличимо от «столько и было».
Тесты фиксируют, что вызывающий теперь видит и настоящий размер списка
(available), и сам факт обрезки (truncated).
"""
import pytest

from app.services.discogs import DiscogsService, DiscogsUserReleases


def _fake_get(total_items: int, items_key: str, per_page: int = 100):
    """Подменяет сетевой слой Discogs: отдаёт страницы с pagination.items."""
    pages = (total_items + per_page - 1) // per_page
    calls: list[int] = []

    async def _get(url, params=None, priority=None, creds=None):
        page = params["page"]
        calls.append(page)
        start = (page - 1) * per_page
        end = min(start + per_page, total_items)
        return {
            "pagination": {"items": total_items, "pages": pages, "page": page},
            items_key: [
                {"basic_information": {"id": i}} for i in range(start, end)
            ],
        }

    return _get, calls


@pytest.mark.asyncio
async def test_wantlist_truncated_reports_real_size():
    """Список больше лимита: качаем max_items, но говорим, сколько их всего."""
    svc = DiscogsService()
    svc._get, calls = _fake_get(3157, "wants")

    res = await svc.get_wantlist_releases("records2303", ("k", "s"), max_items=3000)

    assert isinstance(res, DiscogsUserReleases)
    assert len(res.releases) == 3000
    assert res.available == 3157, "available — размер на Discogs, а не скачанного"
    assert res.truncated is True
    # Хвост не докачиваем: 30 страниц, а не 32.
    assert max(calls) == 30


@pytest.mark.asyncio
async def test_wantlist_fits_under_limit_not_truncated():
    """Список влез целиком — truncated False, available == len(releases)."""
    svc = DiscogsService()
    svc._get, _ = _fake_get(3157, "wants")

    res = await svc.get_wantlist_releases("records2303", ("k", "s"), max_items=20000)

    assert len(res.releases) == 3157
    assert res.available == 3157
    assert res.truncated is False


@pytest.mark.asyncio
async def test_collection_uses_same_contract():
    """У коллекции тот же баг и тот же контракт — не забыть про неё."""
    svc = DiscogsService()
    svc._get, _ = _fake_get(5000, "releases")

    res = await svc.get_collection_releases("records2303", ("k", "s"), max_items=1000)

    assert len(res.releases) == 1000
    assert res.available == 5000
    assert res.truncated is True


@pytest.mark.asyncio
async def test_default_limit_is_not_3000():
    """Дефолт берётся из настроек и выше прежнего хардкода — иначе регресс."""
    from app.config import get_settings

    assert get_settings().discogs_import_max_items > 3000


@pytest.mark.asyncio
async def test_unresolved_release_counted_as_failed():
    """Нерезолвнутый релиз больше не исчезает молча.

    Раньше `record is None` давал `continue` без счётчика: пластинка пропадала,
    а imported + skipped переставало сходиться с total — именно эта арифметика
    была единственным способом заметить проблему постфактум.
    """
    from unittest.mock import AsyncMock, patch

    from app.api import wishlists as wl

    state = {"imported": 0, "skipped": 0, "failed": 0, "total": 3}
    basics = {"1": {"id": 1}, "2": {"id": 2}, "3": {"id": 3}}

    class _Rec:
        def __init__(self, rid):
            self.id = rid

    # Резолвится только "2": "1" и "3" — потери.
    async def _resolve(db, chunk_ids, basics_by_id):
        return {"2": _Rec("rec-2")}, []

    db = AsyncMock()
    db.scalar = AsyncMock(return_value=type("W", (), {"id": "wl-1"})())
    db.execute = AsyncMock(
        return_value=type("R", (), {"scalars": lambda self: type(
            "S", (), {"all": lambda self: []})()})()
    )
    db.add = lambda obj: None

    with patch.object(wl, "_discogs_wishlist_imports", {}), \
            patch("app.api.collections._resolve_import_chunk", _resolve), \
            patch("app.services.discogs_index.enrich_records_from_dump",
                  AsyncMock(return_value=0)):
        await wl._write_imported_wants(
            db, "user-1", [basics[k] for k in ("1", "2", "3")], state
        )

    assert state["imported"] == 1
    assert state["failed"] == 2, "потери должны попасть в счётчик, а не в тишину"
    assert state["imported"] + state["skipped"] + state["failed"] == state["total"]
