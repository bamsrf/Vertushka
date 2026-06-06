"""
Redis-кэш для Вертушка API.

Graceful fallback: если Redis недоступен — приложение работает без кэша.
Singleton-паттерн: один connection pool на всё приложение.
"""
import hashlib
import logging
from typing import Any

import orjson
import redis.asyncio as redis

from app.config import get_settings

logger = logging.getLogger(__name__)

_KEY_PREFIX = "vertushka"

# TTL по типу данных (секунды)
TTL_RELEASE = 7 * 86400       # 7 дней — данные релиза стабильны
TTL_MASTER = 7 * 86400        # 7 дней
TTL_ARTIST = 3 * 86400        # 3 дня — могут появиться новые релизы
TTL_ARTIST_THUMB = 30 * 86400 # 30 дней — фото почти не меняется
TTL_ARTIST_MASTERS = 86400    # 1 день
TTL_SEARCH = 600              # 10 минут — выдача может обновляться
TTL_SUGGEST = 86400           # 24 часа — автодополнение по префиксу стабильно,
                              # горячие префиксы шарятся между юзерами
TTL_PRICE_STATS = 6 * 3600    # 6 часов — цены меняются
TTL_MASTER_VERSIONS = 3 * 86400  # 3 дня
TTL_MASTER_INFO = 7 * 86400   # 7 дней — обложки почти не меняются


class RedisCache:
    """Async Redis-кэш с graceful degradation."""

    def __init__(self) -> None:
        self._pool: redis.Redis | None = None
        self._available = False

    async def connect(self) -> None:
        """Подключение к Redis. Не крашит приложение при недоступности."""
        settings = get_settings()
        try:
            self._pool = redis.from_url(
                settings.redis_url,
                decode_responses=False,
                max_connections=20,
                socket_connect_timeout=5,
                socket_timeout=5,
                retry_on_timeout=True,
            )
            await self._pool.ping()
            self._available = True
            logger.info("Redis connected: %s", settings.redis_url)
        except Exception:
            logger.warning("Redis unavailable — working without cache")
            self._available = False

    async def close(self) -> None:
        """Закрытие соединения."""
        if self._pool:
            await self._pool.aclose()
            self._pool = None
            self._available = False

    @property
    def available(self) -> bool:
        return self._available

    def _key(self, namespace: str, key: str) -> str:
        return f"{_KEY_PREFIX}:{namespace}:{key}"

    async def get(self, namespace: str, key: str) -> Any | None:
        """Получить значение из кэша. Возвращает None при промахе или ошибке."""
        if not self._available:
            return None
        try:
            raw = await self._pool.get(self._key(namespace, key))
            if raw is None:
                return None
            return orjson.loads(raw)
        except Exception:
            logger.warning("Redis GET error: %s:%s", namespace, key, exc_info=True)
            return None

    async def set(self, namespace: str, key: str, value: Any, ttl: int) -> None:
        """Записать значение в кэш с TTL."""
        if not self._available:
            return
        try:
            raw = orjson.dumps(value)
            await self._pool.set(self._key(namespace, key), raw, ex=ttl)
        except Exception:
            logger.warning("Redis SET error: %s:%s", namespace, key, exc_info=True)

    async def delete(self, namespace: str, key: str) -> None:
        """Удалить ключ из кэша."""
        if not self._available:
            return
        try:
            await self._pool.delete(self._key(namespace, key))
        except Exception:
            logger.warning("Redis DELETE error: %s:%s", namespace, key, exc_info=True)

    async def exists(self, namespace: str, key: str) -> bool:
        """Проверить существование ключа."""
        if not self._available:
            return False
        try:
            return bool(await self._pool.exists(self._key(namespace, key)))
        except Exception:
            return False

    # Атомарный инкремент с установкой TTL только при создании ключа.
    # Обычный INCR+EXPIRE двумя командами продлевал бы окно на каждом
    # обращении — дневная квота никогда бы не сбрасывалась.
    _INCR_WITH_TTL_LUA = """
    local value = redis.call('INCR', KEYS[1])
    if value == 1 then
      redis.call('EXPIRE', KEYS[1], ARGV[1])
    end
    return value
    """

    async def incr(self, namespace: str, key: str, ttl: int) -> int | None:
        """Атомарно увеличить счётчик. None если Redis недоступен.

        TTL ставится только при создании ключа, поэтому окно фиксированное
        от первого события, а не скользящее.
        """
        if not self._available:
            return None
        try:
            value = await self._pool.eval(
                self._INCR_WITH_TTL_LUA, 1, self._key(namespace, key), int(ttl),
            )
            return int(value)
        except Exception:
            logger.warning("Redis INCR error: %s:%s", namespace, key, exc_info=True)
            return None

    async def get_counter(self, namespace: str, key: str) -> int | None:
        """Прочитать счётчик без изменения. None если недоступен или пуст."""
        if not self._available:
            return None
        try:
            raw = await self._pool.get(self._key(namespace, key))
            return int(raw) if raw is not None else 0
        except Exception:
            logger.warning("Redis counter GET error: %s:%s", namespace, key, exc_info=True)
            return None

    async def pfadd(self, namespace: str, key: str, *values: str, ttl: int) -> None:
        """Добавить значения в HyperLogLog (счётчик уникальных).

        Зачем HLL, а не SET: нам нужна ОЦЕНКА числа уникальных обложек за сутки,
        а не сам список. HLL держит любой объём в ~12 КБ с погрешностью ~0.8% —
        для планирования ёмкости этого с запасом, а SET на десятки тысяч id рос
        бы линейно и жил в памяти рядом с рабочими данными.

        TTL продлевается при каждой записи: ключ суточный, живёт с запасом.
        """
        if not self._available or not values:
            return
        try:
            k = self._key(namespace, key)
            pipe = self._pool.pipeline()
            pipe.pfadd(k, *values)
            pipe.expire(k, int(ttl))
            await pipe.execute()
        except Exception:
            logger.warning("Redis PFADD error: %s:%s", namespace, key, exc_info=True)

    async def pfcount(self, namespace: str, key: str) -> int:
        """Оценка числа уникальных значений в HyperLogLog. 0 если недоступен."""
        if not self._available:
            return 0
        try:
            return int(await self._pool.pfcount(self._key(namespace, key)))
        except Exception:
            logger.warning("Redis PFCOUNT error: %s:%s", namespace, key, exc_info=True)
            return 0

    async def set_nx(self, namespace: str, key: str, value: Any, ttl: int) -> bool:
        """SET if Not eXists с TTL. Возвращает True если ключ создан, False
        если уже существовал. Используется как single-flight lock.
        Если Redis недоступен — возвращает True (фоновые таски просто
        не имеют защиты от дублирования; это лучше, чем не работать).
        """
        if not self._available:
            return True
        try:
            raw = orjson.dumps(value)
            result = await self._pool.set(self._key(namespace, key), raw, ex=ttl, nx=True)
            return bool(result)
        except Exception:
            logger.warning("Redis SET NX error: %s:%s", namespace, key, exc_info=True)
            return True

    # Атомарное СКОЛЬЗЯЩЕЕ ОКНО (замена token bucket 2026-07-03): Discogs
    # считает лимит скользящим окном 60 req/min на токен, а token bucket в
    # worst case пропускал burst capacity + рефилл = до ~112 запросов в
    # 60с-окне → штормы 429 (и на app-, и на user-токенах при тяжёлых
    # фан-аутах). ZSET timestamp'ов гарантирует ≤ limit запросов в любом
    # 60с-окне. Burst до limit разом по-прежнему разрешён — это Discogs
    # переживает, важно только окно.
    # Возвращает 0 (запрос разрешён) или wait_ms до выхода старейшего
    # запроса из окна. Состояние шарится между всеми воркерами.
    _SLIDING_WINDOW_LUA = """
    local key = KEYS[1]
    local limit = tonumber(ARGV[1])
    local now_ms = tonumber(ARGV[2])
    local member = ARGV[3]
    local window_ms = 60000
    redis.call('ZREMRANGEBYSCORE', key, 0, now_ms - window_ms)
    local count = redis.call('ZCARD', key)
    if count < limit then
      redis.call('ZADD', key, now_ms, member)
      redis.call('PEXPIRE', key, window_ms + 5000)
      return 0
    end
    local oldest = redis.call('ZRANGE', key, 0, 0, 'WITHSCORES')
    return math.max(1, math.ceil(oldest[2] + window_ms - now_ms))
    """

    async def take_token(
        self, bucket_key: str, capacity: float, refill_rate_per_sec: float,
    ) -> int | None:
        """Взять слот в скользящем окне (limit = capacity за 60с).

        Возвращает 0 если запрос разрешён, wait_ms если окно заполнено,
        None если Redis недоступен (caller делает локальный fallback).
        refill_rate_per_sec больше не участвует (семантика окна), параметр
        сохранён для совместимости с локальным fallback в rate_limiter.
        """
        if not self._available:
            return None
        try:
            import time as _time
            import uuid as _uuid
            now_ms = int(_time.time() * 1000)
            wait_ms = await self._pool.eval(
                self._SLIDING_WINDOW_LUA,
                1,
                self._key("ratelimit", bucket_key),
                int(capacity),
                now_ms,
                f"{now_ms}-{_uuid.uuid4().hex[:8]}",
            )
            return int(wait_ms)
        except Exception:
            logger.warning("Redis take_token error: %s", bucket_key, exc_info=True)
            return None

    async def peek_tokens(
        self, bucket_key: str, capacity: float, refill_rate_per_sec: float,
    ) -> float | None:
        """Сколько свободных слотов в скользящем окне — БЕЗ изъятия.

        Для drip-воркера обложек: расходовать app-лимит только когда окно
        почти пустое (юзерский трафик не страдает). None = Redis недоступен —
        caller должен считать, что свободных слотов нет.
        """
        if not self._available:
            return None
        try:
            import time as _time
            now_ms = _time.time() * 1000
            used = await self._pool.zcount(
                self._key("ratelimit", bucket_key), now_ms - 60_000, "+inf",
            )
            return max(0.0, float(capacity) - float(used))
        except Exception:
            logger.warning("Redis peek_tokens error: %s", bucket_key, exc_info=True)
            return None
    async def list_rpush(self, namespace: str, key: str, value: Any, ttl: int) -> None:
        """Добавить элемент в конец Redis-списка (с обновлением TTL на ключ).

        Используется как лёгкая durable-очередь (push-receipts). При недоступном
        Redis — no-op (фича best-effort, не критична для основного потока)."""
        if not self._available:
            return
        try:
            full = self._key(namespace, key)
            await self._pool.rpush(full, orjson.dumps(value))
            await self._pool.expire(full, ttl)
        except Exception:
            logger.warning("Redis RPUSH error: %s:%s", namespace, key, exc_info=True)

    async def list_drain(self, namespace: str, key: str, count: int) -> list[Any]:
        """Атомарно изъять до `count` элементов из начала списка (LPOP count).

        Возвращает распакованные значения. Пустой список — если Redis недоступен
        или очередь пуста."""
        if not self._available:
            return []
        try:
            raw = await self._pool.lpop(self._key(namespace, key), count)
            if not raw:
                return []
            if isinstance(raw, (bytes, bytearray)):
                raw = [raw]
            return [orjson.loads(item) for item in raw]
        except Exception:
            logger.warning("Redis LPOP error: %s:%s", namespace, key, exc_info=True)
            return []

    async def health(self) -> dict:
        """Статус Redis для /health endpoint."""
        if not self._available:
            return {"status": "unavailable"}
        try:
            await self._pool.ping()
            info = await self._pool.info("memory")
            return {
                "status": "connected",
                "used_memory_mb": round(info.get("used_memory", 0) / 1024 / 1024, 1),
                "max_memory_mb": round(info.get("maxmemory", 0) / 1024 / 1024, 1),
            }
        except Exception:
            return {"status": "error"}


def search_cache_key(params: dict) -> str:
    """Генерация стабильного ключа кэша из параметров поиска."""
    sorted_items = sorted((k, str(v)) for k, v in params.items() if v is not None)
    raw = "&".join(f"{k}={v}" for k, v in sorted_items)
    return hashlib.md5(raw.encode()).hexdigest()


# Singleton — один экземпляр на приложение
cache = RedisCache()
