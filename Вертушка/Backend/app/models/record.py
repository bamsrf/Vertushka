"""
Модель виниловой пластинки
"""
import uuid
from datetime import datetime
from decimal import Decimal
from sqlalchemy import String, DateTime, Integer, Text, Numeric, Boolean, ForeignKey
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
    
    # Источник записи: 'discogs' — пришла из Discogs API; 'store' — создана
    # из листинга магазина (для релизов которых нет на Discogs, см. матчер,
    # шаг 6 store-native); 'user' — добавлена юзером вручную (пластинки нет ни
    # в Discogs, ни в Маркете, см. docs/plans/USER_SUBMITTED_RECORDS.md). На
    # 'store' источники нельзя добавлять в коллекции/вишлисты; 'discogs' и
    # 'user' — можно (см. /api/collections, /api/wishlists guards, whitelist).
    source: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="discogs",
        server_default="discogs",
        index=True,
    )

    # --- User-submitted records (source='user') ---
    # Автор записи. Нужен для модерации и прав (приватность pending-записей).
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    # pending — приватна, видит только создатель; approved — общая (в Маркете/
    # ленте); rejected — отклонена модератором; merged — слита в Discogs-релиз
    # через rematch (см. merged_into_id). Для discogs/store всегда 'approved'.
    moderation_status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="approved",
        server_default="approved",
    )
    # Spotify album id из enrichment (§3). Прессинги/каталог Spotify не отдаёт —
    # их юзер вводит руками; отсюда берём год/обложку-кандидат/треклист.
    spotify_album_id: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
    )
    # Сырой ввод юзера + raw Spotify-ответ (аналог discogs_data).
    user_submitted_data: Mapped[dict | None] = mapped_column(
        JSONB,
        nullable=True,
    )

    # --- Yandex-native enrichment (релизы вне Discogs, source='store') ---
    # Альбом Yandex, из которого взяты обложка/год/треклист (аналог
    # spotify_album_id). См. listing_matcher шаг 5.5 + enrich_store_native_yandex.
    yandex_album_id: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
    )
    # cover/year/genre/tracklist из Yandex (аналог discogs_data). Треклист
    # отдаётся на detail-экране для записей вне Discogs.
    yandex_data: Mapped[dict | None] = mapped_column(
        JSONB,
        nullable=True,
    )

    # Discogs данные
    discogs_id: Mapped[str | None] = mapped_column(
        String(50),
        unique=True,
        nullable=True,
        index=True
    )
    # Заполняется weekly_rematch_store_native: если store-native запись позже
    # появилась на Discogs, сюда пишется кандидат. Авто-merge срабатывает,
    # когда тот же candidate подтверждается ≥ 2 раза подряд (см. confirmations).
    discogs_id_candidate: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
    )
    discogs_id_candidate_first_seen_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True,
    )
    discogs_id_candidate_confirmations: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default="0",
    )
    # Soft-delete для merge'нутых store-native: запись остаётся в БД, но во всех
    # эндпоинтах маркета/коллекций фильтруется по merged_into_id IS NULL.
    # Старые ссылки на uuid (push, share-link) могут редиректить на актуальный.
    merged_into_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("records.id", ondelete="SET NULL"),
        nullable=True,
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
    is_collectible: Mapped[bool] = mapped_column(
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

