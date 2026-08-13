"""Лестница источников и ночной перегрев мелких мастеров.

Главное, что здесь сторожится — изоляция от Discogs. Перегрев существует именно
потому, что их 150px-thumb стал мастером; если в эту лестницу когда-нибудь
вернётся вызов Discogs «на всякий случай», задача начнёт жечь их лимиты и
тянуть протухающие подписанные URL, то есть воспроизведёт исходную болезнь.

Второе — порядок ступеней. Он не косметика: CAA по офлайн-маппингу не делает
сетевых вызовов на поиск, barcode стоит MB-троттла 1 rps, iTunes — 3.1с на
запрос. Перестановка ступеней меняет стоимость прогона на порядок.
"""
import asyncio
import inspect

import pytest

from app.services import cover_fallback, cover_warm, deezer

_ROW = {
    "discogs_id": "736788",
    "barcode_norm": "602547311009",
    "artist": "Kendrick Lamar",
    "title": "To Pimp A Butterfly",
    "year": 2015,
    "label": "Top Dawg Entertainment",
}


class _Recorder:
    """Пишет порядок обращений к источникам."""

    def __init__(self) -> None:
        self.calls: list[str] = []


@pytest.fixture
def sources(monkeypatch):
    rec = _Recorder()

    async def caa_by_id(session, did):
        rec.calls.append("caa_id")
        return None

    async def caa_by_barcode(barcode):
        rec.calls.append("caa_barcode")
        return None

    async def itunes(artist, title):
        rec.calls.append("itunes")
        return None

    async def dz(artist, title, year=None, label=None):
        rec.calls.append("deezer")
        return None

    monkeypatch.setattr(cover_fallback, "cover_url_by_discogs_id", caa_by_id)
    monkeypatch.setattr(cover_fallback, "cover_url_by_barcode", caa_by_barcode)
    monkeypatch.setattr(cover_fallback, "cover_url_by_artist_title", itunes)
    monkeypatch.setattr(deezer, "cover_by_meta", dz)
    return rec


def test_ladder_order_when_nothing_found(sources):
    """Без пробы Discogs порядок ровно: CAA(id) → CAA(barcode) → Deezer → iTunes."""
    result = asyncio.run(cover_warm.resolve_cover_url(None, _ROW, discogs_probe=None))
    assert result is None
    assert sources.calls == ["caa_id", "caa_barcode", "deezer", "itunes"]


def test_ladder_short_circuits_on_first_hit(monkeypatch, sources):
    """Нашли на первой ступени — дальше не идём. Каждая следующая стоит дороже."""
    async def caa_hit(session, did):
        sources.calls.append("caa_id")
        return "https://coverartarchive.org/release/abc/front-1200"

    monkeypatch.setattr(cover_fallback, "cover_url_by_discogs_id", caa_hit)

    result = asyncio.run(cover_warm.resolve_cover_url(None, _ROW, discogs_probe=None))
    assert result.endswith("front-1200")
    assert sources.calls == ["caa_id"]


def test_discogs_probe_never_called_when_absent(sources):
    """discogs_probe=None ⇒ Discogs не участвует ни в каком виде."""
    asyncio.run(cover_warm.resolve_cover_url(None, _ROW, discogs_probe=None))
    assert "discogs" not in sources.calls


def test_discogs_probe_sits_between_deezer_and_itunes(sources):
    """Когда проба передана — она четвёртая, не раньше.

    Раньше Discogs шёл бы вперёд бесплатных источников и жёг бы лимиты на то,
    что CAA отдаёт даром.
    """
    async def probe(did):
        sources.calls.append("discogs")
        return None

    asyncio.run(cover_warm.resolve_cover_url(None, _ROW, discogs_probe=probe))
    assert sources.calls == ["caa_id", "caa_barcode", "deezer", "discogs", "itunes"]


def test_row_without_barcode_skips_barcode_step(monkeypatch, sources):
    """Нет barcode — не тратим MB-троттл на заведомо пустой запрос."""
    row = dict(_ROW, barcode_norm=None)
    asyncio.run(cover_warm.resolve_cover_url(None, row, discogs_probe=None))
    assert "caa_barcode" not in sources.calls


def test_sweep_isolates_discogs_by_construction():
    """Перегрев обязан звать лестницу БЕЗ пробы Discogs.

    Проверяем исходник, а не поведение: поднять здесь полноценную БД дороже, чем
    ценность теста, а регрессия выглядела бы именно как появление пробы в вызове.
    """
    from app.tasks import cover_upgrade_tasks

    src = inspect.getsource(cover_upgrade_tasks.upgrade_low_res_covers)
    assert "discogs_probe=None" in src, "перегрев не должен ходить в Discogs"
    assert "get_release_cover" not in src
    assert "DiscogsService" not in src


def test_sweep_respects_disable_flag(monkeypatch):
    """Флаг выключения работает без обращения к БД."""
    from app.config import get_settings
    from app.tasks import cover_upgrade_tasks

    settings = get_settings()
    monkeypatch.setattr(settings, "cover_upgrade_enabled", False)

    result = asyncio.run(cover_upgrade_tasks.upgrade_low_res_covers())
    assert result == {"skipped": "disabled"}
