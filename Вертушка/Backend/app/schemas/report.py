"""Pydantic-схемы жалоб на UGC (App Store Guideline 1.2)."""
import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

ReportTargetType = Literal["record", "user", "message"]
ReportAction = Literal["hide_record", "hide_message", "ban_user", "dismiss"]


class ReportCreate(BaseModel):
    target_type: ReportTargetType
    target_id: uuid.UUID
    reason: str | None = Field(default=None, max_length=500)


class ReportActionRequest(BaseModel):
    action: ReportAction


class ReportResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    reporter_id: uuid.UUID
    target_type: str
    target_id: uuid.UUID
    reason: str | None
    status: str
    created_at: datetime

    # Что именно обжалуют — заголовок записи, текст сообщения, ник юзера.
    # Без этого разобрать жалобу за 24ч можно только через прямой доступ к БД,
    # а SLA мы обещаем и пользователям в Условиях, и Apple при ревью.
    target_preview: str | None = None
