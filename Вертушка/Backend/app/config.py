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
    access_token_expire_minutes: int = Field(default=30, alias="ACCESS_TOKEN_EXPIRE_MINUTES")  # 30 минут (refresh token живёт 90 дней)
    refresh_token_expire_days: int = Field(default=90, alias="REFRESH_TOKEN_EXPIRE_DAYS")  # 90 дней
    
    # Discogs API
    discogs_api_key: str = Field(default="", alias="DISCOGS_API_KEY")
    discogs_api_secret: str = Field(default="", alias="DISCOGS_API_SECRET")
    discogs_token: str = Field(default="", alias="DISCOGS_TOKEN")
    discogs_user_agent: str = Field(default="VertushkaApp/1.0", alias="DISCOGS_USER_AGENT")
    discogs_oauth_callback_url: str = Field(default="https://api.vinyl-vertushka.ru/api/auth/discogs/callback", alias="DISCOGS_OAUTH_CALLBACK_URL")
    discogs_oauth_app_redirect: str = Field(default="vertushka://discogs-callback", alias="DISCOGS_OAUTH_APP_REDIRECT")
    discogs_token_encryption_key: str = Field(default="", alias="DISCOGS_TOKEN_ENCRYPTION_KEY")
    # Drip-прогрев обложек простаивающими токенами app-bucket (cover_drip_tasks)
    cover_drip_enabled: bool = Field(default=True, alias="COVER_DRIP_ENABLED")

    # Yandex-native матчинг (шаг 5.5): создавать записи вне Discogs из Yandex.
    # OFF по умолчанию — включать осознанно, мгновенный откат без деплоя.
    yandex_match_enabled: bool = Field(default=False, alias="YANDEX_MATCH_ENABLED")

    # Публичный домен (не API-хост): на нём живут HTML-страницы из app/web/ и
    # редиректор переходов `/go/...`. Без слеша на конце.
    public_base_url: str = Field(default="https://vinyl-vertushka.ru", alias="PUBLIC_BASE_URL")

    # Счётчик Яндекс.Метрики для ПУБЛИЧНЫХ веб-страниц (профиль, вишлист).
    # Пусто = счётчик не встраивается вообще. Включать только после того, как в
    # privacy.html появится раздел про аналитику и куки: сейчас политика
    # конфиденциальности третьих лиц-аналитиков не упоминает.
    # Мобильные переходы Метрика не видит принципиально — они считаются в
    # offer_clicks. См. docs/plans/CLICK_REDIRECTOR_AND_METRIKA.md §4.
    yandex_metrika_counter_id: str = Field(default="", alias="YANDEX_METRIKA_COUNTER_ID")

    # OpenAI API (распознавание обложки)
    openai_api_key: str = Field(default="", alias="OPENAI_API_KEY")

    # Spotify API (enrichment user-submitted records, Client Credentials flow).
    # Пустые креды → enrichment graceful no-op (юзер вводит всё руками).
    spotify_client_id: str = Field(default="", alias="SPOTIFY_CLIENT_ID")
    spotify_client_secret: str = Field(default="", alias="SPOTIFY_CLIENT_SECRET")
    # api.spotify.com гео-блокирует РФ-IP (403). Прокси в разрешённой стране.
    # Формат: http://user:pass@host:port или socks5://host:port. Пусто → напрямую.
    spotify_proxy_url: str = Field(default="", alias="SPOTIFY_PROXY_URL")

    # Apple Sign In
    apple_client_id: str = Field(default="", alias="APPLE_CLIENT_ID")
    apple_team_id: str = Field(default="", alias="APPLE_TEAM_ID")
    apple_key_id: str = Field(default="", alias="APPLE_KEY_ID")
    
    # Google Sign In
    google_client_id: str = Field(default="", alias="GOOGLE_CLIENT_ID")
    google_client_secret: str = Field(default="", alias="GOOGLE_CLIENT_SECRET")
    
    # Email — Resend HTTP API приоритетный канал; SMTP остаётся как fallback для dev/локалки.
    resend_api_key: str = Field(default="", alias="RESEND_API_KEY")
    smtp_host: str = Field(default="smtp.yandex.ru", alias="SMTP_HOST")
    smtp_port: int = Field(default=465, alias="SMTP_PORT")
    smtp_user: str = Field(default="", alias="SMTP_USER")
    smtp_password: str = Field(default="", alias="SMTP_PASSWORD")
    email_from: str = Field(default="", alias="EMAIL_FROM")
    
    # Pricing формула — расчёт рублёвой цены из USD Discogs
    pricing_base_shipping_usd: float = Field(default=20.0, alias="PRICING_BASE_SHIPPING_USD")
    pricing_import_overhead_pct: float = Field(default=0.20, alias="PRICING_IMPORT_OVERHEAD_PCT")
    pricing_local_overhead_pct: float = Field(default=0.30, alias="PRICING_LOCAL_OVERHEAD_PCT")
    pricing_customs_threshold_usd: float = Field(default=220.0, alias="PRICING_CUSTOMS_THRESHOLD_USD")
    pricing_customs_rate: float = Field(default=0.15, alias="PRICING_CUSTOMS_RATE")

    # Redis
    redis_url: str = Field(default="redis://localhost:6379/0", alias="REDIS_URL")

    # Sentry
    sentry_dsn: str = Field(default="", alias="SENTRY_DSN")

    # URL приложения
    app_url: str = Field(default="http://localhost:8000", alias="APP_URL")
    frontend_url: str = Field(default="https://recordscanner.app", alias="FRONTEND_URL")

    # Хранение обложек
    covers_dir: str = Field(default="uploads/covers", alias="COVERS_DIR")
    # Публичная база зеркала обложек: сетка артиста и поиск отдают
    # {base}/{id}.jpg вместо прямых ссылок на внешние CDN (archive.org из РФ
    # отвечает секундами). nginx: статика → @covers_fallback.
    public_covers_base: str = Field(
        default="https://api.vinyl-vertushka.ru/covers", alias="PUBLIC_COVERS_BASE",
    )
    covers_max_cache_mb: int = Field(default=5000, alias="COVERS_MAX_CACHE_MB")
    # Ночной перегрев мелких мастеров (cover_upgrade_tasks). Батч 1000 при ~13K
    # помеченных = около двух недель на разбор накопленного; wall-clock 30 мин
    # держит прогон в границах, даже если партия уходит на медленный iTunes.
    cover_upgrade_enabled: bool = Field(default=True, alias="COVER_UPGRADE_ENABLED")
    cover_upgrade_batch: int = Field(default=1000, alias="COVER_UPGRADE_BATCH")
    cover_upgrade_max_seconds: int = Field(default=1800, alias="COVER_UPGRADE_MAX_SECONDS")
    # Метрика покрытия обложек (cover_coverage_tasks). Пол — абсолютный порог
    # доли in_stock matched-листингов с рабочей обложкой; ниже → алерт.
    # Дефолт консервативный: подстроить под реальный базовый уровень после
    # первого снапшота в /health/covers, чтобы не крикнуть волками.
    cover_coverage_min_ratio: float = Field(default=0.60, alias="COVER_COVERAGE_MIN_RATIO")
    # Просадка market-покрытия к прошлому снапшоту (в п.п.), выше которой алерт.
    cover_coverage_alert_drop_pp: float = Field(default=5.0, alias="COVER_COVERAGE_ALERT_DROP_PP")
    internal_api_token: str = Field(default="", alias="INTERNAL_API_TOKEN")

    @property
    def public_api_base(self) -> str:
        """Публичный https-хост API (без хвоста пути).

        Выводится из `public_covers_base` (…/covers) — единый источник правды
        для абсолютных ссылок на статику (`/uploads/...`) в push-картинках.
        """
        base = self.public_covers_base.rstrip("/")
        if base.endswith("/covers"):
            base = base[: -len("/covers")]
        return base

    # Анти-фрод для бронирования подарков
    gift_booking_per_ip_limit: int = Field(default=5, alias="GIFT_BOOKING_PER_IP_LIMIT")
    gift_booking_per_ip_window_minutes: int = Field(default=60, alias="GIFT_BOOKING_PER_IP_WINDOW_MINUTES")
    gift_booking_per_email_active_limit: int = Field(default=3, alias="GIFT_BOOKING_PER_EMAIL_ACTIVE_LIMIT")
    # Email-верификация дарителя (под флагом — включать только когда SMTP стабилен)
    gift_booking_require_email_verification: bool = Field(default=False, alias="GIFT_BOOKING_REQUIRE_EMAIL_VERIFICATION")
    gift_booking_verification_window_hours: int = Field(default=24, alias="GIFT_BOOKING_VERIFICATION_WINDOW_HOURS")

    # ── Remote config: force-update gate ────────────────────────────────────
    # Дефолт для GET /api/config. Поднимается на лету через
    # PUT /api/admin/config/min-version/ — без деплоя. См. services/app_config.py
    min_supported_app_version: str = Field(default="1.0.0", alias="MIN_SUPPORTED_APP_VERSION")
    app_store_url: str = Field(
        default="https://apps.apple.com/app/id6774999020", alias="APP_STORE_URL",
    )
    force_update_message: str = Field(
        default="Вышла новая версия Вертушки. Обнови приложение, чтобы продолжить.",
        alias="FORCE_UPDATE_MESSAGE",
    )

    # ── Remote config: kill-switch фич ──────────────────────────────────────
    # Дефолты. Мгновенный флип — PUT /api/admin/config/flags/ (Redis-оверрайд).
    # Выключил на инцидент через API и это надолго → продублируй здесь.
    feature_vision_scan_enabled: bool = Field(default=True, alias="FEATURE_VISION_SCAN_ENABLED")
    feature_market_enabled: bool = Field(default=True, alias="FEATURE_MARKET_ENABLED")
    feature_shop_scrapers_enabled: bool = Field(default=True, alias="FEATURE_SHOP_SCRAPERS_ENABLED")
    feature_user_submitted_enabled: bool = Field(default=True, alias="FEATURE_USER_SUBMITTED_ENABLED")

    # ── Дневные квоты на дорогие операции ───────────────────────────────────
    # Распознавание обложки стоит денег за вызов. Per-user режет абьюзера,
    # глобальный — последняя линия перед разорительным счётом от OpenAI.
    # См. services/quota.py
    vision_scan_daily_limit_per_user: int = Field(
        default=50, alias="VISION_SCAN_DAILY_LIMIT_PER_USER",
    )
    vision_scan_daily_limit_global: int = Field(
        default=2000, alias="VISION_SCAN_DAILY_LIMIT_GLOBAL",
    )

    # ── Алармы в Telegram ───────────────────────────────────────────────────
    # Пустой токен → алармы graceful no-op (как spotify_*). См. services/alerts.py
    telegram_bot_token: str = Field(default="", alias="TELEGRAM_BOT_TOKEN")
    telegram_alert_chat_id: str = Field(default="", alias="TELEGRAM_ALERT_CHAT_ID")
    telegram_alert_throttle_seconds: int = Field(default=300, alias="TELEGRAM_ALERT_THROTTLE_SECONDS")

    # ── Пороги здоровья (services/health_metrics.py) ────────────────────────
    # Ловят то, что не ловит аларм на исключения: 504 от таймаутов, ползучую
    # деградацию p99 без ошибок и шторм 429.
    health_window_seconds: int = Field(default=300, alias="HEALTH_WINDOW_SECONDS")
    # Ниже этого числа запросов доля ошибок — статистический шум.
    health_min_requests: int = Field(default=20, alias="HEALTH_MIN_REQUESTS")
    health_error_rate_threshold: float = Field(default=0.10, alias="HEALTH_ERROR_RATE_THRESHOLD")
    # 5с: обычный ответ укладывается в сотни мс, поиск на холодном Discogs —
    # в единицы секунд. Выше — уже не «медленно», а «сломано».
    health_p99_threshold_ms: float = Field(default=5000.0, alias="HEALTH_P99_THRESHOLD_MS")
    health_rate_limited_threshold: int = Field(default=50, alias="HEALTH_RATE_LIMITED_THRESHOLD")

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"


@lru_cache()
def get_settings() -> Settings:
    """Получение настроек приложения (с кэшированием)"""
    return Settings()

