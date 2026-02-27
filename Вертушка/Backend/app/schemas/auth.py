"""
Схемы для аутентификации
"""
from uuid import UUID
from pydantic import BaseModel, EmailStr, Field


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
    new_password: str = Field(..., min_length=8, max_length=100)

