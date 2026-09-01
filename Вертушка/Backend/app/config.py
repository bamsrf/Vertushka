"""
Конфигурация приложения Вертушка
"""
from functools import lru_cache
from pydantic_settings import BaseSettings
from pydantic import Field

# Значения, с которыми приложение не имеет права работать вне debug. Дефолты
# полей + плейсхолдеры из .env.example: последние проходят проверку длины, но
# секретом не являются — их копируют в прод чаще, чем хотелось бы.
_FORBIDDEN_SECRETS = {
    "change-me-in-production",
    "your-super-secret-key-change-in-production",
    "your-jwt-secret-key-change-in-production",
    "test-secret",
    "secret",
    "changeme",
}
_MIN_SECRET_LEN = 32


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
    # Профиль дрипа. Дефолты — щадящий режим «есть живые юзеры»: ~10 req/min.
    # До релиза (DAU 0) на проде стоит агрессивный профиль через env:
    # HEADROOM=18, MAX_PER_RUN=35, PACE=1.0. Больше из тик-схемы не выжать:
    # peek считает скользящее 60с-окно, и после жирного прогона следующий
    # минутный тик видит окно занятым — устоявшийся темп ≈ (55-headroom)/2
    # в минуту, т.е. ~18 req/min ≈ 26 тыс. обложек/день. ПЕРЕД РЕЛИЗОМ в
    # App Store env убрать (откат на дефолты) — COVERS_RATE_LIMIT_STRATEGY.md.
    #
    # Границы — это защита, не бюрократия: контейнер падает на старте вместо
    # тихого воспроизведения инцидентов.
    #  - headroom ge=16: лимитер вообще не обслуживает фоновые запросы при
    #    free <= INTERACTIVE_RESERVE (15, rate_limiter.py) — headroom ниже
    #    заставляет дрип стрелять в закрытую дверь, ловить таймауты и
    #    выжигать строки очереди через cover_checked_at.
    #  - pace ge=1.0: Discogs считает скользящее окно 60/min, burst из
    #    bucket'а уже давал постоянные 429 (2026-07-03).
    cover_drip_headroom: int = Field(default=35, ge=16, le=54, alias="COVER_DRIP_HEADROOM")
    cover_drip_max_per_run: int = Field(default=10, ge=1, le=55, alias="COVER_DRIP_MAX_PER_RUN")
    cover_drip_pace_sec: float = Field(default=2.0, ge=1.0, alias="COVER_DRIP_PACE_SEC")

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
    # offer_clicks. См. docs/plans/market/CLICK_REDIRECTOR_AND_METRIKA.md §4.
    yandex_metrika_counter_id: str = Field(default="", alias="YANDEX_METRIKA_COUNTER_ID")

    # Блок «Поддержать проект» на публичных веб-страницах и страница /support.
    # Пусто = блок не рендерится, /support отдаёт 404.
    #
    # Дефолт — боевая ссылка CloudTips (она публичная, не секрет), чтобы прод
    # работал без правки .env. Переопределяется переменной окружения, если
    # понадобится вторая ссылка под другой источник трафика.
    #
    # ВАЖНО: ссылка живёт ТОЛЬКО в вебе. В мобильном приложении её быть не
    # должно — App Store Guideline 3.1.1 запрещает во всех сторфронтах, кроме
    # US, кнопки и внешние ссылки на оплату мимо IAP, а российский
    # External Purchase Link Entitlement стоит 27%. Веб-страница профиля к
    # сторам отношения не имеет. См. docs/plans/product/PLAN_SUPPORT_PROJECT.md.
    support_url: str = Field(
        default="https://pay.cloudtips.ru/p/f1fd0e22",
        alias="SUPPORT_URL",
    )
    # Публичный роадмап — открытые планы по приложению.
    support_plans_url: str = Field(
        default="https://timestripe.com/boards/sX8B5Keg/",
        alias="SUPPORT_PLANS_URL",
    )

    # Подтверждение владения сайтом для Google Search Console. Токен публичный
    # по своей природе — он и должен отдаваться любому, кто откроет файл; его
    # единственный смысл в том, что положить его в корень чужого домена нельзя.
    #
    # Нужен, чтобы видеть вердикт Safe Browsing: 2026-08-15 Chrome начал метить
    # /support как «опасный сайт» (сертификат при этом валиден — это репутация
    # URL, не TLS). Без подтверждённого домена причина и статус заявки на
    # пересмотр не видны вообще, чинишь вслепую.
    google_site_verification: str = Field(
        default="google7610363abc027b52.html",
        alias="GOOGLE_SITE_VERIFICATION",
    )

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
    # Содержимое .p8 (Sign in with Apple key из developer.apple.com). Нужен,
    # чтобы отзывать токен при удалении аккаунта — без него Apple реджектит
    # по 5.1.1(v). Переносы строк можно экранировать как \n.
    apple_private_key: str = Field(default="", alias="APPLE_PRIVATE_KEY")
    
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
    # ── S3-слой обложек (подготовка трека A, COVERS_S3_IMGPROXY_MILESTONE) ──
    # Дефолт выключен: пока бакета нет, dual-write в s3_covers — полный no-op
    # (boto3 даже не импортируется). Включение: заполнить переменные ниже,
    # прогнать app/scripts/sync_covers_to_s3 (миграция накопленного зеркала),
    # затем COVERS_S3_ENABLED=true + рестарт. Неполный конфиг при включённом
    # флаге НЕ роняет старт: s3_covers логирует error и живёт как выключенный
    # (обложка на диске важнее дубля в бакете).
    covers_s3_enabled: bool = Field(default=False, alias="COVERS_S3_ENABLED")
    s3_endpoint_url: str = Field(default="", alias="S3_ENDPOINT_URL")
    s3_region: str = Field(default="ru-1", alias="S3_REGION")
    s3_bucket_covers: str = Field(default="vertushka-covers", alias="S3_BUCKET_COVERS")
    s3_access_key_id: str = Field(default="", alias="S3_ACCESS_KEY_ID")
    s3_secret_access_key: str = Field(default="", alias="S3_SECRET_ACCESS_KEY")
    # ── Apple Music API (канал обложек #5, services/apple_music.py) ──
    # Пусто = канал выключен. Как получить ключ — докстринг apple_music.py.
    apple_music_team_id: str = Field(default="", alias="APPLE_MUSIC_TEAM_ID")
    apple_music_key_id: str = Field(default="", alias="APPLE_MUSIC_KEY_ID")
    apple_music_private_key_b64: str = Field(default="", alias="APPLE_MUSIC_PRIVATE_KEY_B64")
    # Дневной бюджет скачиваний КАРТИНОК с хостов Discogs (i.discogs.com).
    # У Discogs неофициальный потолок ~1000 изображений/сутки на IP, дальше
    # 403 на всё — включая обложки, которые видят живые пользователи. 800
    # оставляет запас на ручные refresh, ретраи и погрешность счётчика.
    # Учёт — Redis-счётчик в cover_storage (discogs_img:{YYYY-MM-DD}).
    discogs_img_daily_budget: int = Field(default=800, alias="DISCOGS_IMG_DAILY_BUDGET")
    # Ночной перегрев мелких мастеров (cover_upgrade_tasks).
    #
    # Замер на проде (2026-08-13): 92 кандидата за 432с = ~4.7с на штуку. Цена не
    # в нашем коде, а в троттлах источников: MusicBrainz 1 rps, iTunes 3.1с на
    # запрос. Кандидат, для которого CAA ничего не знает, проходит всю лестницу
    # и упирается в самый медленный конец.
    #
    # Отсюда 2 часа, а не 30 минут: при 1800с прогон брал бы ~380 записей за ночь
    # и накопленные 13k разбирались бы больше месяца. При 7200с — ~1500 за ночь,
    # то есть около девяти ночей. Запускается в 03:40, к 05:40 заканчивается,
    # до метрики покрытия в 06:15 не доходит; load average ночью 0.00.
    cover_upgrade_enabled: bool = Field(default=True, alias="COVER_UPGRADE_ENABLED")
    cover_upgrade_batch: int = Field(default=2000, alias="COVER_UPGRADE_BATCH")
    cover_upgrade_max_seconds: int = Field(default=7200, alias="COVER_UPGRADE_MAX_SECONDS")
    # Метрика покрытия обложек (cover_coverage_tasks). Пол — абсолютный порог
    # доли in_stock matched-листингов с рабочей обложкой; ниже → алерт.
    # Дефолт консервативный: подстроить под реальный базовый уровень после
    # первого снапшота в /health/covers, чтобы не крикнуть волками.
    cover_coverage_min_ratio: float = Field(default=0.60, alias="COVER_COVERAGE_MIN_RATIO")
    # Просадка market-покрытия к прошлому снапшоту (в п.п.), выше которой алерт.
    cover_coverage_alert_drop_pp: float = Field(default=5.0, alias="COVER_COVERAGE_ALERT_DROP_PP")
    # Ночное обновление цен (update_prices_batch). 50 записей в сутки на всю
    # базу — это де-факто «цен нет»: одна импортированная коллекция в 400
    # пластинок занимала бы очередь на восемь суток, а их несколько. Разово
    # поднимать батч бессмысленно без второго рычага — частоты, поэтому джоба
    # теперь ходит каждые 30 минут (см. main.py), а батч задаёт её потолок за
    # проход. 200 × 48 прогонов ≈ 9600 записей в сутки при лимите app-токена
    # 60 req/min (то есть 86 400/сутки) — запас в девять раз.
    price_batch_size: int = Field(default=200, alias="PRICE_BATCH_SIZE")
    # Потолок записей за один проход воркера дозагрузки (price_backfill).
    # Идёт под личным токеном юзера: 60 req/min, прогон раз в минуту, поэтому
    # 50 за проход держится заведомо ниже лимита даже с ретраями.
    price_backfill_batch_size: int = Field(default=50, alias="PRICE_BACKFILL_BATCH_SIZE")
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
    # Короткий стартовый holding-TTL (в днях) для АНОНИМНОЙ неподтверждённой брони
    # (booked_by_user_id IS NULL, verification OFF). 0 = выключено = прежние 60 дней.
    # Смысл: griefer с ротацией email держит пункт не 60 дней, а N — истёкшую бронь
    # снимает почасовой auto_release_expired_bookings. Зарегистрированные дарители и
    # флоу с email-верификацией не затрагиваются. Дефолт безопасный (0), чтобы не
    # ломать честный «подарил без регистрации»; на проде включать осознанно (напр. 14).
    gift_booking_anon_hold_days: int = Field(default=0, alias="GIFT_BOOKING_ANON_HOLD_DAYS")

    # ── Remote config: force-update gate ────────────────────────────────────
    # Дефолт для GET /api/config. Поднимается на лету через
    # PUT /api/admin/config/min-version/ — без деплоя. См. services/app_config.py
    min_supported_app_version: str = Field(default="1.0.0", alias="MIN_SUPPORTED_APP_VERSION")
    # Канонический адрес карточки — ровно тот, что Apple отдаёт в trackViewUrl
    # (itunes.apple.com/lookup?id=6774999020&country=ru), только без ?uo=4.
    # Короткие формы (без витрины и без слага) Apple доводит до него редиректом,
    # и на этом редиректе ловили «An Error Occurred» вместо приложения: без
    # /ru/ витрина выбирается по гео гостя, а без слага страница доезжает не
    # везде. Правится тут — значение уходит и в CTA публичного профиля, и
    # мобилке в /api/config как цель force-update.
    app_store_url: str = Field(
        default=(
            "https://apps.apple.com/ru/app/"
            "%D0%B2%D0%B5%D1%80%D1%82%D1%83%D1%88%D0%BA%D0%B0-"
            "%D0%BA%D0%BE%D0%BB%D0%BB%D0%B5%D0%BA%D1%86%D0%B8%D1%8F-"
            "%D0%B2%D0%B8%D0%BD%D0%B8%D0%BB%D0%B0/id6774999020"
        ),
        alias="APP_STORE_URL",
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

    def secret_problems(self) -> list[str]:
        """Список претензий к секретам. Пустой — всё в порядке.

        Чистая функция без исключения намеренно: поднимать ValueError внутри
        pydantic-валидатора нельзя, потому что ValidationError печатает
        `input_value` со значениями конфига, и обрезок этого дампа уехал бы в
        docker-логи при каждом падении старта. Сообщение оператору собирает
        assert_secrets_ok() ниже — там мы контролируем текст целиком.

        Вне debug пустой или дефолтный JWT_SECRET_KEY недопустим: раньше его
        пропажа (опечатка в .env, потерянная переменная при пересборке, новый
        инстанс с чистым окружением) означала тихий старт с публично известным
        «change-me-in-production», а дальше кто угодно подписывает себе токен
        на любой sub и tv, включая is_staff. См. SECURITY_AUDIT_PRERELEASE §S5.
        """
        if self.debug:
            return []

        problems: list[str] = []
        for field in ("jwt_secret_key", "secret_key"):
            value = getattr(self, field) or ""
            env_name = field.upper()
            if value.strip().lower() in _FORBIDDEN_SECRETS:
                problems.append(f"{env_name} оставлен дефолтным или плейсхолдерным")
            elif len(value) < _MIN_SECRET_LEN:
                # Длину назвать можно, значение — нет.
                problems.append(
                    f"{env_name} короче {_MIN_SECRET_LEN} символов (сейчас {len(value)})"
                )
        return problems

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"


@lru_cache()
def get_settings() -> Settings:
    """Получение настроек приложения (с кэшированием)"""
    return Settings()


class InsecureConfigError(RuntimeError):
    """Конфигурация непригодна для прода. Текст безопасно печатать в логи."""


def assert_secrets_ok(settings: Settings | None = None) -> None:
    """Гейт старта: падаем шумно, вместо того чтобы работать дырявыми.

    Зовётся из main.py до создания приложения. Падение чинится за минуту;
    тихий старт с известным секретом не чинится никогда, потому что о нём
    никто не узнаёт.
    """
    settings = settings or get_settings()
    problems = settings.secret_problems()
    if not problems:
        return
    raise InsecureConfigError(
        "Небезопасная конфигурация, старт отменён:\n  - "
        + "\n  - ".join(problems)
        + "\n\nСгенерировать значение: openssl rand -hex 32"
        + "\nЛокальная разработка и тесты: DEBUG=true"
    )

