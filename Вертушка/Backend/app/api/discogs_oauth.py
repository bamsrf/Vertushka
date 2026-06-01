"""Discogs OAuth 1.0a — endpoints подключения per-user токена."""
import logging
from datetime import datetime, timezone

import httpx
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_current_user
from app.config import get_settings
from app.database import get_db
from app.models.user import User
from app.services import discogs_oauth
from app.services.cache import cache
from app.services.discogs_crypto import encrypt_secret

logger = logging.getLogger(__name__)
router = APIRouter()

_NS = "discogs_oauth"
_TTL = 600  # 10 минут на прохождение flow


@router.post("/connect")
async def connect(current_user: User = Depends(get_current_user)):
    """Шаг 1: вернуть URL авторизации Discogs. Мобилка открывает его в web-browser."""
    try:
        authorize_url, oauth_token, oauth_token_secret = await discogs_oauth.build_authorize_url()
    except httpx.HTTPError:
        logger.exception("Discogs request_token failed")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Не удалось начать подключение Discogs",
        )
    # Связь callback'а (без нашего JWT) с юзером — по oauth_token.
    await cache.set(
        _NS,
        oauth_token,
        {"user_id": str(current_user.id), "secret": oauth_token_secret},
        ttl=_TTL,
    )
    return {"authorize_url": authorize_url}


@router.get("/callback")
async def callback(
    oauth_token: str,
    oauth_verifier: str,
    db: AsyncSession = Depends(get_db),
):
    """Шаг 2: Discogs редиректит сюда с verifier. Обмениваем, сохраняем, ведём в приложение."""
    settings = get_settings()
    pending = await cache.get(_NS, oauth_token)
    if not pending:
        # Просрочено или подделка — не палим детали.
        return RedirectResponse(f"{settings.discogs_oauth_app_redirect}?status=expired")
    await cache.delete(_NS, oauth_token)

    try:
        access_token, access_secret, username = await discogs_oauth.exchange(
            oauth_token, oauth_verifier, pending["secret"]
        )
    except httpx.HTTPError:
        logger.exception("Discogs access_token exchange failed")
        return RedirectResponse(f"{settings.discogs_oauth_app_redirect}?status=error")

    user = await db.get(User, pending["user_id"])
    if not user:
        return RedirectResponse(f"{settings.discogs_oauth_app_redirect}?status=error")

    user.discogs_username = username
    user.discogs_oauth_token = access_token
    user.discogs_oauth_token_secret = encrypt_secret(access_secret)
    user.discogs_connected_at = datetime.now(timezone.utc)
    await db.commit()

    return RedirectResponse(f"{settings.discogs_oauth_app_redirect}?status=connected")


@router.get("/status")
async def status_(current_user: User = Depends(get_current_user)):
    return {
        "connected": bool(current_user.discogs_oauth_token),
        "username": current_user.discogs_username,
    }


@router.delete("")
async def disconnect(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    current_user.discogs_username = None
    current_user.discogs_oauth_token = None
    current_user.discogs_oauth_token_secret = None
    current_user.discogs_connected_at = None
    await db.commit()
    return {"connected": False}
