"""
Утилиты безопасности: хэширование паролей, JWT токены
"""
import asyncio
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


# bcrypt использует только первые 72 БАЙТА пароля, остальное отбрасывает молча.
# Проверено: hash_password('A'*100) успешно верифицируется паролем
# 'A'*72 + любой мусор. Для кириллицы порог вдвое ниже по символам — в UTF-8
# буква занимает 2 байта, то есть 40-символьная фраза «ПППП…» обрезается до 36
# символов, и две разные фразы с общим началом становятся взаимозаменяемыми.
# Для русскоязычного приложения это не теоретический случай.
BCRYPT_MAX_BYTES = 72


def validate_password_length(password: str) -> str:
    """Валидатор для схем, где пароль УСТАНАВЛИВАЕТСЯ (регистрация, сброс).

    Осознанно не применяется на входе: у существующих пользователей пароль мог
    быть длиннее, и bcrypt при проверке обрежет его ровно так же, как при
    создании, — вход продолжит работать. Добавить лимит и туда значило бы
    запереть этих людей снаружи. См. SECURITY_AUDIT_PRERELEASE.md §S19.
    """
    length = len(password.encode("utf-8"))
    if length > BCRYPT_MAX_BYTES:
        raise ValueError(
            f"Пароль слишком длинный: {length} байт при максимуме {BCRYPT_MAX_BYTES}. "
            "Кириллическая буква занимает два байта, поэтому предел — примерно "
            f"{BCRYPT_MAX_BYTES // 2} символов кириллицей или {BCRYPT_MAX_BYTES} латиницей."
        )
    return password


def hash_password(password: str) -> str:
    """Хэширование пароля"""
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Проверка пароля"""
    return pwd_context.verify(plain_password, hashed_password)


# bcrypt — это ~200-300мс чистого CPU. Прод крутится на ОДНОМ uvicorn-воркере
# (CLIP живёт в том же процессе), поэтому синхронный вызов из async-роута
# замораживает весь event loop: на время хэширования встают ВСЕ запросы, а не
# только логин. to_thread уводит расчёт в thread pool — GIL bcrypt отпускает
# внутри C-кода, loop продолжает крутиться. В async-коде использовать ТОЛЬКО
# эти обёртки; синхронные версии выше — для CLI-скриптов и module-level
# констант (см. _DUMMY_RESET_HASH в api/auth.py).


async def hash_password_async(password: str) -> str:
    """Хэширование пароля без блокировки event loop."""
    return await asyncio.to_thread(hash_password, password)


async def verify_password_async(plain_password: str, hashed_password: str) -> bool:
    """Проверка пароля без блокировки event loop."""
    return await asyncio.to_thread(verify_password, plain_password, hashed_password)


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

