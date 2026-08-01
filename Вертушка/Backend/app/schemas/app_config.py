"""
Схемы remote config — force-update gate и kill-switch.
См. app/services/app_config.py.
"""
from pydantic import BaseModel, Field, field_validator


class AppConfigResponse(BaseModel):
    """Ответ публичного GET /api/config — читает каждый холодный старт."""

    min_supported_version: str = Field(
        description="Минимальная версия приложения. Ниже неё показываем блокирующий экран."
    )
    store_url: str = Field(description="Ссылка на приложение в App Store")
    update_message: str = Field(description="Текст на экране принудительного обновления")
    flags: dict[str, bool] = Field(description="Kill-switch фич: имя → включена ли")


class FlagsUpdateRequest(BaseModel):
    """Частичное обновление флагов: передаём только те, что меняем."""

    flags: dict[str, bool] = Field(min_length=1)


class MinVersionUpdateRequest(BaseModel):
    version: str = Field(description="Версия вида 1.2.3")

    @field_validator("version")
    @classmethod
    def _validate(cls, v: str) -> str:
        parts = v.split(".")
        if len(parts) != 3 or not all(p.isdigit() for p in parts):
            raise ValueError("Ожидается версия вида 1.2.3")
        return v
