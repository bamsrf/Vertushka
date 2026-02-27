"""
Схемы для вишлистов и подарков
"""
from datetime import datetime
from uuid import UUID
from pydantic import BaseModel, EmailStr, Field, ConfigDict

from app.schemas.record import RecordBrief
from app.models.gift_booking import GiftStatus


class WishlistItemCreate(BaseModel):
    """Схема для добавления пластинки в вишлист"""
    discogs_id: str | None = Field(None, description="Discogs ID пластинки")
    record_id: UUID | None = Field(None, description="UUID записи в БД (для обратной совместимости)")
    priority: int = Field(0, ge=0, le=10)
    notes: str | None = Field(None, max_length=1000)


class WishlistItemUpdate(BaseModel):
    """Схема для обновления элемента вишлиста"""
    priority: int | None = Field(None, ge=0, le=10)
    notes: str | None = Field(None, max_length=1000)


class GiftBookingInfo(BaseModel):
    """Информация о бронировании подарка"""
    model_config = ConfigDict(from_attributes=True)
    
    id: UUID
    gifter_name: str
    status: GiftStatus
    booked_at: datetime


class WishlistItemResponse(BaseModel):
    """Схема элемента вишлиста"""
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    wishlist_id: UUID
    record_id: UUID
    priority: int
    notes: str | None
    is_purchased: bool
    added_at: datetime
    purchased_at: datetime | None
    record: RecordBrief
    is_booked: bool = False
    gift_booking: GiftBookingInfo | None = None


class WishlistResponse(BaseModel):
    """Схема вишлиста (для владельца)"""
    model_config = ConfigDict(from_attributes=True)
    
    id: UUID
    user_id: UUID
    share_token: str
    is_public: bool
    show_gifter_names: bool
    custom_message: str | None
    created_at: datetime
    updated_at: datetime
    items: list[WishlistItemResponse] = []


class WishlistPublicItemResponse(BaseModel):
    """Публичная схема элемента вишлиста"""
    model_config = ConfigDict(from_attributes=True)
    
    id: UUID
    record: RecordBrief
    priority: int
    notes: str | None
    is_booked: bool = False
    gifter_name: str | None = None  # Показывается если разрешено


class WishlistPublicResponse(BaseModel):
    """Публичная схема вишлиста"""
    owner_name: str
    owner_avatar: str | None
    custom_message: str | None
    items: list[WishlistPublicItemResponse] = []
    total_items: int


class GiftBookingCreate(BaseModel):
    """Схема для бронирования подарка"""
    wishlist_item_id: UUID
    gifter_name: str = Field(..., min_length=2, max_length=100)
    gifter_email: EmailStr
    gifter_phone: str | None = Field(None, max_length=50)
    gifter_message: str | None = Field(None, max_length=500)


class GiftBookingResponse(BaseModel):
    """Схема ответа на бронирование подарка"""
    model_config = ConfigDict(from_attributes=True)
    
    id: UUID
    wishlist_item_id: UUID
    gifter_name: str
    gifter_email: str
    gifter_phone: str | None
    gifter_message: str | None
    status: GiftStatus
    cancel_token: str  # Токен для отмены бронирования
    booked_at: datetime
    record: RecordBrief  # Информация о пластинке


class GiftBookingOwnerResponse(BaseModel):
    """Схема бронирования для владельца вишлиста"""
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    wishlist_item_id: UUID
    gifter_name: str
    gifter_email: str
    gifter_phone: str | None
    gifter_message: str | None
    status: GiftStatus
    booked_at: datetime
    completed_at: datetime | None
    cancelled_at: datetime | None
    record: RecordBrief


class GiftRecipientInfo(BaseModel):
    """Информация о получателе подарка"""
    username: str
    display_name: str | None = None
    avatar_url: str | None = None


class GiftGivenResponse(BaseModel):
    """Схема бронирования для дарителя (секция 'Я дарю')"""
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    status: GiftStatus
    cancel_token: str
    booked_at: datetime
    completed_at: datetime | None = None
    record: RecordBrief
    for_user: GiftRecipientInfo


class MoveToCollectionRequest(BaseModel):
    """Схема для переноса из вишлиста в коллекцию"""
    collection_id: UUID

