"""Серии «Рыночный нюх» (M*) и «Стоимость коллекции» (MV*).

M* опираются на `OfferClick` — affiliate-переходы в магазин. Анти-фарм тут
обязателен: клик по одному и тому же листингу перезаходами накрутил бы
«Завсегдатая» за минуту, поэтому M5 считает УНИКАЛЬНЫЕ листинги, а не строки.

MV* считают стоимость коллекции. Пересчёт живёт на `DAILY_TICK`: гонять оценку
всей коллекции (курс + правила ценообразования на каждую запись) при каждом
добавлении — дорого и не нужно, порог в сотни тысяч рублей за сутки не убегает.
Источник — последний `CollectionValueSnapshot`, его пишет тот же daily-джоб.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.collection import Collection, CollectionItem
from app.models.collection_value_snapshot import CollectionValueSnapshot
from app.models.offer_click import OfferClick
from app.models.record import Record
from app.models.store_listing import StoreListing
from app.models.user_achievement import UserAchievement
from app.models.wishlist import Wishlist, WishlistItem
from app.services.achievements.events import (
    COLLECTION_ITEM_ADDED,
    DAILY_TICK,
    OFFER_CLICKED,
    PRICE_DRAWER_OPENED,
)
from app.services.achievements.registry import (
    AchievementDefinition,
    AchievementTier,
    EvalResult,
)

M1_CODE = "M1_first_drawer"
M2_CODE = "M2_first_click"
M3_CODE = "M3_wishlist_hunter"
M4_CODE = "M4_deal_finder"
M5_CODE = "M5_regular"
META_MARKET_CODE = "META_market"
_M_CODES = {M1_CODE, M2_CODE, M3_CODE, M4_CODE, M5_CODE}

MV1_CODE = "MV1_appraised"
MV2_CODE = "MV2_50k"
MV3_CODE = "MV3_100k"
MV4_CODE = "MV4_250k"
MV5_CODE = "MV5_500k"
MV6_CODE = "MV6_million"
MV_CROWN_CODE = "MV_crown_jewel"

M5_TARGET = 50
CROWN_JEWEL_RUB = Decimal("20000")

# «Цена-огонь»: листинг должен быть дешевле рыночной оценки хотя бы на пятую
# часть. Без порога ачивкой считалась разница в рубль.
DEAL_MAX_SHARE_OF_MARKET = 0.80


# --- Рыночный нюх ------------------------------------------------------------

async def _evaluate_first_drawer(
    db: AsyncSession, user_id: UUID, payload: dict[str, Any], unlocked_now: set[str]
) -> EvalResult:
    """Открыл price drawer. Факт открытия приходит событием, в БД его нет."""
    return EvalResult(unlocked=True)


async def _count_unique_clicked_listings(db: AsyncSession, user_id: UUID) -> int:
    return int(
        await db.scalar(
            select(func.count(func.distinct(OfferClick.listing_id))).where(
                OfferClick.user_id == user_id
            )
        )
        or 0
    )


async def _evaluate_first_click(
    db: AsyncSession, user_id: UUID, payload: dict[str, Any], unlocked_now: set[str]
) -> EvalResult:
    return EvalResult(unlocked=await _count_unique_clicked_listings(db, user_id) > 0)


async def _evaluate_regular(
    db: AsyncSession, user_id: UUID, payload: dict[str, Any], unlocked_now: set[str]
) -> EvalResult:
    """50 переходов. Считаем уникальные листинги — иначе фарм перезаходами."""
    count = await _count_unique_clicked_listings(db, user_id)
    return EvalResult(
        unlocked=count >= M5_TARGET,
        progress=min(count, M5_TARGET),
        progress_target=M5_TARGET,
    )


async def _evaluate_wishlist_hunter(
    db: AsyncSession, user_id: UUID, payload: dict[str, Any], unlocked_now: set[str]
) -> EvalResult:
    """Переход по пластинке, которая лежит в собственном вишлисте."""
    hit = await db.scalar(
        select(func.count())
        .select_from(OfferClick)
        .join(StoreListing, StoreListing.id == OfferClick.listing_id)
        .join(WishlistItem, WishlistItem.record_id == StoreListing.matched_record_id)
        .join(Wishlist, Wishlist.id == WishlistItem.wishlist_id)
        .where(OfferClick.user_id == user_id, Wishlist.user_id == user_id)
    )
    return EvalResult(unlocked=bool(hit))


async def _evaluate_deal_finder(
    db: AsyncSession, user_id: UUID, payload: dict[str, Any], unlocked_now: set[str]
) -> EvalResult:
    """Кликнутый листинг заметно дешевле рыночной оценки Discogs.

    Сравниваем с ЧИСТОЙ оценкой — median × курс, — а не с `record_value_rub`.
    Тот считает стоимость ВВОЗА: к цене Discogs он добавляет фиксированные
    ~$20 доставки, 20% накладных и пошлину. Для дешёвой пластинки это
    множитель под ×6 ($5 → «оценка» $30), и любой российский магазин
    оказывается «дешевле» автоматически. Ачивка редкого тира открывалась на
    первом же переходе в магазин, вместе с «Первой вылазкой».

    Median, а не min: `record_usd` откатывается на min, а Discogs отдаёт его
    по живым лотам — у релиза без истории продаж это одна-единственная цена.
    Оценки рынка за ней нет, и сравнивать не с чем.

    Порог `DEAL_MAX_SHARE_OF_MARKET` отсекает случайную копеечную разницу:
    находка — это заметно дешевле, а не дешевле на рубль.

    Ужесточение не отбирает ачивку у тех, кто её уже получил: открытые коды
    эвалюатор пропускает (см. evaluator.py) и заново не считает.
    """
    from app.services.exchange import get_usd_rub_rate

    rows = await db.execute(
        select(StoreListing.price_rub, Record)
        .join(OfferClick, OfferClick.listing_id == StoreListing.id)
        .join(Record, Record.id == StoreListing.matched_record_id)
        .where(OfferClick.user_id == user_id, StoreListing.price_rub.isnot(None))
    )
    pairs = rows.all()
    if not pairs:
        return EvalResult()

    rate = await get_usd_rub_rate()
    if rate <= 0:
        return EvalResult()

    for price_rub, record in pairs:
        median_usd = record.estimated_price_median
        if not median_usd:
            continue
        market_rub = float(median_usd) * rate
        if float(price_rub) <= market_rub * DEAL_MAX_SHARE_OF_MARKET:
            return EvalResult(unlocked=True)
    return EvalResult()


async def _evaluate_meta_market(
    db: AsyncSession, user_id: UUID, payload: dict[str, Any], unlocked_now: set[str]
) -> EvalResult:
    rows = await db.execute(
        select(UserAchievement.code).where(
            UserAchievement.user_id == user_id,
            UserAchievement.is_unlocked.is_(True),
            UserAchievement.code.in_(list(_M_CODES)),
        )
    )
    unlocked = set(rows.scalars().all()) | (unlocked_now & _M_CODES)
    return EvalResult(
        unlocked=unlocked == _M_CODES,
        progress=len(unlocked),
        progress_target=len(_M_CODES),
    )


# --- Стоимость коллекции -----------------------------------------------------

async def _latest_value_rub(db: AsyncSession, user_id: UUID) -> Decimal | None:
    return await db.scalar(
        select(CollectionValueSnapshot.total_value_rub)
        .where(CollectionValueSnapshot.user_id == user_id)
        .order_by(CollectionValueSnapshot.snapshot_date.desc())
        .limit(1)
    )


def _make_value_threshold(threshold: Decimal):
    async def evaluator(
        db: AsyncSession, user_id: UUID, payload: dict[str, Any], unlocked_now: set[str]
    ) -> EvalResult:
        value = await _latest_value_rub(db, user_id)
        if value is None:
            return EvalResult()
        return EvalResult(
            unlocked=value >= threshold,
            progress=int(min(value, threshold)),
            progress_target=int(threshold),
        )

    return evaluator


async def _evaluate_appraised(
    db: AsyncSession, user_id: UUID, payload: dict[str, Any], unlocked_now: set[str]
) -> EvalResult:
    """Первый расчёт стоимости — есть хотя бы один снапшот с ненулевой суммой."""
    value = await _latest_value_rub(db, user_id)
    return EvalResult(unlocked=value is not None and value > 0)


async def _evaluate_crown_jewel(
    db: AsyncSession, user_id: UUID, payload: dict[str, Any], unlocked_now: set[str]
) -> EvalResult:
    """Одна пластинка дороже 20 000 ₽."""
    from app.config import get_settings
    from app.services.exchange import get_usd_rub_rate
    from app.services.pricing import PricingParams
    from app.services.valuation import record_value_rub

    records = (
        (
            await db.execute(
                select(Record)
                .join(CollectionItem, CollectionItem.record_id == Record.id)
                .join(Collection, Collection.id == CollectionItem.collection_id)
                .where(Collection.user_id == user_id)
            )
        )
        .scalars()
        .all()
    )
    if not records:
        return EvalResult()
    rate = await get_usd_rub_rate()
    params = PricingParams.from_settings(get_settings())
    best = max((record_value_rub(r, rate, params) for r in {r.id: r for r in records}.values()), default=0.0)
    return EvalResult(unlocked=Decimal(str(best)) >= CROWN_JEWEL_RUB)


_MARKET_TRIGGERS = (OFFER_CLICKED, PRICE_DRAWER_OPENED)
_VALUE_TRIGGERS = (DAILY_TICK, COLLECTION_ITEM_ADDED)


def _d(code, title, desc, tier, triggers, evaluator, flavor, slug, series, done=""):
    return AchievementDefinition(
        code=code, title_ru=title, description_ru=desc, description_done_ru=done,
        series=series, tier=tier, is_hidden=False, triggers=triggers,
        evaluator=evaluator, flavor_ru=flavor, icon_slug=slug,
    )


DEFINITIONS: list[AchievementDefinition] = [
    _d(M1_CODE, "Прицениться", "Открой карточку цен на пластинку.",
       AchievementTier.SIMPLE, (PRICE_DRAWER_OPENED,), _evaluate_first_drawer,
       "Сначала посмотреть. Потом уже решать.", "m1_first_drawer", "market",
       done="Карточка цен на пластинку открыта."),
    _d(M2_CODE, "Первая вылазка", "Перейди в магазин по предложению.",
       AchievementTier.SIMPLE, (OFFER_CLICKED,), _evaluate_first_click,
       "Первый шаг наружу.", "m2_first_click", "market",
       done="Первый переход в магазин по предложению сделан."),
    _d(M3_CODE, "Закрыл гештальт", "Перейди в магазин по пластинке из своего вишлиста.",
       AchievementTier.NOTABLE, (OFFER_CLICKED,), _evaluate_wishlist_hunter,
       "То, чего давно не хватало, оказалось в наличии.", "m3_wishlist_hunter", "market",
       done="Переход в магазин по пластинке из своего вишлиста."),
    _d(M4_CODE, "Цена-огонь", "Найди предложение минимум на 20% дешевле оценки Discogs.",
       AchievementTier.RARE, _MARKET_TRIGGERS, _evaluate_deal_finder,
       "Дешевле, чем принято считать.", "m4_deal_finder", "market",
       done="Найдено предложение минимум на 20% дешевле оценки Discogs."),
    _d(M5_CODE, "Завсегдатай", "Сделай 50 переходов в магазины.",
       AchievementTier.RARE, (OFFER_CLICKED,), _evaluate_regular,
       "Тебя тут уже узнают.", "m5_regular", "market",
       done="50 переходов в магазины сделано."),
    _d(META_MARKET_CODE, "Рыночный нюх", "Открой все ачивки серии «Рыночный нюх».",
       AchievementTier.NOTABLE, _MARKET_TRIGGERS, _evaluate_meta_market,
       "Ты чувствуешь цену до того, как её увидел.", "meta_market", "market",
       done="Вся серия «Рыночный нюх» закрыта: цены, вылазки в магазины, "
            "покупка из вишлиста и находка дешевле рынка."),

    _d(MV1_CODE, "Оценено", "Дождись первой оценки стоимости коллекции.",
       AchievementTier.SIMPLE, _VALUE_TRIGGERS, _evaluate_appraised,
       "Теперь у полки есть цена.", "mv1_appraised", "value",
       done="Коллекция впервые оценена в деньгах."),
    _d(MV2_CODE, "Полтинник", "Коллекция дороже 50 000 ₽.",
       AchievementTier.SIMPLE, _VALUE_TRIGGERS, _make_value_threshold(Decimal("50000")),
       "Полтинник на полке.", "mv2_50k", "value"),
    _d(MV3_CODE, "Шестизнак", "Коллекция дороже 100 000 ₽.",
       AchievementTier.NOTABLE, _VALUE_TRIGGERS, _make_value_threshold(Decimal("100000")),
       "Шесть знаков в оценке.", "mv3_100k", "value"),
    _d(MV4_CODE, "Четверть лимона", "Коллекция дороже 250 000 ₽.",
       AchievementTier.RARE, _VALUE_TRIGGERS, _make_value_threshold(Decimal("250000")),
       "Четверть миллиона в виниле.", "mv4_250k", "value"),
    _d(MV5_CODE, "Сокровищница", "Коллекция дороже 500 000 ₽.",
       AchievementTier.EPIC, _VALUE_TRIGGERS, _make_value_threshold(Decimal("500000")),
       "Это уже не полка, это хранилище.", "mv5_500k", "value"),
    _d(MV6_CODE, "Миллионер", "Коллекция дороже 1 000 000 ₽.",
       AchievementTier.LEGEND, _VALUE_TRIGGERS, _make_value_threshold(Decimal("1000000")),
       "Семь знаков. И всё это музыка.", "mv6_million", "value"),
    _d(MV_CROWN_CODE, "Жемчужина", "Одна пластинка в коллекции дороже 20 000 ₽.",
       AchievementTier.RARE, _VALUE_TRIGGERS, _evaluate_crown_jewel,
       "Одна пластинка дороже иной полки.", "mv_crown_jewel", "value",
       done="В коллекции есть пластинка дороже 20 000 ₽."),
]
