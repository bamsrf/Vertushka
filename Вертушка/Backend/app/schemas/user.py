"""
Схемы для пользователей
"""
from datetime import datetime
from uuid import UUID
from pydantic import BaseModel, EmailStr, Field, ConfigDict, model_validator


class UserBase(BaseModel):
    """Базовая схема пользователя"""
    email: EmailStr
    username: str = Field(..., min_length=3, max_length=50)


class UserCreate(UserBase):
    """Схема для создания пользователя"""
    password: str = Field(..., min_length=8, max_length=100)
    display_name: str | None = Field(None, max_length=100)


class UserLogin(BaseModel):
    """Схема для входа (email или username)"""
    login: str | None = Field(None, min_length=1)
    email: str | None = None  # обратная совместимость
    password: str

    @model_validator(mode='after')
    def set_login_from_email(self) -> 'UserLogin':
        """Если пришёл email (старый формат) — копируем в login"""
        if not self.login and self.email:
            self.login = self.email
        return self


class UserUpdate(BaseModel):
    """Схема для обновления пользователя"""
    display_name: str | None = Field(None, max_length=100)
    bio: str | None = Field(None, max_length=500)
    avatar_url: str | None = None


class UserResponse(BaseModel):
    """Полная схема пользователя (для владельца)"""
    model_config = ConfigDict(from_attributes=True)
    
    id: UUID
    email: EmailStr
    username: str
    display_name: str | None
    avatar_url: str | None
    bio: str | None
    is_active: bool
    is_verified: bool
    created_at: datetime
    updated_at: datetime
    last_login_at: datetime | None


class UserPublicResponse(BaseModel):
    """Публичная схема пользователя (для других пользователей)"""
    model_config = ConfigDict(from_attributes=True)
    
    id: UUID
    username: str
    display_name: str | None
    avatar_url: str | None
    bio: str | None
    created_at: datetime


class UserWithStats(UserPublicResponse):
    """Пользователь со статистикой"""
    followers_count: int = 0
    following_count: int = 0
    collection_count: int = 0
    is_following: bool = False  # Подписан ли текущий пользователь

