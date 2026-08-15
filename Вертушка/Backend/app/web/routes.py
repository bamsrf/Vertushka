"""
Web-маршруты для публичных страниц (HTML, не API)
"""
import hashlib
import logging
from datetime import datetime, timedelta
from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse
from fastapi.templating import Jinja2Templates
from markupsafe import Markup
from sqlalchemy import select, func, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload, selectinload

from app.database import get_db
from app.config import get_settings
from app.models.user import User
from app.models.record import Record
from app.models.collection import Collection, CollectionItem
from app.models.wishlist import Wishlist, WishlistItem
from app.models.follow import Follow
from app.models.profile_share import ProfileShare
from app.models.gift_booking import GiftBooking, GiftStatus
from app.models.offer_click import OfferClick
from app.models.store import Store
from app.models.store_listing import StoreListing, ListingStatus
from app.api.profile import get_public_profile_payload, _get_top_expensive, _get_market_storefront
from app.services.affiliate import wrap_url
from app.services.exchange import get_usd_rub_rate
from app.utils.bot_ua import is_bot_ua
from app.utils.rate_limit import limiter
from app.utils.request_ip import get_client_ip
from app.services.pricing import PricingParams, estimate_rub
from app.services.valuation import get_monthly_delta

logger = logging.getLogger(__name__)

router = APIRouter()
templates = Jinja2Templates(directory="app/web/templates")
settings = get_settings()

BASE_URL = settings.public_base_url.rstrip("/")


_GENRE_RU = {
    # {rel} → склоняется на «релиз / релиза / релизов» по числу.
    # Жанры без дефиса (электроника, классика, джаз) идут как прилагательное в род. падеже.
    "rock": "рок-{rel}",
    "pop": "поп-{rel}",
    "electronic": "электронных {rel}",
    "hip hop": "хип-хоп {rel}",
    "hip-hop": "хип-хоп {rel}",
    "jazz": "джазовых {rel}",
    "classical": "классических {rel}",
    "funk / soul": "фанк- и соул-{rel}",
    "funk": "фанк-{rel}",
    "soul": "соул-{rel}",
    "reggae": "регги-{rel}",
    "blues": "блюзовых {rel}",
    "folk, world, & country": "фолк- и кантри-{rel}",
    "folk": "фолк-{rel}",
    "country": "кантри-{rel}",
    "latin": "латинских {rel}",
    "stage & screen": "саундтрек-{rel}",
    "non-music": "non-music {rel}",
    "children's": "детских {rel}",
    "brass & military": "бравурных {rel}",
}


def _ru_plural(n: int, one: str, few: str, many: str) -> str:
    """Русское склонение существительного по числу.
    one — для 1, 21, 31… (last digit 1, кроме 11–14)
    few — для 2–4, 22–24… (last digit 2–4, кроме 12–14)
    many — для 0, 5–20, 25–30…
    """
    n_abs = abs(int(n))
    if 11 <= n_abs % 100 <= 14:
        return many
    last = n_abs % 10
    if last == 1:
        return one
    if 2 <= last <= 4:
        return few
    return many


def _genre_label(genre: str, count: int) -> str:
    """Возвращает русскую форму жанра + склонённое 'релиз/-а/-ов' по числу."""
    rel = _ru_plural(count, "релиз", "релиза", "релизов")
    key = (genre or "").strip().lower()
    template = _GENRE_RU.get(key) or f"{genre}-{{rel}}"
    return template.replace("{rel}", rel)


# Локальные логотипы (есть в /static/store-logos/{slug}.png). Если slug не в списке —
# фронт нарисует monogram-fallback (первая буква в фирменном цвете).
_LOCAL_STORE_LOGOS = {
    "korobkavinyla", "plastinka_com", "vinyl_ru", "stoprobotvinyl", "found", "doctorhead",
    "skifmusic", "rotaryrecords",
}

_MAX_OFFERS_PER_RECORD = 4


def _offer_dict(slug, store_name, logo_url, price_rub, listing_id, status, *, is_alt: bool) -> dict:
    # logo: приоритет — локальный PNG в статике (мы их положили из мобилки),
    # затем external logo_url из БД, иначе None → фронт нарисует monogram.
    if slug in _LOCAL_STORE_LOGOS:
        logo = f"/static/store-logos/{slug}.png"
    else:
        logo = logo_url or None
    return {
        "store_slug": slug,
        "store_name": store_name,
        "store_logo": logo,
        "price_rub": int(price_rub),
        # Ссылка на свой редиректор, а не на магазин. Раньше тут стоял сырой
        # `listing.url` — без UTM и без трекинга, поэтому весь трафик с
        # публичных страниц был неатрибутирован. Относительный путь: страницы
        # отдаются с того же хоста.
        "url": f"/go/l/{listing_id}",
        "status": status,
        "is_alt_version": is_alt,
    }


async def _load_offers_by_record(
    record_ids: list[UUID],
    master_by_record: dict[UUID, str],
    db: AsyncSession,
) -> dict[UUID, list[dict]]:
    """Возвращает {record_id: [offer, ...]} — активные in_stock-листинги по магазинам.

    Два тира офферов (как в Mobile `/offers/full`):
      • exact — листинги, замэтченные на сам прессинг (`matched_record_id == rid`);
      • alt-version (`is_alt_version=True`) — листинги других прессингов того же
        `discogs_master_id`. Показываются отдельной секцией «Другая версия».

    Сортировка внутри тира: по price_rub ASC, до _MAX_OFFERS_PER_RECORD на тир.
    Цена приведена к целым рублям, чтобы матчилось с подачей в мобилке.
    """
    if not record_ids:
        return {}

    grouped: dict[UUID, list[dict]] = {}

    # === Exact: листинги на сам прессинг ===
    rows = (
        await db.execute(
            select(
                StoreListing.matched_record_id,
                StoreListing.id,
                StoreListing.price_rub,
                StoreListing.status,
                Store.slug,
                Store.name,
                Store.logo_url,
            )
            .join(Store, Store.id == StoreListing.store_id)
            .where(
                StoreListing.matched_record_id.in_(record_ids),
                StoreListing.status == ListingStatus.IN_STOCK,
                StoreListing.price_rub.isnot(None),
                Store.is_active == True,  # noqa: E712
            )
            .order_by(StoreListing.matched_record_id, StoreListing.price_rub.asc())
        )
    ).all()

    for rid, listing_id, price_rub, status, slug, store_name, logo_url in rows:
        bucket = grouped.setdefault(rid, [])
        if len(bucket) >= _MAX_OFFERS_PER_RECORD:
            continue
        # Дедуп по магазину: показываем самое дешёвое предложение от каждого магазина.
        if any(o["store_slug"] == slug for o in bucket):
            continue
        bucket.append(
            _offer_dict(slug, store_name, logo_url, price_rub, listing_id, status, is_alt=False)
        )

    # === Alt-version: листинги других прессингов того же мастера ===
    # master '0' / None — мусорный master, пропускаем (иначе склеит несвязанные записи).
    masters = {m for m in master_by_record.values() if m and m != "0"}
    if not masters:
        return grouped

    alt_rows = (
        await db.execute(
            select(
                StoreListing.matched_record_id,   # прессинг, на который замэтчен листинг
                Record.discogs_master_id,
                StoreListing.id,
                StoreListing.price_rub,
                StoreListing.status,
                Store.slug,
                Store.name,
                Store.logo_url,
            )
            .join(Record, Record.id == StoreListing.matched_record_id)
            .join(Store, Store.id == StoreListing.store_id)
            .where(
                Record.discogs_master_id.in_(masters),
                StoreListing.status == ListingStatus.IN_STOCK,
                StoreListing.price_rub.isnot(None),
                Store.is_active == True,  # noqa: E712
            )
            .order_by(Record.discogs_master_id, StoreListing.price_rub.asc())
        )
    ).all()

    # master → [(listing_record_id, offer_dict)], отсортированы по цене ASC.
    alt_by_master: dict[str, list[tuple[UUID, dict]]] = {}
    for src_rid, master_id, listing_id, price_rub, status, slug, store_name, logo_url in alt_rows:
        alt_by_master.setdefault(master_id, []).append(
            (
                src_rid,
                _offer_dict(
                    slug, store_name, logo_url, price_rub, listing_id, status, is_alt=True
                ),
            )
        )

    for rid in record_ids:
        master_id = master_by_record.get(rid)
        if not master_id or master_id == "0":
            continue
        candidates = alt_by_master.get(master_id)
        if not candidates:
            continue
        exact_bucket = grouped.get(rid, [])
        exact_slugs = {o["store_slug"] for o in exact_bucket}
        alt_bucket: list[dict] = []
        for src_rid, offer in candidates:
            if src_rid == rid:
                continue  # это сам прессинг — уже в exact-тире
            if len(alt_bucket) >= _MAX_OFFERS_PER_RECORD:
                break
            # Дедуп по магазину внутри alt-тира + не дублируем магазин из exact.
            if offer["store_slug"] in exact_slugs:
                continue
            if any(o["store_slug"] == offer["store_slug"] for o in alt_bucket):
                continue
            alt_bucket.append(offer)
        if alt_bucket:
            grouped.setdefault(rid, []).extend(alt_bucket)

    return grouped


def cover_url(record, width: int | None = None) -> str:
    """URL обложки для веб-страницы.

    Две задачи разом.

    1. **Ручные релизы.** У записи, добавленной руками с фото, картинка
       лежит только на диске (`cover_local_path`), а `cover_image_url`
       пустой — в API это разворачивает схема RecordResponse, а веб читал
       поле напрямую и показывал заглушку.
    2. **Вес страницы.** В профиле под сотню обложек, и раньше все шли
       прямыми ссылками на i.discogs.com в 600×600 при ячейке ~200 px.
       600×600 — это 1,4 МБ распакованных пикселей на штуку; на сотне
       обложек браузер начинает выбрасывать декодированное за экраном и
       декодировать заново при возврате, отчего обложки мерцают на
       скролле. `/covers/w/{width}/` режет мастер под ячейку (≈6 КБ WebP
       вместо 49 КБ JPEG).

    Нарезка возможна только для файлов в корне `covers/` — регекс в nginx
    не пускает слэши в имени. Вложенные (`covers/store/…`) отдаём как есть.
    Зеркала нет — остаётся прежний внешний URL, ничего не ломается.
    """
    if not record:
        return ""

    local = getattr(record, "cover_local_path", None)
    if not local:
        return getattr(record, "cover_image_url", None) or ""

    base = settings.public_api_base
    name = local[len("covers/"):] if local.startswith("covers/") else ""
    if width and name and "/" not in name:
        url = f"{base}/covers/w/{width}/{name}"
    else:
        url = f"{base}/uploads/{local}"

    # Cache-bust как в API: перезалив фото меняет метку → новый URL.
    cached_at = getattr(record, "cover_cached_at", None)
    if cached_at:
        url = f"{url}?v={int(cached_at.timestamp())}"
    return url


@router.get("/privacy", response_class=HTMLResponse)
async def privacy_policy(request: Request):
    """Политика конфиденциальности"""
    return templates.TemplateResponse("privacy.html", {"request": request})


@router.get("/terms", response_class=HTMLResponse)
async def terms_of_service(request: Request):
    """Условия использования"""
    return templates.TemplateResponse("terms.html", {"request": request})


@router.get("/support", response_class=HTMLResponse)
async def support_page(request: Request):
    """Страница «Поддержать проект».

    Пустой SUPPORT_URL = сборы выключены, страницы не существует. Отдаём 404, а
    не пустой каркас: страница без единственного целевого действия бессмысленна,
    и её не должно быть в индексе.
    """
    if not settings.support_url:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)

    return templates.TemplateResponse("support.html", {
        "request": request,
        "base_url": BASE_URL,
        "support_url": settings.support_url,
        "support_plans_url": settings.support_plans_url,
        "metrika_id": settings.yandex_metrika_counter_id,
    })


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

    # Эмиссия события ачивок (K5/K6)
    try:
        from app.services.achievements import emit_event
        from app.services.achievements.events import PROFILE_VIEW
        await emit_event(
            db,
            user.id,
            PROFILE_VIEW,
            {"view_count": profile.view_count},
        )
    except Exception:  # noqa: BLE001
        pass  # web-страница не должна падать из-за ачивок

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
    market_releases = await _get_market_storefront(db, limit=24, user_id=user.id)

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

        # Самая свежая пластинка
        newest_row = await db.execute(
            select(Record.year)
            .select_from(ur_join)
            .where(Record.year.isnot(None), Record.year > 1900)
            .order_by(Record.year.desc())
            .limit(1)
        )
        newest = newest_row.first()

        # Релизы текущего года.
        # added_at в БД хранится без таймзоны — работаем с naive UTC,
        # чтобы asyncpg не падал на сравнении offset-aware с naive.
        now_utc_naive = datetime.utcnow()
        current_year = now_utc_naive.year
        fresh_count = await db.scalar(
            select(func.count(Record.id))
            .select_from(ur_join)
            .where(Record.year == current_year)
        ) or 0

        # Distinct artists
        artists_count = await db.scalar(
            select(func.count(func.distinct(Record.artist)))
            .select_from(ur_join)
            .where(Record.artist.isnot(None), Record.artist != "")
        ) or 0

        # Топ-артист (count distinct records по artist)
        top_artist_row = await db.execute(
            select(Record.artist, func.count(Record.id).label("cnt"))
            .select_from(ur_join)
            .where(Record.artist.isnot(None), Record.artist != "")
            .group_by(Record.artist)
            .order_by(func.count(Record.id).desc())
            .limit(1)
        )
        top_artist = top_artist_row.first()

        # Первые прессы / Каноничные / Коллекционка
        rare_count = await db.scalar(
            select(func.count(Record.id))
            .select_from(ur_join)
            .where(or_(Record.is_first_press == True, Record.is_canon == True, Record.is_collectible == True))
        ) or 0

        # Самая дорогая (по estimated_price_rub в коллекции юзера).
        # select_from(CollectionItem) — иначе SQLA вывел бы FROM из Record и
        # JOIN-цепочка не сошлась бы.
        priciest_row = await db.execute(
            select(Record.artist, Record.title, CollectionItem.estimated_price_rub)
            .select_from(CollectionItem)
            .join(Collection, CollectionItem.collection_id == Collection.id)
            .join(Record, CollectionItem.record_id == Record.id)
            .where(
                Collection.user_id == user.id,
                CollectionItem.estimated_price_rub.isnot(None),
                CollectionItem.estimated_price_rub > 0,
            )
            .order_by(CollectionItem.estimated_price_rub.desc())
            .limit(1)
        )
        priciest = priciest_row.first()

        # Возраст коллекции (дни от первой добавленной записи)
        first_added = await db.scalar(
            select(func.min(CollectionItem.added_at))
            .join(Collection, Collection.id == CollectionItem.collection_id)
            .where(Collection.user_id == user.id)
        )

        # Новых за последние 7 дней
        week_ago = now_utc_naive - timedelta(days=7)
        new_this_week = await db.scalar(
            select(func.count(CollectionItem.id))
            .join(Collection, Collection.id == CollectionItem.collection_id)
            .where(
                Collection.user_id == user.id,
                CollectionItem.added_at >= week_ago,
            )
        ) or 0

        # === Сборка списка ===
        # Правило: stat показывается только если значение > 0 и проходит порог.
        # Все формы существительных/прилагательных склоняются по числу через _ru_plural.
        #
        # ВАЖНО про `html`: значение обязано быть Markup, собранным через
        # Markup(...).format(...) — этот .format() экранирует КАЖДЫЙ аргумент.
        # Обычная f-строка сюда класть нельзя: имя артиста и жанр приходят из
        # Record и задаются пользователем (schemas/record.py: artist/genre —
        # свободные строки), то есть попадали бы в разметку публичной страницы
        # как есть. Шаблон больше не делает `|safe`, поэтому забытый Markup
        # даст видимые теги, а не исполнение — ошибка станет заметной, но
        # безопасной.
        if color_count > 0:
            phrase = _ru_plural(color_count, "цветная пластинка", "цветные пластинки", "цветных пластинок")
            fun_stats.append({
                "icon": "🎨",
                "html": Markup("<b>{}</b> {}").format(color_count, phrase),
            })
        if top_genre and top_genre_count >= 2:
            fun_stats.append({
                "icon": "🎧",
                "html": Markup("<b>{}</b> {}").format(
                    top_genre_count, _genre_label(top_genre, top_genre_count),
                ),
            })
        if top_decade and top_decade_count >= 2:
            word = _ru_plural(top_decade_count, "пластинка", "пластинки", "пластинок")
            fun_stats.append({
                "icon": "📻",
                "html": Markup("<b>{}</b> {} из {}-х").format(top_decade_count, word, top_decade),
            })
        if fresh_count > 0:
            word = _ru_plural(fresh_count, "релиз", "релиза", "релизов")
            fun_stats.append({
                "icon": "🚀",
                "html": Markup("<b>{}</b> {} {}-го").format(fresh_count, word, current_year),
            })
        if countries_count >= 2:
            word = _ru_plural(countries_count, "страна", "страны", "стран")
            fun_stats.append({
                "icon": "🌍",
                "html": Markup("<b>{}</b> {} в коллекции").format(countries_count, word),
            })
        if labels_count >= 3:
            phrase = _ru_plural(labels_count, "разный лейбл", "разных лейбла", "разных лейблов")
            fun_stats.append({
                "icon": "🏷️",
                "html": Markup("<b>{}</b> {}").format(labels_count, phrase),
            })
        if artists_count >= 5:
            phrase = _ru_plural(artists_count, "разный артист", "разных артиста", "разных артистов")
            fun_stats.append({
                "icon": "🎙️",
                "html": Markup("<b>{}</b> {}").format(artists_count, phrase),
            })
        if top_artist and top_artist[1] >= 2:
            artist_name = (top_artist[0] or "").strip()
            if len(artist_name) > 22:
                artist_name = artist_name[:22] + "…"
            fun_stats.append({
                "icon": "👑",
                "html": Markup("Топ-артист: <b>{}</b>").format(artist_name),
            })
        if oldest and oldest[0]:
            artist_name = (oldest[1] or "").strip()
            if len(artist_name) > 18:
                artist_name = artist_name[:18] + "…"
            suffix = f" · {artist_name}" if artist_name else ""
            fun_stats.append({
                "icon": "🕰️",
                "html": Markup("Самая старая: <b>{}</b>{}").format(oldest[0], suffix),
            })
        if newest and newest[0] and (not oldest or newest[0] != oldest[0]):
            fun_stats.append({
                "icon": "🆕",
                "html": Markup("Самая свежая: <b>{}</b>").format(newest[0]),
            })
        if rare_count > 0:
            phrase = _ru_plural(rare_count, "редкое издание", "редких издания", "редких изданий")
            fun_stats.append({
                "icon": "💎",
                "html": Markup("<b>{}</b> {}").format(rare_count, phrase),
            })
        if priciest and priciest[2] and priciest[2] >= 1000:
            price_fmt = f"{int(priciest[2]):,}".replace(",", " ")
            fun_stats.append({
                "icon": "💸",
                "html": Markup("Самая дорогая: <b>{} ₽</b>").format(price_fmt),
            })
        if first_added:
            fa = first_added.replace(tzinfo=None) if first_added.tzinfo else first_added
            days = (now_utc_naive - fa).days
            if days >= 365:
                years = days // 365
                word = _ru_plural(years, "год", "года", "лет")
                fun_stats.append({
                    "icon": "📅",
                    "html": Markup("Собирает <b>{}</b> {}").format(years, word),
                })
            elif days >= 90:
                months = max(1, days // 30)
                word = _ru_plural(months, "месяц", "месяца", "месяцев")
                fun_stats.append({
                    "icon": "📅",
                    "html": Markup("Собирает <b>{}</b> {}").format(months, word),
                })
        if new_this_week >= 2:
            phrase = _ru_plural(new_this_week, "новая пластинка", "новые пластинки", "новых пластинок")
            fun_stats.append({
                "icon": "⚡",
                "html": Markup("<b>{}</b> {} за неделю").format(new_this_week, phrase),
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

    # Витрина "Самые дорогие" должна идти в том же порядке, что отображается:
    # _get_top_expensive сортирует по estimated_price_median (USD-база), а
    # шаблон рисует RUB через compute_rub с поправками на страну/формат/курс,
    # поэтому без пересортировки порядок выглядит "вразнобой".
    top_expensive = sorted(top_expensive, key=compute_rub, reverse=True)

    # === Активные офферы магазинов-партнёров ===
    # Собираем все record_id, которые попадут в любую модалку профиля (карточки в
    # сетке, рейлы, highlights). Один query вытягивает по каждой записи топ-4
    # in_stock-листинга — фронт прокинет их через data-offers в JSON.
    _record_id_set: set[UUID] = set()
    _master_by_record: dict[UUID, str] = {}

    def _track(record) -> None:
        if not record:
            return
        _record_id_set.add(record.id)
        master = getattr(record, "discogs_master_id", None)
        if master:
            _master_by_record[record.id] = master

    for it in collection_items:
        _track(it.record)
    for it in wishlist_items:
        _track(it.record)
    for r in top_expensive:
        _track(r)
    for r in market_releases:
        _track(r)
    for r in highlights:
        _track(r)
    offers_by_record = await _load_offers_by_record(
        list(_record_id_set), _master_by_record, db
    )

    def offers_for(record) -> list[dict]:
        if not record:
            return []
        return offers_by_record.get(record.id, [])

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
        "market_releases": market_releases,
        "highlights": highlights,
        "collection_items": collection_items,
        "wishlist_items": wishlist_items,
        "active_tab": tab if tab in ("collection", "wishlist") else "collection",
        "og_description": og_description,
        "base_url": BASE_URL,
        "usd_rub_rate": float(usd_rub_rate),
        "compute_rub": compute_rub,
        "cover_url": cover_url,
        "offers_for": offers_for,
        # Пусто по умолчанию → _metrika.html не рендерит ничего.
        "metrika_id": settings.yandex_metrika_counter_id,
        # Пусто по умолчанию → _support.html не рендерит ничего.
        "support_url": settings.support_url,
        "support_plans_url": settings.support_plans_url,
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


@router.get("/confirm/{booking_id}", response_class=HTMLResponse)
async def confirm_booking_page(
    request: Request,
    booking_id: UUID,
    token: str = "",
    db: AsyncSession = Depends(get_db)
):
    """Страница подтверждения email-верификации бронирования."""
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
        return templates.TemplateResponse("confirm_booking.html", {
            "request": request, "page_status": "not_found",
            "booking": None, "token": "",
        })

    if not booking.verify_token or booking.verify_token != token:
        # Возможно уже подтверждено (verify_token обнулён) — даём дружелюбный экран
        if booking.status == GiftStatus.BOOKED and not booking.verify_token:
            return templates.TemplateResponse("confirm_booking.html", {
                "request": request, "page_status": "already_confirmed",
                "booking": booking, "token": "",
            })
        return templates.TemplateResponse("confirm_booking.html", {
            "request": request, "page_status": "invalid_token",
            "booking": None, "token": "",
        })

    if booking.status == GiftStatus.CANCELLED:
        return templates.TemplateResponse("confirm_booking.html", {
            "request": request, "page_status": "cancelled",
            "booking": booking, "token": token,
        })

    if booking.status == GiftStatus.COMPLETED:
        return templates.TemplateResponse("confirm_booking.html", {
            "request": request, "page_status": "completed",
            "booking": booking, "token": token,
        })

    if booking.status == GiftStatus.BOOKED:
        return templates.TemplateResponse("confirm_booking.html", {
            "request": request, "page_status": "already_confirmed",
            "booking": booking, "token": token,
        })

    # PENDING — основной кейс, показываем форму подтверждения
    return templates.TemplateResponse("confirm_booking.html", {
        "request": request, "page_status": "confirm",
        "booking": booking, "token": token,
    })


# ============================================================================
# Редиректор переходов в магазин — docs/plans/CLICK_REDIRECTOR_AND_METRIKA.md
# ============================================================================
#
# Почему 302, а не страница со счётчиком Метрики и `location.replace()`:
# tag.js грузится асинхронно, адблок/Private Relay/DNS-фильтр режут домен
# Метрики, а любой таймер — выбор между потерей кликов и торможением перехода.
# Здесь гонки нет вообще: истина живёт в `offer_clicks`, а хит в Метрику уйдёт
# fire-and-forget и на редирект не влияет.

# no-store обязателен вместе с 302. С 301 браузер закешировал бы редирект
# практически навсегда: второй клик по тому же офферу пошёл бы в магазин
# напрямую, минуя нас, и исчез из статистики.
_REDIRECT_HEADERS = {"Cache-Control": "no-store, no-cache, must-revalidate"}


def _offer_redirect(url: str) -> RedirectResponse:
    """302 в магазин. Только 302/307 — см. комментарий к _REDIRECT_HEADERS."""
    return RedirectResponse(url=url, status_code=status.HTTP_302_FOUND, headers=_REDIRECT_HEADERS)


def _dead_link_response() -> HTMLResponse:
    """Ссылка не резолвится: чужой/устаревший id, снятый с продажи листинг."""
    return HTMLResponse(
        content=(
            "<!doctype html><meta charset=utf-8>"
            "<title>Ссылка недействительна</title>"
            "<p>Это предложение больше недоступно. "
            f'<a href="{BASE_URL}">Открыть Вертушку</a></p>'
        ),
        status_code=status.HTTP_404_NOT_FOUND,
        headers=_REDIRECT_HEADERS,
    )


@router.get("/go/{click_id}", include_in_schema=False)
async def redirect_registered_click(
    click_id: UUID,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Переход по клику, зарегистрированному заранее (мобилка).

    Клик уже создан в `POST /api/offers/{id}/click` — там он нужен ДО открытия
    браузера, чтобы его id уехал в affiliate-deeplink как `subid`. Здесь мы
    только подтверждаем, что переход реально состоялся, и отдаём 302.

    Резолвим строго UUID из своей БД. URL в query-параметре не принимаем ни
    сейчас, ни в будущих версиях: это мгновенно превратило бы наш домен в
    инструмент фишинга (открытый редиректор).
    """
    stmt = (
        select(OfferClick)
        .options(
            joinedload(OfferClick.listing).joinedload(StoreListing.store),
        )
        .where(OfferClick.id == click_id)
    )
    click = (await db.execute(stmt)).unique().scalar_one_or_none()
    if click is None or click.listing is None or click.listing.store is None:
        return _dead_link_response()

    listing = click.listing
    final_url = wrap_url(
        listing.store,
        listing.url,
        subid=str(click.id),
        user_id=str(click.user_id) if click.user_id else None,
    )

    # Пишем подтверждение только на первом заходе. Повторное открытие той же
    # ссылки (кнопка «назад» в браузере) — не новый переход, и портить им
    # метрику потерь нельзя.
    if click.redirected_at is None:
        click.redirected_at = datetime.utcnow()
        click.is_bot = is_bot_ua(request.headers.get("user-agent"))
        await db.commit()

    return _offer_redirect(final_url)


@router.get("/go/l/{listing_id}", include_in_schema=False)
# Этот маршрут СОЗДАЁТ строку в offer_clicks на каждый GET, поэтому он
# накручиваемый ровно как и click-эндпоинт. Лимит выше мобильного (30/мин):
# страница профиля показывает до 4 офферов на пластинку, и живой человек может
# открыть несколько подряд в новых вкладках.
@limiter.limit("30/minute")
async def redirect_web_listing(
    listing_id: UUID,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Переход с публичной веб-страницы (профиль, вишлист).

    Здесь клик создаётся В МОМЕНТ GET, в отличие от мобильного
    `/go/{click_id}`. Создавать его при рендере страницы нельзя: тогда каждый
    показ карточки считался бы кликом, и CTR стал бы бессмысленным.

    Именно этот маршрут попадает в HTML, поэтому по нему ходят краулеры и
    превью мессенджеров — их помечаем `is_bot`, но редирект отдаём (ломать
    превью незачем).
    """
    stmt = (
        select(StoreListing)
        .options(joinedload(StoreListing.store))
        .where(StoreListing.id == listing_id)
    )
    listing = (await db.execute(stmt)).unique().scalar_one_or_none()
    if listing is None or listing.store is None or not listing.store.is_active:
        return _dead_link_response()

    user_agent = request.headers.get("user-agent")
    now = datetime.utcnow()
    click = OfferClick(
        listing_id=listing.id,
        # Веб публичный и анонимный: узнать юзера здесь нельзя, поэтому
        # utm_content у таких переходов не будет — это ожидаемо.
        user_id=None,
        ip_hash=_hash_client_ip(request),
        user_agent=(user_agent or "")[:500] or None,
        surface="web",
        source="web_profile",
        redirected_at=now,
        is_bot=is_bot_ua(user_agent),
    )
    db.add(click)
    await db.flush()  # нужен click.id для subid
    final_url = wrap_url(listing.store, listing.url, subid=str(click.id))
    await db.commit()

    return _offer_redirect(final_url)


def _hash_client_ip(request: Request) -> str | None:
    """sha256(ip + SECRET_KEY) — тот же контракт, что `api/offers._hash_ip`.

    IP берём через `get_client_ip` (X-Real-IP / последний хоп XFF), а не из
    первого элемента X-Forwarded-For: тот присылает клиент, и накрутчик
    выглядел бы как тысяча разных людей.
    """
    ip = get_client_ip(request)
    if not ip or ip == "unknown":
        return None
    return hashlib.sha256(f"{ip}|{settings.secret_key}".encode("utf-8")).hexdigest()
