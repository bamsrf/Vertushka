"""Форма штрихкода у Deezer и сторож нулевого выхлопа.

Инцидент 18.08.2026, который сторожит файл. Deezer НЕ нормализует ведущий ноль:
Discogs хранит UPC-A в 13-значном EAN-виде (`0602537191154`), Deezer индексирует
канонические 12 цифр (`602537191154`). На первую форму приходит
`{"error": {"code": 800, "message": "no data"}}` — неотличимо от честного промаха.

Обход шёл по возрастанию штрихкода и залип в блоках Universal (`06025x`), где
работает только 12-значная форма: 1775 запросов подряд с нулём попаданий, три
часа, все помечены пройденными. Ни детектор квоты, ни защита волны от потери
элементов этого не ловили — запрос был доставлен и честно отвечен, просто
спрошено было не то.
"""
import asyncio

import pytest

from app.services import deezer
from app.services.deezer import _upc_forms, cover_by_upc
from app.scripts import backfill_covers_upc as upc


class _Resp:
    def __init__(self, status=200, payload=None):
        self.status_code = status
        self._payload = payload if payload is not None else {}

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            import httpx
            raise httpx.HTTPStatusError("boom", request=None, response=None)


_NO_DATA = {"error": {"type": "DataException", "message": "no data", "code": 800}}
_ALBUM = {"id": 6131403, "title": "Till Brönner", "cover_xl": "https://x/1000.jpg",
          "md5_image": "abc"}


def _client_by_upc(mapping: dict, seen: list):
    """Клиент, отвечающий по коду из URL; фиксирует порядок спрошенных форм."""
    class _Client:
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        async def get(self, url, *a, **kw):
            code = url.rsplit("upc:", 1)[1]
            seen.append(code)
            return _Resp(200, mapping.get(code, _NO_DATA))
    return lambda *a, **kw: _Client()


@pytest.fixture(autouse=True)
def _no_throttle(monkeypatch):
    async def noop(): return None
    monkeypatch.setattr(deezer, "_throttle", noop)


def test_forms_try_as_is_then_stripped():
    """Порядок важен: как есть находится 17.5% случайных кодов, снятие нуля —
    добавка. Начинать со снятого значило бы тратить лишний запрос на большинстве."""
    assert _upc_forms("0602537191154") == ["0602537191154", "602537191154"]


def test_forms_no_duplicate_when_nothing_to_strip():
    assert _upc_forms("743213000329") == ["743213000329"]


def test_forms_do_not_produce_too_short_code():
    """`lstrip` на коде из нулей и трёх цифр дал бы огрызок — такой запрос
    бессмысленен и мог бы случайно попасть в чужой альбом."""
    assert _upc_forms("00000000123") == ["00000000123"]


@pytest.mark.asyncio
async def test_leading_zero_barcode_is_found_via_second_form(monkeypatch):
    """ГЛАВНЫЙ тест: 13-значная форма молчит, 12-значная отдаёт альбом."""
    seen = []
    monkeypatch.setattr(deezer.httpx, "AsyncClient",
                        _client_by_upc({"602537191154": _ALBUM}, seen))
    cover = await cover_by_upc("0602537191154")
    assert cover is not None and cover.album_id == 6131403
    assert seen == ["0602537191154", "602537191154"], "обе формы, именно в этом порядке"


@pytest.mark.asyncio
async def test_hit_on_first_form_skips_second_request(monkeypatch):
    """Лишний запрос только на промахе — иначе обход стоил бы вдвое дороже."""
    seen = []
    monkeypatch.setattr(deezer.httpx, "AsyncClient",
                        _client_by_upc({"0602537191154": _ALBUM}, seen))
    assert await cover_by_upc("0602537191154") is not None
    assert seen == ["0602537191154"]


@pytest.mark.asyncio
async def test_genuine_miss_still_returns_none(monkeypatch):
    seen = []
    monkeypatch.setattr(deezer.httpx, "AsyncClient", _client_by_upc({}, seen))
    assert await cover_by_upc("0602537191154") is None
    assert len(seen) == 2


def test_zero_streak_threshold_is_set():
    """Сторож обязан существовать: волна защищает от ПОТЕРИ элементов, но не от
    систематически неверного запроса, который выглядит честным промахом."""
    assert upc._ZERO_STREAK_ABORT == 500
