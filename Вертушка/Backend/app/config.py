"""
Конфигурация приложения Вертушка
"""
from functools import lru_cache
from pydantic_settings import BaseSettings
from pydantic import Field


class Settings(BaseSettings):
    """Настройки приложения"""
    
    # Основные настройки
    app_name: str = Field(default="Вертушка", alias="APP_NAME")
    app_version: str = Field(default="1.0.0", alias="APP_VERSION")
    debug: bool = Field(default=False, alias="DEBUG")
    secret_key: str = Field(default="change-me-in-production", alias="SECRET_KEY")
    
    # База данных
    database_url: str = Field(
        default="postgresql+asyncpg://postgres:postgres@localhost:5432/recordscanner",
        alias="DATABASE_URL"
    )
    
    # JWT настройки
    jwt_secret_key: str = Field(default="change-me-in-production", alias="JWT_SECRET_KEY")
    jwt_algorithm: str = Field(default="HS256", alias="JWT_ALGORITHM")
    access_token_expire_minutes: int = Field(default=43200, alias="ACCESS_TOKEN_EXPIRE_MINUTES")  # 30 дней
    refresh_token_expire_days: int = Field(default=90, alias="REFRESH_TOKEN_EXPIRE_DAYS")  # 90 дней
    
    # Discogs API
    discogs_api_key: str = Field(default="", alias="DISCOGS_API_KEY")
    discogs_api_secret: str = Field(default="", alias="DISCOGS_API_SECRET")
    discogs_token: str = Field(default="", alias="DISCOGS_TOKEN")
    discogs_user_agent: str = Field(default="VertushkaApp/1.0", alias="DISCOGS_USER_AGENT")
    
    # OpenAI API (распознавание обложки)
    openai_api_key: str = Field(default="", alias="OPENAI_API_KEY")

    # Apple Sign In
    apple_client_id: str = Field(default="", alias="APPLE_CLIENT_ID")
    apple_team_id: str = Field(default="", alias="APPLE_TEAM_ID")
    apple_key_id: str = Field(default="", alias="APPLE_KEY_ID")
    
    # Google Sign In
    google_client_id: str = Field(default="", alias="GOOGLE_CLIENT_ID")
    google_client_secret: str = Field(default="", alias="GOOGLE_CLIENT_SECRET")
    
    # Email настройки (Yandex SMTP)
    smtp_host: str = Field(default="smtp.yandex.ru", alias="SMTP_HOST")
    smtp_port: int = Field(default=465, alias="SMTP_PORT")
    smtp_user: str = Field(default="", alias="SMTP_USER")
    smtp_password: str = Field(default="", alias="SMTP_PASSWORD")
    email_from: str = Field(default="", alias="EMAIL_FROM")
    
    # Наценка на винил для РФ (доставка + таможня + маржа)
    ru_vinyl_markup: float = Field(default=2.5, alias="RU_VINYL_MARKUP")

    # Sentry
    sentry_dsn: str = Field(default="", alias="SENTRY_DSN")

    # URL приложения
    app_url: str = Field(default="http://localhost:8000", alias="APP_URL")
    frontend_url: str = Field(default="https://recordscanner.app", alias="FRONTEND_URL")
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"


@lru_cache()
def get_settings() -> Settings:
    """Получение настроек приложения (с кэшированием)"""
    return Settings()

