"""Suggest: минимальная длина запроса и Redis-кэш локального ответа.

Живые БД/Redis не нужны: локальный путь и кэш подменяются, проверяется сама
механика — короткие запросы не доходят ни до БД, ни до Discogs, а повторный
запрос горячего префикса обслуживается из кэша без второго похода в БД.
"""
import pytest


class FakeCache:
    """In-memory замена RedisCache — ровно те методы, что зовёт suggest."""

    def __init__(self) -> None:
        self.store: dict = {}
        self.available = True

    async def get(self, namespace: str, key: str):
        return self.store.get((namespace, key))

    async def set(self, namespace: str, key: str, value, ttl: int) -> None:
        self.store[(namespace, key)] = value


@pytest.fixture
def client():
    from fastapi.testclient import TestClient

    from app.main import app

    return TestClient(app)  # без `with` — lifespan не нужен


@pytest.fixture
def fake_cache(monkeypatch):
    from app.api import records

    fake = FakeCache()
    monkeypatch.setattr(records, "cache", fake)
    return fake


@pytest.fixture
def local_calls(monkeypatch):
    """Стаб _suggest_local: всегда находит один мастер, считает вызовы."""
    from app.api import records

    calls: list[str] = []

    async def _stub(db, q):
        calls.append(q)
        return {
            "artists": [],
            "masters": [{
                "master_id": "1", "title": "Test", "artist": "A",
                "year": 2000, "thumb": None,
            }],
        }

    monkeypatch.setattr(records, "_suggest_local", _stub)
    return calls


class TestMinLength:
    def test_short_query_returns_empty_not_422(self, client, fake_cache, local_calls):
        """Мобилка шлёт от 2 символов — HTTP-контракт держим: 200 и пусто."""
        for q in ("ab", "abc", "  abc  "):
            resp = client.get("/api/records/suggest", params={"q": q})
            assert resp.status_code == 200
            assert resp.json() == {"artists": [], "masters": []}
        # Короткий префикс не тронул ни БД (стаб не звался), ни кэш.
        assert local_calls == []
        assert fake_cache.store == {}

    def test_one_char_still_422(self, client, fake_cache, local_calls):
        """Query(min_length=2) не менялся — 1 символ отсекает валидация."""
        resp = client.get("/api/records/suggest", params={"q": "a"})
        assert resp.status_code == 422


class TestCache:
    def test_local_hit_cached_by_normalized_prefix(self, client, fake_cache, local_calls):
        r1 = client.get("/api/records/suggest", params={"q": "Pink Floyd"})
        assert r1.status_code == 200
        assert len(local_calls) == 1

        # Другой регистр и пробелы → тот же нормализованный ключ, БД не трогаем.
        r2 = client.get("/api/records/suggest", params={"q": "  pink floyd "})
        assert r2.status_code == 200
        assert r2.json() == r1.json()
        assert len(local_calls) == 1
        assert ("suggest_local", "pink floyd") in fake_cache.store

    def test_local_miss_cached_too(self, client, fake_cache, monkeypatch):
        """Промах локального пути кэшируется маркером: повтор пустого
        префикса не гоняет trgm-запрос заново, а идёт сразу в Discogs."""
        from app.api import records

        calls: list[str] = []

        async def _miss(db, q):
            calls.append(q)
            return None

        async def _discogs_stub(self, query, per_page=8, creds=None):
            return {"artists": [], "masters": []}

        monkeypatch.setattr(records, "_suggest_local", _miss)
        monkeypatch.setattr(records.DiscogsService, "suggest", _discogs_stub)

        for _ in range(2):
            resp = client.get("/api/records/suggest", params={"q": "zzzz"})
            assert resp.status_code == 200

        assert len(calls) == 1
        assert fake_cache.store[("suggest_local", "zzzz")] == {"__miss__": True}
