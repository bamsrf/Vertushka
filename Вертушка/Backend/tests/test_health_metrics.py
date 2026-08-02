"""Smoke-тесты порогов здоровья (services/health_metrics.py).

Смысл модуля — ловить аварии, которые не ловит аларм на исключения. Главная
из них: волна 504 от таймаут-middleware, который отдаёт ответ напрямую и
обработчик исключений не трогает. Если эти тесты позеленеют неправильно,
залипшая БД снова будет означать тишину в Telegram.
"""
import pytest

from app.services import health_metrics
from app.services.health_metrics import RequestMetrics


@pytest.fixture(autouse=True)
def captured_alerts(monkeypatch):
    sent: list[str] = []
    monkeypatch.setattr(
        health_metrics.alerts, "fire_and_forget",
        lambda key, title, body="": sent.append(key),
    )
    # Свежее окно на каждый тест.
    monkeypatch.setattr(health_metrics, "_metrics", None)
    return sent


def feed(status_code: int, count: int, duration_ms: float = 100.0) -> None:
    for _ in range(count):
        health_metrics.observe(status_code, duration_ms)


class TestWindow:
    def test_counts_and_percentile(self):
        window = RequestMetrics(window_seconds=300)
        for ms in range(1, 101):
            window.record(200, float(ms))

        snapshot = window.snapshot()

        assert snapshot.total == 100
        assert snapshot.server_errors == 0
        assert snapshot.p99_ms == 99.0

    def test_server_errors_counted_from_500_up(self):
        window = RequestMetrics(window_seconds=300)
        for code in (200, 404, 429, 500, 502, 504):
            window.record(code, 10.0)

        snapshot = window.snapshot()

        assert snapshot.server_errors == 3, "500, 502 и 504 — все серверные"
        assert snapshot.rate_limited == 1

    def test_empty_window_is_safe(self):
        snapshot = RequestMetrics(window_seconds=300).snapshot()

        assert snapshot.total == 0
        assert snapshot.error_rate == 0.0
        assert snapshot.p99_ms == 0.0

    def test_old_events_fall_out(self):
        window = RequestMetrics(window_seconds=0)  # всё мгновенно протухает
        window.record(500, 10.0)
        window.record(200, 10.0)

        assert window.snapshot().total <= 1


class TestErrorRateAlert:
    def test_silent_below_min_requests(self, captured_alerts):
        """Две пятисотки на трёх запросах — это 67% и повод для паники на пустом месте."""
        feed(500, 3)

        assert captured_alerts == []

    def test_fires_above_threshold(self, captured_alerts):
        feed(200, 25)
        feed(500, 10)  # ~29% при пороге 10%

        assert "error_rate" in captured_alerts

    def test_silent_on_healthy_traffic(self, captured_alerts):
        feed(200, 100)

        assert captured_alerts == []

    def test_client_errors_do_not_count_as_outage(self, captured_alerts):
        """404 и 401 — это про клиента, а не про сломанный сервер."""
        feed(404, 50)
        feed(401, 50)

        assert "error_rate" not in captured_alerts


class TestTimeoutCoverage:
    def test_timeout_wave_raises_alert(self, captured_alerts):
        """Ради этого теста модуль и написан.

        504 отдаётся timeout_middleware напрямую, минуя обработчик исключений,
        поэтому аларм на 5xx его не видит. Залипшая БД = тишина.
        """
        feed(200, 25)
        feed(504, 15)

        assert "error_rate" in captured_alerts, (
            "волна таймаутов обязана поднимать аларм — это самая незаметная авария"
        )


class TestLatencyAlert:
    def test_slow_p99_alerts_without_any_errors(self, captured_alerts):
        """Деградация без ошибок: ответы честные, но пользоваться нельзя."""
        feed(200, 30, duration_ms=9000.0)

        assert "p99_latency" in captured_alerts
        assert "error_rate" not in captured_alerts

    def test_fast_traffic_is_silent(self, captured_alerts):
        feed(200, 30, duration_ms=120.0)

        assert captured_alerts == []

    def test_single_slow_request_does_not_alert(self, captured_alerts):
        """Один долгий запрос среди сотни — это хвост, а не авария."""
        feed(200, 99, duration_ms=100.0)
        health_metrics.observe(200, 30_000.0)

        assert "p99_latency" not in captured_alerts


class TestRateLimitStorm:
    def test_storm_alerts(self, captured_alerts):
        feed(429, 60)

        assert "rate_limit_storm" in captured_alerts

    def test_few_429_are_normal(self, captured_alerts):
        feed(200, 50)
        feed(429, 5)

        assert "rate_limit_storm" not in captured_alerts


class TestMiddlewareWiring:
    """Middleware должен быть САМЫМ ВНЕШНИМ, иначе он не увидит 504.

    В Starlette внешним становится добавленный последним. Стоит кому-то
    дописать ещё один `@app.middleware` ниже — и метрики перестанут видеть
    ответы таймаут-middleware. Тест ловит и это, и просто отвалившуюся
    регистрацию.
    """

    def test_requests_are_recorded(self, monkeypatch):
        from fastapi.testclient import TestClient

        from app.main import app

        monkeypatch.setattr(health_metrics, "_metrics", None)
        client = TestClient(app)  # без `with` — lifespan не нужен

        client.get("/api/config/")
        client.get("/api/config/")

        assert health_metrics.get_metrics().snapshot().total >= 2, (
            "middleware не считает запросы — проверь регистрацию в main.py"
        )

    def test_metrics_middleware_is_outermost(self):
        """Позиция в стеке: наш middleware должен стоять последним в списке."""
        from app.main import app

        http_middleware = [m for m in app.user_middleware]
        names = [getattr(m.kwargs.get("dispatch", None), "__name__", "") for m in http_middleware]

        assert "health_metrics_middleware" in names, "middleware не зарегистрирован"
        assert names[0] == "health_metrics_middleware", (
            "health_metrics должен быть добавлен последним (= самый внешний), "
            "иначе 504 от timeout_middleware пройдут мимо метрик"
        )
