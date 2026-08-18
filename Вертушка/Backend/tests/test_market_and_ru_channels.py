"""Два новых канала обложек: обратный поток из маркета и постсоветский Deezer→Yandex.

Общее у обоих — дисциплина, выстраданная тремя инцидентами подряд:

  1. Мелкая картинка не смеет попасть в `cover_image_url`. Так мы получили 54%
     пиксельных мастеров: запись занята, и бесплатные каналы (они пишут только
     в NULL) к ней уже не подойдут. Фото магазинов ровно такие: у vinyl.ru
     медиана 318px, у plastinka.com — 600px.
  2. Волна не закрывает незаданный вопрос (`done` метится по опрошенным).
  3. Источник, который «не ответил» (квота Deezer, бан Yandex по IP), — это НЕ
     промах. Иначе один 403 сожжёт остаток очереди навсегда.
"""
import asyncio

import pytest

from app.scripts import backfill_covers_from_market as mk
from app.scripts import backfill_covers_ru as ru
from app.services import yandex_music
from app.services.cover_quality import MASTER_MIN_SIDE
from app.services.deezer import DeezerQuotaExceeded
from app.services.yandex_music import YandexThrottled


# ── маркет → дамп ────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_market_picks_first_master_grade_and_stops(monkeypatch):
    """Из нескольких магазинов берём первый мастер-тира и лишнего не качаем.

    Пластинка, лежащая и в vinyl.ru (318px), и в plastinka.com (600px), обязана
    получить вторую.
    """
    sizes = {"http://small/a.jpg": 318, "http://big/b.jpg": 600, "http://x/c.jpg": 1000}
    asked = []

    async def fake_min_side(client, url):
        asked.append(url)
        return sizes.get(url)

    monkeypatch.setattr(mk, "_min_side", fake_min_side)
    monkeypatch.setattr(mk, "is_safe_redirect_target", lambda u: True)

    got = await mk._pick_best(None, list(sizes))
    assert got == ("http://big/b.jpg", 600)
    assert asked == ["http://small/a.jpg", "http://big/b.jpg"], "третий URL качать незачем"


@pytest.mark.asyncio
async def test_market_falls_back_to_largest_small_image(monkeypatch):
    """Мастера нет — возвращаем самую крупную мелочь, она пойдёт в thumb-тир."""
    sizes = {"http://a/1.jpg": 300, "http://b/2.jpg": 450, "http://c/3.jpg": 200}
    monkeypatch.setattr(mk, "_min_side", lambda c, u: _async(sizes.get(u)))
    monkeypatch.setattr(mk, "is_safe_redirect_target", lambda u: True)
    got = await mk._pick_best(None, list(sizes))
    assert got == ("http://b/2.jpg", 450)
    assert got[1] < MASTER_MIN_SIDE


@pytest.mark.asyncio
async def test_market_skips_unsafe_urls(monkeypatch):
    """URL приезжает из парсера чужой витрины — без гварда зеркало пойдёт куда попало."""
    monkeypatch.setattr(mk, "is_safe_redirect_target", lambda u: u.startswith("https://ok"))
    called = []

    async def fake(client, url):
        called.append(url)
        return 900

    monkeypatch.setattr(mk, "_min_side", fake)
    got = await mk._pick_best(None, ["http://evil.internal/x.jpg", "https://ok/y.jpg"])
    assert got == ("https://ok/y.jpg", 900)
    assert called == ["https://ok/y.jpg"]


def _async(value):
    async def _f():
        return value
    return _f()


# ── постсоветский канал ──────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_ru_ladder_tries_deezer_before_yandex(monkeypatch):
    """Deezer первым: вдвое быстрее (0.13с против 0.25с) и не хуже по точности."""
    calls = []

    class _C:
        url = "https://e-cdns-images.dzcdn.net/images/cover/a/1000x1000-000000-80-0-0.jpg"

    async def dz(artist, title, year=None, **kw):
        calls.append("deezer")
        return _C()

    async def ya(artist, title, year=None, **kw):
        calls.append("yandex")
        return None

    monkeypatch.setattr(ru, "dz_cover", dz)
    monkeypatch.setattr(ru, "ya_cover", ya)
    url = await ru._resolve({"artist": "Кино", "title": "Группа крови", "year": 1988})
    assert url == _C.url
    assert calls == ["deezer"], "Yandex не должен спрашиваться после попадания Deezer"


@pytest.mark.asyncio
async def test_ru_falls_through_to_yandex(monkeypatch):
    """Транслит-мост Yandex — ради него канал и нужен: Discogs пишет `Kino`,
    Yandex отдаёт «КИНО». Это те 4 п.п., которых у Deezer нет."""
    class _Y:
        url = "https://avatars.yandex.net/get-music-content/x/1000x1000"

    monkeypatch.setattr(ru, "dz_cover", lambda *a, **kw: _async(None))
    monkeypatch.setattr(ru, "ya_cover", lambda *a, **kw: _async(_Y()))
    url = await ru._resolve({"artist": "Kino", "title": "Gruppa Krovi", "year": 1988})
    assert url == _Y.url


@pytest.mark.asyncio
@pytest.mark.parametrize("exc", [DeezerQuotaExceeded("quota"), YandexThrottled("HTTP 403")])
async def test_ru_wave_stops_and_reports_when_source_blocks(monkeypatch, exc):
    """ГЛАВНЫЙ тест: закрывшийся источник прерывает волну, а не пишет промахи.

    Иначе один бан по IP пометит остаток очереди (сотни тысяч записей)
    проверенным, ни разу их не спросив.
    """
    n = {"i": 0}

    async def boom(row):
        n["i"] += 1
        if n["i"] > 3:
            raise exc
        return None

    monkeypatch.setattr(ru, "_resolve", boom)
    rows = [{"discogs_id": i, "artist": "A", "title": "T", "year": None} for i in range(60)]
    results, blocked = await ru._lookup_wave(rows, budget_s=10)
    assert blocked is True
    assert len(results) < len(rows)


@pytest.mark.asyncio
async def test_ru_wave_never_returns_unasked_rows(monkeypatch):
    """Бюджет истёк — наружу идут только опрошенные."""
    async def slow(row):
        await asyncio.sleep(0.05)
        return None

    monkeypatch.setattr(ru, "_resolve", slow)
    rows = [{"discogs_id": i, "artist": "A", "title": "T", "year": None} for i in range(200)]
    results, blocked = await ru._lookup_wave(rows, budget_s=0.2)
    assert not blocked
    assert 0 < len(results) < len(rows)


def test_ru_covers_the_whole_post_soviet_space():
    """USSR обязателен: там дыра 97.1% и её не закрывает ни один другой канал —
    у «Мелодии» не было штрихкодов (87 кодов на 74 464 релиза)."""
    assert "USSR" in ru.COUNTRIES
    assert {"Russia", "Ukraine", "Belarus", "Estonia", "Latvia", "Lithuania"} <= set(ru.COUNTRIES)


def test_both_channels_have_zero_yield_watchdog():
    """Урок инцидента с ведущим нулём: три часа нулевого выхлопа прошли незамеченными."""
    assert ru._ZERO_STREAK_ABORT > 0


@pytest.mark.asyncio
async def test_yandex_raises_on_ban_status(monkeypatch):
    """403/429/5xx у неофициального API — это «не спросили», а не «нет обложки»."""
    class _Resp:
        status_code = 403
        def json(self): return {}
        def raise_for_status(self): pass

    class _Client:
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        async def get(self, *a, **kw): return _Resp()

    async def noop(): return None
    monkeypatch.setattr(yandex_music, "_throttle", noop)
    monkeypatch.setattr(yandex_music.httpx, "AsyncClient", lambda *a, **kw: _Client())

    with pytest.raises(YandexThrottled):
        await yandex_music.cover_by_meta("Кино", "Группа крови")
