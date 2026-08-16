"""
Схемы для пользователей
"""
from datetime import datetime
from typing import Annotated
from uuid import UUID
from pydantic import AfterValidator, BaseModel, EmailStr, Field, ConfigDict, model_validator

from app.utils.security import validate_password_length

# Пароль, который УСТАНАВЛИВАЕТСЯ. max_length оставлен в символах для быстрой
# отсечки, реальный предел — 72 байта, его считает валидатор (§S19).
NewPassword = Annotated[
    str,
    Field(min_length=8, max_length=100),
    AfterValidator(validate_password_length),
]


class UserBase(BaseModel):
    """Базовая схема пользователя"""
    email: EmailStr
    username: str = Field(..., min_length=3, max_length=50)


class UserCreate(UserBase):
    """Схема для создания пользователя"""
    password: NewPassword
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
    username: str | None = Field(None, min_length=3, max_length=50, pattern=r'^[a-z0-9_]+$')
    display_name: str | None = Field(None, max_length=100)
    bio: str | None = Field(None, max_length=500)
    avatar_url: str | None = None


class UsernameCheckResponse(BaseModel):
    """Ответ проверки доступности username"""
    available: bool
    reason: str | None = None  # "taken" | "invalid" | "too_short"


class UserResponse(BaseModel):
    """Полная схема пользователя (для владельца)"""
    model_config = ConfigDict(from_attributes=True)
    
    id: UUID
    email: EmailStr | None  # None для аккаунтов через Discogs-логин
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
    # Приватные профили: статус заявки на подписку от current_user → этого пользователя.
    # 'none'   — заявки нет (или профиль публичный — кнопка «Подписаться»)
    # 'pending' — заявка отправлена, ждём подтверждения (кнопка «Запрос отправлен»)
    follow_request_status: str = "none"
    is_private_profile: bool = False


class NotificationSettingsResponse(BaseModel):
    """Настройки уведомлений"""
    model_config = ConfigDict(from_attributes=True)

    notify_new_follower: bool = True
    notify_gift_booked: bool = True
    notify_gift_confirmed: bool = True
    notify_app_updates: bool = True
    notify_follow_request: bool = True
    notify_wishlist_in_stock: bool = True
    notify_achievement: bool = True
    notify_milestone: bool = True

    quiet_hours_enabled: bool = False
    quiet_hours_start: str | None = None  # "HH:MM"
    quiet_hours_end: str | None = None  # "HH:MM"


class NotificationSettingsUpdate(BaseModel):
    """Обновление настроек уведомлений"""
    notify_new_follower: bool | None = None
    notify_gift_booked: bool | None = None
    notify_gift_confirmed: bool | None = None
    notify_app_updates: bool | None = None
    notify_follow_request: bool | None = None
    notify_wishlist_in_stock: bool | None = None
    notify_achievement: bool | None = None
    notify_milestone: bool | None = None

    quiet_hours_enabled: bool | None = None
    quiet_hours_start: str | None = None  # "HH:MM"
    quiet_hours_end: str | None = None  # "HH:MM"


class PushTokenUpdate(BaseModel):
    """Сохранение push token"""
    push_token: str = Field(..., max_length=255)

