"""
Модель бронирования подарка
"""
import uuid
from datetime import datetime
from enum import Enum
from sqlalchemy import String, DateTime, ForeignKey, Text, Enum as SQLEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID

from app.database import Base


class GiftStatus(str, Enum):
    """Статусы бронирования подарка"""
    PENDING = "pending"      # Ожидает подтверждения
    BOOKED = "booked"        # Забронировано
    COMPLETED = "completed"  # Подарок получен
    CANCELLED = "cancelled"  # Бронирование отменено


class GiftBooking(Base):
    """Модель бронирования подарка из вишлиста"""
    
    __tablename__ = "gift_bookings"
    
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4
    )
    
    # Связь с элементом вишлиста (nullable — при переносе в коллекцию отвязываем)
    wishlist_item_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("wishlist_items.id", ondelete="SET NULL"),
        nullable=True,
        unique=True,
        index=True
    )
    
    # Даритель (может быть зарегистрированным пользователем)
    booked_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True
    )
    
    # Данные дарителя (для незарегистрированных пользователей)
    gifter_name: Mapped[str] = mapped_column(
        String(100),
        nullable=False
    )
    gifter_email: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        index=True
    )
    gifter_phone: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True
    )
    
    # Сообщение от дарителя
    gifter_message: Mapped[str | None] = mapped_column(
        Text,
        nullable=True
    )
    
    # Статус бронирования
    status: Mapped[GiftStatus] = mapped_column(
        SQLEnum(GiftStatus),
        default=GiftStatus.BOOKED,
        nullable=False
    )
    
    # Секретный токен для управления бронированием (для дарителя)
    cancel_token: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        unique=True
    )
    
    # Временные метки
    booked_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        nullable=False
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True
    )
    cancelled_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True
    )

    # Срок бронирования
    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True
    )
    reminder_sent_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True
    )

    # Отношения
    wishlist_item = relationship("WishlistItem", back_populates="gift_booking")
    booked_by_user = relationship("User", foreign_keys=[booked_by_user_id])
    
    def __repr__(self) -> str:
        return f"<GiftBooking {self.id} - {self.status}>"

