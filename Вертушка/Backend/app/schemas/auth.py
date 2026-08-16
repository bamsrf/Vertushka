"""
Схемы для аутентификации
"""
from uuid import UUID
from pydantic import BaseModel, EmailStr, Field

from app.schemas.user import NewPassword


class Token(BaseModel):
    """Токен доступа"""
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class TokenPayload(BaseModel):
    """Payload JWT токена"""
    sub: UUID  # user_id
    exp: int   # expiration time
    type: str  # "access" или "refresh"


class RefreshToken(BaseModel):
    """Схема для обновления токена"""
    refresh_token: str


class AppleSignIn(BaseModel):
    """Схема для Apple Sign In"""
    identity_token: str
    authorization_code: str
    user_identifier: str
    email: str | None = None
    full_name: str | None = None


class GoogleSignIn(BaseModel):
    """Схема для Google Sign In"""
    id_token: str


class ForgotPasswordRequest(BaseModel):
    """Запрос на сброс пароля"""
    email: EmailStr


class VerifyResetCodeRequest(BaseModel):
    """Проверка кода сброса"""
    email: EmailStr
    code: str = Field(..., min_length=6, max_length=6)


class ResetPasswordRequest(BaseModel):
    """Установка нового пароля"""
    reset_token: str
    # Тот же тип, что при регистрации: предел bcrypt в 72 байта (§S19).
    new_password: NewPassword


class RestoreAccountRequest(BaseModel):
    """Запрос на восстановление удалённого аккаунта"""
    restore_token: str

