"""
Модель настроек публичного профиля
"""
import uuid
from datetime import datetime
from sqlalchemy import String, DateTime, Boolean, Integer, Text, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID, ARRAY

from app.database import Base


class ProfileShare(Base):
    """Настройки публичного профиля пользователя"""

    __tablename__ = "profile_shares"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
        index=True
    )

    # Публичность
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False
    )
    is_private_profile: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False
    )
    show_collection: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False
    )
    show_wishlist: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False
    )

    # Персонализация
    custom_title: Mapped[str | None] = mapped_column(
        String(200),
        nullable=True
    )
    highlight_record_ids: Mapped[list | None] = mapped_column(
        ARRAY(UUID(as_uuid=True)),
        nullable=True
    )

    # Настройки отображения карточек пластинок
    show_record_year: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False
    )
    show_record_label: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False
    )
    show_record_format: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False
    )
    show_record_prices: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False
    )

    # Настройки статистики профиля
    show_collection_value: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False
    )

    # OG Meta
    og_image_url: Mapped[str | None] = mapped_column(
        Text,
        nullable=True
    )

    # Статистика
    view_count: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False
    )

    # Временные метки
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False
    )

    # Отношения
    user = relationship("User", back_populates="profile_share")

    def __repr__(self) -> str:
        return f"<ProfileShare user_id={self.user_id} active={self.is_active}>"
