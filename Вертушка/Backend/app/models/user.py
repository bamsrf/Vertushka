"""
Модель пользователя
"""
import uuid
from datetime import datetime, time
from sqlalchemy import String, DateTime, Boolean, Text, Integer, Time
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
    # nullable: Discogs-логин создаёт аккаунт без email (см. миграцию
    # 20260602_discogs_login). NULL не конфликтует в UNIQUE-индексе Postgres.
    email: Mapped[str | None] = mapped_column(
        String(255),
        unique=True,
        nullable=True,
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

    # Discogs OAuth 1.0a — per-user токен. oauth_token_secret шифруется (Fernet) до записи.
    discogs_username: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True
    )
    discogs_oauth_token: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True
    )
    discogs_oauth_token_secret: Mapped[str | None] = mapped_column(
        Text,
        nullable=True
    )
    discogs_connected_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True
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

    # Нотификации
    push_token: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True
    )
    notify_new_follower: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
        server_default="true"
    )
    notify_gift_booked: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
        server_default="true"
    )
    notify_app_updates: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
        server_default="true"
    )
    notify_messages: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
        server_default="true"
    )
    notify_follow_request: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
        server_default="true"
    )
    notify_wishlist_in_stock: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
        server_default="true"
    )
    notify_achievement: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
        server_default="true"
    )
    notify_gift_confirmed: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
        server_default="true"
    )
    notify_milestone: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
        server_default="true"
    )

    # Quiet hours / Do Not Disturb
    quiet_hours_enabled: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
        server_default="false"
    )
    # Хранится в UTC (Time без таймзоны); фронт показывает в локальном времени.
    quiet_hours_start: Mapped["time | None"] = mapped_column(  # type: ignore[name-defined]
        Time,
        nullable=True
    )
    quiet_hours_end: Mapped["time | None"] = mapped_column(  # type: ignore[name-defined]
        Time,
        nullable=True
    )

    # Soft delete
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True
    )
    scheduled_purge_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True
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
    last_seen_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True,
        index=True,
    )
    signup_source: Mapped[str | None] = mapped_column(
        String(20),
        nullable=True,
        index=True,
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

    # Ачивки
    achievements = relationship(
        "UserAchievement",
        back_populates="user",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<User {self.username}>"

