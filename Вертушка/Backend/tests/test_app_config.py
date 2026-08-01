"""Smoke-тесты remote config (services/app_config.py).

Это аварийная кнопка: kill-switch и force-update gate. Если она соврёт,
инцидент будет чиниться деплоем вместо секунды — то есть не будет починен.
Фиксируем именно поведение при отказах: Redis лёг, флаг неизвестен, версия
кривая. Живой Redis не нужен — подменяем слой кэша фейком.
"""
import pytest

from app.services import app_config


class FakeCache:
    """Мини-Redis в памяти. available=False имитирует лежащий Redis."""

    def __init__(self, available: bool = True):
        self.available = available
        self.store: dict[tuple[str, str], object] = {}

    async def get(self, namespace: str, key: str):
        if not self.available:
            return None
        return self.store.get((namespace, key))

    async def set(self, namespace: str, key: str, value, ttl: int):
        if not self.available:
            return
        self.store[(namespace, key)] = value

    async def delete(self, namespace: str, key: str):
        self.store.pop((namespace, key), None)


@pytest.fixture(autouse=True)
def fake_cache(monkeypatch):
    """Подменяем Redis и чистим in-process кэш между тестами."""
    cache = FakeCache()
    monkeypatch.setattr(app_config, "cache", cache)
    app_config._local_invalidate()
    yield cache
    app_config._local_invalidate()


class TestFlags:
    async def test_defaults_are_all_enabled(self):
        """Без оверрайдов всё включено — новый деплой не гасит фичи молча."""
        flags = await app_config.get_flags()
        assert set(flags) == set(app_config.FLAG_NAMES)
        assert all(flags.values())

    async def test_override_disables_single_flag(self, fake_cache):
        await app_config.set_flags({"vision_scan": False})

        flags = await app_config.get_flags()
        assert flags["vision_scan"] is False
        assert flags["market"] is True, "выключение одного флага не трогает соседние"

    async def test_overrides_merge_across_calls(self):
        await app_config.set_flags({"vision_scan": False})
        app_config._local_invalidate()
        await app_config.set_flags({"market": False})

        flags = await app_config.get_flags()
        assert flags["vision_scan"] is False, "второй вызов не должен затирать первый"
        assert flags["market"] is False

    async def test_flag_can_be_turned_back_on(self):
        await app_config.set_flags({"vision_scan": False})
        await app_config.set_flags({"vision_scan": True})

        assert (await app_config.get_flags())["vision_scan"] is True

    async def test_unknown_flag_rejected(self):
        with pytest.raises(ValueError, match="Неизвестные флаги"):
            await app_config.set_flags({"нет_такого": False})

    async def test_is_enabled_unknown_flag_is_fail_open(self):
        """Опечатка в имени флага не должна выключать работающую фичу."""
        assert await app_config.is_enabled("опечатка") is True

    async def test_dead_redis_falls_back_to_env_defaults(self, fake_cache):
        await app_config.set_flags({"vision_scan": False})
        app_config._local_invalidate()

        fake_cache.available = False
        flags = await app_config.get_flags()

        assert flags["vision_scan"] is True, (
            "потеря Redis откатывает к env-дефолтам — это задокументированное "
            "поведение, а не баг: см. докстринг services/app_config.py"
        )

    async def test_reset_clears_overrides(self):
        await app_config.set_flags({"vision_scan": False, "market": False})
        await app_config.clear_overrides()

        assert all((await app_config.get_flags()).values())


class TestMinVersion:
    async def test_default_from_settings(self):
        assert await app_config.get_min_supported_version() == "1.0.0"

    async def test_override_applies(self):
        await app_config.set_min_supported_version("1.2.3")
        assert await app_config.get_min_supported_version() == "1.2.3"

    @pytest.mark.parametrize("bad", ["1.0", "1.0.0.0", "v1.0.0", "1.0.x", "", "latest"])
    async def test_malformed_version_rejected(self, bad):
        """Кривая версия в гейте выгонит на обновление всех сразу."""
        with pytest.raises(ValueError):
            await app_config.set_min_supported_version(bad)

    async def test_rejected_version_does_not_persist(self):
        with pytest.raises(ValueError):
            await app_config.set_min_supported_version("сломай")

        assert await app_config.get_min_supported_version() == "1.0.0"


class TestLocalCache:
    async def test_write_invalidates_local_cache_immediately(self):
        """Kill-switch обязан сработать сразу, а не через TTL локального кэша."""
        await app_config.get_flags()  # прогреваем кэш
        await app_config.set_flags({"market": False})

        assert (await app_config.get_flags())["market"] is False

    async def test_min_version_write_invalidates_local_cache(self):
        await app_config.get_min_supported_version()
        await app_config.set_min_supported_version("9.9.9")

        assert await app_config.get_min_supported_version() == "9.9.9"


class TestConfigEndpoint:
    """Публичный GET /api/config — контракт с мобильным клиентом.

    Без lifespan: Redis и БД не поднимаются, эндпоинт обязан отвечать на
    одних env-дефолтах. Если он это сломает, каждый холодный старт приложения
    будет получать ошибку.
    """

    @pytest.fixture
    def client(self):
        from fastapi.testclient import TestClient
        from app.main import app

        return TestClient(app)  # без `with` — lifespan намеренно не запускаем

    def test_returns_full_contract(self, client):
        response = client.get("/api/config/")

        assert response.status_code == 200
        body = response.json()
        assert set(body) == {
            "min_supported_version",
            "store_url",
            "update_message",
            "flags",
        }
        assert body["min_supported_version"] == "1.0.0"
        assert body["store_url"].startswith("https://")
        assert body["update_message"]

    def test_all_flags_present_and_enabled_by_default(self, client):
        flags = client.get("/api/config/").json()["flags"]

        assert set(flags) == set(app_config.FLAG_NAMES)
        assert all(flags.values())

    def test_public_endpoint_needs_no_auth(self, client):
        """Гейт читается до логина — авторизации тут быть не должно."""
        assert client.get("/api/config/").status_code == 200

    def test_admin_endpoints_require_auth(self, client):
        assert client.put("/api/admin/config/flags/", json={"flags": {"market": False}}).status_code in (401, 403)
        assert client.put("/api/admin/config/min-version/", json={"version": "1.0.1"}).status_code in (401, 403)
        assert client.post("/api/admin/config/reset/").status_code in (401, 403)


class TestFeatureGate:
    """Зависимость require_flag — то, чем рубильник реально закрывает эндпоинты."""

    async def test_enabled_flag_lets_request_through(self):
        from app.api.app_config import require_flag

        assert await require_flag("market")() is None

    async def test_disabled_flag_raises_503(self):
        from fastapi import HTTPException

        from app.api.app_config import require_flag

        await app_config.set_flags({"market": False})

        with pytest.raises(HTTPException) as exc:
            await require_flag("market")()

        assert exc.value.status_code == 503

    async def test_disabled_flag_marks_response_as_deliberate(self):
        """Заголовок гасит ретраи на клиенте (Mobile/lib/api.ts).

        Без него выключенная фича получит 4 запроса вместо одного и 7 секунд
        ожидания у пользователя.
        """
        from fastapi import HTTPException

        from app.api.app_config import FEATURE_DISABLED_HEADER, require_flag

        await app_config.set_flags({"vision_scan": False})

        with pytest.raises(HTTPException) as exc:
            await require_flag("vision_scan")()

        assert exc.value.headers[FEATURE_DISABLED_HEADER] == "vision_scan"

    async def test_gate_does_not_leak_between_flags(self):
        from app.api.app_config import require_flag

        await app_config.set_flags({"market": False})

        assert await require_flag("vision_scan")() is None
