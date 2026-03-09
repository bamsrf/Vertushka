"""
Схемы для коллекций
"""
from datetime import datetime
from uuid import UUID
from pydantic import BaseModel, Field, ConfigDict

from app.schemas.record import RecordBrief


class CollectionBase(BaseModel):
    """Базовая схема коллекции"""
    name: str = Field(..., min_length=1, max_length=100)
    description: str | None = Field(None, max_length=500)


class CollectionCreate(CollectionBase):
    """Схема для создания коллекции"""
    pass


class CollectionUpdate(BaseModel):
    """Схема для обновления коллекции"""
    name: str | None = Field(None, min_length=1, max_length=100)
    description: str | None = Field(None, max_length=500)


class CollectionResponse(BaseModel):
    """Схема коллекции"""
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: UUID
    name: str
    description: str | None
    sort_order: int
    created_at: datetime
    updated_at: datetime
    items_count: int = 0


class CollectionItemCreate(BaseModel):
    """Схема для добавления пластинки в коллекцию"""
    discogs_id: str | None = Field(None, description="Discogs ID пластинки")
    record_id: UUID | None = Field(None, description="UUID записи в БД (для обратной совместимости)")
    condition: str | None = Field(None, max_length=50)
    sleeve_condition: str | None = Field(None, max_length=50)
    notes: str | None = Field(None, max_length=1000)


class CollectionItemUpdate(BaseModel):
    """Схема для обновления элемента коллекции"""
    condition: str | None = Field(None, max_length=50)
    sleeve_condition: str | None = Field(None, max_length=50)
    notes: str | None = Field(None, max_length=1000)
    shelf_position: int | None = None


class CollectionItemResponse(BaseModel):
    """Схема элемента коллекции"""
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    collection_id: UUID
    record_id: UUID
    condition: str | None
    sleeve_condition: str | None
    notes: str | None
    shelf_position: int | None
    estimated_price_rub: float | None
    added_at: datetime
    record: RecordBrief


class CollectionWithItems(CollectionResponse):
    """Коллекция с элементами"""
    items: list[CollectionItemResponse] = []


class CollectionStats(BaseModel):
    """Статистика коллекции"""
    total_records: int
    total_estimated_value_min: float | None
    total_estimated_value_max: float | None
    total_estimated_value_median: float | None
    total_estimated_value_rub: float | None
    usd_rub_rate: float | None
    ru_markup: float
    most_expensive: RecordBrief | None
    most_expensive_price_rub: float | None
    records_with_price: int
    records_by_year: dict[int, int]
    records_by_genre: dict[str, int]
    oldest_record_year: int | None
    newest_record_year: int | None
