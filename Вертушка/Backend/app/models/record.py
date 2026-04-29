"""
Модель виниловой пластинки
"""
import uuid
from datetime import datetime
from decimal import Decimal
from sqlalchemy import String, DateTime, Integer, Text, Numeric, Boolean
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID, JSONB

from app.database import Base


class Record(Base):
    """Модель виниловой пластинки"""
    
    __tablename__ = "records"
    
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4
    )
    
    # Discogs данные
    discogs_id: Mapped[str | None] = mapped_column(
        String(50),
        unique=True,
        nullable=True,
        index=True
    )
    discogs_master_id: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
        index=True
    )
    
    # Основная информация
    title: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
        index=True
    )
    artist: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
        index=True
    )
    
    # Дополнительная информация
    label: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True
    )
    catalog_number: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True
    )
    year: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
        index=True
    )
    country: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True
    )
    genre: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True
    )
    style: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True
    )
    
    # Формат
    format_type: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True  # LP, EP, Single, и т.д.
    )
    format_description: Mapped[str | None] = mapped_column(
        Text,
        nullable=True
    )
    
    # Штрихкод
    barcode: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
        index=True
    )
    
    # Цена и стоимость
    estimated_price_min: Mapped[Decimal | None] = mapped_column(
        Numeric(10, 2),
        nullable=True
    )
    estimated_price_max: Mapped[Decimal | None] = mapped_column(
        Numeric(10, 2),
        nullable=True
    )
    estimated_price_median: Mapped[Decimal | None] = mapped_column(
        Numeric(10, 2),
        nullable=True
    )
    price_currency: Mapped[str] = mapped_column(
        String(3),
        default="USD",
        nullable=False
    )

    # Признаки редкости — см. Mobile/components/RarityAura.tsx
    is_first_press: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
        server_default="false",
    )
    is_canon: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
        server_default="false",
    )
    is_limited: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
        server_default="false",
    )
    is_hot: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
        server_default="false",
    )

    # Изображения
    cover_image_url: Mapped[str | None] = mapped_column(
        Text,
        nullable=True
    )
    thumb_image_url: Mapped[str | None] = mapped_column(
        Text,
        nullable=True
    )

    # Локальный кэш обложки
    cover_local_path: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True
    )
    cover_cached_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True
    )
    
    # Полные данные от Discogs (JSON)
    discogs_data: Mapped[dict | None] = mapped_column(
        JSONB,
        nullable=True
    )
    
    # Треклист (JSON)
    tracklist: Mapped[list | None] = mapped_column(
        JSONB,
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
    
    # Отношения
    collection_items = relationship(
        "CollectionItem",
        back_populates="record",
        cascade="all, delete-orphan"
    )
    wishlist_items = relationship(
        "WishlistItem",
        back_populates="record",
        cascade="all, delete-orphan"
    )
    
    @property
    def artist_id(self) -> str | None:
        if self.discogs_data:
            return self.discogs_data.get("artist_id")
        return None

    @property
    def artist_thumb_image_url(self) -> str | None:
        if self.discogs_data:
            return self.discogs_data.get("artist_thumb_image_url")
        return None

    def __repr__(self) -> str:
        return f"<Record {self.artist} - {self.title}>"

