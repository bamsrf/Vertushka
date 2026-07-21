"""
Pydantic-схемы для API offers и market.
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field


class StoreInfo(BaseModel):
    slug: str
    name: str
    logo_url: str | None = None
    rating: float = 0.0


class OfferResponse(BaseModel):
    listing_id: UUID
    store: StoreInfo
    price_rub: Decimal | None = None
    condition: str | None = None
    vinyl_color: str | None = None
    format: str | None = None
    url: str = Field(
        ...,
        description=(
            "UTM-обогащённая ссылка магазина (без affiliate-subid). "
            "Mobile перед открытием должен вызвать POST /api/offers/{id}/click "
            "и использовать оттуда финальный URL с subid для аттрибуции."
        ),
    )
    status: str
    last_seen_at: datetime
    # Поля для полной карточки оффера в bottom-sheet (Phase 5 Mobile):
    catalog_number: str | None = Field(
        None,
        description="Артикул/SKU магазина. Mobile показывает в OfferDetailCard как «Артикул: ...»",
    )
    is_alt_version: bool = Field(
        False,
        description="True если другой pressing того же master_id (для бейджа «АЛТ»)",
    )
    pressing_match: Literal["exact", "album"] = Field(
        "exact",
        description=(
            "Уверенность что листинг — ИМЕННО этот пресс, а не просто тот же "
            "альбом. 'exact' — матч по barcode/discogs_url/catalog или "
            "store-native (точная идентичность пресса). 'album' — матч по "
            "fuzzy(artist+title) / низкой confidence ИЛИ конфликт цвета: "
            "альбом тот, но цвет/издание может отличаться. Mobile рисует такие "
            "офферы в секции «пресс может отличаться» + дисклеймер + увод в "
            "магазин. is_alt_version=true всегда подразумевает album."
        ),
    )
    image_url: str | None = Field(
        None, description="Обложка из листинга (fallback для record.cover_image_url)"
    )
    record_discogs_id: str | None = Field(
        None,
        description=(
            "discogs_id записи, к которой матчен листинг. Может ОТЛИЧАТЬСЯ "
            "от запроса для is_alt_version=true (другой pressing того же мастера). "
            "Mobile использует для navigation: тап на alt-карточку в bottom-sheet "
            "→ /record/{record_discogs_id} → детальная альтернативного прессинга."
        ),
    )


class OfferClickResponse(BaseModel):
    """Ответ POST /api/offers/{id}/click — финальный URL для Linking.openURL."""

    click_id: UUID
    url: str = Field(..., description="Полный URL с affiliate-обёрткой и subid=click_id")


# ============================================================================
# Hot Stock pill — batch summary (Mobile Phase 1: HotStockTag в карточках)
# ============================================================================


class RecordOffersSummary(BaseModel):
    """
    Аггрегат по офферам на одну запись. Mobile использует для вычисления
    variant'а HotStockTag (inStock / inStockMulti / lastOne / altVersion /
    preorder / none) без необходимости пуллить все offers.

    Вычислять variant правилами:
      - in_stock_count == 1                       → 'inStock'
      - in_stock_count >= 2                       → 'inStockMulti'
      - has_last_one == true                      → префикс 'lastOne' к любому inStock
      - in_stock_count == 0 AND alt_version_count > 0  → 'altVersion'
      - in_stock_count == 0 AND preorder_count > 0     → 'preorder'
      - всё ноль                                  → 'none' (рендерим null)
    """

    in_stock_count: int = Field(
        0,
        description=(
            "Листинги ИМЕННО этого пресса (pressing_match='exact') со "
            "status=in_stock. Album-level матчи (fuzzy/конфликт цвета) сюда НЕ "
            "входят — они в alt_version_count, чтобы pill «N в наличии» не врал."
        ),
    )
    preorder_count: int = Field(0, description="Листинги со status=preorder")
    alt_version_count: int = Field(
        0,
        description=(
            "Листинги «другого/неуверенного пресса»: другой discogs_id того же "
            "master_id ЛИБО album-level матч на этой же записи "
            "(pressing_match='album'). Используется если in_stock_count == 0 — "
            "для variant=altVersion."
        ),
    )
    min_price_rub: Decimal | None = Field(
        None, description="Min цена для inStock/inStockMulti pill'ов"
    )
    min_price_alt_rub: Decimal | None = Field(
        None, description="Min цена среди alt-version листингов (для altVersion pill'а)"
    )
    has_last_one: bool = Field(
        False, description="≥1 листинг с quantity == 1 (для микро-надписи «1 экз.»)"
    )
    stores_with_stock: int = Field(
        0, description="Сколько уникальных магазинов держат in_stock для этой записи"
    )


class RecordOffersSummaryRequest(BaseModel):
    """
    Body для POST /api/records/offers/summary — batch до 100 discogs_ids.

    Один запрос Mobile делает на всю видимую сетку (20 карточек поиска /
    60 карточек коллекции), мапит summary к карточкам и рисует HotStockTag.
    """

    discogs_ids: list[str] = Field(
        ..., min_length=1, max_length=100,
        description="Discogs IDs пластинок. До 100 за раз.",
    )


class RecordOffersFullResponse(BaseModel):
    """
    Расширенный response для детального экрана пластинки (Mobile Phase 5).

    Возвращает и сами offers (как в GET /records/{id}/offers), и summary
    (как в POST /records/offers/summary) одним запросом. Бэк делает один
    SQL → один SQL = меньше round-trip'ов чем два отдельных вызова.
    """

    summary: RecordOffersSummary
    offers: list[OfferResponse]


# ============================================================================
# Market — карусель «В наличии сейчас» (legacy)
# ============================================================================


class MarketCarouselItem(BaseModel):
    """
    Карточка для карусели «В наличии сейчас» в поиске (Mobile/app/(tabs)/search.tsx).

    Один элемент = одна запись (`Record`). Если на запись висят несколько листингов
    из разных магазинов — здесь только самый дешёвый. Это даёт «N разных пластинок»
    в карусели вместо «N дублей одной обложки».
    """

    record_id: UUID
    discogs_id: str | None = None
    artist: str
    title: str
    year: int | None = None
    format_type: str | None = None
    cover_image_url: str | None = None
    min_price_rub: Decimal
    store_slug: str = Field(..., description="Магазин с минимальной ценой — для аналитики")
    first_seen_at: datetime = Field(..., description="Когда впервые увидели в продаже")


# ============================================================================
# Market — раздел «Маркет» (Mobile Phase 4)
# ============================================================================


class MarketStoreInfo(BaseModel):
    """
    Метаданные магазина для витрин в Маркете.
    `GET /api/market/stores` возвращает list[MarketStoreInfo].
    """

    slug: str
    name: str
    logo_url: str | None = None
    rating: float = 0.0
    in_stock_count: int = Field(..., description="Сколько листингов in_stock сейчас")
    avg_price_rub: Decimal | None = Field(None, description="Средняя цена in_stock листинга")
    new_today_count: int = Field(0, description="Появилось в продаже за последние 24ч")


class MarketSearchItem(BaseModel):
    """
    Карточка пластинки в результатах поиска по Маркету.
    Дедуплицирована по record_id (один record = одна карточка, min_price из всех магазинов).

    Используется `GET /api/market/search` и `GET /api/market/stores/{slug}/all`.
    """

    record_id: UUID
    discogs_id: str | None = None
    artist: str
    title: str
    year: int | None = None
    format_type: str | None = None
    cover_image_url: str | None = None
    min_price_rub: Decimal
    stores_with_stock: int = Field(
        1, description="Сколько магазинов держат in_stock для этой записи"
    )
    cheapest_store_slug: str = Field(..., description="Магазин с min ценой")
    first_seen_at: datetime


MarketFormatFilter = Literal["vinyl", "cd", "cassette"]
MarketSortMode = Literal["price_asc", "newest"]


class MarketFacetItem(BaseModel):
    """Одна опция фильтра с числом доступных карточек (data-driven чипы)."""

    key: str = Field(..., description="Канонический ключ (rock / colored / …)")
    label: str = Field(..., description="Человекочитаемая метка для чипа")
    count: int = Field(..., description="Сколько карточек в наличии под этой опцией")


class MarketFacetsResponse(BaseModel):
    """Доступные фильтры Маркета со счётчиками — только опции с count > 0.

    Позволяет Mobile рисовать чипы жанров/особенностей строго по наличию, а не
    хардкодом (иначе показали бы «Jazz», а там пусто).
    """

    genres: list[MarketFacetItem] = []
    features: list[MarketFacetItem] = []
