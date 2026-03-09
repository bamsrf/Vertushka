"""
Модель кэша поисковых запросов Discogs в PostgreSQL
"""
import uuid
from datetime import datetime, timedelta

from sqlalchemy import String, DateTime, Index
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID, JSONB

from app.database import Base


# TTL по умолчанию для разных типов запросов (в минутах)
SEARCH_CACHE_TTL = {
    "release": 10,
    "master": 10,
    "artist": 10,
    "barcode": 60,
    "releases": 10,
    "masters": 10,
    "artists": 10,
}


class SearchCache(Base):
    """Кэш поисковых запросов Discogs в PostgreSQL.
    Работает как второй уровень кэша после Redis — переживает рестарт Redis.
    """

    __tablename__ = "search_cache"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    query_hash: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
    )
    query_type: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
    )
    response_json: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        nullable=False,
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
    )

    __table_args__ = (
        Index("idx_search_cache_hash", "query_hash", "query_type"),
        Index("idx_search_cache_expires", "expires_at"),
    )

    @staticmethod
    def make_expires_at(query_type: str) -> datetime:
        ttl_minutes = SEARCH_CACHE_TTL.get(query_type, 10)
        return datetime.utcnow() + timedelta(minutes=ttl_minutes)
