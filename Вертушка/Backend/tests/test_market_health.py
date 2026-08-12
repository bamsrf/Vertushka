"""Сводка здоровья Маркета обязана ловить ровно те поломки, что молчали 12.08.

Три реальных случая, каждый нашёлся только руками:
  * очередь матчинга стояла — новый магазин не получил ни одного запроса;
  * vinyl.ru не обновлялся 48 дней при зелёном статусе;
  * харвест обложек три недели выбрасывал уже скачанные картинки.

Тесты подсовывают сводке данные каждого случая и требуют, чтобы он назвался
словами в `problems`.
"""
import pytest

from app.services import market_health


def _store(**over):
    base = {
        "slug": "shop", "is_active": True,
        "last_successful_scrape_at": "2026-08-12 02:00:00",
        "hours_since_scrape": 6.0, "last_error": None,
        "listings": 1000, "in_stock": 900, "matched": 800, "never_tried": 0,
    }
    base.update(over)
    return base


def _queue(**over):
    base = {"total": 100, "never_tried": 10, "oldest_never_tried_days": 0.5}
    base.update(over)
    return base


@pytest.fixture
def report(monkeypatch):
    """Подменяем БД: сводка — чистая функция над тремя выборками."""
    state = {"stores": [_store()], "queue": _queue(), "covers": {"harvestable": 0}}

    class _Result:
        def __init__(self, payload):
            self.payload = payload

        def mappings(self):
            return self

        def all(self):
            return self.payload

        def one(self):
            return self.payload

    class _Session:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def execute(self, stmt):
            sql = str(stmt)
            if "FROM stores" in sql:
                return _Result(state["stores"])
            if "FROM store_listings" in sql:
                return _Result(state["queue"])
            return _Result(state["covers"])

    monkeypatch.setattr(market_health, "async_session_maker", lambda: _Session())
    return state


async def _run():
    return await market_health.build_market_health_report()


@pytest.mark.asyncio
async def test_healthy_market_reports_ok(report):
    res = await _run()
    assert res["ok"] is True
    assert res["problems"] == []
    assert res["stores"][0]["matched_pct"] == 80.0


@pytest.mark.asyncio
async def test_stale_store_is_flagged(report):
    """Случай vinyl.ru: 48 дней тишины при зелёном статусе."""
    report["stores"] = [_store(slug="vinyl_ru", hours_since_scrape=48 * 24)]
    res = await _run()
    assert res["ok"] is False
    assert any("vinyl_ru" in p and "обход" in p for p in res["problems"])


@pytest.mark.asyncio
async def test_store_that_never_succeeded_is_flagged(report):
    report["stores"] = [_store(hours_since_scrape=None, last_successful_scrape_at=None)]
    res = await _run()
    assert any("ни одного успешного обхода" in p for p in res["problems"])


@pytest.mark.asyncio
async def test_last_error_surfaces(report):
    report["stores"] = [_store(last_error="crash: обход прерван")]
    res = await _run()
    assert any("обход прерван" in p for p in res["problems"])


@pytest.mark.asyncio
async def test_stalled_match_queue_is_flagged(report):
    """Случай rotaryrecords: позиции ждали очереди неделями."""
    report["queue"] = _queue(never_tried=1804, oldest_never_tried_days=21.0)
    res = await _run()
    assert any("очередь матчинга стоит" in p for p in res["problems"])


@pytest.mark.asyncio
async def test_fresh_queue_is_not_flagged(report):
    """Разбор в пределах суток — норма, а не повод шуметь."""
    report["queue"] = _queue(never_tried=5000, oldest_never_tried_days=0.9)
    res = await _run()
    assert not any("очередь" in p for p in res["problems"])


@pytest.mark.asyncio
async def test_broken_cover_harvest_is_flagged(report):
    """Случай мёртвого харвеста: 5 956 записей без обложки при наличии картинки."""
    report["covers"] = {"harvestable": 5956}
    res = await _run()
    assert any("обложки не осаждаются" in p for p in res["problems"])


@pytest.mark.asyncio
async def test_small_cover_tail_is_tolerated(report):
    """Плейсхолдеры магазинов отсекает фильтр мусора — ноль недостижим."""
    report["covers"] = {"harvestable": 2}
    res = await _run()
    assert res["ok"] is True


@pytest.mark.asyncio
async def test_zero_listings_does_not_crash(report):
    """Только что заведённый магазин: деления на ноль быть не должно."""
    report["stores"] = [_store(listings=0, matched=0, in_stock=0)]
    res = await _run()
    assert res["stores"][0]["matched_pct"] is None


def test_thresholds_are_sane():
    """Пороги должны прощать одну пропущенную ночь, но не двое суток молчания."""
    assert 24 < market_health.STALE_CRAWL_HOURS <= 48
    # Разбор новых позиций обязан быть быстрее кулдауна повтора.
    from app.services.listing_matcher import _MATCH_RETRY_DAYS
    assert market_health.STALE_QUEUE_DAYS < _MATCH_RETRY_DAYS
