"""
Модель пользователя
"""
import uuid
from datetime import datetime
from sqlalchemy import String, DateTime, Boolean, Text, Integer
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID

from app.database import Base


class User(Base):
    """Модель пользователя"""
    
    __tablename__ = "users"
    
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4
    )
    
    # Основные данные
    email: Mapped[str] = mapped_column(
        String(255),
        unique=True,
        nullable=False,
        index=True
    )
    username: Mapped[str] = mapped_column(
        String(50),
        unique=True,
        nullable=False,
        index=True
    )
    password_hash: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True  # Может быть null для OAuth пользователей
    )
    
    # Профиль
    display_name: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True
    )
    avatar_url: Mapped[str | None] = mapped_column(
        Text,
        nullable=True
    )
    bio: Mapped[str | None] = mapped_column(
        Text,
        nullable=True
    )
    
    # OAuth данные
    apple_id: Mapped[str | None] = mapped_column(
        String(255),
        unique=True,
        nullable=True,
        index=True
    )
    google_id: Mapped[str | None] = mapped_column(
        String(255),
        unique=True,
        nullable=True,
        index=True
    )
    
    # Статус
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False
    )
    is_verified: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False
    )
    
    # Сброс пароля
    reset_code_hash: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True
    )
    reset_code_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True
    )
    reset_code_attempts: Mapped[int] = mapped_column(
        default=0,
        nullable=False,
        server_default="0"
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
    last_login_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True
    )
    
    # Отношения
    collections = relationship(
        "Collection",
        back_populates="user",
        cascade="all, delete-orphan"
    )
    wishlist = relationship(
        "Wishlist",
        back_populates="user",
        uselist=False,
        cascade="all, delete-orphan"
    )
    
    # Настройки публичного профиля
    profile_share = relationship(
        "ProfileShare",
        back_populates="user",
        uselist=False,
        cascade="all, delete-orphan"
    )

    # Подписки (кого пользователь фоловит)
    following = relationship(
        "Follow",
        foreign_keys="Follow.follower_id",
        back_populates="follower",
        cascade="all, delete-orphan"
    )
    
    # Подписчики (кто фоловит пользователя)
    followers = relationship(
        "Follow",
        foreign_keys="Follow.following_id",
        back_populates="following",
        cascade="all, delete-orphan"
    )
    
    def __repr__(self) -> str:
        return f"<User {self.username}>"

