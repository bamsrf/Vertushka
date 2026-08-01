"""Smoke-тесты дневных квот (services/quota.py).

Квота на Vision — единственное, что стоит между одним скриптом и счётом от
OpenAI. Ошибка в любую сторону дорогая: слишком строго — ломаем сканер всем,
слишком мягко — платим. Фиксируем границы и поведение при отказе Redis.
"""
import pytest

from app.services import quota


class FakeCache:
    """Счётчики в памяти. available=False имитирует лежащий Redis."""

    def __init__(self, available: bool = True):
        self.available = available
        self.counters: dict[tuple[str, str], int] = {}
        self.ttls: dict[tuple[str, str], int] = {}
        # Сколько слотов бёрст-окна уже занято, по ключу.
        self.burst_used: dict[str, int] = {}
        self.burst_capacity_override: int | None = None

    async def incr(self, namespace: str, key: str, ttl: int):
        if not self.available:
            return None
        k = (namespace, key)
        self.counters[k] = self.counters.get(k, 0) + 1
        self.ttls.setdefault(k, ttl)
        return self.counters[k]

    async def get_counter(self, namespace: str, key: str):
        if not self.available:
            return None
        return self.counters.get((namespace, key), 0)

    async def take_token(self, bucket_key: str, capacity: float, refill_rate_per_sec: float):
        if not self.available:
            return None
        used = self.burst_used.get(bucket_key, 0)
        if used < capacity:
            self.burst_used[bucket_key] = used + 1
            return 0
        return 1500  # окно заполнено, ждать


@pytest.fixture
def fake_cache(monkeypatch):
    cache = FakeCache()
    monkeypatch.setattr(quota, "cache", cache)
    return cache


@pytest.fixture
def captured_alerts(monkeypatch):
    """Перехватываем алармы: в тестах в Telegram ходить нельзя."""
    sent: list[str] = []
    monkeypatch.setattr(
        quota.alerts, "fire_and_forget", lambda key, title, body="": sent.append(key)
    )
    return sent


class TestConsumeDaily:
    async def test_first_call_allowed(self, fake_cache):
        status = await quota.consume_daily("test", "user-1", limit=3)

        assert status.allowed
        assert status.used == 1
        assert status.remaining == 2

    async def test_exactly_at_limit_still_allowed(self, fake_cache):
        for _ in range(2):
            await quota.consume_daily("test", "user-1", limit=3)

        status = await quota.consume_daily("test", "user-1", limit=3)

        assert status.allowed, "третий запрос при лимите 3 — ещё в пределах"
        assert status.used == 3
        assert status.remaining == 0

    async def test_one_over_limit_denied(self, fake_cache):
        for _ in range(3):
            await quota.consume_daily("test", "user-1", limit=3)

        status = await quota.consume_daily("test", "user-1", limit=3)

        assert not status.allowed
        assert status.retry_after_seconds > 0, "клиенту нужен Retry-After"

    async def test_quota_is_per_subject(self, fake_cache):
        for _ in range(5):
            await quota.consume_daily("test", "жадный", limit=3)

        status = await quota.consume_daily("test", "обычный", limit=3)

        assert status.allowed, "абьюзер не должен тратить квоту соседа"

    async def test_ttl_set_once_and_bounded_by_day(self, fake_cache):
        await quota.consume_daily("test", "user-1", limit=10)
        first_ttl = list(fake_cache.ttls.values())[0]

        await quota.consume_daily("test", "user-1", limit=10)

        assert list(fake_cache.ttls.values())[0] == first_ttl, (
            "TTL не должен продлеваться на каждом вызове — иначе дневная "
            "квота никогда не сбросится"
        )
        assert 60 <= first_ttl <= 24 * 3600


class TestFailOpen:
    async def test_dead_redis_allows_request(self, fake_cache, captured_alerts):
        fake_cache.available = False

        status = await quota.consume_daily("test", "user-1", limit=1)

        assert status.allowed, "Redis лёг — не ломаем продукт всем пользователям"

    async def test_dead_redis_raises_alert(self, fake_cache, captured_alerts):
        fake_cache.available = False

        await quota.consume_daily("test", "user-1", limit=1)

        assert "quota_redis_down" in captured_alerts, (
            "работать без квот молча опаснее, чем работать с ними"
        )

    async def test_dead_redis_allows_burst(self, fake_cache):
        fake_cache.available = False

        assert await quota.consume_burst("test", "user-1", per_minute=1)


class TestBurst:
    async def test_within_burst_allowed(self, fake_cache):
        assert await quota.consume_burst("test", "user-1", per_minute=2)
        assert await quota.consume_burst("test", "user-1", per_minute=2)

    async def test_over_burst_denied(self, fake_cache):
        for _ in range(2):
            await quota.consume_burst("test", "user-1", per_minute=2)

        assert not await quota.consume_burst("test", "user-1", per_minute=2)


class TestVisionScan:
    async def test_normal_use_passes_all_gates(self, fake_cache, captured_alerts):
        status = await quota.consume_vision_scan("user-1")

        assert status.allowed
        assert captured_alerts == []

    async def test_burst_blocks_before_daily_quota(self, fake_cache, captured_alerts):
        for _ in range(quota._VISION_BURST_PER_MINUTE):
            await quota.consume_vision_scan("user-1")

        status = await quota.consume_vision_scan("user-1")

        assert not status.allowed
        assert status.retry_after_seconds == 60, "бёрст — это подождать минуту, а не сутки"

    async def test_rejected_user_does_not_burn_global_budget(
        self, fake_cache, captured_alerts, monkeypatch
    ):
        """Ключевое свойство: один абьюзер не выключает сканер всем.

        Если бы глобальный счётчик инкрементировался до проверки per-user,
        достаточно было бы одного скрипта, чтобы исчерпать общий потолок.
        """
        monkeypatch.setattr(
            quota.get_settings(), "vision_scan_daily_limit_per_user", 2, raising=False
        )

        for _ in range(6):
            await quota.consume_vision_scan("абьюзер")

        global_used = await quota.peek_daily("vision_scan_global", "all")

        assert global_used == 2, (
            f"глобальный счётчик вырос на {global_used} при 2 разрешённых "
            "запросах — отклонённые жгут общий лимит"
        )

    async def test_warn_alert_fires_once_at_threshold(
        self, fake_cache, captured_alerts, monkeypatch
    ):
        settings = quota.get_settings()
        monkeypatch.setattr(settings, "vision_scan_daily_limit_global", 10, raising=False)
        monkeypatch.setattr(settings, "vision_scan_daily_limit_per_user", 1000, raising=False)
        monkeypatch.setattr(quota, "_VISION_BURST_PER_MINUTE", 1000)

        for _ in range(10):
            await quota.consume_vision_scan("user-1")

        assert captured_alerts.count("vision_quota_warn") == 1, (
            "аларм на пороге должен сработать ровно один раз, а не на каждом "
            "запросе после порога"
        )

    async def test_exhausted_alert_and_denial(
        self, fake_cache, captured_alerts, monkeypatch
    ):
        settings = quota.get_settings()
        monkeypatch.setattr(settings, "vision_scan_daily_limit_global", 3, raising=False)
        monkeypatch.setattr(settings, "vision_scan_daily_limit_per_user", 1000, raising=False)
        monkeypatch.setattr(quota, "_VISION_BURST_PER_MINUTE", 1000)

        results = [await quota.consume_vision_scan(f"user-{i}") for i in range(5)]

        assert [r.allowed for r in results] == [True, True, True, False, False]
        assert captured_alerts.count("vision_quota_exhausted") == 1
