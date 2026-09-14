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


# Сколько худших запросов показать в теле аларма. Три — чтобы было видно,
# один это выброс или у эндпоинта системная беда, и при этом сообщение
# осталось читаемым с экрана блокировки.
SLOWEST_IN_ALERT = 3

# Классы запросов: у каждого свой порог задержки.
#
# Один порог на всё сразу и шумел, и слепнул. Обычная ручка отвечает за 0.25с
# — она могла деградировать в двадцать раз и остаться ниже общего порога 5с,
# то есть настоящая авария (залипшая БД, лок-шторм, выеденный пул) проходила
# молча. А /covers/ штатно ходит за обложкой во внешние источники по 3–7с и
# поднимал аларм на совершенно нормальной работе.
#
# Классы определяются по шаблону маршрута, который пишет middleware.
CLASS_COVERS = "covers"
CLASS_SCAN = "scan"
CLASS_DEFAULT = "default"

# Человеческие названия для тела аларма.
CLASS_TITLES = {
    CLASS_COVERS: "обложки",
    CLASS_SCAN: "скан обложки",
    CLASS_DEFAULT: "обычные ручки",
}


def classify(endpoint: str) -> str:
    """Класс запроса по шаблону маршрута («POST /api/records/scan/cover/»)."""
    if "/scan/cover" in endpoint:
        return CLASS_SCAN
    if "/covers/" in endpoint or endpoint.endswith("/covers"):
        return CLASS_COVERS
    return CLASS_DEFAULT


@dataclass(frozen=True)
class ClassLatency:
    """Задержки одного класса запросов внутри окна."""

    name: str
    total: int
    p99_ms: float
    slowest: tuple[tuple[str, float], ...] = ()

    @property
    def title(self) -> str:
        return CLASS_TITLES.get(self.name, self.name)


@dataclass(frozen=True)
class WindowSnapshot:
    total: int
    server_errors: int
    rate_limited: int
    p99_ms: float
    # (эндпоинт, мс) — худшие в окне, по убыванию. Пусто, если окно пустое.
    slowest: tuple[tuple[str, float], ...] = ()

    @property
    def error_rate(self) -> float:
        return self.server_errors / self.total if self.total else 0.0


class RequestMetrics:
    """Кольцо последних запросов за окно."""

    def __init__(self, window_seconds: int):
        self.window_seconds = window_seconds
        # (момент, код ответа, длительность мс, эндпоинт)
        self._events: deque[tuple[float, int, float, str]] = deque()

    def record(
        self, status_code: int, duration_ms: float, endpoint: str = ""
    ) -> None:
        now = time.monotonic()
        self._events.append((now, status_code, duration_ms, endpoint))
        self._prune(now)

    def _prune(self, now: float) -> None:
        cutoff = now - self.window_seconds
        while self._events and self._events[0][0] < cutoff:
            self._events.popleft()

    def snapshot(self) -> WindowSnapshot:
        self._prune(time.monotonic())
        if not self._events:
            return WindowSnapshot(total=0, server_errors=0, rate_limited=0, p99_ms=0.0)

        p99, slowest = _percentile_and_worst(self._events)
        return WindowSnapshot(
            total=len(self._events),
            server_errors=sum(1 for e in self._events if e[1] >= 500),
            rate_limited=sum(1 for e in self._events if e[1] == 429),
            p99_ms=p99,
            slowest=slowest,
        )

    def latency_by_class(self) -> dict[str, ClassLatency]:
        """Задержки в разрезе классов запросов.

        Доля ошибок и шторм 429 остаются общими по окну: пятисотки — авария
        независимо от того, какая ручка их отдаёт. А вот «медленно» у каждого
        класса своё, поэтому здесь разрез обязателен.
        """
        self._prune(time.monotonic())
        buckets: dict[str, list] = {}
        for event in self._events:
            buckets.setdefault(classify(event[3]), []).append(event)

        result: dict[str, ClassLatency] = {}
        for name, events in buckets.items():
            p99, slowest = _percentile_and_worst(events)
            result[name] = ClassLatency(
                name=name, total=len(events), p99_ms=p99, slowest=slowest
            )
        return result


def _percentile_and_worst(events) -> tuple[float, tuple[tuple[str, float], ...]]:
    """p99 и топ худших для набора событий окна.

    Индекс p99 по «ближайшему рангу»: на маленьких выборках это честнее
    линейной интерполяции и не выдумывает значений между замерами. NB: пока
    в наборе меньше ~100 запросов, это по факту «второй с конца» — на редком
    классе порог стоит держать выше, чем кажется по медиане.
    """
    if not events:
        return 0.0, ()

    durations = sorted(e[2] for e in events)
    index = max(0, min(len(durations) - 1, int(len(durations) * 0.99) - 1))

    # Сортируем по одной длительности: адреса в ключ не берём, иначе при
    # равных миллисекундах порядок начнёт зависеть от алфавита.
    top = sorted(events, key=lambda e: e[2], reverse=True)
    slowest = tuple((e[3] or "—", e[2]) for e in top[:SLOWEST_IN_ALERT])
    return durations[index], slowest


_metrics: RequestMetrics | None = None


def get_metrics() -> RequestMetrics:
    global _metrics
    if _metrics is None:
        _metrics = RequestMetrics(get_settings().health_window_seconds)
    return _metrics


def observe(status_code: int, duration_ms: float, endpoint: str = "") -> None:
    """Записать запрос и, если пороги пробиты, поднять аларм.

    endpoint — «METHOD /шаблон/пути». Именно шаблон, а не подставленный URL:
    иначе `/api/records/{id}` размажется по тысяче адресов и в аларме окажется
    случайная пластинка вместо ручки, которая тормозит.
    """
    metrics = get_metrics()
    metrics.record(status_code, duration_ms, endpoint)
    _check_thresholds(metrics)


def _format_slowest(snapshot: WindowSnapshot | ClassLatency) -> str:
    """Список худших запросов для тела аларма.

    Без этого аларм сообщал цифру и молчал о том, где она получена, — каждое
    сообщение превращалось в расследование с нуля. Длительность запроса больше
    нигде не фиксируется: nginx пишет combined-формат без $request_time,
    трассировка в Sentry не включена.
    """
    if not snapshot.slowest:
        return "  (нет данных)"
    return "\n".join(
        f"  • {endpoint} — {ms / 1000:.1f}с" for endpoint, ms in snapshot.slowest
    )


def _class_limits(name: str) -> tuple[float, int]:
    """(порог мс, минимум запросов) для класса."""
    settings = get_settings()
    if name == CLASS_COVERS:
        return settings.health_p99_covers_ms, settings.health_min_requests
    if name == CLASS_SCAN:
        return settings.health_p99_scan_ms, settings.health_min_requests_scan
    return settings.health_p99_threshold_ms, settings.health_min_requests


def _check_latency(by_class: dict[str, ClassLatency], window_min: int) -> None:
    """Аларм на задержки — отдельно по каждому классу.

    Ключ троттлинга тоже свой на класс: иначе разговорчивые обложки глушили бы
    сообщение про обычные ручки, а именно оно означает настоящую аварию.
    """
    for name, latency in sorted(by_class.items()):
        threshold_ms, min_requests = _class_limits(name)
        if latency.total < min_requests or latency.p99_ms < threshold_ms:
            continue

        alerts.fire_and_forget(
            key=f"p99_latency:{name}",
            title=f"p99 задержки ({latency.title}) — {latency.p99_ms / 1000:.1f}с",
            body=(
                f"Порог {threshold_ms / 1000:.1f}с, выборка {latency.total} "
                f"запросов этого класса за {window_min} мин.\n"
                f"Ошибок при этом может не быть — приложение просто «думает».\n\n"
                f"Самые медленные в окне:\n{_format_slowest(latency)}"
            ),
        )


def _check_thresholds(metrics: RequestMetrics) -> None:
    settings = get_settings()
    snapshot = metrics.snapshot()
    window_min = settings.health_window_seconds // 60 or 1

    # Задержки — раньше общего минимума: у каждого класса свой порог входа.
    # Скан обложки живёт десятками в сутки и общие 20 запросов в пятиминутном
    # окне не набирает никогда — под общим гейтом аларм по нему не сработал бы.
    _check_latency(metrics.latency_by_class(), window_min)

    # Дальше — про долю ошибок и шторм 429: они считаются по всему окну, и
    # пока запросов мало, доля — шум. Две пятисотки на трёх запросах дадут
    # 67% и разбудят среди ночи на пустом месте.
    if snapshot.total < settings.health_min_requests:
        return

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

    if snapshot.rate_limited >= settings.health_rate_limited_threshold:
        alerts.fire_and_forget(
            key="rate_limit_storm",
            title=f"Шторм 429 — {snapshot.rate_limited} за {window_min} мин",
            body="Лимитер держит нагрузку, но стоит посмотреть, кто долбится.",
        )
