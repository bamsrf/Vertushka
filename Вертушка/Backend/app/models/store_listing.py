"""
Листинг товара в магазине-партнёре.
"""
import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import String, DateTime, Text, Numeric, ForeignKey, UniqueConstraint, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID, JSONB

from app.database import Base


class ListingStatus:
    IN_STOCK = "in_stock"
    OUT_OF_STOCK = "out_of_stock"
    PREORDER = "preorder"
    ON_REQUEST = "on_request"
    REMOVED = "removed"


class MatchMethod:
    DISCOGS_URL = "discogs_url"
    BARCODE = "barcode"
    CATALOG = "catalog"
    FUZZY = "fuzzy"
    DISCOGS_FETCH = "discogs_fetch"
    MANUAL = "manual"
    STORE_NATIVE = "store_native"  # Record создан из данных самого листинга (нет на Discogs)
    YANDEX_NATIVE = "yandex_native"  # Record обогащён Yandex Music (нет на Discogs, шаг 5.5)
    MERGED_FROM_STORE_NATIVE = "merged_from_store_native"  # перепривязан safe_merge_store_native_into
    DUMP_INDEX = "dump_index"  # найден в discogs_releases_index (slim local dump)


class StoreListing(Base):
    """Карточка товара у магазина — может быть привязана к Record после матчинга."""

    __tablename__ = "store_listings"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    store_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("stores.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    external_id: Mapped[str] = mapped_column(String(255), nullable=False)
    url: Mapped[str] = mapped_column(Text, nullable=False)

    title_raw: Mapped[str] = mapped_column(Text, nullable=False)
    artist_raw: Mapped[str | None] = mapped_column(Text, nullable=True)
    year_raw: Mapped[int | None] = mapped_column(nullable=True)
    format_raw: Mapped[str | None] = mapped_column(String(255), nullable=True)
    vinyl_color_raw: Mapped[str | None] = mapped_column(String(255), nullable=True)
    condition: Mapped[str | None] = mapped_column(String(64), nullable=True)

    price_rub: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    price_currency: Mapped[str] = mapped_column(String(3), nullable=False, server_default="RUB")

    status: Mapped[str] = mapped_column(String(32), nullable=False, server_default=ListingStatus.IN_STOCK)

    first_seen_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)

    raw_payload: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    matched_record_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("records.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    match_confidence: Mapped[Decimal | None] = mapped_column(Numeric(4, 3), nullable=True)
    match_method: Mapped[str | None] = mapped_column(String(32), nullable=True)
    matched_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )

    store = relationship("Store", back_populates="listings")
    record = relationship("Record")

    __table_args__ = (
        UniqueConstraint("store_id", "external_id", name="uq_listing_store_external"),
        Index("ix_listing_match_active", "matched_record_id", "status", "last_seen_at"),
        Index("ix_listing_unmatched_review", "store_id", "matched_record_id", "first_seen_at"),
    )

    def __repr__(self) -> str:
        return f"<StoreListing {self.store_id}/{self.external_id}>"
