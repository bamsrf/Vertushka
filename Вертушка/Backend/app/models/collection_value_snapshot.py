"""
Модель ежедневных снапшотов стоимости коллекции
"""
import uuid
from datetime import datetime, date
from decimal import Decimal

from sqlalchemy import Date, DateTime, ForeignKey, Integer, Numeric, UniqueConstraint, Index
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID

from app.database import Base


class CollectionValueSnapshot(Base):
    """Ежедневный снапшот стоимости коллекции пользователя."""

    __tablename__ = "collection_value_snapshots"
    __table_args__ = (
        UniqueConstraint("user_id", "snapshot_date", name="uq_value_snapshot_user_date"),
        Index("ix_value_snapshot_user_date", "user_id", "snapshot_date"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    snapshot_date: Mapped[date] = mapped_column(Date, nullable=False)
    total_value_rub: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False, default=0)
    items_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )

    def __repr__(self) -> str:
        return f"<CollectionValueSnapshot user={self.user_id} date={self.snapshot_date} value={self.total_value_rub}>"
