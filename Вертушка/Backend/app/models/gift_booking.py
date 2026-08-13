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
    
    # Получатель подарка (владелец вишлиста). Денормализовано, т.к. при
    # завершении брони wishlist_item_id обнуляется и связь теряется. Нужно
    # для серии «Дарящая рука»: распределение по разным получателям, Бумеранг,
    # Любимчик. Заполняется на /book и в complete_gift_booking.
    recipient_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True
    )

    # Какую пластинку дарят. Денормализовано по той же причине, что и
    # recipient_user_id: при завершении брони wishlist_item_id обнуляется, и
    # достать релиз через пункт вишлиста уже нельзя. Без этой колонки раздел
    # «Я дарю» не мог показать вручённые подарки — ему нечего было отрисовать.
    record_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("records.id", ondelete="SET NULL"),
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

    # Токен подтверждения email (используется при флаге verification, иначе NULL)
    verify_token: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
        unique=True,
        index=True,
    )

    # Анти-фрод метки (заполняются на /book)
    gifter_ip: Mapped[str | None] = mapped_column(
        String(45),  # IPv6 max length
        nullable=True,
        index=True,
    )
    gifter_user_agent_hash: Mapped[str | None] = mapped_column(
        String(64),  # sha256 hex
        nullable=True,
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
    cancellation_reason: Mapped[str | None] = mapped_column(
        String(50),
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

    # Получатель добавил в коллекцию похожую пластинку, мы спросили «это подарок?»
    # и он ответил «нет». Больше не спрашиваем по этой броне — иначе поп-ап
    # всплывал бы при каждом следующем сканировании того же альбома.
    match_dismissed_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True
    )

    # Отношения
    wishlist_item = relationship("WishlistItem", back_populates="gift_booking")
    record = relationship("Record")
    booked_by_user = relationship("User", foreign_keys=[booked_by_user_id])
    recipient_user = relationship("User", foreign_keys=[recipient_user_id])
    
    def __repr__(self) -> str:
        return f"<GiftBooking {self.id} - {self.status}>"

