"""Батч должен честно считать провалы магазинов.

Ночь 08-11: `scraper batch done: {'stores': 7, 'ok': 7, 'failed': 0}` при двух
магазинах, у которых в БД проставлена ошибка. Старый счётчик считал успехом
всё, что не бросило исключение, а `crawl_store` их гасит внутри.
"""
import pytest

from app.tasks import scraper_tasks


class _Store:
    def __init__(self, slug):
        self.slug = slug


@pytest.fixture
def _stores(monkeypatch):
    """Подменяем БД-выборку магазинов и kill-switch."""
    slugs = ["alpha", "beta", "gamma"]

    class _Result:
        def scalars(self):
            return self

        def all(self):
            return [_Store(s) for s in slugs]

    class _Session:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def execute(self, *a, **kw):
            return _Result()

    monkeypatch.setattr(scraper_tasks, "async_session_maker", lambda: _Session())

    async def _enabled(_flag):
        return True

    monkeypatch.setattr(scraper_tasks.app_config, "is_enabled", _enabled)
    return slugs


@pytest.mark.asyncio
async def test_failed_store_is_counted_as_failed(monkeypatch, _stores):
    outcomes = {
        "alpha": {"status": "ok", "upserted": 100},
        "beta": {"status": "failed", "upserted": 812},   # doctorhead-сценарий
        "gamma": {"status": "blocked", "upserted": 0},
    }

    async def _crawl(slug, *, mode, **kw):
        return outcomes[slug]

    monkeypatch.setattr(scraper_tasks, "crawl_store", _crawl)

    res = await scraper_tasks._crawl_active_stores(mode="full")

    assert res["ok"] == 1
    assert res["failed"] == 2
    # Позиции упавшего магазина всё равно записаны — их не теряем в отчёте.
    assert res["total_upserted"] == 912
    assert sorted(res["failed_stores"]) == ["beta:failed", "gamma:blocked"]


@pytest.mark.asyncio
async def test_raised_exception_still_counted(monkeypatch, _stores):
    async def _crawl(slug, *, mode, **kw):
        if slug == "beta":
            raise RuntimeError("unexpected")
        return {"status": "ok", "upserted": 10}

    monkeypatch.setattr(scraper_tasks, "crawl_store", _crawl)

    res = await scraper_tasks._crawl_active_stores(mode="full")
    assert res["ok"] == 2
    assert res["failed"] == 1
