"""
RadarStatusEvent — хронология смен статуса пластинки на радаре.

Пишется продюсерами уведомлений при появлении/подешевении/альтернативе для
подписанного (notify_mode='subscribed') айтема. Питает «Историю» в шторке цены.
Статусы: 'available' (появилась), 'match' (подошла под порог), 'alt' (аналог),
'price_drop' (подешевела), 'absent' (пропала).
"""
import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import String, DateTime, ForeignKey, Numeric, Index
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID

from app.database import Base


class RadarStatusEvent(Base):
    __tablename__ = "radar_status_events"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    wishlist_item_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("wishlist_items.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    record_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("records.id", ondelete="CASCADE"),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    price_rub: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    store_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        Index("ix_radar_events_item_ts", "wishlist_item_id", "created_at"),
    )

    def __repr__(self) -> str:
        return f"<RadarStatusEvent {self.wishlist_item_id} {self.status}>"
