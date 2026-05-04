"""
Web-маршруты для публичных страниц (HTML, не API)
"""
import logging
from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select, func, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.config import get_settings
from app.models.user import User
from app.models.record import Record
from app.models.collection import Collection, CollectionItem
from app.models.wishlist import Wishlist, WishlistItem
from app.models.follow import Follow
from app.models.profile_share import ProfileShare
from app.models.gift_booking import GiftBooking, GiftStatus
from app.api.profile import get_public_profile_payload, _get_top_expensive, _get_new_releases
from app.services.exchange import get_usd_rub_rate
from app.services.pricing import PricingParams, estimate_rub
from app.services.valuation import get_monthly_delta

logger = logging.getLogger(__name__)

router = APIRouter()
templates = Jinja2Templates(directory="app/web/templates")
settings = get_settings()

BASE_URL = "https://vinyl-vertushka.ru"


_GENRE_RU = {
    "rock": "рока",
    "pop": "поп-пластинок",
    "electronic": "электроники",
    "hip hop": "хип-хоп пластинок",
    "hip-hop": "хип-хоп пластинок",
    "jazz": "джазовых пластинок",
    "classical": "классики",
    "funk / soul": "фанка и соула",
    "funk": "фанка и соула",
    "soul": "фанка и соула",
    "reggae": "регги-пластинок",
    "blues": "блюза",
    "folk, world, & country": "фолка и кантри",
    "folk": "фолка",
    "country": "кантри",
    "latin": "латинских пластинок",
    "stage & screen": "саундтреков",
    "non-music": "non-music записей",
    "children's": "детских пластинок",
    "brass & military": "бравурных пластинок",
}


def _genre_label(genre: str) -> str:
    """Переводит жанр в русскую форму для fun-stats. Иначе возвращает 'пластинок {genre}'."""
    key = (genre or "").strip().lower()
    if key in _GENRE_RU:
        return _GENRE_RU[key]
    return f"пластинок жанра {genre}"


@router.get("/privacy", response_class=HTMLResponse)
async def privacy_policy(request: Request):
    """Политика конфиденциальности"""
    return templates.TemplateResponse("privacy.html", {"request": request})


@router.get("/terms", response_class=HTMLResponse)
async def terms_of_service(request: Request):
    """Условия использования"""
    return templates.TemplateResponse("terms.html", {"request": request})


@router.get("/@{username}", response_class=HTMLResponse)
async def public_profile_page(
    request: Request,
    username: str,
    tab: str = "collection",
    db: AsyncSession = Depends(get_db)
):
    """Публичная страница профиля с OG-тегами"""
    # Получаем пользователя с ProfileShare
    result = await db.execute(
        select(User)
        .where(User.username == username, User.is_active == True)
        .options(selectinload(User.profile_share))
    )
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Пользователь не найден")

    profile = user.profile_share
    if not profile or not profile.is_active:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Профиль не активирован")

    # Инкремент просмотров
    profile.view_count += 1
    await db.commit()

    # === Статистика ===
    # Считаем уникальные пластинки (distinct record_id), чтобы не дублировать
    # одну и ту же пластинку из разных папок — мобила показывает дефолт-папку,
    # а здесь должна быть единая картина «сколько пластинок у юзера всего».
    collection_count = await db.scalar(
        select(func.count(func.distinct(CollectionItem.record_id)))
        .join(Collection)
        .where(Collection.user_id == user.id)
    ) or 0

    wishlist_count = await db.scalar(
        select(func.count(WishlistItem.id))
        .join(Wishlist)
        .where(Wishlist.user_id == user.id, WishlistItem.is_purchased == False)
    ) or 0

    followers_count = await db.scalar(
        select(func.count(Follow.id)).where(Follow.following_id == user.id)
    ) or 0

    # Курс USD→RUB (кэшируется, дёшево)
    usd_rub_rate = await get_usd_rub_rate()
    pricing_params = PricingParams.from_settings(settings)

    # Стоимость коллекции — суммируем по уникальным пластинкам (дедуп по record_id),
    # чтобы пластинка, добавленная в несколько папок, не считалась дважды.
    collection_value = None
    collection_value_rub = None
    monthly_delta = None
    if profile.show_collection_value:
        # Суррогат базовой USD-цены через distinct запись (берём min/median)
        usd_subq = (
            select(
                CollectionItem.record_id.label("rid"),
                func.coalesce(Record.estimated_price_min, Record.estimated_price_median).label("usd"),
            )
            .join(Collection, Collection.id == CollectionItem.collection_id)
            .join(Record, Record.id == CollectionItem.record_id)
            .where(Collection.user_id == user.id)
            .distinct(CollectionItem.record_id)
            .subquery()
        )
        value_result = await db.scalar(select(func.sum(usd_subq.c.usd)))
        collection_value = round(float(value_result), 2) if value_result else 0.0

        # Рубли — кэшированные на уровне CollectionItem.estimated_price_rub.
        # Берём max среди дублей (разные папки могут иметь разные значения).
        rub_subq = (
            select(
                CollectionItem.record_id.label("rid"),
                func.max(CollectionItem.estimated_price_rub).label("rub"),
            )
            .join(Collection, Collection.id == CollectionItem.collection_id)
            .where(Collection.user_id == user.id)
            .group_by(CollectionItem.record_id)
            .subquery()
        )
        value_rub_result = await db.scalar(select(func.sum(rub_subq.c.rub)))
        collection_value_rub = round(float(value_rub_result), 2) if value_rub_result else 0.0
        delta = await get_monthly_delta(user.id, db)
        monthly_delta = float(delta) if delta is not None else None

    # Рейлы
    top_expensive = await _get_top_expensive(user.id, db, limit=12) if profile.show_collection else []
    new_releases = await _get_new_releases(db, limit=24, user_id=user.id)

    # === Fun stats — ротирующие фишки коллекции ===
    # Все агрегации идут поверх DISTINCT record_id, чтобы один и тот же релиз
    # из разных папок не задваивал статистику.
    fun_stats: list[dict] = []
    try:
      if profile.show_collection and collection_count > 0:
        # Подзапрос с уникальными record_id юзера
        user_records_subq = (
            select(CollectionItem.record_id.distinct().label("rid"))
            .join(Collection, Collection.id == CollectionItem.collection_id)
            .where(Collection.user_id == user.id)
            .subquery()
        )
        ur_join = user_records_subq.join(Record, Record.id == user_records_subq.c.rid)

        # Цветные пластинки (по format_description: Coloured / Translucent / Picture / Splatter)
        color_keywords = ["Coloured", "Color", "Translucent", "Picture Disc", "Splatter", "Marbled", "Glow"]
        color_filter = func.coalesce(Record.format_description, "")
        color_clauses = [color_filter.ilike(f"%{kw}%") for kw in color_keywords]
        color_count = await db.scalar(
            select(func.count(Record.id))
            .select_from(ur_join)
            .where(or_(*color_clauses))
        ) or 0

        # Топ-жанр (Discogs хранит несколько через запятую — расщепляем в Python)
        genre_rows = await db.execute(
            select(Record.genre)
            .select_from(ur_join)
            .where(Record.genre.isnot(None), Record.genre != "")
        )
        genre_counter: dict[str, int] = {}
        for (genre_str,) in genre_rows:
            for g in (genre_str or "").split(","):
                g_clean = g.strip()
                if g_clean:
                    genre_counter[g_clean] = genre_counter.get(g_clean, 0) + 1
        top_genre, top_genre_count = (None, 0)
        if genre_counter:
            top_genre, top_genre_count = max(genre_counter.items(), key=lambda kv: kv[1])

        # Декада с наибольшим количеством
        year_rows = await db.execute(
            select(Record.year)
            .select_from(ur_join)
            .where(Record.year.isnot(None), Record.year > 1900)
        )
        decade_counter: dict[int, int] = {}
        for (yr,) in year_rows:
            if yr is None:
                continue
            d = (int(yr) // 10) * 10
            decade_counter[d] = decade_counter.get(d, 0) + 1
        top_decade, top_decade_count = (None, 0)
        if decade_counter:
            top_decade, top_decade_count = max(decade_counter.items(), key=lambda kv: kv[1])

        # Стран и лейблов (distinct по уникальным записям)
        countries_count = await db.scalar(
            select(func.count(func.distinct(Record.country)))
            .select_from(ur_join)
            .where(Record.country.isnot(None), Record.country != "")
        ) or 0

        labels_count = await db.scalar(
            select(func.count(func.distinct(Record.label)))
            .select_from(ur_join)
            .where(Record.label.isnot(None), Record.label != "")
        ) or 0

        # Самая старая пластинка
        oldest_row = await db.execute(
            select(Record.year, Record.artist, Record.title)
            .select_from(ur_join)
            .where(Record.year.isnot(None), Record.year > 1900)
            .order_by(Record.year.asc())
            .limit(1)
        )
        oldest = oldest_row.first()

        # Первые прессы / Каноничные / Коллекционка
        rare_count = await db.scalar(
            select(func.count(Record.id))
            .select_from(ur_join)
            .where(or_(Record.is_first_press == True, Record.is_canon == True, Record.is_collectible == True))
        ) or 0

        # Собираем список (только непустые)
        if color_count >= 1:
            fun_stats.append({
                "icon": "🎨",
                "html": f"<b>{color_count}</b> цветных пластинок",
            })
        if top_genre and top_genre_count >= 2:
            fun_stats.append({
                "icon": "🎧",
                "html": f"<b>{top_genre_count}</b> {_genre_label(top_genre)}",
            })
        if top_decade and top_decade_count >= 2:
            fun_stats.append({
                "icon": "📻",
                "html": f"<b>{top_decade_count}</b> пластинок из {top_decade}-х",
            })
        if countries_count >= 2:
            fun_stats.append({
                "icon": "🌍",
                "html": f"<b>{countries_count}</b> стран в коллекции",
            })
        if labels_count >= 3:
            fun_stats.append({
                "icon": "🏷️",
                "html": f"<b>{labels_count}</b> разных лейблов",
            })
        if oldest:
            fun_stats.append({
                "icon": "🕰️",
                "html": f"Самая старая: <b>{oldest[0]}</b> · {oldest[1]}",
            })
        if rare_count >= 1:
            fun_stats.append({
                "icon": "💎",
                "html": f"<b>{rare_count}</b> редких изданий",
            })
    except Exception as e:
        logger.warning("fun_stats computation failed: %s", e)
        fun_stats = []

    # === Избранные пластинки ===
    highlights = []
    if profile.highlight_record_ids:
        for record_id in profile.highlight_record_ids[:4]:
            rec_result = await db.execute(
                select(Record).where(Record.id == record_id)
            )
            record = rec_result.scalar_one_or_none()
            if record:
                highlights.append(record)

    # === Коллекция (с дедупом по record_id) ===
    collection_items = []
    if profile.show_collection:
        result = await db.execute(
            select(CollectionItem)
            .join(Collection)
            .where(Collection.user_id == user.id)
            .options(selectinload(CollectionItem.record))
            .order_by(CollectionItem.added_at.desc())
            .limit(200)
        )
        seen_record_ids: set = set()
        for item in result.scalars().all():
            if not item.record or item.record.id in seen_record_ids:
                continue
            seen_record_ids.add(item.record.id)
            collection_items.append(item)
            if len(collection_items) >= 100:
                break

    # === Вишлист ===
    wishlist_items = []
    if profile.show_wishlist:
        result = await db.execute(
            select(WishlistItem)
            .join(Wishlist)
            .where(
                Wishlist.user_id == user.id,
                WishlistItem.is_purchased == False
            )
            .options(
                selectinload(WishlistItem.record),
                selectinload(WishlistItem.gift_booking)
            )
            .order_by(WishlistItem.priority.desc())
        )
        wishlist_items = result.scalars().all()

    # OG description
    og_parts = [f"{collection_count} пластинок"]
    if collection_value and profile.show_collection_value:
        og_parts.append(f"~${collection_value:,.0f}")
    if wishlist_count > 0:
        og_parts.append(f"{wishlist_count} в вишлисте")
    og_description = " \u00b7 ".join(og_parts)

    def compute_rub(record) -> int:
        """\u0421\u0447\u0438\u0442\u0430\u0435\u0442 \u0440\u0443\u0431\u043b\u0451\u0432\u0443\u044e \u0446\u0435\u043d\u0443 \u0437\u0430\u043f\u0438\u0441\u0438 \u0447\u0435\u0440\u0435\u0437 \u043a\u043e\u043c\u043f\u043e\u043d\u0435\u043d\u0442\u043d\u0443\u044e \u0444\u043e\u0440\u043c\u0443\u043b\u0443.
        \u041f\u0440\u0438\u043d\u0438\u043c\u0430\u0435\u0442 \u0438 SQLAlchemy Record, \u0438 Pydantic PublicProfileRecord \u2014 \u043d\u0435\u0434\u043e\u0441\u0442\u0430\u044e\u0449\u0438\u0435
        \u043f\u043e\u043b\u044f \u0434\u0435\u0433\u0440\u0430\u0434\u0438\u0440\u0443\u044e\u0442 \u0434\u043e None \u0447\u0435\u0440\u0435\u0437 getattr."""
        if not record:
            return 0
        base = getattr(record, "estimated_price_median", None) or getattr(record, "estimated_price_min", None)
        if not base:
            return 0
        try:
            return int(estimate_rub(
                float(base),
                getattr(record, "country", None),
                usd_rub_rate,
                pricing_params,
                format_type=getattr(record, "format_type", None),
                format_description=getattr(record, "format_description", None),
                discogs_data=getattr(record, "discogs_data", None),
            ))
        except Exception:
            return 0

    return templates.TemplateResponse("public_profile.html", {
        "request": request,
        "user": user,
        "profile": profile,
        "collection_count": collection_count,
        "wishlist_count": wishlist_count,
        "followers_count": followers_count,
        "collection_value": collection_value,
        "collection_value_rub": collection_value_rub,
        "monthly_delta": monthly_delta,
        "fun_stats": fun_stats,
        "top_expensive": top_expensive,
        "new_releases": new_releases,
        "highlights": highlights,
        "collection_items": collection_items,
        "wishlist_items": wishlist_items,
        "active_tab": tab if tab in ("collection", "wishlist") else "collection",
        "og_description": og_description,
        "base_url": BASE_URL,
        "usd_rub_rate": float(usd_rub_rate),
        "compute_rub": compute_rub,
    })


@router.get("/@{username}/og-image.png")
async def profile_og_image(
    username: str,
    db: AsyncSession = Depends(get_db)
):
    """Динамическое OG-изображение профиля"""
    result = await db.execute(
        select(User)
        .where(User.username == username, User.is_active == True)
        .options(selectinload(User.profile_share))
    )
    user = result.scalar_one_or_none()

    if not user or not user.profile_share or not user.profile_share.is_active:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)

    profile = user.profile_share

    collection_count = await db.scalar(
        select(func.count(CollectionItem.id))
        .join(Collection)
        .where(Collection.user_id == user.id)
    ) or 0

    collection_value = None
    if profile.show_collection_value:
        value_result = await db.scalar(
            select(func.sum(Record.estimated_price_median))
            .join(CollectionItem, CollectionItem.record_id == Record.id)
            .join(Collection)
            .where(Collection.user_id == user.id)
        )
        collection_value = round(float(value_result), 2) if value_result else None

    # Обложки избранных пластинок
    cover_urls = []
    if profile.highlight_record_ids:
        for record_id in profile.highlight_record_ids[:4]:
            rec_result = await db.execute(
                select(Record.cover_image_url).where(Record.id == record_id)
            )
            url = rec_result.scalar_one_or_none()
            if url:
                cover_urls.append(url)

    # Если нет highlights — берём последние из коллекции
    if len(cover_urls) < 4:
        result = await db.execute(
            select(Record.cover_image_url)
            .join(CollectionItem, CollectionItem.record_id == Record.id)
            .join(Collection)
            .where(Collection.user_id == user.id, Record.cover_image_url.isnot(None))
            .order_by(CollectionItem.added_at.desc())
            .limit(4 - len(cover_urls))
        )
        for row in result.scalars().all():
            cover_urls.append(row)

    try:
        from app.services.og_image import generate_profile_og_image

        image_bytes = await generate_profile_og_image(
            username=user.username,
            display_name=user.display_name,
            collection_count=collection_count,
            collection_value=collection_value,
            cover_urls=cover_urls,
        )

        return StreamingResponse(
            image_bytes,
            media_type="image/png",
            headers={"Cache-Control": "public, max-age=3600"}
        )
    except Exception as e:
        logger.error(f"OG image generation failed: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR)


@router.get("/cancel/{booking_id}", response_class=HTMLResponse)
async def cancel_booking_page(
    request: Request,
    booking_id: UUID,
    token: str = "",
    db: AsyncSession = Depends(get_db)
):
    """Страница подтверждения отмены бронирования."""
    result = await db.execute(
        select(GiftBooking)
        .where(GiftBooking.id == booking_id)
        .options(
            selectinload(GiftBooking.wishlist_item)
            .selectinload(WishlistItem.record)
        )
    )
    booking = result.scalar_one_or_none()

    if not booking:
        return templates.TemplateResponse("cancel_booking.html", {
            "request": request, "page_status": "not_found",
            "booking": None, "token": "",
        })

    if booking.cancel_token != token:
        return templates.TemplateResponse("cancel_booking.html", {
            "request": request, "page_status": "invalid_token",
            "booking": None, "token": "",
        })

    if booking.status == GiftStatus.CANCELLED:
        return templates.TemplateResponse("cancel_booking.html", {
            "request": request, "page_status": "already_cancelled",
            "booking": booking, "token": token,
        })

    if booking.status == GiftStatus.COMPLETED:
        return templates.TemplateResponse("cancel_booking.html", {
            "request": request, "page_status": "completed",
            "booking": booking, "token": token,
        })

    return templates.TemplateResponse("cancel_booking.html", {
        "request": request, "page_status": "confirm",
        "booking": booking, "token": token,
    })
