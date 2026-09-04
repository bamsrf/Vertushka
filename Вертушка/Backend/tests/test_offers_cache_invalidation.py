"""WS7 2.2 — версионная инвалидация offers-кэша вместо Redis SCAN.

Старая схема делала scan_iter(match=prefix*) на каждую запись — полный обход
keyspace × ~31.5k записей после каждого обхода. Новая: версия в cache-key,
инвалидация = INCR. Тесты — на фейковом Redis-стабе.
"""
import asyncio

import pytest

from app.api import offers as offers_mod
from app.services.cache import cache


class _FakePipe:
    def __init__(self, store):
        self.store = store
        self.ops: list = []

    def incr(self, key):
        self.ops.append(("incr", key))

    def expire(self, key, ttl):
        self.ops.append(("expire", key, ttl))

    async def execute(self):
        for op in self.ops:
            if op[0] == "incr":
                self.store[op[1]] = str(int(self.store.get(op[1], "0")) + 1)
        return [True] * len(self.ops)


class _FakeRedis:
    """Минимум, который использует версионная схема. scan_iter НАМЕРЕННО нет:
    вызов старого SCAN-пути упадёт с AttributeError и провалит тест."""

    def __init__(self):
        self.store: dict[str, str] = {}
        self.incr_calls = 0
        self.pipelines = 0

    async def get(self, key):
        return self.store.get(key)

    async def incr(self, key):
        self.incr_calls += 1
        self.store[key] = str(int(self.store.get(key, "0")) + 1)
        return int(self.store[key])

    async def expire(self, key, ttl):
        return True

    def pipeline(self, transaction=True):
        self.pipelines += 1
        return _FakePipe(self.store)


@pytest.fixture()
def fake_redis(monkeypatch):
    fake = _FakeRedis()
    monkeypatch.setattr(cache, "_pool", fake)
    monkeypatch.setattr(cache, "_available", True)
    return fake


@pytest.mark.asyncio
async def test_invalidate_bumps_version_without_scan(fake_redis):
    v0 = await offers_mod._cache_version(offers_mod._OFFERS_VER_NS, "123")
    assert v0 == "0"
    await offers_mod.invalidate_record_offers("123")
    v1 = await offers_mod._cache_version(offers_mod._OFFERS_VER_NS, "123")
    assert v1 == "1"
    # ключ кэша с новой версией отличается → старое значение недостижимо
    assert f"123:v{v0}:" != f"123:v{v1}:"
    assert fake_redis.incr_calls == 1


@pytest.mark.asyncio
async def test_bulk_invalidation_uses_single_pipeline(fake_redis):
    ids = [str(i) for i in range(500)]
    done = await offers_mod.invalidate_records_offers_bulk(ids)
    assert done == 500
    assert fake_redis.pipelines == 1          # один пакет, не 500 команд
    assert fake_redis.incr_calls == 0          # и не по-одному
    v = await offers_mod._cache_version(offers_mod._OFFERS_VER_NS, "42")
    assert v == "1"


@pytest.mark.asyncio
async def test_market_feed_invalidation_is_incr(fake_redis):
    await offers_mod.invalidate_market_feed()
    v = await offers_mod._cache_version(
        offers_mod.MARKET_CACHE_NS + "_ver", offers_mod._MARKET_VER_KEY
    )
    assert v == "1"


@pytest.mark.asyncio
async def test_version_survives_redis_unavailable(monkeypatch):
    monkeypatch.setattr(cache, "_available", False)
    monkeypatch.setattr(cache, "_pool", None)
    # без Redis — версия '0', инвалидации no-op, ничего не бросает
    assert await offers_mod._cache_version(offers_mod._OFFERS_VER_NS, "x") == "0"
    await offers_mod.invalidate_record_offers("x")
    assert await offers_mod.invalidate_records_offers_bulk(["a", "b"]) == 0


def test_no_scan_iter_left_in_invalidation_paths():
    """Сторож: SCAN не должен вернуться в пути инвалидации."""
    import inspect

    for fn in (offers_mod.invalidate_record_offers,
               offers_mod.invalidate_records_offers_bulk,
               offers_mod.invalidate_market_feed):
        assert "scan_iter" not in inspect.getsource(fn)
