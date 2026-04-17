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
