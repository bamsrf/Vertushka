"""
Схемы для вишлистов и подарков
"""
from datetime import datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID
from pydantic import BaseModel, EmailStr, Field, ConfigDict

NotifyMode = Literal["watched", "subscribed"]
WishlistCondition = Literal["sealed", "mint", "vg_plus", "vg"]
RadarStatus = Literal["match", "available", "alt", "absent"]

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
    # Колокольчик: 'subscribed' → мгновенный push при in_stock/price_drop/аналоге.
    notify_mode: NotifyMode | None = None
    # Порог «уведомить, когда дешевле X ₽». None = любое появление/падение.
    price_threshold_rub: Decimal | None = Field(None, ge=0)
    # Режим «дешевле обычного»: скидка в % от медианы за 90 дней. Задан → решает
    # он, price_threshold_rub остаётся лежать как память о фиксированном режиме.
    # Границы: ниже 5% шум колебаний, выше 90% порог недостижим.
    threshold_pct: int | None = Field(None, ge=5, le=90)
    # Принятые грейды состояния (['sealed','mint','vg_plus','vg']). None = любое.
    conditions: list[WishlistCondition] | None = None
    # Принять альт-прессинг как подходящий (радар: статус «в продаже», не «альтернатива»).
    accept_alt: bool | None = None
    # «Нет» в шите радара: этот прессинг больше не предлагать как аналог.
    reject_alt_record_id: UUID | None = None


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
    notify_mode: NotifyMode = "watched"
    price_threshold_rub: Decimal | None = None
    conditions: list[WishlistCondition] | None = None
    accept_alt: bool = False


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
    added_at: datetime | None = None  # Для сортировки на клиенте


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


# ==================== Wishlist Folders ====================


class WishlistFolderCreate(BaseModel):
    """Создание папки в вишлисте"""
    name: str = Field(..., min_length=1, max_length=100)


class WishlistFolderUpdate(BaseModel):
    """Обновление папки в вишлисте"""
    name: str | None = Field(None, min_length=1, max_length=100)


class WishlistFolderResponse(BaseModel):
    """Папка в вишлисте"""
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    wishlist_id: UUID
    name: str
    sort_order: int
    items_count: int = 0
    created_at: datetime
    updated_at: datetime


class WishlistFolderWithItems(WishlistFolderResponse):
    """Папка с её содержимым"""
    items: list[WishlistItemResponse] = []


class WishlistFolderItemsAdd(BaseModel):
    """Bulk-добавление items в папку"""
    wishlist_item_ids: list[UUID] = Field(..., min_length=1)


# ── Радар ──────────────────────────────────────────────────────────────────

class RadarAlt(BaseModel):
    """Данные альтернативной версии (другой прессинг того же мастера) в наличии."""
    record_id: UUID
    title: str | None = None
    cover_url: str | None = None
    price_rub: Decimal | None = None
    # Отличия от версии в вишлисте — для экрана подтверждения.
    year: int | None = None
    country: str | None = None
    format: str | None = None
    buy_url: str | None = None
    buy_listing_id: UUID | None = None


class RadarItem(BaseModel):
    """Одна пластинка на радаре — с вычисленным статусом и позицией."""
    model_config = ConfigDict(from_attributes=True)

    wishlist_item_id: UUID
    record: RecordBrief
    status: RadarStatus
    lowest_price_rub: Decimal | None = None
    # Порог, по которому реально считался статус. В относительном режиме это
    # база × (1 − pct/100), а не сохранённая когда-то сумма.
    threshold_rub: Decimal | None = None
    # Заданы вместе → режим «дешевле обычного». baseline_rub = медиана дневных
    # минимумов за 90 дней; None — истории не хватило, работал абсолютный порог.
    threshold_pct: int | None = None
    baseline_rub: Decimal | None = None
    conditions: list[WishlistCondition] | None = None
    accept_alt: bool = False
    radius: float  # 0..1: 0 = у центра (зона покупки), 1 = внешний край
    offers_count: int = 0       # сколько подходящих in_stock листингов
    buy_url: str | None = None  # ссылка на самый дешёвый листинг (прямой заказ)
    # id того же листинга: клиент шлёт POST /offers/{id}/click, чтобы переход
    # получил affiliate-subid и попал в серию «Рыночный нюх». Без него ссылка
    # уходит мимо трекинга — комиссия теряется, ачивки не считаются.
    buy_listing_id: UUID | None = None
    alt: RadarAlt | None = None
    # Когда пластинка ушла в absent (начало текущей серии по radar_status_events).
    # Нужно, чтобы при заполненном радаре было видно, кого не жалко выселить.
    # None — событий нет (айтем подписан недавно) либо статус не absent.
    absent_since: datetime | None = None


class RadarResponse(BaseModel):
    """Ответ GET /wishlists/radar."""
    items: list[RadarItem] = []
    count: int = 0
    match_count: int = 0  # сколько в зоне покупки (для бейджа кнопки)
    limit: int = 5        # максимум пластинок на радаре


class RadarEventItem(BaseModel):
    """Одна запись хронологии смен статуса на радаре."""
    model_config = ConfigDict(from_attributes=True)

    status: RadarStatus | str
    price_rub: Decimal | None = None
    store_name: str | None = None
    created_at: datetime


class RadarEventsResponse(BaseModel):
    events: list[RadarEventItem] = []

