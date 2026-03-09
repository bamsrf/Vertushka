"""
API для аутентификации
"""
import logging
import random
import uuid as uuid_mod
from datetime import datetime, timedelta, timezone
from uuid import UUID

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from slowapi import Limiter
from slowapi.util import get_remote_address
from jose import jwt as jose_jwt, JWTError, jwk
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database import get_db
from app.models.user import User
from app.models.wishlist import Wishlist
from app.models.collection import Collection
from app.schemas.user import UserCreate, UserLogin, UserResponse
from app.schemas.auth import (
    Token, RefreshToken, AppleSignIn, GoogleSignIn,
    ForgotPasswordRequest, VerifyResetCodeRequest, ResetPasswordRequest,
)
from app.services.email import send_reset_code_email
from app.utils.security import (
    hash_password,
    verify_password,
    create_access_token,
    create_refresh_token,
    verify_token_type,
)

logger = logging.getLogger(__name__)

router = APIRouter()
security = HTTPBearer()
limiter = Limiter(key_func=get_remote_address)

# ---------- Apple Sign In verification ----------

APPLE_JWKS_URL = "https://appleid.apple.com/auth/keys"
_apple_jwks_cache: dict | None = None


async def _get_apple_jwks() -> dict:
    """Получение Apple JWKS (с кэшированием в памяти)."""
    global _apple_jwks_cache
    if _apple_jwks_cache:
        return _apple_jwks_cache
    async with httpx.AsyncClient() as client:
        resp = await client.get(APPLE_JWKS_URL, timeout=10.0)
        resp.raise_for_status()
        _apple_jwks_cache = resp.json()
        return _apple_jwks_cache


async def _verify_apple_identity_token(identity_token: str) -> dict:
    """Верифицирует Apple identity_token через Apple JWKS.
    Возвращает payload с sub, email и др."""
    settings = get_settings()
    try:
        unverified_header = jose_jwt.get_unverified_header(identity_token)
        kid = unverified_header.get("kid")
        if not kid:
            raise ValueError("No kid in token header")

        jwks = await _get_apple_jwks()
        key_data = None
        for key in jwks.get("keys", []):
            if key["kid"] == kid:
                key_data = key
                break

        if not key_data:
            global _apple_jwks_cache
            _apple_jwks_cache = None
            jwks = await _get_apple_jwks()
            for key in jwks.get("keys", []):
                if key["kid"] == kid:
                    key_data = key
                    break

        if not key_data:
            raise ValueError(f"Apple public key with kid={kid} not found")

        public_key = jwk.construct(key_data)
        payload = jose_jwt.decode(
            identity_token,
            public_key,
            algorithms=["RS256"],
            audience=settings.apple_client_id,
            issuer="https://appleid.apple.com",
        )
        return payload
    except (JWTError, ValueError, Exception) as e:
        logger.warning("Apple identity_token verification failed: %s", e)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Недействительный Apple identity token"
        )


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: AsyncSession = Depends(get_db)
) -> User:
    """Dependency для получения текущего пользователя"""
    token = credentials.credentials
    payload = verify_token_type(token, "access")
    
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Недействительный токен авторизации",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    user_id = UUID(payload["sub"])
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Пользователь не найден",
        )
    
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Аккаунт деактивирован",
        )
    
    return user


async def get_current_user_optional(
    credentials: HTTPAuthorizationCredentials | None = Depends(
        HTTPBearer(auto_error=False)
    ),
    db: AsyncSession = Depends(get_db)
) -> User | None:
    """Опциональная аутентификация"""
    if not credentials:
        return None
    
    try:
        return await get_current_user(credentials, db)
    except HTTPException:
        return None


@router.post("/register", response_model=Token, status_code=status.HTTP_201_CREATED)
@limiter.limit("3/minute")
async def register(
    request: Request,
    user_data: UserCreate,
    db: AsyncSession = Depends(get_db)
):
    """Регистрация нового пользователя"""
    # Проверка уникальности email
    result = await db.execute(select(User).where(User.email == user_data.email))
    if result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Пользователь с таким email уже существует"
        )
    
    # Проверка уникальности username
    result = await db.execute(select(User).where(User.username == user_data.username))
    if result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Имя пользователя уже занято"
        )
    
    # Создание пользователя
    user = User(
        email=user_data.email,
        username=user_data.username,
        password_hash=hash_password(user_data.password),
        display_name=user_data.display_name or user_data.username,
    )
    db.add(user)
    await db.flush()
    
    # Создание вишлиста для пользователя
    wishlist = Wishlist(user_id=user.id)
    db.add(wishlist)
    
    # Создание дефолтной коллекции
    collection = Collection(
        user_id=user.id,
        name="Моя коллекция",
        description="Основная коллекция"
    )
    db.add(collection)
    
    await db.commit()
    
    # Создание токенов
    access_token = create_access_token(user.id)
    refresh_token = create_refresh_token(user.id)
    
    return Token(
        access_token=access_token,
        refresh_token=refresh_token
    )


@router.post("/login", response_model=Token)
@limiter.limit("5/minute")
async def login(
    request: Request,
    credentials: UserLogin,
    db: AsyncSession = Depends(get_db)
):
    """Вход в систему (по email или username)"""
    login_value = (credentials.login or "").strip().lower()
    if not login_value:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Введите email или имя пользователя"
        )

    # Определяем: email или username
    if "@" in login_value:
        result = await db.execute(select(User).where(User.email == login_value))
    else:
        result = await db.execute(
            select(User).where(User.username.ilike(login_value))
        )
    user = result.scalar_one_or_none()

    if not user or not user.password_hash:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Неверный логин или пароль"
        )

    if not verify_password(credentials.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Неверный логин или пароль"
        )
    
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Аккаунт деактивирован"
        )
    
    # Обновление времени последнего входа
    user.last_login_at = datetime.utcnow()
    await db.commit()

    access_token = create_access_token(user.id)
    refresh_token = create_refresh_token(user.id)

    return Token(
        access_token=access_token,
        refresh_token=refresh_token
    )


@router.post("/refresh", response_model=Token)
async def refresh_token(
    token_data: RefreshToken,
    db: AsyncSession = Depends(get_db)
):
    """Обновление токенов"""
    payload = verify_token_type(token_data.refresh_token, "refresh")
    
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Недействительный refresh токен"
        )
    
    user_id = UUID(payload["sub"])
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    
    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Пользователь не найден или деактивирован"
        )
    
    access_token = create_access_token(user.id)
    new_refresh_token = create_refresh_token(user.id)
    
    return Token(
        access_token=access_token,
        refresh_token=new_refresh_token
    )


@router.get("/me", response_model=UserResponse)
async def get_me(current_user: User = Depends(get_current_user)):
    """Получение информации о текущем пользователе"""
    return current_user


@router.post("/apple", response_model=Token)
@limiter.limit("5/minute")
async def apple_sign_in(
    request: Request,
    data: AppleSignIn,
    db: AsyncSession = Depends(get_db)
):
    """Вход через Apple Sign In"""
    # Верификация identity_token через Apple JWKS
    apple_payload = await _verify_apple_identity_token(data.identity_token)
    apple_sub = apple_payload.get("sub")
    if apple_sub != data.user_identifier:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="user_identifier не совпадает с sub токена"
        )

    # Поиск пользователя по Apple ID
    result = await db.execute(
        select(User).where(User.apple_id == data.user_identifier)
    )
    user = result.scalar_one_or_none()

    if not user:
        # Создание нового пользователя
        email = data.email or apple_payload.get("email")
        if not email:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email обязателен для регистрации"
            )

        # Генерация уникального username (с лимитом итераций)
        base_username = email.split("@")[0]
        username = base_username
        counter = 1
        while counter <= 100:
            result = await db.execute(select(User).where(User.username == username))
            if not result.scalar_one_or_none():
                break
            username = f"{base_username}{counter}"
            counter += 1
        else:
            # Fallback на UUID-суффикс
            username = f"{base_username}_{uuid_mod.uuid4().hex[:8]}"

        user = User(
            email=email,
            username=username,
            apple_id=data.user_identifier,
            display_name=data.full_name or username,
            is_verified=True,  # Apple верифицирует email
        )
        db.add(user)
        await db.flush()

        # Создание вишлиста
        wishlist = Wishlist(user_id=user.id)
        db.add(wishlist)

        # Создание коллекции
        collection = Collection(
            user_id=user.id,
            name="Моя коллекция"
        )
        db.add(collection)

        await db.commit()
    
    user.last_login_at = datetime.utcnow()
    await db.commit()

    access_token = create_access_token(user.id)
    refresh_token = create_refresh_token(user.id)

    return Token(
        access_token=access_token,
        refresh_token=refresh_token
    )


@router.post("/google", response_model=Token)
async def google_sign_in(
    data: GoogleSignIn,
    db: AsyncSession = Depends(get_db)
):
    """Вход через Google Sign In"""
    # TODO: Верификация id_token через Google
    # Пока заглушка для структуры
    
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Google Sign In ещё не реализован"
    )


# ---------- Password Reset ----------

RESET_CODE_TTL_MINUTES = 15
RESET_CODE_MAX_ATTEMPTS = 3


@router.post("/forgot-password/")
@limiter.limit("3/minute")
async def forgot_password(
    request: Request,
    data: ForgotPasswordRequest,
    db: AsyncSession = Depends(get_db)
):
    """Запрос кода сброса пароля — отправка на email"""
    # Всегда возвращаем успех, чтобы не раскрывать существование email
    result = await db.execute(select(User).where(User.email == data.email.lower()))
    user = result.scalar_one_or_none()

    if user and user.is_active:
        # Генерируем 6-значный код
        code = f"{random.randint(0, 999999):06d}"

        # Сохраняем хеш кода в БД
        user.reset_code_hash = hash_password(code)
        user.reset_code_expires_at = datetime.utcnow() + timedelta(minutes=RESET_CODE_TTL_MINUTES)
        user.reset_code_attempts = 0
        await db.commit()

        # Отправляем email
        logger.info("DEV: Reset code for %s: %s", data.email, code)
        await send_reset_code_email(data.email, code)

    return {"message": "Если аккаунт существует, код отправлен на email"}


@router.post("/verify-reset-code/")
@limiter.limit("5/minute")
async def verify_reset_code(
    request: Request,
    data: VerifyResetCodeRequest,
    db: AsyncSession = Depends(get_db)
):
    """Проверка кода сброса — возвращает reset_token"""
    result = await db.execute(select(User).where(User.email == data.email.lower()))
    user = result.scalar_one_or_none()

    error_msg = "Неверный или просроченный код"

    if not user or not user.reset_code_hash or not user.reset_code_expires_at:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=error_msg)

    # Проверка TTL
    if datetime.utcnow() > user.reset_code_expires_at:
        user.reset_code_hash = None
        user.reset_code_expires_at = None
        user.reset_code_attempts = 0
        await db.commit()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=error_msg)

    # Проверка количества попыток
    if user.reset_code_attempts >= RESET_CODE_MAX_ATTEMPTS:
        user.reset_code_hash = None
        user.reset_code_expires_at = None
        user.reset_code_attempts = 0
        await db.commit()
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Превышено количество попыток. Запросите новый код"
        )

    # Проверка кода
    if not verify_password(data.code, user.reset_code_hash):
        user.reset_code_attempts += 1
        await db.commit()
        remaining = RESET_CODE_MAX_ATTEMPTS - user.reset_code_attempts
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Неверный код. Осталось попыток: {remaining}"
        )

    # Код верный — очищаем и выдаём reset_token
    user.reset_code_hash = None
    user.reset_code_expires_at = None
    user.reset_code_attempts = 0
    await db.commit()

    settings = get_settings()
    reset_token = jose_jwt.encode(
        {
            "sub": str(user.id),
            "type": "reset",
            "exp": datetime.now(timezone.utc) + timedelta(minutes=10),
        },
        settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm,
    )

    return {"reset_token": reset_token}


@router.post("/reset-password/")
@limiter.limit("3/minute")
async def reset_password(
    request: Request,
    data: ResetPasswordRequest,
    db: AsyncSession = Depends(get_db)
):
    """Установка нового пароля с помощью reset_token"""
    payload = verify_token_type(data.reset_token, "reset")

    if not payload:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Недействительный или просроченный токен сброса"
        )

    user_id = UUID(payload["sub"])
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Пользователь не найден"
        )

    user.password_hash = hash_password(data.new_password)
    user.last_login_at = datetime.utcnow()
    await db.commit()

    # Сразу выдаём токены для автологина
    access_token = create_access_token(user.id)
    refresh_token = create_refresh_token(user.id)

    return Token(
        access_token=access_token,
        refresh_token=refresh_token
    )

