"""Канал обложек по штрихкоду: точный ключ вместо угадывания по названию.

Зачем канал. `cover_by_meta` ищет по artist+title и промахивается на разнописи
(`Cause For Conflict` против `Cause for Conflict (Remastered)`, `Kreator`
против `Kreator (2)`). Полный обход 1.86 млн мастеров так дал 24%, остаток —
ровно несовпавшие названия. UPC однозначен: либо это издание, либо ничего.

Главное, что сторожит файл, — различение ПРОМАХА и КВОТЫ. Deezer на
превышение лимита отдаёт HTTP 200 с телом `{"error": {"code": 4}}`, а не 429.
Если считать это промахом, bulk-обход пометит штрихкоды `done` навсегда, и при
первом упоре в лимит десятки тысяч закроются, ни разу не будучи спрошенными.
Ровно тот же класс потери, что был в таймауте батча backfill_covers.
"""
import asyncio

import pytest

from app.services import deezer
from app.services.deezer import DeezerQuotaExceeded, cover_by_upc
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


def _client_returning(resp):
    class _Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def get(self, *a, **kw):
            return resp

    return lambda *a, **kw: _Client()


@pytest.fixture(autouse=True)
def _no_throttle(monkeypatch):
    """Троттл Deezer 0.13с в юнит-тестах только тормозит."""
    async def noop():
        return None
    monkeypatch.setattr(deezer, "_throttle", noop)


_ALBUM_OK = {
    "id": 12345,
    "cover_xl": "https://e-cdns-images.dzcdn.net/images/cover/abc/1000x1000-000000-80-0-0.jpg",
    "md5_image": "abc",
}


@pytest.mark.asyncio
async def test_returns_cover_on_exact_match(monkeypatch):
    monkeypatch.setattr(deezer.httpx, "AsyncClient", _client_returning(_Resp(200, _ALBUM_OK)))
    cover = await cover_by_upc("743213000329")
    assert cover is not None
    assert cover.url.endswith("1000x1000-000000-80-0-0.jpg")
    assert cover.album_id == 12345


@pytest.mark.asyncio
async def test_unknown_upc_is_a_plain_miss(monkeypatch):
    """404 — штатный промах: штрихкод спрошен, ответ «нет», можно закрывать."""
    monkeypatch.setattr(deezer.httpx, "AsyncClient", _client_returning(_Resp(404)))
    assert await cover_by_upc("743213000329") is None


@pytest.mark.asyncio
async def test_quota_error_body_raises_not_returns_none(monkeypatch):
    """ГЛАВНЫЙ тест: квота приходит как 200 + error.code=4, и это НЕ промах."""
    body = {"error": {"type": "Exception", "message": "Quota limit exceeded", "code": 4}}
    monkeypatch.setattr(deezer.httpx, "AsyncClient", _client_returning(_Resp(200, body)))
    with pytest.raises(DeezerQuotaExceeded):
        await cover_by_upc("743213000329")


@pytest.mark.asyncio
async def test_quota_detected_by_message_when_code_differs(monkeypatch):
    """Код Deezer может смениться — держимся ещё и за текст сообщения."""
    body = {"error": {"message": "you have exceeded the QUOTA", "code": 999}}
    monkeypatch.setattr(deezer.httpx, "AsyncClient", _client_returning(_Resp(200, body)))
    with pytest.raises(DeezerQuotaExceeded):
        await cover_by_upc("743213000329")


@pytest.mark.asyncio
async def test_other_error_body_is_a_miss(monkeypatch):
    """Прочие error-тела — обычный промах, штрихкод закрываем."""
    body = {"error": {"type": "DataException", "message": "no data", "code": 800}}
    monkeypatch.setattr(deezer.httpx, "AsyncClient", _client_returning(_Resp(200, body)))
    assert await cover_by_upc("743213000329") is None


@pytest.mark.asyncio
async def test_http_429_raises_quota(monkeypatch):
    monkeypatch.setattr(deezer.httpx, "AsyncClient", _client_returning(_Resp(429)))
    with pytest.raises(DeezerQuotaExceeded):
        await cover_by_upc("743213000329")


@pytest.mark.asyncio
@pytest.mark.parametrize("bad", ["", "   ", "none", "LC 00287", "12345", "1" * 15, None])
async def test_non_barcode_never_hits_network(monkeypatch, bad):
    """В barcode_norm дампа лежат каталожные номера и мусор — на них не тратим
    запросы вообще. Клиент подменён на взрывающийся: любой вызов = провал."""
    def _boom(*a, **kw):
        raise AssertionError("сетевой запрос на не-штрихкоде")
    monkeypatch.setattr(deezer.httpx, "AsyncClient", _boom)
    assert await cover_by_upc(bad) is None


@pytest.mark.asyncio
async def test_wave_never_returns_unasked_barcodes(monkeypatch):
    """Бюджет истёк — в результат попадают только реально спрошенные.

    Вызывающий метит `done` ровно то, что получил из волны, поэтому попадание
    сюда незаданного вопроса означало бы необратимую потерю штрихкода.
    """
    asked = []

    async def slow(bc):
        asked.append(bc)
        await asyncio.sleep(0.05)
        return None

    monkeypatch.setattr(upc, "cover_by_upc", slow)
    barcodes = [f"{i:012d}" for i in range(200)]

    results, quota = await upc._lookup_wave(barcodes, budget_s=0.2)

    assert not quota
    assert 0 < len(results) < len(barcodes), "бюджет обязан отсечь часть волны"
    returned = {bc for bc, _ in results}
    assert returned <= set(asked), "в результат попал незаданный вопрос"


@pytest.mark.asyncio
async def test_wave_stops_and_reports_quota(monkeypatch):
    """Упор в квоту прерывает волну и сообщает наружу — прогон встанет,
    а недоспрошенные штрихкоды останутся в очереди."""
    calls = {"n": 0}

    async def quota_after_three(bc):
        calls["n"] += 1
        if calls["n"] > 3:
            raise DeezerQuotaExceeded("Quota limit exceeded")
        return None

    monkeypatch.setattr(upc, "cover_by_upc", quota_after_three)
    barcodes = [f"{i:012d}" for i in range(100)]

    results, quota = await upc._lookup_wave(barcodes, budget_s=10)

    assert quota is True
    assert len(results) < len(barcodes)


def test_fanout_guard_excludes_garbage_barcodes():
    """Порог на число релизов за штрихкодом. Замер на проде: таких кодов 138 из
    2.3 млн, худший держит 251 релиз — общий код лейбла или ошибка ввода.
    Пустить их значит уехать одной обложкой на 251 разную пластинку."""
    assert upc._MAX_FANOUT == 20
    src = _worklist_sql()
    assert "HAVING count(*) <= {_MAX_FANOUT}" in src, "порог fanout ушёл из HAVING"
    # Заодно форма кода: каталожные номера и мусор не должны попадать в очередь.
    assert "'^[0-9]{8,14}$'" in src


def _worklist_sql() -> str:
    """SQL построения worklist — читаем из исходника, чтобы тест ловил правку
    условия, а не дублировал его."""
    import inspect
    return inspect.getsource(upc._build_worklist)
