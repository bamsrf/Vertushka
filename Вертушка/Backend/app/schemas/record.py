"""
Схемы для виниловых пластинок
"""
from datetime import datetime
from decimal import Decimal
from uuid import UUID
from pydantic import BaseModel, Field, ConfigDict, model_validator


class RecordBase(BaseModel):
    """Базовая схема пластинки"""
    title: str = Field(..., max_length=500)
    artist: str = Field(..., max_length=500)
    label: str | None = Field(None, max_length=255)
    year: int | None = Field(None, ge=1900, le=2100)
    country: str | None = Field(None, max_length=100)
    genre: str | None = Field(None, max_length=255)


class RecordCreate(RecordBase):
    """Схема для создания пластинки.

    НЕ ИСПОЛЬЗУЕТСЯ ни одним эндпоинтом и не должна использоваться в новом коде.
    Эндпоинт POST /api/records/, который её принимал, удалён: он splat'ил вход
    в модель (`Record(**data.model_dump())`), из-за чего запись создавалась
    мимо модерации — source='discogs', moderation_status='approved', без автора.
    Для пользовательских записей есть UserRecordCreate + POST /records/user/.

    Если понадобится серверное создание записи — присваивай поля явно и
    проставляй source/moderation_status/created_by_user_id сам; cover_image_url
    из клиентского запроса не брать (открытый редирект + SSRF, см.
    docs/plans/appstore/SECURITY_AUDIT_PRERELEASE.md §S2).
    """
    discogs_id: str | None = None
    discogs_master_id: str | None = None
    catalog_number: str | None = None
    style: str | None = None
    format_type: str | None = None
    format_description: str | None = None
    barcode: str | None = None
    cover_image_url: str | None = None
    thumb_image_url: str | None = None
    estimated_price_min: Decimal | None = None
    estimated_price_max: Decimal | None = None
    estimated_price_median: Decimal | None = None
    price_currency: str = "USD"
    discogs_data: dict | None = None
    tracklist: list | None = None


def is_flat_mirror(local_path: str | None) -> bool:
    """Зеркало лежит плоско в covers/ — значит адресуемо как /covers/{id}.jpg.

    Вложенные пути (covers/store/…, user_photos/…) отдаются только как
    /uploads/…: регекс nginx не пускает слэши в имя, а imgproxy-нарезка и мост
    работают лишь по плоскому имени.
    """
    if not local_path:
        return False
    name = local_path.removeprefix("covers/")
    return local_path.startswith("covers/") and "/" not in name


def build_cover_url(
    local_path: str | None, cached_at: datetime | None
) -> str | None:
    """URL зеркалированной обложки: /uploads/-путь плюс метка перезалива.

    Только для того, что мостом не отдать: вложенные пути и ручные фото. Для
    плоского зеркала URL строит bridge_cover_url — см. там, почему /uploads/
    для него хуже.

    Cache-bust по cover_cached_at обязателен: перезалив меняет файл по тому
    же пути, и без метки клиент (expo-image disk / nginx expires 7d) показал
    бы старую картинку.
    """
    if not local_path:
        return None
    base = local_path if local_path.startswith("/") else f"/uploads/{local_path}"
    if cached_at:
        base = f"{base}?v={int(cached_at.timestamp())}"
    return base


def bridge_cover_url(
    discogs_id: str | None,
    cover_image_url: str | None,
    cached_at: datetime | None = None,
    local_path: str | None = None,
) -> str | None:
    """Путь `/covers/{discogs_id}.jpg` — и для зеркала в бакете, и self-healing.

    Две разные ситуации приводят сюда, и различает их `cached_at`.

    1. Зеркало ЕСТЬ, но `cover_local_path` пуст (`cached_at` не пуст). Так
       выглядит запись, у которой LRU выселила локальную копию: с S3 эвикция
       гасит только указатель на диск, файл жив в бакете и отдаётся через
       `@covers_s3`. Тир-гейт здесь не применяется: зеркало уже прошло его при
       записи, а `cover_image_url` может быть и пустым (CAA/Deezer), и мелким —
       к содержимому файла это отношения не имеет. Ровно та же логика, что в
       `_COVER_BRIDGE` витрины (api/market.py): третий источник наравне с
       local/url. Без неё карточка релиза для выселенной обложки отдавала
       `cover_url=None` и клиент падал на i.discogs.com.

    1б. Зеркало лежит плоско на диске (`local_path` = covers/{id}.jpg). Мост
       отдаёт его тем же путём, а не через /uploads/: так URL совпадает с
       витриной (общий кэш), и клиентский sizedCoverUrl умеет его нарезать —
       он ищет только /covers/{name}.jpg. С /uploads/-путём карточка тянула
       полный мастер вместо ступени.

    2. Зеркала ЕЩЁ нет (`cached_at` пуст). Тогда мост self-healing: nginx не
       найдёт файл, уйдёт в `@covers_fallback` → get_cover → 302 на оригинал +
       фоновое зеркалирование, и второй заход отдаёт уже наш файл. Из РФ
       i.discogs.com недоступен/медленный: на реальном Android (10.09.2026)
       коллекция из 71 записи, где зеркало было только у 5, минутами висела
       серыми blurhash'ами. Мостим только то, что зеркало примет: числовой id и
       мастер-грейд URL — мелкое тир-гейт не пустит, и `/covers/{id}.jpg` вечно
       был бы холодным 302.

    Метка версии обязательна везде, где она известна: именно она делает
    `immutable` в nginx безопасным (зеркало перезаписывает мелкий мастер лучшим
    источником) и — не менее важно — даёт тот же URL, что уже отдала витрина.
    Без неё карточка просила `/covers/{id}.jpg`, а плитка Маркета
    `/covers/w/640/{id}.jpg?v=…`: разные ключи кэша, одна и та же картинка
    качается дважды и живёт неделю вместо года.
    """
    if not discogs_id or not str(discogs_id).isdigit():
        return None

    # Локальная копия есть, но лежит НЕ плоско (covers/store/…) — мостом такое
    # не отдать: регекс nginx не пускает слэши в имя. Пусть строит /uploads/.
    if local_path and not is_flat_mirror(local_path):
        return None

    if cached_at is None:
        if not cover_image_url or not cover_image_url.startswith("http"):
            return None
        from app.services.cover_quality import is_thumb_grade

        if is_thumb_grade(cover_image_url):
            return None
        return f"/covers/{discogs_id}.jpg"

    return f"/covers/{discogs_id}.jpg?v={int(cached_at.timestamp())}"


class RecordResponse(BaseModel):
    """Полная схема пластинки"""
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    source: str = "discogs"  # 'discogs' | 'store' | 'user' — store/pending нельзя в коллекцию
    moderation_status: str = "approved"  # pending/approved/rejected/merged (user-records)
    created_by_user_id: UUID | None = None  # автор user-record (§11 edit-gate на фронте)
    discogs_id: str | None
    discogs_master_id: str | None
    title: str
    artist: str
    label: str | None
    catalog_number: str | None
    year: int | None
    country: str | None
    genre: str | None
    style: str | None
    format_type: str | None
    format_description: str | None
    vinyl_color_raw: str | None = None
    # Цвет винила для показа (прототип/чип) — уже разрешён на бэке: цвет реального
    # in-stock оффера этого релиза (exact > album, самый дешёвый), иначе фолбэк на
    # vinyl_color_raw из Discogs. Позволяет Mobile отрисовать верный цвет с первого
    # кадра, без второго запроса и «моргания». None → используй vinyl_color_raw.
    display_vinyl_color: str | None = None
    barcode: str | None
    estimated_price_min: float | None
    estimated_price_max: float | None
    estimated_price_median: float | None
    price_currency: str
    estimated_price_min_rub: float | None = None
    estimated_price_median_rub: float | None = None
    estimated_price_max_rub: float | None = None
    usd_rub_rate: float | None = None
    ru_markup: float | None = None
    # marketplace_active | marketplace_historical | discogs_raw | discogs_import_estimate
    price_source: str | None = None
    price_offers_count: int | None = None
    cover_image_url: str | None
    thumb_image_url: str | None
    cover_url: str | None = None  # локальный URL (/uploads/covers/...) или fallback на Discogs
    cover_local_path: str | None = Field(default=None, exclude=True)
    # blurhash обложки — клиент рисует blur-плейсхолдер, пока грузится full-res.
    blurhash: str | None = None
    artist_id: str | None = None
    artist_thumb_image_url: str | None = None
    tracklist: list | None
    is_first_press: bool = False
    is_canon: bool = False
    is_collectible: bool = False
    is_limited: bool = False
    is_hot: bool = False
    created_at: datetime
    updated_at: datetime

    cover_cached_at: datetime | None = Field(default=None, exclude=True)

    @model_validator(mode="after")
    def _populate_cover_url(self) -> "RecordResponse":
        if not self.cover_url:
            # Мост ПЕРВЫМ, /uploads/ — только для того, что мостом не отдать.
            # Иначе зеркало на диске отдавалось как /uploads/covers/x.jpg, а
            # витрина то же самое — как /covers/x.jpg: разные ключи кэша, и
            # клиентский sizedCoverUrl (он ищет только /covers/{name}.jpg)
            # такой URL не режет вовсе — карточка тянула полный мастер.
            self.cover_url = bridge_cover_url(
                self.discogs_id, self.cover_image_url, self.cover_cached_at,
                local_path=self.cover_local_path,
            ) or build_cover_url(self.cover_local_path, self.cover_cached_at)
        return self


class RecordBrief(BaseModel):
    """Краткая схема пластинки (для списков)"""
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    source: str = "discogs"  # 'discogs' | 'store'
    discogs_id: str | None
    title: str
    artist: str
    artist_id: str | None = None
    artist_thumb_image_url: str | None = None
    year: int | None
    cover_image_url: str | None
    thumb_image_url: str | None
    cover_url: str | None = None  # локальный URL (/uploads/covers/...) или fallback на Discogs
    cover_local_path: str | None = Field(default=None, exclude=True)
    blurhash: str | None = None  # blur-плейсхолдер для сетки
    format_type: str | None = None
    estimated_price_median: float | None
    price_currency: str
    is_first_press: bool = False
    is_canon: bool = False
    is_collectible: bool = False
    is_limited: bool = False
    is_hot: bool = False

    cover_cached_at: datetime | None = Field(default=None, exclude=True)

    @model_validator(mode="after")
    def _populate_cover_url(self) -> "RecordBrief":
        if not self.cover_url:
            # Мост ПЕРВЫМ, /uploads/ — только для того, что мостом не отдать.
            # Иначе зеркало на диске отдавалось как /uploads/covers/x.jpg, а
            # витрина то же самое — как /covers/x.jpg: разные ключи кэша, и
            # клиентский sizedCoverUrl (он ищет только /covers/{name}.jpg)
            # такой URL не режет вовсе — карточка тянула полный мастер.
            self.cover_url = bridge_cover_url(
                self.discogs_id, self.cover_image_url, self.cover_cached_at,
                local_path=self.cover_local_path,
            ) or build_cover_url(self.cover_local_path, self.cover_cached_at)
        return self


class RecordSearchResult(BaseModel):
    """Результат поиска пластинки (от Discogs)"""
    discogs_id: str
    title: str
    artist: str
    label: str | None
    year: int | None
    country: str | None
    cover_image_url: str | None
    thumb_image_url: str | None
    format_type: str | None
    # Rarity-флаги — подмешиваются из локальной БД (если запись виделась раньше)
    # + on-the-fly is_limited по парсингу format_type. Дешёвые сигналы только.
    is_first_press: bool = False
    is_canon: bool = False
    is_collectible: bool = False
    is_limited: bool = False
    is_hot: bool = False
    # Визуальная близость фото к обложке (косинус CLIP, 0..1). None если re-rank не делался.
    match_score: float | None = None
    # Скан по штрихкоду: True — релиз действительно несёт отсканированный код,
    # False — издание-сиблинг того же мастера (другой год/страна/пресс).
    is_exact_match: bool = False


class RecordSearchResponse(BaseModel):
    """Ответ на поиск пластинок"""
    results: list[RecordSearchResult]
    total: int
    page: int
    per_page: int


class MasterSearchResult(BaseModel):
    """Результат поиска мастер-релиза (от Discogs)"""
    master_id: str
    title: str
    artist: str
    year: int | None = None
    main_release_id: str
    cover_image_url: str | None = None
    thumb_image_url: str | None = None
    release_type: str | None = None


class MasterVersion(BaseModel):
    """Версия (издание) мастер-релиза"""
    release_id: str
    title: str
    label: str | None = None
    catalog_number: str | None = None
    country: str | None = None
    year: int | None = None
    format: str | None = None
    major_formats: list[str] = []
    thumb_image_url: str | None = None
    cover_image_url: str | None = None
    # Community-счётчики из stats.community мастер-versions response. Приходят
    # бесплатно вместе со списком версий (один вызов на страницу) и работают как
    # дешёвый пре-фильтр для is_collectible: условие требует have <= 200, поэтому
    # массовые прессы отсеиваются БЕЗ похода в /marketplace/stats на каждую версию.
    have: int | None = None
    want: int | None = None
    # Rarity-флаги, подмешиваются из локальной БД (или вычисляются on-the-fly где можно)
    is_first_press: bool = False  # тир закрыт, поле остаётся для обратной совместимости
    is_canon: bool = False
    is_collectible: bool = False
    is_limited: bool = False
    is_hot: bool = False


class MasterRelease(BaseModel):
    """Полная информация о мастер-релизе"""
    master_id: str
    title: str
    artist: str
    artist_id: str | None = None
    artist_thumb_image_url: str | None = None
    year: int | None = None
    main_release_id: str
    genres: list[str] = []
    styles: list[str] = []
    cover_image_url: str | None = None
    tracklist: list | None = None


class MasterSearchResponse(BaseModel):
    """Ответ на поиск мастер-релизов"""
    results: list[MasterSearchResult]
    total: int
    page: int
    per_page: int
    has_more: bool = False
    next_cursor: int | None = None


class MasterVersionsResponse(BaseModel):
    """Ответ на запрос версий мастер-релиза"""
    results: list[MasterVersion]
    total: int
    page: int
    per_page: int


class ReleaseSearchResult(BaseModel):
    """Результат поиска конкретных релизов с фильтрами (от Discogs)"""
    release_id: str
    title: str
    artist: str
    label: str | None = None
    catalog_number: str | None = None
    country: str | None = None
    year: int | None = None
    format: str | None = None
    cover_image_url: str | None = None
    thumb_image_url: str | None = None
    # Rarity-флаги — подмешиваются из локальной БД + парсинг is_limited из format
    is_first_press: bool = False
    is_canon: bool = False
    is_collectible: bool = False
    is_limited: bool = False
    is_hot: bool = False


class ReleaseSearchResponse(BaseModel):
    """Ответ на поиск релизов с фильтрами"""
    results: list[ReleaseSearchResult]
    total: int
    page: int
    per_page: int


class CoverScanRequest(BaseModel):
    """Запрос на распознавание обложки"""
    image_base64: str = Field(..., description="Base64-encoded JPEG image")


class CoverScanResponse(BaseModel):
    """Ответ на распознавание обложки"""
    recognized_artist: str
    recognized_album: str
    results: list[RecordSearchResult]
    # Визуальный re-rank: уверенность лучшего совпадения (косинус CLIP, 0..1).
    confidence: float | None = None
    # True если лучший score ниже порога — клиенту показать "выбери вручную".
    low_confidence: bool = False


class ArtistSearchResult(BaseModel):
    """Результат поиска артиста (от Discogs)"""
    artist_id: str
    name: str
    cover_image_url: str | None = None
    thumb_image_url: str | None = None


class Artist(BaseModel):
    """Полная информация об артисте"""
    artist_id: str
    name: str
    profile: str | None = None
    images: list[str] = []


class ArtistSearchResponse(BaseModel):
    """Ответ на поиск артистов"""
    results: list[ArtistSearchResult]
    total: int
    page: int
    per_page: int


# ── User-submitted records (source='user') ─────────────────────────────── #


class PreflightRequest(BaseModel):
    """Дабл-чек перед созданием user-record (см. USER_SUBMITTED_RECORDS.md §2)."""
    artist: str = Field(..., max_length=500)
    title: str = Field(..., max_length=500)
    year: int | None = Field(None, ge=1900, le=2100)
    barcode: str | None = Field(None, max_length=50)
    catalog: str | None = Field(None, max_length=100)
    format_type: str | None = Field(None, max_length=100)  # §9 format-aware dedup


class PreflightDiscogsMatch(BaseModel):
    """Превью найденного в Discogs релиза — чтобы экран-перехват показал юзеру,
    что именно добавится, а не безымянную заглушку."""
    discogs_id: str
    artist: str | None = None
    title: str | None = None
    year: int | None = None
    cover_image_url: str | None = None


class PreflightResponse(BaseModel):
    """DUPLICATE/LIKELY_DUPLICATE/FOUND_IN_DISCOGS/ALLOW_CREATE."""
    status: str
    match: RecordResponse | None = None
    discogs_id: str | None = None
    discogs_match: PreflightDiscogsMatch | None = None
    score: float | None = None


class SpotifyAlbumCandidate(BaseModel):
    """Кандидат из Spotify-поиска (автозаполнение)."""
    id: str
    name: str
    artist: str
    year: int | None = None
    cover_url: str | None = None
    image_url: str | None = None
    tracks: list = []


class SpotifySearchResponse(BaseModel):
    results: list[SpotifyAlbumCandidate]


class UserRecordCreate(BaseModel):
    """Создание source='user' записи. Фото — base64 JPEG (как scan/cover)."""
    artist: str = Field(..., max_length=500)
    title: str = Field(..., max_length=500)
    year: int | None = Field(None, ge=1900, le=2100)
    label: str | None = Field(None, max_length=255)
    catalog_number: str | None = Field(None, max_length=100)
    country: str | None = Field(None, max_length=100)
    format_type: str | None = Field(None, max_length=100)
    barcode: str | None = Field(None, max_length=50)
    spotify_album_id: str | None = Field(None, max_length=64)
    tracklist: list | None = None
    cover_photo_base64: str | None = None
    spine_photo_base64: str | None = None


class UserRecordUpdate(BaseModel):
    """Правка своей user-record автором (§11). Все поля опциональны (PATCH)."""
    artist: str | None = Field(None, max_length=500)
    title: str | None = Field(None, max_length=500)
    year: int | None = Field(None, ge=1900, le=2100)
    label: str | None = Field(None, max_length=255)
    catalog_number: str | None = Field(None, max_length=100)
    country: str | None = Field(None, max_length=100)
    format_type: str | None = Field(None, max_length=100)
    barcode: str | None = Field(None, max_length=50)
    tracklist: list | None = None
    cover_photo_base64: str | None = None

