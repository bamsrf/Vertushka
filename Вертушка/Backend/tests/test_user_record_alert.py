"""Аларм на публикацию ручного релиза.

Зачем: премодерацию user-records отменили (§6, revised 2026-06-17) — запись
создаётся сразу approved и видна всем. С тех пор единственный сигнал о плохом
контенте — жалоба, то есть кто-то уже успел его увидеть, а владелец узнаёт о
заливках только опросом API. Аларм на публикацию возвращает наблюдаемость.

Живой БД тесты не требуют (см. conftest), поэтому эндпоинт проверяем по
исходнику, а доставку и маркер — на самом alerts.
"""
import inspect

import pytest

from app.api import records
from app.services import alerts


def test_endpoint_fires_alert_on_publish():
    """Ключ и вызов зашиты в сам эндпоинт, а не в фоновую джобу."""
    src = inspect.getsource(records.create_user_submitted_record)
    assert "alerts.fire_and_forget" in src
    assert 'key="user_record_created"' in src


def test_alert_key_is_separate_from_reports():
    """Троттлинг в alerts общий по ключу: раздели ключи, иначе всплеск
    заливок съест окно и настоящая жалоба не долетит."""
    from app.api import reports

    published = inspect.getsource(records.create_user_submitted_record)
    complained = inspect.getsource(reports.create_report)
    assert 'key="user_record_created"' in published
    assert 'key="ugc_report"' in complained


@pytest.mark.asyncio
async def test_custom_emoji_reaches_telegram(monkeypatch):
    """💿, а не 🔴: красный кружок на не-аварии обесценивает красный
    кружок на настоящей пятисотке."""
    sent = {}

    class _Resp:
        status_code = 200
        text = ""

    class _Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def post(self, url, json):
            sent.update(json)
            return _Resp()

    monkeypatch.setattr(alerts, "_enabled", lambda: True)
    monkeypatch.setattr(alerts, "_should_send", lambda key: (True, 0))
    monkeypatch.setattr(alerts.httpx, "AsyncClient", lambda **kw: _Client())

    await alerts.send_alert("k", "Новый ручной релиз", "Boards of Canada — MHTRTC", emoji="💿")

    assert sent["text"].startswith("💿 <b>Новый ручной релиз</b>")


@pytest.mark.asyncio
async def test_emoji_defaults_to_red(monkeypatch):
    """Существующие вызовы (их десятки) остаются авариями без правок."""
    sent = {}

    class _Resp:
        status_code = 200
        text = ""

    class _Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def post(self, url, json):
            sent.update(json)
            return _Resp()

    monkeypatch.setattr(alerts, "_enabled", lambda: True)
    monkeypatch.setattr(alerts, "_should_send", lambda key: (True, 0))
    monkeypatch.setattr(alerts.httpx, "AsyncClient", lambda **kw: _Client())

    await alerts.send_alert("k", "500 на /api/records")

    assert sent["text"].startswith("🔴 ")
