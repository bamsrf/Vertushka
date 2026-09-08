"""
Схемы remote config — force-update gate и kill-switch.
См. app/services/app_config.py.
"""
from typing import Literal

from pydantic import BaseModel, Field, field_validator

Platform = Literal["ios", "android"]


class PlatformConfig(BaseModel):
    """Платформенная часть конфига: гейт и ссылка на стор."""

    min_supported_version: str = Field(
        description="Минимальная версия приложения на этой платформе"
    )
    store_url: str = Field(description="Ссылка на приложение в сторе этой платформы")


class AppConfigResponse(BaseModel):
    """Ответ публичного GET /api/config — читает каждый холодный старт.

    Legacy-поля `min_supported_version` и `store_url` — контракт с iOS
    1.0.0/1.0.1, они всегда равны `platforms.ios`. Новые клиенты читают
    `platforms[Platform.OS]` и падают обратно на legacy (Mobile/lib/remoteConfig.ts).
    """

    min_supported_version: str = Field(
        description="Минимальная версия приложения (iOS, legacy). Ниже неё показываем блокирующий экран."
    )
    store_url: str = Field(description="Ссылка на приложение в App Store (iOS, legacy)")
    update_message: str = Field(description="Текст на экране принудительного обновления")
    flags: dict[str, bool] = Field(description="Kill-switch фич: имя → включена ли")
    platforms: dict[Platform, PlatformConfig] = Field(
        description="Гейт и ссылка на стор по платформам: ios, android"
    )


class FlagsUpdateRequest(BaseModel):
    """Частичное обновление флагов: передаём только те, что меняем."""

    flags: dict[str, bool] = Field(min_length=1)


class MinVersionUpdateRequest(BaseModel):
    version: str = Field(description="Версия вида 1.2.3")
    # Обязательно: бамп без платформы означал бы «всем сразу», а именно от
    # этого мы уходим — Android-инцидент не должен выгонять iOS.
    platform: Platform = Field(description="Платформа, для которой поднимаем планку")

    @field_validator("version")
    @classmethod
    def _validate(cls, v: str) -> str:
        parts = v.split(".")
        if len(parts) != 3 or not all(p.isdigit() for p in parts):
            raise ValueError("Ожидается версия вида 1.2.3")
        return v
