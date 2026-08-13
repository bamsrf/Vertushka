"""Обложки магазинов не должны выбрасываться.

Регрессия 2026-07-22 → 2026-08-12: блок харвеста в `_apply_match` оказался
ПОСЛЕ `return True` и три недели был недостижим. Ошибки не было — просто
картинки, которые мы уже скачали при обходе, молча уходили в никуда.
На момент починки 5 956 сматченных записей сидели без обложки, имея
магазинную под рукой.

Тест сторожит именно достижимость: харвест обязан вызываться при успешной
привязке и не вызываться, когда привязки не случилось.
"""
import ast
import inspect
from decimal import Decimal

import pytest

from app.models.store_listing import MatchMethod
from app.services import listing_matcher


class _Listing:
    def __init__(self, image_url="https://shop.example/cover.jpg", fmt="LP"):
        self.raw_payload = {"image_url": image_url} if image_url else {}
        self.format_raw = fmt
        self.matched_record_id = None
        self.match_confidence = None
        self.match_method = None
        self.matched_at = None


class _Record:
    def __init__(self, discogs_id="12345", master_id="777", fmt="LP"):
        self.id = "rec-1"
        self.discogs_id = discogs_id
        self.discogs_master_id = master_id
        self.format_type = fmt


@pytest.fixture
def harvested(monkeypatch):
    calls = []
    monkeypatch.setattr(
        "app.services.cover_storage.schedule_harvest_store_cover",
        lambda *a: calls.append(a),
    )
    return calls


def test_apply_match_harvests_store_cover(harvested):
    """Главный тест регрессии: при успешной привязке обложка уходит в харвест."""
    listing, rec = _Listing(), _Record()
    assert listing_matcher._apply_match(listing, rec, Decimal("1.0"), MatchMethod.BARCODE)
    assert harvested == [("12345", "777", "https://shop.example/cover.jpg")]


def test_no_harvest_when_format_conflicts(harvested):
    """Привязки не было — картинку к чужому релизу не цепляем."""
    listing, rec = _Listing(fmt="LP"), _Record(fmt="CD")
    assert not listing_matcher._apply_match(listing, rec, Decimal("1.0"), MatchMethod.BARCODE)
    assert harvested == []


def test_no_harvest_without_store_image(harvested):
    listing, rec = _Listing(image_url=None), _Record()
    assert listing_matcher._apply_match(listing, rec, Decimal("1.0"), MatchMethod.FUZZY)
    assert harvested == []


def test_no_harvest_without_discogs_id(harvested):
    """store-native запись: осаждать обложку в discogs-индекс некуда."""
    listing, rec = _Listing(), _Record(discogs_id=None)
    assert listing_matcher._apply_match(
        listing, rec, Decimal("1.0"), MatchMethod.STORE_NATIVE
    )
    assert harvested == []


class _FakeRow:
    def __init__(self, cover_image_url=None, cover_local_path=None):
        self.cover_image_url = cover_image_url
        self.cover_local_path = cover_local_path


def _patch_records_lookup(monkeypatch, row):
    """Подменяет сессию БД внутри `_release_cover_is_empty`: SELECT отдаёт row."""
    class _Result:
        def first(self):
            return row

    class _Session:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def execute(self, *a, **kw):
            return _Result()

    monkeypatch.setattr("app.database.async_session_maker", lambda: _Session())


@pytest.mark.asyncio
async def test_harvest_skipped_when_discogs_cover_exists(monkeypatch):
    """Регрессия Tim Maia (release 2875867, 12.08.2026).

    У записи есть дискогсовский `cover_image_url`, зеркала ещё нет. Магазинная
    картинка обязана пройти мимо: иначе `download_and_store` поставит
    `cover_local_path` + новый `cover_cached_at` и перекрасит карточку.
    """
    from app.services import cover_storage

    _patch_records_lookup(monkeypatch, _FakeRow(cover_image_url="https://i.discogs.com/x"))
    downloaded = []
    monkeypatch.setattr(
        cover_storage, "_download_cover_background",
        lambda *a: downloaded.append(a),
    )

    ok = await cover_storage._harvest_store_cover(
        "2875867", "805853", "https://shop.example/other-album.jpg",
    )
    assert ok is False
    assert downloaded == [], "магазин не должен качать поверх Discogs"


@pytest.mark.asyncio
async def test_harvest_skipped_when_mirror_exists(monkeypatch):
    """Зеркало на диске — тоже занято, даже если cover_image_url пуст."""
    from app.services import cover_storage

    _patch_records_lookup(monkeypatch, _FakeRow(cover_local_path="covers/2875867.jpg"))
    downloaded = []
    monkeypatch.setattr(
        cover_storage, "_download_cover_background",
        lambda *a: downloaded.append(a),
    )

    assert await cover_storage._harvest_store_cover(
        "2875867", "805853", "https://shop.example/x.jpg",
    ) is False
    assert downloaded == []


@pytest.mark.asyncio
async def test_harvest_proceeds_when_record_has_no_cover(monkeypatch):
    """Главный сценарий добора: обложки нет вообще — магазин закрывает дырку.

    Сторожит, что guard не убил смысл харвеста (те самые 5 956 записей).
    """
    from app.services import cover_storage

    _patch_records_lookup(monkeypatch, _FakeRow())
    downloaded = []
    monkeypatch.setattr(
        cover_storage, "_download_cover_background",
        lambda *a: downloaded.append(a) or _noop(),
    )

    assert await cover_storage._harvest_store_cover(
        "555", "777", "https://shop.example/cover.jpg", await_downloads=True,
    ) is True
    assert [a[0] for a in downloaded] == ["555", "m777"]


async def _noop():
    return None


@pytest.mark.asyncio
async def test_harvest_skipped_when_lookup_fails(monkeypatch):
    """БД недоступна — трактуем как «занято», молчаливая порча дороже пропуска."""
    from app.services import cover_storage

    class _Boom:
        async def __aenter__(self):
            raise RuntimeError("db down")

        async def __aexit__(self, *exc):
            return False

    monkeypatch.setattr("app.database.async_session_maker", lambda: _Boom())
    assert await cover_storage._release_cover_is_empty("1") is False


def test_no_unreachable_code_after_return_in_apply_match():
    """Структурная страховка: ровно та форма бага, что жила три недели.

    Проверяем не текст, а AST — любой statement после `return` на верхнем
    уровне функции недостижим, как бы он ни был написан.
    """
    src = inspect.getsource(listing_matcher._apply_match)
    fn = ast.parse(src.lstrip()).body[0]
    for i, node in enumerate(fn.body):
        if isinstance(node, ast.Return):
            assert i == len(fn.body) - 1, (
                f"после return на строке {node.lineno} есть недостижимый код"
            )
