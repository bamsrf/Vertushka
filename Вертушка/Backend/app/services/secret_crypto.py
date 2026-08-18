"""Шифрование сторонних токенов перед записью в БД (Fernet).

Общий модуль: Discogs oauth_token_secret, Apple refresh_token. Переменная
окружения исторически называется DISCOGS_TOKEN_ENCRYPTION_KEY — переименовывать
её нельзя, иначе прод перестанет читать уже сохранённые Discogs-секреты.
"""
import base64
import hashlib
from functools import lru_cache

from cryptography.fernet import Fernet, InvalidToken

from app.config import get_settings


@lru_cache()
def _fernet() -> Fernet:
    settings = get_settings()
    key = settings.discogs_token_encryption_key.strip()
    if key:
        return Fernet(key.encode())
    # Fallback: детерминированный ключ из jwt_secret_key. Для прода задавать
    # DISCOGS_TOKEN_ENCRYPTION_KEY явно (ротация jwt_secret_key иначе сделает
    # сохранённые секреты нечитаемыми).
    derived = hashlib.sha256(settings.jwt_secret_key.encode()).digest()
    return Fernet(base64.urlsafe_b64encode(derived))


def encrypt_secret(plaintext: str) -> str:
    return _fernet().encrypt(plaintext.encode()).decode()


def decrypt_secret(ciphertext: str) -> str | None:
    try:
        return _fernet().decrypt(ciphertext.encode()).decode()
    except (InvalidToken, ValueError):
        return None
