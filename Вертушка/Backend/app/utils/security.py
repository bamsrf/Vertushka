"""
Утилиты безопасности: хэширование паролей, JWT токены
"""
import secrets
from datetime import datetime, timedelta
from uuid import UUID

import jwt
from jwt import PyJWTError
from passlib.context import CryptContext

from app.config import get_settings

settings = get_settings()

# Контекст для хэширования паролей
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    """Хэширование пароля"""
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Проверка пароля"""
    return pwd_context.verify(plain_password, hashed_password)


def create_access_token(user_id: UUID, token_version: int = 0) -> str:
    """Создание access токена"""
    expire = datetime.utcnow() + timedelta(minutes=settings.access_token_expire_minutes)
    payload = {
        "sub": str(user_id),
        "exp": expire,
        "type": "access",
        "tv": token_version,
    }
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def create_refresh_token(user_id: UUID, token_version: int = 0) -> str:
    """Создание refresh токена"""
    expire = datetime.utcnow() + timedelta(days=settings.refresh_token_expire_days)
    payload = {
        "sub": str(user_id),
        "exp": expire,
        "type": "refresh",
        "tv": token_version,
    }
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def decode_token(token: str) -> dict | None:
    """
    Декодирование JWT токена.
    Возвращает payload или None если токен невалиден.
    """
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret_key,
            algorithms=[settings.jwt_algorithm]
        )
        return payload
    except PyJWTError:
        return None


def generate_random_token(length: int = 32) -> str:
    """Генерация случайного токена (для ссылок, отмены бронирования и т.д.)"""
    return secrets.token_urlsafe(length)


def verify_token_type(token: str, expected_type: str) -> dict | None:
    """
    Проверка токена с валидацией типа.
    Возвращает payload если токен валиден и типа expected_type, иначе None.
    """
    payload = decode_token(token)
    if payload and payload.get("type") == expected_type:
        return payload
    return None

