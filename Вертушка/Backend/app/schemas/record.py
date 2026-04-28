"""
Схемы для виниловых пластинок
"""
from datetime import datetime
from decimal import Decimal
from uuid import UUID
from pydantic import BaseModel, Field, ConfigDict, model_validator


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
    vinyl_color_raw: str | None = None
    barcode: str | None
    estimated_price_min: float | None
    estimated_price_max: float | None
    estimated_price_median: float | None
    price_currency: str
    estimated_price_min_rub: float | None = None
    estimated_price_median_rub: float | None = None
    estimated_price_max_rub: float | None = None
    usd_rub_rate: float | None = None
    ru_markup: float | None = None
    cover_image_url: str | None
    thumb_image_url: str | None
    cover_url: str | None = None  # локальный URL (/uploads/covers/...) или fallback на Discogs
    cover_local_path: str | None = Field(default=None, exclude=True)
    artist_id: str | None = None
    artist_thumb_image_url: str | None = None
    tracklist: list | None
    created_at: datetime
    updated_at: datetime

    @model_validator(mode="after")
    def _populate_cover_url(self) -> "RecordResponse":
        if self.cover_local_path and not self.cover_url:
            lp = self.cover_local_path
            self.cover_url = lp if lp.startswith("/") else f"/uploads/{lp}"
        return self


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
    cover_url: str | None = None  # локальный URL (/uploads/covers/...) или fallback на Discogs
    cover_local_path: str | None = Field(default=None, exclude=True)
    format_type: str | None = None
    estimated_price_median: float | None
    price_currency: str

    @model_validator(mode="after")
    def _populate_cover_url(self) -> "RecordBrief":
        if self.cover_local_path and not self.cover_url:
            lp = self.cover_local_path
            self.cover_url = lp if lp.startswith("/") else f"/uploads/{lp}"
        return self


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
    major_formats: list[str] = []
    thumb_image_url: str | None = None
    cover_image_url: str | None = None


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
    has_more: bool = False
    next_cursor: int | None = None


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


class CoverScanRequest(BaseModel):
    """Запрос на распознавание обложки"""
    image_base64: str = Field(..., description="Base64-encoded JPEG image")


class CoverScanResponse(BaseModel):
    """Ответ на распознавание обложки"""
    recognized_artist: str
    recognized_album: str
    results: list[RecordSearchResult]


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

