"""Smoke-тесты порогов здоровья (services/health_metrics.py).

Смысл модуля — ловить аварии, которые не ловит аларм на исключения. Главная
из них: волна 504 от таймаут-middleware, который отдаёт ответ напрямую и
обработчик исключений не трогает. Если эти тесты позеленеют неправильно,
залипшая БД снова будет означать тишину в Telegram.
"""
import pytest

from app.services import health_metrics
from app.services.health_metrics import RequestMetrics


class _Sent(list):
    """Список ключей алармов, который помнит ещё и тела сообщений."""

    def __init__(self):
        super().__init__()
        self.bodies: dict[str, str] = {}

    def add(self, key: str, body: str) -> None:
        self.append(key)
        self.bodies[key] = body


@pytest.fixture(autouse=True)
def captured_alerts(monkeypatch):
    sent = _Sent()
    monkeypatch.setattr(
        health_metrics.alerts, "fire_and_forget",
        lambda key, title, body="": sent.add(key, body),
    )
    # Свежее окно на каждый тест.
    monkeypatch.setattr(health_metrics, "_metrics", None)
    return sent


def feed(
    status_code: int, count: int, duration_ms: float = 100.0, endpoint: str = ""
) -> None:
    for _ in range(count):
        health_metrics.observe(status_code, duration_ms, endpoint)


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

    def test_endpoint_template_reaches_metrics(self, monkeypatch):
        """В окно должен попадать ШАБЛОН маршрута, а не подставленный URL.

        Иначе `/api/records/{id}` размажется по тысяче адресов и в аларме
        окажется случайная пластинка вместо ручки, которая тормозит.
        """
        from fastapi.testclient import TestClient

        from app.main import app

        monkeypatch.setattr(health_metrics, "_metrics", None)
        client = TestClient(app)

        client.get("/api/config/")

        endpoints = [e[3] for e in health_metrics.get_metrics()._events]
        assert "GET /api/config/" in endpoints, (
            f"middleware не передаёт путь в метрики: {endpoints}"
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


class TestSlowestEndpoints:
    """Аларм обязан называть виновника.

    Без этого сообщение содержит цифру и ничего больше, а найти по ней путь
    неоткуда: nginx пишет combined-формат без $request_time, трассировка в
    Sentry не включена, приложение логирует только таймауты на 90с. Каждый
    аларм превращался в расследование с нуля — ровно это и случилось
    10.09.2026.
    """

    def test_alert_body_names_the_slow_endpoint(self, captured_alerts):
        feed(200, 30, duration_ms=9000.0, endpoint="GET /api/records/{record_id}")

        body = captured_alerts.bodies["p99_latency"]
        assert "GET /api/records/{record_id}" in body
        assert "9.0с" in body

    def test_slowest_is_sorted_and_capped(self):
        window = RequestMetrics(window_seconds=300)
        window.record(200, 100.0, "GET /fast")
        window.record(200, 9000.0, "GET /slowest")
        window.record(200, 5000.0, "GET /middle")
        window.record(200, 7000.0, "GET /second")

        slowest = window.snapshot().slowest

        assert len(slowest) == health_metrics.SLOWEST_IN_ALERT
        assert [ep for ep, _ in slowest] == [
            "GET /slowest", "GET /second", "GET /middle",
        ]

    def test_missing_endpoint_does_not_break_alert(self, captured_alerts):
        """Путь может не приехать (404 мимо роутера) — аларм всё равно уходит."""
        feed(200, 30, duration_ms=9000.0)

        assert "p99_latency" in captured_alerts
        assert "9.0с" in captured_alerts.bodies["p99_latency"]

    def test_empty_window_has_no_slowest(self):
        assert RequestMetrics(window_seconds=300).snapshot().slowest == ()
