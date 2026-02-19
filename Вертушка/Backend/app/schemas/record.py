"""
Схемы для виниловых пластинок
"""
from datetime import datetime
from decimal import Decimal
from uuid import UUID
from pydantic import BaseModel, Field, ConfigDict


class RecordBase(BaseModel):
    """Базовая схема пластинки"""
    title: str = Field(..., max_length=500)
    artist: str = Field(..., max_length=500)
    label: str | None = Field(None, max_length=255)
    year: int | None = Field(None, ge=1900, le=2100)
    country: str | None = Field(None, max_length=100)
    genre: str | None = Field(None, max_length=255)


class RecordCreate(RecordBase):
    """Схема для создания пластинки"""
    discogs_id: str | None = None
    discogs_master_id: str | None = None
    catalog_number: str | None = None
    style: str | None = None
    format_type: str | None = None
    format_description: str | None = None
    barcode: str | None = None
    cover_image_url: str | None = None
    thumb_image_url: str | None = None
    estimated_price_min: Decimal | None = None
    estimated_price_max: Decimal | None = None
    estimated_price_median: Decimal | None = None
    price_currency: str = "USD"
    discogs_data: dict | None = None
    tracklist: list | None = None


class RecordResponse(BaseModel):
    """Полная схема пластинки"""
    model_config = ConfigDict(from_attributes=True)
    
    id: UUID
    discogs_id: str | None
    discogs_master_id: str | None
    title: str
    artist: str
    label: str | None
    catalog_number: str | None
    year: int | None
    country: str | None
    genre: str | None
    style: str | None
    format_type: str | None
    format_description: str | None
    barcode: str | None
    estimated_price_min: Decimal | None
    estimated_price_max: Decimal | None
    estimated_price_median: Decimal | None
    price_currency: str
    cover_image_url: str | None
    thumb_image_url: str | None
    artist_id: str | None = None
    artist_thumb_image_url: str | None = None
    tracklist: list | None
    created_at: datetime
    updated_at: datetime


class RecordBrief(BaseModel):
    """Краткая схема пластинки (для списков)"""
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    discogs_id: str | None
    title: str
    artist: str
    artist_id: str | None = None
    artist_thumb_image_url: str | None = None
    year: int | None
    cover_image_url: str | None
    thumb_image_url: str | None
    estimated_price_median: Decimal | None
    price_currency: str


class RecordSearchResult(BaseModel):
    """Результат поиска пластинки (от Discogs)"""
    discogs_id: str
    title: str
    artist: str
    label: str | None
    year: int | None
    country: str | None
    cover_image_url: str | None
    thumb_image_url: str | None
    format_type: str | None


class RecordSearchResponse(BaseModel):
    """Ответ на поиск пластинок"""
    results: list[RecordSearchResult]
    total: int
    page: int
    per_page: int


class MasterSearchResult(BaseModel):
    """Результат поиска мастер-релиза (от Discogs)"""
    master_id: str
    title: str
    artist: str
    year: int | None = None
    main_release_id: str
    cover_image_url: str | None = None
    thumb_image_url: str | None = None
    release_type: str | None = None


class MasterVersion(BaseModel):
    """Версия (издание) мастер-релиза"""
    release_id: str
    title: str
    label: str | None = None
    catalog_number: str | None = None
    country: str | None = None
    year: int | None = None
    format: str | None = None
    thumb_image_url: str | None = None


class MasterRelease(BaseModel):
    """Полная информация о мастер-релизе"""
    master_id: str
    title: str
    artist: str
    artist_id: str | None = None
    artist_thumb_image_url: str | None = None
    year: int | None = None
    main_release_id: str
    genres: list[str] = []
    styles: list[str] = []
    cover_image_url: str | None = None
    tracklist: list | None = None


class MasterSearchResponse(BaseModel):
    """Ответ на поиск мастер-релизов"""
    results: list[MasterSearchResult]
    total: int
    page: int
    per_page: int


class MasterVersionsResponse(BaseModel):
    """Ответ на запрос версий мастер-релиза"""
    results: list[MasterVersion]
    total: int
    page: int
    per_page: int


class ReleaseSearchResult(BaseModel):
    """Результат поиска конкретных релизов с фильтрами (от Discogs)"""
    release_id: str
    title: str
    artist: str
    label: str | None = None
    catalog_number: str | None = None
    country: str | None = None
    year: int | None = None
    format: str | None = None
    cover_image_url: str | None = None
    thumb_image_url: str | None = None


class ReleaseSearchResponse(BaseModel):
    """Ответ на поиск релизов с фильтрами"""
    results: list[ReleaseSearchResult]
    total: int
    page: int
    per_page: int


class ArtistSearchResult(BaseModel):
    """Результат поиска артиста (от Discogs)"""
    artist_id: str
    name: str
    cover_image_url: str | None = None
    thumb_image_url: str | None = None


class Artist(BaseModel):
    """Полная информация об артисте"""
    artist_id: str
    name: str
    profile: str | None = None
    images: list[str] = []


class ArtistSearchResponse(BaseModel):
    """Ответ на поиск артистов"""
    results: list[ArtistSearchResult]
    total: int
    page: int
    per_page: int

