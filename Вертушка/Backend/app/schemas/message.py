"""
Pydantic-схемы для личных сообщений.
"""

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.utc import UtcDatetime


RequestStatus = Literal["accepted", "pending"]
MessageFolder = Literal["primary", "requests", "archived"]
MuteDuration = Literal["off", "hour", "8hours", "day", "forever"]


class ConversationPartner(BaseModel):
    """Собеседник в карточке диалога."""
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    username: str
    display_name: str | None = None
    avatar_url: str | None = None


class ReplyPreview(BaseModel):
    """Превью сообщения, на которое отвечают."""
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    sender_id: UUID
    body: str | None = None
    deleted_at: UtcDatetime | None = None


class AttachedRecord(BaseModel):
    """Карточка прикреплённой пластинки для рендера в треде."""
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    title: str
    artist: str
    year: int | None = None
    cover_image_url: str | None = None
    cover_url: str | None = None


class ReactionRead(BaseModel):
    """Реакция (emoji + кто поставил) на сообщение."""
    model_config = ConfigDict(from_attributes=True)

    user_id: UUID
    emoji: str


class MessageRead(BaseModel):
    """Одно сообщение для отдачи на клиент."""
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    conversation_id: UUID
    sender_id: UUID
    body: str | None = None
    created_at: UtcDatetime
    edited_at: UtcDatetime | None = None
    deleted_at: UtcDatetime | None = None
    client_nonce: str | None = None
    reply_to_message_id: UUID | None = None
    reply_to: ReplyPreview | None = None
    attached_record_id: UUID | None = None
    attached_record: AttachedRecord | None = None
    media_url: str | None = None
    media_type: str | None = None
    reactions: list[ReactionRead] = Field(default_factory=list)


class ReactionToggle(BaseModel):
    """Toggle реакции пользователя на сообщение."""
    emoji: str = Field(..., min_length=1, max_length=16)


class PinnedMessagePreview(BaseModel):
    """Превью закреплённого в треде сообщения."""
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    sender_id: UUID
    body: str | None = None
    deleted_at: UtcDatetime | None = None


class ConversationRead(BaseModel):
    """Карточка диалога в инбоксе."""
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    partner: ConversationPartner
    last_message_preview: str | None = None
    last_message_at: UtcDatetime | None = None
    last_message_sender_id: UUID | None = None
    unread_count: int = 0
    muted: bool = False
    request_status: RequestStatus = "accepted"
    is_blocked: bool = False
    # last_read_at собеседника — для отрисовки read-receipt ✓✓ на своих сообщениях
    partner_last_read_at: UtcDatetime | None = None
    # Закреплено пользователем (Telegram-style pinned chat)
    pinned: bool = False
    # Закреплённое сообщение в треде (TG pin)
    pinned_message: PinnedMessagePreview | None = None
    # Когда заканчивается mute — null если mute навсегда (при muted=true) или нет
    muted_until: UtcDatetime | None = None


class ConversationDetail(BaseModel):
    """Детали диалога + первая страница сообщений."""
    conversation: ConversationRead
    messages: list[MessageRead]


class ConversationCreate(BaseModel):
    """Запрос на создание/получение диалога с пользователем."""
    recipient_user_id: UUID


class MessageCreate(BaseModel):
    """Новое сообщение в диалоге."""
    # Тело может быть пустым, если задано вложение (attached_record_id или media_url).
    body: str = Field("", max_length=4000)
    client_nonce: str | None = Field(None, max_length=64)
    reply_to_message_id: UUID | None = None
    attached_record_id: UUID | None = None
    media_url: str | None = Field(None, max_length=512)
    media_type: str | None = Field(None, max_length=32)


class MessageEdit(BaseModel):
    """Редактирование текста сообщения (15-минутное окно)."""
    body: str = Field(..., min_length=1, max_length=4000)


class MuteRequest(BaseModel):
    """Установить mute на диалог с длительностью."""
    duration: MuteDuration


class ReadMarker(BaseModel):
    """Пометить прочитанными до этого сообщения включительно."""
    up_to_message_id: UUID


class UnreadCount(BaseModel):
    """Счётчики непрочитанного для бейджа в табе."""
    primary: int
    requests: int


class PresenceResponse(BaseModel):
    """Статус собеседника: онлайн / был N мин назад."""
    online: bool
    last_seen_at: UtcDatetime | None = None
