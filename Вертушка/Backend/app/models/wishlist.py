"""
Модели вишлиста (списка желаемых пластинок)
"""
import uuid
import secrets
from datetime import datetime
from decimal import Decimal
from sqlalchemy import String, DateTime, ForeignKey, Text, Integer, Boolean, Table, Column, Numeric
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID

from app.database import Base


# Ассоциативная таблица: пластинки в вишлисте ↔ папки (M2M, тегирование)
wishlist_folder_items = Table(
    "wishlist_folder_items",
    Base.metadata,
    Column(
        "wishlist_folder_id",
        UUID(as_uuid=True),
        ForeignKey("wishlist_folders.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column(
        "wishlist_item_id",
        UUID(as_uuid=True),
        ForeignKey("wishlist_items.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column("added_at", DateTime, default=datetime.utcnow, nullable=False),
)


def generate_share_token() -> str:
    """Генерация уникального токена для публичной ссылки"""
    return secrets.token_urlsafe(16)


class Wishlist(Base):
    """Модель вишлиста пользователя"""
    
    __tablename__ = "wishlists"
    
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4
    )
    
    # Владелец вишлиста
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,  # У пользователя один вишлист
        index=True
    )
    
    # Публичный доступ
    share_token: Mapped[str] = mapped_column(
        String(50),
        unique=True,
        nullable=False,
        default=generate_share_token,
        index=True
    )
    is_public: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False
    )
    
    # Настройки отображения
    # show_gifter_names: видно ли имя дарителя ПУБЛИКЕ (гостям на share-link)
    show_gifter_names: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False
    )
    # reveal_gifter_to_owner: хочет ли владелец знать имя дарителя сразу при бронировании.
    # Дефолт False — анонимность для владельца сохраняется как было.
    reveal_gifter_to_owner: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
        server_default="false",
    )
    custom_message: Mapped[str | None] = mapped_column(
        Text,
        nullable=True  # Сообщение для дарителей
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
    user = relationship("User", back_populates="wishlist")
    items = relationship(
        "WishlistItem",
        back_populates="wishlist",
        cascade="all, delete-orphan",
        order_by="WishlistItem.priority.desc(), WishlistItem.added_at.desc()"
    )
    folders = relationship(
        "WishlistFolder",
        back_populates="wishlist",
        cascade="all, delete-orphan",
        order_by="WishlistFolder.sort_order, WishlistFolder.created_at",
    )

    def regenerate_share_token(self) -> str:
        """Перегенерация токена публичной ссылки"""
        self.share_token = generate_share_token()
        return self.share_token
    
    def __repr__(self) -> str:
        return f"<Wishlist {self.id}>"


class WishlistItem(Base):
    """Элемент вишлиста"""
    
    __tablename__ = "wishlist_items"
    
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4
    )
    
    # Связи
    wishlist_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("wishlists.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    record_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("records.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    
    # Приоритет (для сортировки)
    priority: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False
    )
    
    # Заметки от пользователя
    notes: Mapped[str | None] = mapped_column(
        Text,
        nullable=True
    )
    
    # Статус
    is_purchased: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False
    )

    # Колокольчик: 'watched' (дефолт, тихо + недельный digest) |
    # 'subscribed' (мгновенный push при in_stock / price_drop / аналоге).
    notify_mode: Mapped[str] = mapped_column(
        String(16),
        default="watched",
        server_default="watched",
        nullable=False,
    )

    # Порог цены для push. None = уведомлять при любом появлении/падении.
    price_threshold_rub: Mapped[Decimal | None] = mapped_column(
        Numeric(12, 2),
        nullable=True,
    )
    
    # Временные метки
    added_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        nullable=False
    )
    purchased_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True
    )
    
    # Отношения
    wishlist = relationship("Wishlist", back_populates="items")
    record = relationship("Record", back_populates="wishlist_items")
    gift_booking = relationship(
        "GiftBooking",
        back_populates="wishlist_item",
        uselist=False,
        cascade="all, delete-orphan"
    )
    folders = relationship(
        "WishlistFolder",
        secondary=wishlist_folder_items,
        back_populates="items",
    )

    def __repr__(self) -> str:
        return f"<WishlistItem {self.id}>"


class WishlistFolder(Base):
    """Папка-тег в вишлисте (M2M c WishlistItem)"""

    __tablename__ = "wishlist_folders"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    wishlist_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("wishlists.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    sort_order: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
        server_default="0",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )

    wishlist = relationship("Wishlist", back_populates="folders")
    items = relationship(
        "WishlistItem",
        secondary=wishlist_folder_items,
        back_populates="folders",
        order_by="WishlistItem.priority.desc(), WishlistItem.added_at.desc()",
    )

    def __repr__(self) -> str:
        return f"<WishlistFolder {self.name}>"

