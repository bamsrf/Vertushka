"""
API для waitlist — сбор email-ов на рассылку ссылки на стор при запуске мобильного приложения.
"""
import logging
import re
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.waitlist import WaitlistEntry

logger = logging.getLogger(__name__)

router = APIRouter()


class WaitlistJoinRequest(BaseModel):
    email: EmailStr
    source: str | None = Field(default=None, max_length=255)


class WaitlistJoinResponse(BaseModel):
    ok: bool
    already_subscribed: bool = False


_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


@router.post("/", response_model=WaitlistJoinResponse, status_code=status.HTTP_201_CREATED)
async def join_waitlist(
    data: WaitlistJoinRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """
    Сохраняет email пользователя для рассылки ссылки на стор после релиза.
    Идемпотентно: дубликаты с тем же email + source считаются «уже подписан».
    """
    email = data.email.strip().lower()
    if not _EMAIL_RE.match(email):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Некорректный email")

    source = (data.source or "").strip() or None

    # Простая защита от спама: один и тот же IP не может писать чаще 1 раз в 30 сек
    client_ip = request.client.host if request.client else None
    if client_ip:
        recent = await db.scalar(
            select(func.count(WaitlistEntry.id)).where(
                WaitlistEntry.user_agent == client_ip,
                WaitlistEntry.created_at > datetime.utcnow() - timedelta(seconds=30),
            )
        )
        if recent and recent > 0:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Слишком часто. Попробуйте через несколько секунд.",
            )

    # Проверяем дубль
    existing = await db.scalar(
        select(WaitlistEntry).where(
            WaitlistEntry.email == email,
            WaitlistEntry.source == source,
        )
    )
    if existing:
        return WaitlistJoinResponse(ok=True, already_subscribed=True)

    entry = WaitlistEntry(
        email=email,
        source=source,
        user_agent=client_ip,
    )
    db.add(entry)
    await db.commit()
    logger.info("waitlist_join email=%s source=%s", email, source)

    return WaitlistJoinResponse(ok=True, already_subscribed=False)
