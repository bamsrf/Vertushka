"""Discogs OAuth 1.0a — endpoints подключения и логина по per-user токену."""
import logging
import secrets
import uuid as uuid_mod
from datetime import datetime, timezone

import httpx
from fastapi import APIRouter, Body, Depends, HTTPException, status
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_current_user
from app.config import get_settings
from app.database import get_db
from app.models.collection import Collection
from app.models.user import User
from app.models.wishlist import Wishlist
from app.schemas.auth import Token
from app.services import discogs_oauth
from app.services.cache import cache
from app.services.discogs_crypto import encrypt_secret
from app.utils.security import create_access_token, create_refresh_token

logger = logging.getLogger(__name__)
router = APIRouter()

_NS = "discogs_oauth"
_NS_TICKET = "discogs_login_ticket"
_TTL = 600  # 10 минут на прохождение flow
_TICKET_TTL = 120  # one-time login ticket живёт 2 минуты


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
        {"purpose": "connect", "user_id": str(current_user.id), "secret": oauth_token_secret},
        ttl=_TTL,
    )
    return {"authorize_url": authorize_url}


@router.post("/login")
async def login_start():
    """Шаг 1 логина через Discogs (без JWT — юзер ещё не залогинен).

    Возвращает authorize_url. Связь с будущим аккаунтом — по oauth_token,
    user_id ещё нет (создадим/найдём в callback по Discogs username)."""
    try:
        authorize_url, oauth_token, oauth_token_secret = await discogs_oauth.build_authorize_url()
    except httpx.HTTPError:
        logger.exception("Discogs request_token failed (login)")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Не удалось начать вход через Discogs",
        )
    await cache.set(
        _NS,
        oauth_token,
        {"purpose": "login", "secret": oauth_token_secret},
        ttl=_TTL,
    )
    return {"authorize_url": authorize_url}


async def _find_or_create_discogs_user(
    db: AsyncSession, username: str, access_token: str, access_secret: str
) -> User:
    """Найти юзера по Discogs username (или ранее привязанному токену), иначе
    создать аккаунт без email. Обновляет сохранённые OAuth-креды."""
    result = await db.execute(select(User).where(User.discogs_username == username))
    user = result.scalar_one_or_none()

    if user is None:
        # username для нашего аккаунта: discogs username, lowercased, разрешённые
        # символы; коллизии разводим суффиксом.
        import re

        base = re.sub(r"[^a-z0-9_]", "", username.lower()) or "discogs"
        base = base[:40]
        candidate = base
        counter = 1
        while counter <= 100:
            exists = await db.execute(select(User).where(User.username == candidate))
            if exists.scalar_one_or_none() is None:
                break
            candidate = f"{base}{counter}"
            counter += 1
        else:
            candidate = f"{base}_{uuid_mod.uuid4().hex[:8]}"

        user = User(
            email=None,
            username=candidate,
            display_name=username,
            is_verified=False,
            signup_source="discogs",
        )
        db.add(user)
        await db.flush()
        db.add(Wishlist(user_id=user.id))
        db.add(Collection(user_id=user.id, name="Моя коллекция"))

    # Сохраняем/обновляем OAuth-креды (секрет шифруем).
    user.discogs_username = username
    user.discogs_oauth_token = access_token
    user.discogs_oauth_token_secret = encrypt_secret(access_secret)
    user.discogs_connected_at = datetime.now(timezone.utc)
    user.last_login_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(user)
    return user


@router.post("/exchange-ticket", response_model=Token)
async def exchange_ticket(ticket: str = Body(..., embed=True)):
    """Шаг 3 логина: мобилка меняет one-time ticket из deep-link на JWT-пару."""
    payload = await cache.get(_NS_TICKET, ticket)
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Ticket недействителен или истёк",
        )
    await cache.delete(_NS_TICKET, ticket)
    return Token(
        access_token=payload["access_token"],
        refresh_token=payload["refresh_token"],
    )


@router.get("/callback")
async def callback(
    oauth_token: str,
    oauth_verifier: str,
    db: AsyncSession = Depends(get_db),
):
    """Шаг 2: Discogs редиректит сюда с verifier. Обмениваем, сохраняем, ведём в приложение."""
    settings = get_settings()
    redirect = settings.discogs_oauth_app_redirect
    pending = await cache.get(_NS, oauth_token)
    if not pending:
        # Просрочено или подделка — не палим детали.
        return RedirectResponse(f"{redirect}?status=expired")
    await cache.delete(_NS, oauth_token)

    try:
        access_token, access_secret, username = await discogs_oauth.exchange(
            oauth_token, oauth_verifier, pending["secret"]
        )
    except httpx.HTTPError:
        logger.exception("Discogs access_token exchange failed")
        return RedirectResponse(f"{redirect}?status=error")

    purpose = pending.get("purpose", "connect")

    if purpose == "login":
        # Логин: найти/создать аккаунт, выдать JWT через one-time ticket.
        try:
            user = await _find_or_create_discogs_user(db, username, access_token, access_secret)
        except Exception:
            logger.exception("Discogs login user upsert failed")
            return RedirectResponse(f"{redirect}?status=error")

        ticket = secrets.token_urlsafe(32)
        await cache.set(
            _NS_TICKET,
            ticket,
            {
                "access_token": create_access_token(user.id, user.token_version),
                "refresh_token": create_refresh_token(user.id, user.token_version),
            },
            ttl=_TICKET_TTL,
        )
        return RedirectResponse(f"{redirect}?status=login&ticket={ticket}")

    # purpose == "connect": привязка к уже залогиненному юзеру.
    user = await db.get(User, pending["user_id"])
    if not user:
        return RedirectResponse(f"{redirect}?status=error")

    user.discogs_username = username
    user.discogs_oauth_token = access_token
    user.discogs_oauth_token_secret = encrypt_secret(access_secret)
    user.discogs_connected_at = datetime.now(timezone.utc)
    await db.commit()

    return RedirectResponse(f"{redirect}?status=connected")


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
