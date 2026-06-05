"""
Схемы для уведомлений и социальной ленты
"""
from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class NotificationActor(BaseModel):
    """Краткая информация об инициаторе уведомления."""
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    username: str
    display_name: str | None = None
    avatar_url: str | None = None


class NotificationResponse(BaseModel):
    """Уведомление в персональной ленте «Ты»."""
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    type: str
    dedup_key: str | None = None
    entity_type: str | None = None
    entity_id: str | None = None
    data: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    bumped_at: datetime
    occurrences: int = 1
    snoozed_until: datetime | None = None
    read_at: datetime | None = None
    actor: NotificationActor | None = None


class SnoozeRequest(BaseModel):
    """Откладываем повторы по этому dedup_key на N дней."""
    days: int = Field(ge=1, le=365)


class SnoozeResponse(BaseModel):
    """Подтверждение snooze."""
    snoozed_until: datetime


class NotificationListResponse(BaseModel):
    """Постраничный ответ со списком уведомлений."""
    items: list[NotificationResponse]
    unread_count: int
    next_cursor: str | None = None


class UnreadCountResponse(BaseModel):
    """Счётчик непрочитанных personal-уведомлений."""
    unread_count: int


class MarkReadResponse(BaseModel):
    """Ответ после отметки прочитанным."""
    unread_count: int


class MarkReadBatchRequest(BaseModel):
    """Батч-отметка прочитанными по списку id (Instagram-паттерн «seen = read»)."""
    ids: list[UUID] = Field(min_length=1, max_length=100)


# --- Social feed (что делают подписки) ---

class FeedActor(BaseModel):
    """Краткая инфа о пользователе, чьё действие в ленте."""
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    username: str
    display_name: str | None = None
    avatar_url: str | None = None


class FeedRecord(BaseModel):
    """Краткая инфа о пластинке."""
    model_config = ConfigDict(from_attributes=True)

    id: str
    title: str
    artist: str | None = None
    cover_url: str | None = None


class SocialFeedItem(BaseModel):
    """Событие в социальной ленте подписок."""
    type: str  # collection_add, wishlist_add, gift_completed, friend_achievement, friend_new_following
    actor: FeedActor
    created_at: datetime
    record: FeedRecord | None = None
    target_user: FeedActor | None = None
    payload: dict[str, Any] = Field(default_factory=dict)


class SocialFeedResponse(BaseModel):
    """Постраничный ответ социальной ленты."""
    items: list[SocialFeedItem]
    next_cursor: str | None = None
