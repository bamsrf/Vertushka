"""
Скользящее окно метрик запросов: доля ошибок и p99 задержки.

Зачем отдельно от аларма на 5xx. Тот висит на глобальном обработчике
исключений и ловит только необработанные падения. Мимо него проходит целый
класс аварий:

- **504 от таймаут-middleware.** Он возвращает JSONResponse напрямую, минуя
  обработчик исключений. Значит залипшая БД, зависший вызов к Discogs или
  лок-шторм дают волну таймаутов и при этом **полную тишину** в алармах —
  ровно та авария, которую труднее всего заметить.
- **Деградация без ошибок.** Ответы честные, но p99 уполз с 300мс до 8с.
  Формально всё работает, фактически приложение непригодно.
- **Шторм 429.** Кто-то долбит API, лимитер держит — но знать об этом надо.

Окно живёт в памяти процесса. В проде один воркер (см. docker-compose.prod:
`--workers 1` из-за резидентной CLIP-модели), поэтому окно видит весь трафик.
Появятся воркеры — метрики станут пер-процессные, и пороги надо будет делить.

См. docs/plans/appstore/APPSTORE_LAUNCH_PLAN.md §4.2.
"""
from __future__ import annotations

import logging
import time
from collections import deque
from dataclasses import dataclass

from app.config import get_settings
from app.services import alerts

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class WindowSnapshot:
    total: int
    server_errors: int
    rate_limited: int
    p99_ms: float

    @property
    def error_rate(self) -> float:
        return self.server_errors / self.total if self.total else 0.0


class RequestMetrics:
    """Кольцо последних запросов за окно."""

    def __init__(self, window_seconds: int):
        self.window_seconds = window_seconds
        # (момент, код ответа, длительность мс)
        self._events: deque[tuple[float, int, float]] = deque()

    def record(self, status_code: int, duration_ms: float) -> None:
        now = time.monotonic()
        self._events.append((now, status_code, duration_ms))
        self._prune(now)

    def _prune(self, now: float) -> None:
        cutoff = now - self.window_seconds
        while self._events and self._events[0][0] < cutoff:
            self._events.popleft()

    def snapshot(self) -> WindowSnapshot:
        self._prune(time.monotonic())
        if not self._events:
            return WindowSnapshot(total=0, server_errors=0, rate_limited=0, p99_ms=0.0)

        durations = sorted(event[2] for event in self._events)
        # Индекс p99 по «ближайшему рангу»: на маленьких выборках это честнее
        # линейной интерполяции и не выдумывает значений между замерами.
        index = max(0, min(len(durations) - 1, int(len(durations) * 0.99) - 1))

        return WindowSnapshot(
            total=len(self._events),
            server_errors=sum(1 for e in self._events if e[1] >= 500),
            rate_limited=sum(1 for e in self._events if e[1] == 429),
            p99_ms=durations[index],
        )


_metrics: RequestMetrics | None = None


def get_metrics() -> RequestMetrics:
    global _metrics
    if _metrics is None:
        _metrics = RequestMetrics(get_settings().health_window_seconds)
    return _metrics


def observe(status_code: int, duration_ms: float) -> None:
    """Записать запрос и, если пороги пробиты, поднять аларм."""
    metrics = get_metrics()
    metrics.record(status_code, duration_ms)
    _check_thresholds(metrics.snapshot())


def _check_thresholds(snapshot: WindowSnapshot) -> None:
    settings = get_settings()

    # Пока запросов мало, доля ошибок — шум: две пятисотки на трёх запросах
    # дадут 67% и разбудят среди ночи на пустом месте.
    if snapshot.total < settings.health_min_requests:
        return

    window_min = settings.health_window_seconds // 60 or 1

    if snapshot.error_rate >= settings.health_error_rate_threshold:
        alerts.fire_and_forget(
            key="error_rate",
            title=f"Доля 5xx — {snapshot.error_rate:.0%}",
            body=(
                f"{snapshot.server_errors} ошибок на {snapshot.total} запросов "
                f"за последние {window_min} мин.\n"
                f"Сюда же попадают 504 от таймаутов — их не видно в обычных "
                f"алармах на исключения."
            ),
        )

    if snapshot.p99_ms >= settings.health_p99_threshold_ms:
        alerts.fire_and_forget(
            key="p99_latency",
            title=f"p99 задержки — {snapshot.p99_ms / 1000:.1f}с",
            body=(
                f"Порог {settings.health_p99_threshold_ms / 1000:.1f}с, выборка "
                f"{snapshot.total} запросов за {window_min} мин.\n"
                f"Ошибок при этом может не быть — приложение просто «думает»."
            ),
        )

    if snapshot.rate_limited >= settings.health_rate_limited_threshold:
        alerts.fire_and_forget(
            key="rate_limit_storm",
            title=f"Шторм 429 — {snapshot.rate_limited} за {window_min} мин",
            body="Лимитер держит нагрузку, но стоит посмотреть, кто долбится.",
        )
