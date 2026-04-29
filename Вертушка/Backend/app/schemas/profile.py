"""
Схемы для публичного профиля
"""
from datetime import datetime
from uuid import UUID
from pydantic import BaseModel, Field, ConfigDict


class ProfileShareSettings(BaseModel):
    """Настройки публичного профиля (для владельца)"""
    model_config = ConfigDict(from_attributes=True)

    is_active: bool = False
    is_private_profile: bool = False
    show_collection: bool = True
    show_wishlist: bool = True
    custom_title: str | None = None
    highlight_record_ids: list[UUID] | None = None
    show_record_year: bool = True
    show_record_label: bool = True
    show_record_format: bool = True
    show_record_prices: bool = False
    show_collection_value: bool = False


class ProfileShareUpdate(BaseModel):
    """Обновление настроек публичного профиля"""
    is_active: bool | None = None
    is_private_profile: bool | None = None
    show_collection: bool | None = None
    show_wishlist: bool | None = None
    custom_title: str | None = Field(None, max_length=200)
    show_record_year: bool | None = None
    show_record_label: bool | None = None
    show_record_format: bool | None = None
    show_record_prices: bool | None = None
    show_collection_value: bool | None = None


class ProfileHighlightsUpdate(BaseModel):
    """Установка избранных пластинок"""
    record_ids: list[UUID] = Field(..., max_length=4)


class PublicProfileRecord(BaseModel):
    """Пластинка в публичном профиле"""
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    title: str
    artist: str
    year: int | None = None
    label: str | None = None
    format_type: str | None = None
    cover_image_url: str | None = None
    thumb_image_url: str | None = None
    estimated_price_median: float | None = None
    price_currency: str = "USD"
    is_booked: bool = False
    discogs_id: str | None = None
    discogs_master_id: str | None = None
    discogs_want: int | None = None
    discogs_have: int | None = None
    is_first_press: bool = False
    is_canon: bool = False
    is_limited: bool = False
    is_hot: bool = False


class PublicProfileResponse(BaseModel):
    """Публичный профиль пользователя"""
    username: str
    display_name: str | None = None
    avatar_url: str | None = None
    bio: str | None = None
    custom_title: str | None = None

    # Статистика
    collection_count: int = 0
    wishlist_count: int = 0
    collection_value: float | None = None
    collection_value_rub: float | None = None
    monthly_value_delta_rub: float | None = None
    followers_count: int = 0

    # Настройки отображения
    show_collection: bool = True
    show_wishlist: bool = True
    show_record_year: bool = True
    show_record_label: bool = True
    show_record_format: bool = True
    show_record_prices: bool = False

    # Избранные пластинки
    highlights: list[PublicProfileRecord] = []

    # Полная коллекция (для грида)
    collection: list[PublicProfileRecord] = []

    # Рейлы для главного экрана
    top_expensive: list[PublicProfileRecord] = []
    new_releases: list[PublicProfileRecord] = []
