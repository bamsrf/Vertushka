"""
Модели коллекции виниловых пластинок
"""
import uuid
from datetime import datetime
from sqlalchemy import String, DateTime, ForeignKey, Text, Integer, Numeric
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID

from app.database import Base


class Collection(Base):
    """Модель коллекции пользователя"""
    
    __tablename__ = "collections"
    
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4
    )
    
    # Владелец коллекции
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    
    # Информация о коллекции
    name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        default="Моя коллекция"
    )
    description: Mapped[str | None] = mapped_column(
        Text,
        nullable=True
    )
    
    # Порядок сортировки (для нескольких коллекций)
    sort_order: Mapped[int] = mapped_column(
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
    user = relationship("User", back_populates="collections")
    items = relationship(
        "CollectionItem",
        back_populates="collection",
        cascade="all, delete-orphan",
        order_by="CollectionItem.added_at.desc()"
    )
    
    def __repr__(self) -> str:
        return f"<Collection {self.name}>"


class CollectionItem(Base):
    """Связь между коллекцией и пластинкой"""
    
    __tablename__ = "collection_items"
    
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4
    )
    
    # Связи
    collection_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("collections.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    record_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("records.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    
    # Дополнительная информация
    condition: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True  # Mint, Near Mint, VG+, VG, G+, G, Fair, Poor
    )
    sleeve_condition: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True
    )
    notes: Mapped[str | None] = mapped_column(
        Text,
        nullable=True
    )
    
    # Оценочная стоимость в рублях (на момент добавления)
    estimated_price_rub: Mapped[float | None] = mapped_column(
        Numeric(10, 2),
        nullable=True
    )

    # Порядок на полке
    shelf_position: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True
    )
    
    # Временные метки
    added_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        nullable=False
    )
    
    # Отношения
    collection = relationship("Collection", back_populates="items")
    record = relationship("Record", back_populates="collection_items")
    
    def __repr__(self) -> str:
        return f"<CollectionItem {self.id}>"

