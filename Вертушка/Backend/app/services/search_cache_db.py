"""
Сервис для работы с search_cache в PostgreSQL.
Второй уровень кэша после Redis — переживает рестарт Redis и шарится между воркерами.
"""
import hashlib
import logging
from datetime import datetime

import orjson
from sqlalchemy import select, delete

from app.database import async_session_maker
from app.models.search_cache import SearchCache

logger = logging.getLogger(__name__)


def make_query_hash(params: dict) -> str:
    """MD5-хеш от отсортированных параметров запроса."""
    sorted_str = str(sorted(params.items()))
    return hashlib.md5(sorted_str.encode()).hexdigest()


async def get_from_search_cache(query_type: str, params: dict) -> dict | None:
    """Получить результат из PostgreSQL search_cache. Возвращает None при промахе."""
    query_hash = make_query_hash(params)
    try:
        async with async_session_maker() as session:
            result = await session.execute(
                select(SearchCache).where(
                    SearchCache.query_hash == query_hash,
                    SearchCache.query_type == query_type,
                    SearchCache.expires_at > datetime.utcnow(),
                )
            )
            entry = result.scalar_one_or_none()
            if entry:
                return entry.response_json
    except Exception:
        logger.exception("search_cache DB read error")
    return None


async def save_to_search_cache(query_type: str, params: dict, response_data: dict) -> None:
    """Сохранить результат поиска в PostgreSQL search_cache."""
    query_hash = make_query_hash(params)
    try:
        async with async_session_maker() as session:
            entry = SearchCache(
                query_hash=query_hash,
                query_type=query_type,
                response_json=response_data,
                expires_at=SearchCache.make_expires_at(query_type),
            )
            session.add(entry)
            await session.commit()
    except Exception:
        logger.exception("search_cache DB write error")


async def cleanup_expired_search_cache() -> int:
    """Удалить просроченные записи из search_cache. Возвращает количество удалённых."""
    try:
        async with async_session_maker() as session:
            result = await session.execute(
                delete(SearchCache).where(SearchCache.expires_at < datetime.utcnow())
            )
            await session.commit()
            deleted = result.rowcount
            if deleted:
                logger.info("Cleaned up %d expired search_cache entries", deleted)
            return deleted
    except Exception:
        logger.exception("search_cache cleanup error")
        return 0
