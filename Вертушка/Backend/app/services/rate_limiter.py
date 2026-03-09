"""
Token Bucket Rate Limiter с приоритетной очередью для Discogs API.

Гарантирует, что мы никогда не превысим лимит Discogs (60 req/min).
Высокоприоритетные запросы (поиск) обслуживаются раньше низкоприоритетных (обогащение данных).
"""
import asyncio
import logging
import time

logger = logging.getLogger(__name__)


class Priority:
    """Приоритеты запросов к Discogs API (меньше = выше приоритет)."""
    SEARCH = 1           # Юзер ждёт результата поиска прямо сейчас
    DETAIL = 2           # Юзер открыл экран детали
    SCAN = 3             # Сканирование баркода/обложки
    ENRICHMENT = 4       # Фоновое обогащение (artist_thumb, prices)
    BATCH = 5            # Массовые операции (recalculate-prices, load_all)


class TokenBucketRateLimiter:
    """Token bucket с приоритетной очередью.

    - capacity: максимум токенов в bucket (= burst)
    - refill_rate: токенов в секунду (60 req/min = 1 token/sec)
    - Запросы ждут в PriorityQueue, обслуживаются по приоритету
    """

    def __init__(
        self,
        capacity: int = 55,
        refill_rate: float = 0.95,
    ):
        self._capacity = capacity
        self._refill_rate = refill_rate
        self._tokens = float(capacity)
        self._last_refill = time.monotonic()
        self._lock = asyncio.Lock()
        self._queue: asyncio.PriorityQueue[tuple[int, float, asyncio.Event]] = asyncio.PriorityQueue()
        self._processor_task: asyncio.Task | None = None
        # Метрики
        self._total_requests = 0
        self._total_wait_time = 0.0

    def start(self) -> None:
        """Запуск фонового процессора очереди."""
        if self._processor_task is None or self._processor_task.done():
            self._processor_task = asyncio.create_task(self._process_queue())

    def stop(self) -> None:
        """Остановка процессора."""
        if self._processor_task and not self._processor_task.done():
            self._processor_task.cancel()

    def _refill(self) -> None:
        """Пополнение токенов пропорционально прошедшему времени."""
        now = time.monotonic()
        elapsed = now - self._last_refill
        self._tokens = min(self._capacity, self._tokens + elapsed * self._refill_rate)
        self._last_refill = now

    async def acquire(self, priority: int = Priority.DETAIL, timeout: float = 30.0) -> None:
        """Запросить токен с приоритетом. Блокируется до получения или таймаута.

        Args:
            priority: приоритет запроса (Priority.SEARCH, Priority.DETAIL и т.д.)
            timeout: максимальное время ожидания в секундах

        Raises:
            asyncio.TimeoutError: если токен не получен за timeout
        """
        event = asyncio.Event()
        await self._queue.put((priority, time.monotonic(), event))
        try:
            await asyncio.wait_for(event.wait(), timeout=timeout)
        except asyncio.TimeoutError:
            logger.warning(
                "Rate limiter timeout (priority=%d, timeout=%.1fs, queue_size=%d)",
                priority, timeout, self._queue.qsize(),
            )
            raise

    async def _process_queue(self) -> None:
        """Фоновый цикл: выдаёт токены из bucket по приоритету."""
        try:
            while True:
                priority, enqueue_time, event = await self._queue.get()

                async with self._lock:
                    self._refill()
                    while self._tokens < 1.0:
                        wait_time = (1.0 - self._tokens) / self._refill_rate
                        await asyncio.sleep(wait_time)
                        self._refill()
                    self._tokens -= 1.0

                wait_duration = time.monotonic() - enqueue_time
                self._total_requests += 1
                self._total_wait_time += wait_duration

                event.set()
                self._queue.task_done()
        except asyncio.CancelledError:
            pass

    def stats(self) -> dict:
        """Метрики для мониторинга."""
        avg_wait = (self._total_wait_time / self._total_requests) if self._total_requests else 0
        return {
            "queue_size": self._queue.qsize(),
            "tokens_available": round(self._tokens, 1),
            "total_requests": self._total_requests,
            "avg_wait_seconds": round(avg_wait, 3),
        }


# Singleton — один лимитер на приложение
discogs_limiter = TokenBucketRateLimiter()
