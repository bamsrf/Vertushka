"""
История цен листингов — снапшот при каждой смене price/status (Волна B).

Пишется из runner._upsert_listing ТОЛЬКО когда price или status изменились
относительно прошлого прогона. Соседние строки одного listing_id = точки
изменения → price_drop producer берёт падение через LAG(price) по captured_at.
"""
import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import String, DateTime, ForeignKey, Numeric, Index
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID

from app.database import Base


class ListingPriceHistory(Base):
    """Снапшот цены/статуса одного листинга в момент изменения."""

    __tablename__ = "listing_price_history"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )

    listing_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("store_listings.id", ondelete="CASCADE"),
        nullable=False,
    )

    # Денорм: producer/график не джойнят store_listings. SET NULL переживает
    # отвязку записи.
    record_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("records.id", ondelete="SET NULL"),
        nullable=True,
    )

    price_rub: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False)

    captured_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )

    __table_args__ = (
        Index("ix_price_history_record_time", "record_id", "captured_at"),
        Index("ix_price_history_listing_time", "listing_id", "captured_at"),
        Index("ix_price_history_captured", "captured_at"),
    )

    def __repr__(self) -> str:
        return f"<ListingPriceHistory {self.listing_id} {self.price_rub} @ {self.captured_at}>"
