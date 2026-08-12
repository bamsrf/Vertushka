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
