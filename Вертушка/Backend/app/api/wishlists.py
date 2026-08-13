"""
API для работы с вишлистами
"""
from datetime import datetime, timedelta
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.models.user import User
from app.models.record import Record
from app.models.wishlist import Wishlist, WishlistItem, WishlistFolder, wishlist_folder_items
from app.models.store_listing import StoreListing, ListingStatus
from app.models.radar_status_event import RadarStatusEvent
from app.models.gift_booking import GiftBooking, GiftStatus
from app.api.auth import get_current_user, get_current_user_optional
from app.services.cover_storage import ensure_cover_cached
from app.services.alt_media_match import alt_media_ok
from app.schemas.wishlist import (
    WishlistResponse,
    WishlistItemCreate,
    WishlistItemUpdate,
    WishlistItemResponse,
    WishlistPublicResponse,
    WishlistPublicItemResponse,
    GiftBookingInfo,
    MoveToCollectionRequest,
    WishlistFolderCreate,
    WishlistFolderUpdate,
    WishlistFolderResponse,
    WishlistFolderWithItems,
    WishlistFolderItemsAdd,
    RadarResponse,
    RadarItem,
    RadarAlt,
    RadarEventItem,
    RadarEventsResponse,
)
from app.schemas.record import RecordBrief
from app.schemas.collection import CollectionItemResponse

router = APIRouter()


@router.get("/", response_model=WishlistResponse)
async def get_my_wishlist(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Получение вишлиста текущего пользователя"""
    result = await db.execute(
        select(Wishlist)
        .where(Wishlist.user_id == current_user.id)
        .options(
            selectinload(Wishlist.items)
            .selectinload(WishlistItem.record),
            selectinload(Wishlist.items)
            .selectinload(WishlistItem.gift_booking)
        )
    )
    wishlist = result.scalar_one_or_none()
    
    if not wishlist:
        # Создаём вишлист если его нет
        wishlist = Wishlist(user_id=current_user.id)
        db.add(wishlist)
        await db.commit()
        await db.refresh(wishlist)
        wishlist.items = []
    
    return WishlistResponse(
        id=wishlist.id,
        user_id=wishlist.user_id,
        share_token=wishlist.share_token,
        is_public=wishlist.is_public,
        show_gifter_names=wishlist.show_gifter_names,
        custom_message=wishlist.custom_message,
        created_at=wishlist.created_at,
        updated_at=wishlist.updated_at,
        items=[WishlistItemResponse(
            id=item.id,
            wishlist_id=item.wishlist_id,
            record_id=item.record_id,
            priority=item.priority,
            notes=item.notes,
            is_purchased=item.is_purchased,
            added_at=item.added_at,
            purchased_at=item.purchased_at,
            record=item.record,
            notify_mode=item.notify_mode,
            price_threshold_rub=item.price_threshold_rub,
            conditions=item.conditions,
            accept_alt=item.accept_alt,
            is_booked=item.gift_booking is not None,
            # Имя дарителя владельцу — только если он сам включил
            # reveal_gifter_to_owner. Раньше оно уходило безусловно, и бронь,
            # обещанная анонимной, раскрывалась прямо в своём же вишлисте.
            gift_booking=GiftBookingInfo(
                id=item.gift_booking.id,
                gifter_name=(
                    item.gift_booking.gifter_name
                    if wishlist.reveal_gifter_to_owner else ""
                ),
                status=item.gift_booking.status,
                booked_at=item.gift_booking.booked_at
            ) if item.gift_booking else None
        ) for item in wishlist.items]
    )


# ── Радар ────────────────────────────────────────────────────────────────────

_MIN_DROP = None  # (не используется здесь; статусы считаются напрямую)


def _grade_of(condition_raw: str | None) -> str | None:
    """Сырой `StoreListing.condition` → канон-грейд ('sealed'|'mint'|'vg_plus'|'vg').

    Неизвестное/пустое → None (лениво: считаем подходящим при любом фильтре, чтобы
    не прятать реальные предложения из-за нераспознанного текста состояния).
    """
    if not condition_raw:
        return None
    c = condition_raw.strip().lower()
    if any(k in c for k in ("seal", "запечат", "ss", "new", "новая")):
        return "sealed"
    if "vg+" in c or "vg plus" in c or "very good plus" in c:
        return "vg_plus"
    if any(k in c for k in ("mint", "nm", "m-", "m/", "идеальн")):
        return "mint"
    if "vg" in c or "very good" in c or "хорош" in c:
        return "vg"
    return None


def _condition_ok(condition_raw: str | None, accepted: list | None) -> bool:
    """Проходит ли листинг по выбранным грейдам. accepted=None → любое."""
    if not accepted:
        return True
    grade = _grade_of(condition_raw)
    if grade is None:
        return True  # нераспознанное — не отсеиваем
    return grade in accepted


def _alt_media_ok(wanted: Record, alt: Record | None, listing: StoreListing) -> bool:
    """Носитель альтернативы совпадает с желаемым (винил→винил, а не mp3)."""
    return alt_media_ok(
        getattr(wanted, "format_type", None),
        getattr(wanted, "format_description", None),
        getattr(alt, "format_type", None),
        getattr(alt, "format_description", None),
        getattr(listing, "format_raw", None),
    )


RADAR_MAX = 5  # максимум подписанных пластинок на радаре
# Окно свежести: на радаре учитываем только листинги, перепроверенные за N часов.
# Гарантированное протухание (weekly_cleanup_stale) — лишь через 30 дней, а
# stock_refresh_active берёт stale>6ч с лимитом на магазин, поэтому фантомный
# IN_STOCK может жить днями и «дёргать» самую дешёвую цену. Окно это отсекает.
RADAR_FRESHNESS_HOURS = 48


def _radar_radius(status: str, price: float | None, threshold: float | None) -> float:
    """Доля 0..1 ВНУТРИ полосы статуса (клиент раскладывает по зонам).

    0 — у ближнего края полосы, 1 — у дальнего. Для match/available зависит от
    близости цены к порогу: чем дешевле относительно порога, тем ближе к центру.
    """
    if status == "match":
        if threshold and price is not None and threshold > 0:
            return round(min(1.0, price / threshold), 3)  # цена→порог = дальше в зоне
        return 0.4
    if status == "available":
        if threshold and price is not None and threshold > 0:
            over = (price - threshold) / threshold
            return round(min(1.0, max(0.0, over)), 3)  # сильно дороже порога = дальше
        return 0.5  # порог не задан — середина
    return 0.5  # alt / absent — середина своей полосы


@router.get("/radar", response_model=RadarResponse)
async def get_radar(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Радар: subscribed-пластинки с вычисленным статусом, ценой по состоянию и позицией."""
    items = (
        await db.execute(
            select(WishlistItem)
            .join(Wishlist)
            .where(
                Wishlist.user_id == current_user.id,
                WishlistItem.notify_mode == "subscribed",
            )
            .options(selectinload(WishlistItem.record))
        )
    ).scalars().all()
    if not items:
        return RadarResponse(items=[], count=0, match_count=0)

    records = {i.record.id: i.record for i in items if i.record}
    record_ids = list(records.keys())
    masters: dict[str, list] = {}
    for rec in records.values():
        mid = getattr(rec, "discogs_master_id", None)
        if mid:
            masters.setdefault(str(mid), []).append(rec.id)

    # In_stock листинги: для записей радара И для записей-аналогов (тот же мастер).
    # Фикс A: только свежие (перепроверенные за RADAR_FRESHNESS_HOURS) — иначе
    # протухшие фантомные офферы гоняют «самую дешёвую» цену.
    fresh_cutoff = datetime.utcnow() - timedelta(hours=RADAR_FRESHNESS_HOURS)
    listing_q = (
        select(StoreListing, Record.id.label("rec_id"), Record.discogs_master_id.label("mid"))
        .join(Record, StoreListing.matched_record_id == Record.id)
        .where(
            StoreListing.status == ListingStatus.IN_STOCK,
            StoreListing.last_seen_at >= fresh_cutoff,
        )
    )
    conds = [StoreListing.matched_record_id.in_(record_ids)]
    if masters:
        conds.append(Record.discogs_master_id.in_(list(masters.keys())))
    from sqlalchemy import or_ as _or
    listing_rows = (await db.execute(listing_q.where(_or(*conds)))).all()

    # Бакеты: по exact record и по master. Храним листинг целиком (нужен url).
    exact_by_record: dict[str, list[StoreListing]] = {}
    by_master: dict[str, list[tuple[StoreListing, str]]] = {}
    for listing, rec_id, mid in listing_rows:
        if rec_id in record_ids:
            exact_by_record.setdefault(str(rec_id), []).append(listing)
        if mid:
            by_master.setdefault(str(mid), []).append((listing, str(rec_id)))

    # Догружаем Record'ы альтернативных прессингов (их нет в вишлисте, но нужны
    # обложка/год/страна/формат для экрана подтверждения).
    alt_ids = {
        listing.matched_record_id
        for listing, rec_id, _mid in listing_rows
        if rec_id not in record_ids and listing.matched_record_id is not None
    }
    alt_records: dict = dict(records)
    if alt_ids:
        rows = (await db.execute(select(Record).where(Record.id.in_(list(alt_ids))))).scalars().all()
        for r in rows:
            alt_records[r.id] = r

    out: list[RadarItem] = []
    match_count = 0
    for wi in items:
        rec = wi.record
        if not rec:
            continue
        accepted = wi.conditions
        threshold = float(wi.price_threshold_rub) if wi.price_threshold_rub is not None else None

        exact = [
            l for l in exact_by_record.get(str(rec.id), [])
            if l.price_rub is not None and _condition_ok(l.condition, accepted)
        ]
        # Tie-break по id (Фикс B): при равных ценах выбор оффера стабилен.
        exact.sort(key=lambda l: (float(l.price_rub), str(l.id)))
        lowest = float(exact[0].price_rub) if exact else None
        buy_url = exact[0].url if exact else None
        buy_listing_id = exact[0].id if exact else None

        alt_payload = None
        # Кандидаты-аналоги (другой прессинг того же мастера) — считаем всегда,
        # чтобы отдать их для экрана подтверждения и для accept_alt.
        mid = str(getattr(rec, "discogs_master_id", "") or "")
        rejected_alts = set(wi.rejected_alt_record_ids or [])
        alt_candidates = [
            (l, rid) for (l, rid) in by_master.get(mid, [])
            if rid != str(rec.id)
            and str(l.matched_record_id) not in rejected_alts
            and l.price_rub is not None
            and _condition_ok(l.condition, accepted)
            # Мастер объединяет винил, CD и цифру — предлагаем только тот же
            # носитель, что в вишлисте. Иначе под винил прилетал «File, MP3».
            and _alt_media_ok(rec, alt_records.get(l.matched_record_id), l)
        ]
        if alt_candidates:
            cheapest_alt, alt_rid = min(alt_candidates, key=lambda x: (float(x[0].price_rub), str(x[0].id)))
            alt_rec = alt_records.get(cheapest_alt.matched_record_id)
            alt_payload = RadarAlt(
                record_id=cheapest_alt.matched_record_id,
                title=getattr(alt_rec, "title", None),
                cover_url=getattr(alt_rec, "cover_image_url", None),
                price_rub=cheapest_alt.price_rub,
                year=getattr(alt_rec, "year", None),
                country=getattr(alt_rec, "country", None),
                format=getattr(alt_rec, "format_description", None) or getattr(alt_rec, "format_type", None),
                buy_url=cheapest_alt.url,
                buy_listing_id=cheapest_alt.id,
            )

        if exact:
            if threshold is not None and lowest is not None and lowest <= threshold:
                status_v = "match"
                match_count += 1
            else:
                status_v = "available"
        elif wi.accept_alt and alt_payload is not None:
            # Юзер принял аналог как подходящий → считаем его «в продаже».
            status_v = "available"
            lowest = float(alt_payload.price_rub) if alt_payload.price_rub is not None else None
            buy_url = alt_payload.buy_url
            buy_listing_id = alt_payload.buy_listing_id
            if threshold is not None and lowest is not None and lowest <= threshold:
                status_v = "match"
                match_count += 1
        elif alt_payload is not None:
            status_v = "alt"
        else:
            status_v = "absent"

        out.append(
            RadarItem(
                wishlist_item_id=wi.id,
                record=RecordBrief.model_validate(rec),
                status=status_v,
                lowest_price_rub=(lowest if status_v in ("match", "available") else None),
                threshold_rub=wi.price_threshold_rub,
                conditions=accepted,
                accept_alt=wi.accept_alt,
                radius=_radar_radius(status_v, lowest, threshold),
                offers_count=(len(exact) if exact else (1 if status_v == "available" else 0)),
                buy_url=buy_url,
                buy_listing_id=buy_listing_id,
                # Отдаём альтернативу и когда она уже принята (accept_alt) —
                # иначе с фронта нельзя открыть шит и отменить решение.
                alt=(alt_payload if (status_v == "alt" or wi.accept_alt) else None),
            )
        )

    return RadarResponse(items=out, count=len(out), match_count=match_count, limit=RADAR_MAX)


@router.get("/radar/events/{item_id}", response_model=RadarEventsResponse)
async def get_radar_events(
    item_id: UUID,
    limit: int = 20,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Хронология смен статуса пластинки на радаре (для шторки цены)."""
    wi = (
        await db.execute(
            select(WishlistItem).join(Wishlist).where(
                WishlistItem.id == item_id,
                Wishlist.user_id == current_user.id,
            )
        )
    ).scalar_one_or_none()
    if wi is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Элемент не найден")
    rows = (
        await db.execute(
            select(RadarStatusEvent)
            .where(RadarStatusEvent.wishlist_item_id == item_id)
            .order_by(RadarStatusEvent.created_at.desc())
            .limit(min(max(limit, 1), 100))
        )
    ).scalars().all()
    return RadarEventsResponse(events=[RadarEventItem.model_validate(r) for r in rows])


@router.post("/items", response_model=WishlistItemResponse, status_code=status.HTTP_201_CREATED)
async def add_to_wishlist(
    data: WishlistItemCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Добавление пластинки в вишлист"""
    from app.api.records import get_or_create_record_by_discogs_id

    # Получаем вишлист
    result = await db.execute(
        select(Wishlist).where(Wishlist.user_id == current_user.id)
    )
    wishlist = result.scalar_one_or_none()

    if not wishlist:
        wishlist = Wishlist(user_id=current_user.id)
        db.add(wishlist)
        await db.flush()

    # Получаем Record: либо по discogs_id, либо по record_id
    if data.discogs_id:
        record = await get_or_create_record_by_discogs_id(data.discogs_id, db)
    elif data.record_id:
        result = await db.execute(select(Record).where(Record.id == data.record_id))
        record = result.scalar_one_or_none()
        if not record:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Пластинка не найдена"
            )
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Необходимо указать либо discogs_id, либо record_id"
        )

    # Whitelist: в вишлист пускаем 'discogs', 'user' и 'store'. При будущем merge
    # в Discogs все переезжают через merged_into_id (soft-delete), а
    # safe_merge_store_native_into ремапит wishlist_items source→target.
    # Физического DELETE записей нет → CASCADE FK не теряет items.
    if record.source not in ("discogs", "user", "store"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Пока эту пластинку нельзя добавить в вишлист — её ещё нет на Discogs",
        )

    # Проверяем, есть ли эта пластинка в коллекции (хотя бы одна копия)
    from app.models.collection import Collection, CollectionItem

    collection_item_query = await db.execute(
        select(CollectionItem)
        .join(Collection)
        .where(
            Collection.user_id == current_user.id,
            CollectionItem.record_id == record.id
        )
    )
    if collection_item_query.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Пластинка уже в вашей коллекции"
        )

    # Проверяем, не добавлена ли уже в вишлист
    result = await db.execute(
        select(WishlistItem)
        .where(
            WishlistItem.wishlist_id == wishlist.id,
            WishlistItem.record_id == record.id
        )
    )
    if result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Пластинка уже в вишлисте"
        )

    # Добавляем
    item = WishlistItem(
        wishlist_id=wishlist.id,
        record_id=record.id,
        priority=data.priority,
        notes=data.notes
    )
    db.add(item)
    await db.commit()
    await db.refresh(item)

    # Запускаем фоновое скачивание обложки (если ещё не скачана)
    if record.discogs_id:
        await ensure_cover_cached(record.discogs_id, record.cover_image_url, db)

    # Эмиссия события ачивок
    from app.services.achievements import emit_event
    from app.services.achievements.events import RECORD_WANTED, WISHLIST_ITEM_ADDED
    await emit_event(
        db,
        current_user.id,
        WISHLIST_ITEM_ADDED,
        {"wishlist_item_id": item.id, "record_id": record.id},
    )

    # Триггерим K14–K16 у владельцев этой пластинки (она у них в коллекции).
    # Сам себе не считается. Кол-во «хотельщиков» evaluator берёт из БД.
    from sqlalchemy import distinct as _distinct
    from app.models.collection import Collection as _Collection, CollectionItem as _CI
    owner_rows = await db.execute(
        select(_distinct(_Collection.user_id))
        .join(_CI, _CI.collection_id == _Collection.id)
        .where(_CI.record_id == record.id, _Collection.user_id != current_user.id)
    )
    for (owner_id,) in owner_rows.all():
        await emit_event(db, owner_id, RECORD_WANTED, {"record_id": record.id})

    return WishlistItemResponse(
        id=item.id,
        wishlist_id=item.wishlist_id,
        record_id=item.record_id,
        priority=item.priority,
        notes=item.notes,
        is_purchased=item.is_purchased,
        added_at=item.added_at,
        purchased_at=item.purchased_at,
        record=record,
        notify_mode=item.notify_mode,
        price_threshold_rub=item.price_threshold_rub,
        conditions=item.conditions,
        accept_alt=item.accept_alt,
        is_booked=False,
        gift_booking=None
    )


@router.put("/records/{item_id}", response_model=WishlistItemResponse)
async def update_wishlist_item(
    item_id: UUID,
    data: WishlistItemUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Обновление элемента вишлиста"""
    result = await db.execute(
        select(WishlistItem)
        .where(WishlistItem.id == item_id)
        .options(
            selectinload(WishlistItem.wishlist),
            selectinload(WishlistItem.record),
            selectinload(WishlistItem.gift_booking)
        )
    )
    item = result.scalar_one_or_none()
    
    if not item:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Элемент не найден"
        )
    
    if item.wishlist.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Нет доступа"
        )
    
    if data.priority is not None:
        item.priority = data.priority
    if data.notes is not None:
        item.notes = data.notes
    if data.notify_mode is not None:
        # Лимит радара: не больше RADAR_MAX подписанных пластинок.
        if data.notify_mode == "subscribed" and item.notify_mode != "subscribed":
            active = (
                await db.execute(
                    select(func.count())
                    .select_from(WishlistItem)
                    .join(Wishlist)
                    .where(
                        Wishlist.user_id == current_user.id,
                        WishlistItem.notify_mode == "subscribed",
                        WishlistItem.id != item.id,
                    )
                )
            ).scalar_one()
            if active >= RADAR_MAX:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail={"code": "radar_limit", "limit": RADAR_MAX},
                )
        item.notify_mode = data.notify_mode
    # threshold: только при subscribed имеет смысл, но храним как задано —
    # producer сам применяет порог лишь для subscribed-item'ов.
    if "price_threshold_rub" in data.model_fields_set:
        item.price_threshold_rub = data.price_threshold_rub
    if "conditions" in data.model_fields_set:
        item.conditions = data.conditions
    if "accept_alt" in data.model_fields_set and data.accept_alt is not None:
        item.accept_alt = data.accept_alt
    if data.reject_alt_record_id is not None:
        # «Нет» на аналоге: запоминаем прессинг, чтобы радар его не предлагал.
        rejected = list(item.rejected_alt_record_ids or [])
        rid = str(data.reject_alt_record_id)
        if rid not in rejected:
            rejected.append(rid)
        item.rejected_alt_record_ids = rejected
        item.accept_alt = False

    await db.commit()
    await db.refresh(item)

    return WishlistItemResponse(
        id=item.id,
        wishlist_id=item.wishlist_id,
        record_id=item.record_id,
        priority=item.priority,
        notes=item.notes,
        is_purchased=item.is_purchased,
        added_at=item.added_at,
        purchased_at=item.purchased_at,
        record=item.record,
        notify_mode=item.notify_mode,
        price_threshold_rub=item.price_threshold_rub,
        conditions=item.conditions,
        accept_alt=item.accept_alt,
        is_booked=item.gift_booking is not None,
        # Имя дарителя — только при явном reveal_gifter_to_owner (см. GET /)
        gift_booking=GiftBookingInfo(
            id=item.gift_booking.id,
            gifter_name=(
                item.gift_booking.gifter_name
                if item.wishlist.reveal_gifter_to_owner else ""
            ),
            status=item.gift_booking.status,
            booked_at=item.gift_booking.booked_at
        ) if item.gift_booking else None
    )


@router.delete("/records/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_from_wishlist(
    item_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Удаление пластинки из вишлиста.
    Если есть активная бронь — авто-cancel + письмо дарителю.
    """
    result = await db.execute(
        select(WishlistItem)
        .where(WishlistItem.id == item_id)
        .options(
            selectinload(WishlistItem.wishlist),
            selectinload(WishlistItem.record),
            selectinload(WishlistItem.gift_booking),
        )
    )
    item = result.scalar_one_or_none()

    if not item:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Элемент не найден"
        )

    if item.wishlist.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Нет доступа"
        )

    # Снимок данных для письма дарителю + авто-cancel активной брони
    pending_email_payload = None
    if item.gift_booking and item.gift_booking.status == GiftStatus.BOOKED:
        booking = item.gift_booking
        if booking.gifter_email and item.record:
            pending_email_payload = {
                "gifter_email": booking.gifter_email,
                "gifter_name": booking.gifter_name,
                "record_title": item.record.title,
                "owner_name": current_user.display_name or current_user.username,
            }
        booking.status = GiftStatus.CANCELLED
        booking.cancelled_at = datetime.utcnow()
        booking.cancellation_reason = "item_removed_by_owner"
        booking.wishlist_item_id = None
        await db.flush()

    await db.delete(item)
    await db.commit()

    if pending_email_payload:
        try:
            from app.services.notifications import send_wishlist_item_removed_to_gifter
            await send_wishlist_item_removed_to_gifter(**pending_email_payload)
        except Exception:
            pass


@router.get("/share/{share_token}", response_model=WishlistPublicResponse)
async def get_public_wishlist(
    share_token: str,
    q: str | None = Query(None, description="Поиск по вишлисту"),
    db: AsyncSession = Depends(get_db)
):
    """
    Публичный доступ к вишлисту по токену.
    Не требует авторизации.
    """
    result = await db.execute(
        select(Wishlist)
        .where(
            Wishlist.share_token == share_token,
            Wishlist.is_public == True
        )
        .options(
            selectinload(Wishlist.user),
            selectinload(Wishlist.items)
            .selectinload(WishlistItem.record),
            selectinload(Wishlist.items)
            .selectinload(WishlistItem.gift_booking)
        )
    )
    wishlist = result.scalar_one_or_none()
    
    if not wishlist:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Вишлист не найден или недоступен"
        )
    
    # Фильтрация по поиску
    items = wishlist.items
    if q:
        q_lower = q.lower()
        items = [
            item for item in items
            if q_lower in item.record.title.lower() or q_lower in item.record.artist.lower()
        ]
    
    # Формируем публичный ответ
    public_items = []
    for item in items:
        if not item.is_purchased:  # Не показываем купленные
            is_booked = item.gift_booking is not None
            gifter_name = None
            if is_booked and wishlist.show_gifter_names:
                gifter_name = item.gift_booking.gifter_name
            
            public_items.append(WishlistPublicItemResponse(
                id=item.id,
                record=RecordBrief(
                    id=item.record.id,
                    title=item.record.title,
                    artist=item.record.artist,
                    year=item.record.year,
                    cover_image_url=item.record.cover_image_url,
                    thumb_image_url=item.record.thumb_image_url,
                    estimated_price_median=item.record.estimated_price_median,
                    price_currency=item.record.price_currency
                ),
                priority=item.priority,
                notes=item.notes,
                is_booked=is_booked,
                gifter_name=gifter_name,
                added_at=item.added_at,
            ))

    # Сортируем по приоритету
    public_items.sort(key=lambda x: -x.priority)
    
    return WishlistPublicResponse(
        owner_name=wishlist.user.display_name or wishlist.user.username,
        owner_avatar=wishlist.user.avatar_url,
        custom_message=wishlist.custom_message,
        items=public_items,
        total_items=len(public_items)
    )


@router.post("/generate-link", response_model=dict)
async def generate_share_link(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Legacy-ручка: ротирует токен при каждом вызове (для back-compat).
    Новые клиенты должны использовать /share-info (read) и /regenerate-share-token (rotate).
    """
    result = await db.execute(
        select(Wishlist).where(Wishlist.user_id == current_user.id)
    )
    wishlist = result.scalar_one_or_none()

    if not wishlist:
        wishlist = Wishlist(user_id=current_user.id)
        db.add(wishlist)
    else:
        wishlist.regenerate_share_token()

    await db.commit()
    await db.refresh(wishlist)

    from app.config import get_settings
    settings = get_settings()

    return {
        "share_token": wishlist.share_token,
        "share_url": f"{settings.app_url}/wishlist/{wishlist.share_token}"
    }


def _build_share_url(share_token: str) -> str:
    from app.config import get_settings
    settings = get_settings()
    return f"{settings.app_url}/wishlist/{share_token}"


@router.get("/share-info", response_model=dict)
async def get_share_info(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Возвращает текущий share-token и url без ротации.
    Если вишлиста ещё нет — создаёт пустой (с уже сгенерированным токеном).
    """
    result = await db.execute(
        select(Wishlist).where(Wishlist.user_id == current_user.id)
    )
    wishlist = result.scalar_one_or_none()

    if not wishlist:
        wishlist = Wishlist(user_id=current_user.id)
        db.add(wishlist)
        await db.commit()
        await db.refresh(wishlist)

    return {
        "share_token": wishlist.share_token,
        "share_url": _build_share_url(wishlist.share_token),
    }


@router.post("/regenerate-share-token", response_model=dict)
async def regenerate_share_token(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Явная ротация share-токена. Старая ссылка немедленно перестаёт работать.
    """
    result = await db.execute(
        select(Wishlist).where(Wishlist.user_id == current_user.id)
    )
    wishlist = result.scalar_one_or_none()

    if not wishlist:
        wishlist = Wishlist(user_id=current_user.id)
        db.add(wishlist)
    else:
        wishlist.regenerate_share_token()

    await db.commit()
    await db.refresh(wishlist)

    return {
        "share_token": wishlist.share_token,
        "share_url": _build_share_url(wishlist.share_token),
    }


@router.put("/settings")
async def update_wishlist_settings(
    is_public: bool | None = None,
    show_gifter_names: bool | None = None,
    reveal_gifter_to_owner: bool | None = None,
    custom_message: str | None = Query(None, max_length=500),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Обновление настроек вишлиста"""
    result = await db.execute(
        select(Wishlist).where(Wishlist.user_id == current_user.id)
    )
    wishlist = result.scalar_one_or_none()

    if not wishlist:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Вишлист не найден"
        )

    if is_public is not None:
        wishlist.is_public = is_public
    if show_gifter_names is not None:
        wishlist.show_gifter_names = show_gifter_names
    if reveal_gifter_to_owner is not None:
        wishlist.reveal_gifter_to_owner = reveal_gifter_to_owner
    if custom_message is not None:
        wishlist.custom_message = custom_message

    await db.commit()

    return {"status": "ok"}


@router.get("/search", response_model=list[WishlistItemResponse])
async def search_wishlist(
    q: str = Query(..., min_length=1, description="Поисковый запрос"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Поиск по своему вишлисту"""
    result = await db.execute(
        select(Wishlist)
        .where(Wishlist.user_id == current_user.id)
        .options(
            selectinload(Wishlist.items)
            .selectinload(WishlistItem.record),
            selectinload(Wishlist.items)
            .selectinload(WishlistItem.gift_booking)
        )
    )
    wishlist = result.scalar_one_or_none()

    if not wishlist:
        return []

    q_lower = q.lower()
    matching_items = [
        item for item in wishlist.items
        if q_lower in item.record.title.lower() or q_lower in item.record.artist.lower()
    ]

    return [WishlistItemResponse(
        id=item.id,
        wishlist_id=item.wishlist_id,
        record_id=item.record_id,
        priority=item.priority,
        notes=item.notes,
        is_purchased=item.is_purchased,
        added_at=item.added_at,
        purchased_at=item.purchased_at,
        record=item.record,
        notify_mode=item.notify_mode,
        price_threshold_rub=item.price_threshold_rub,
        conditions=item.conditions,
        accept_alt=item.accept_alt,
        is_booked=item.gift_booking is not None,
        gift_booking=GiftBookingInfo(
            id=item.gift_booking.id,
            gifter_name=item.gift_booking.gifter_name,
            status=item.gift_booking.status,
            booked_at=item.gift_booking.booked_at
        ) if item.gift_booking else None
    ) for item in matching_items]


@router.post("/items/{item_id}/move-to-collection", response_model=CollectionItemResponse)
async def move_to_collection(
    item_id: UUID,
    data: MoveToCollectionRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Атомарный перенос из вишлиста в коллекцию.
    Если у пункта есть активная бронь — она завершается через единый
    путь complete_gift_booking (письмо дарителю, обнуление связи).
    """
    from app.models.collection import Collection, CollectionItem
    from app.services.gifts import complete_gift_booking, send_pending_gift_email

    # 1. Находим элемент вишлиста с gift_booking
    result = await db.execute(
        select(WishlistItem)
        .where(WishlistItem.id == item_id)
        .options(
            selectinload(WishlistItem.wishlist),
            selectinload(WishlistItem.record),
            selectinload(WishlistItem.gift_booking)
        )
    )
    item = result.scalar_one_or_none()

    if not item or item.wishlist.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Элемент не найден"
        )

    # 2. Проверяем коллекцию
    result = await db.execute(
        select(Collection).where(
            Collection.id == data.collection_id,
            Collection.user_id == current_user.id
        )
    )
    target_collection = result.scalar_one_or_none()
    if not target_collection:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Коллекция не найдена"
        )

    record = item.record  # сохраняем до удаления

    if item.gift_booking and item.gift_booking.status == GiftStatus.BOOKED:
        # Путь «получили подарок» — единый сервис: создаст CollectionItem,
        # завершит бронь, удалит пункт, подготовит письмо дарителю.
        gifter_user_id = item.gift_booking.booked_by_user_id
        booking_id_done = item.gift_booking.id
        collection_item = await complete_gift_booking(
            booking=item.gift_booking,
            owner=current_user,
            db=db,
            collection=target_collection,
        )
        await db.commit()
        await db.refresh(collection_item)
        await send_pending_gift_email(collection_item)

        # Ачивки серии «Дарящая рука» (после commit)
        from app.services.gifts import emit_gift_completion_events
        await emit_gift_completion_events(
            db,
            gifter_user_id=gifter_user_id,
            recipient_user_id=current_user.id,
            booking_id=booking_id_done,
        )
    else:
        # Путь «сам купил» — без брони. Просто перенос.
        # Цену в рубли считаем как в collections.add_record_to_collection —
        # иначе CollectionItemResponse.estimated_price_rub (required) роняет
        # сериализацию 500-кой (item при этом уже закоммичен → юзер видит
        # «ошибку», но запись добавлена).
        estimated_price_rub = None
        if record.estimated_price_min:
            from app.api.collections import _record_rub
            from app.services.exchange import get_usd_rub_rate
            from app.services.pricing import PricingParams
            from app.config import get_settings
            usd_rub = await get_usd_rub_rate()
            params = PricingParams.from_settings(get_settings())
            estimated_price_rub = _record_rub(record, usd_rub, params)

        collection_item = CollectionItem(
            collection_id=target_collection.id,
            record_id=item.record_id,
            estimated_price_rub=estimated_price_rub,
        )
        db.add(collection_item)
        await db.delete(item)
        await db.commit()
        await db.refresh(collection_item)

    # Ачивки коллекции (C-серия редкости, scale, genres, eras, geo). Прямое
    # добавление в коллекцию эмитит это событие; перенос вишлист→коллекция
    # раньше НЕ эмитил — поэтому коллекционка/лимитка из вишлиста не открывала
    # ачивку. payload.record даёт evaluator-у свежий объект без доп. запроса.
    from app.services.achievements import emit_event
    from app.services.achievements.events import COLLECTION_ITEM_ADDED
    await emit_event(
        db,
        current_user.id,
        COLLECTION_ITEM_ADDED,
        {
            "collection_item_id": collection_item.id,
            "record_id": record.id,
            "record": record,
        },
    )

    return CollectionItemResponse(
        id=collection_item.id,
        collection_id=collection_item.collection_id,
        record_id=collection_item.record_id,
        condition=collection_item.condition,
        sleeve_condition=collection_item.sleeve_condition,
        notes=collection_item.notes,
        shelf_position=collection_item.shelf_position,
        estimated_price_rub=(
            float(collection_item.estimated_price_rub)
            if collection_item.estimated_price_rub is not None else None
        ),
        added_at=collection_item.added_at,
        record=record
    )


# ==================== Wishlist Folders ====================


async def _get_or_create_wishlist(db: AsyncSession, user: User) -> Wishlist:
    """Получает (или создаёт) вишлист текущего юзера. Без коммита."""
    result = await db.execute(
        select(Wishlist).where(Wishlist.user_id == user.id)
    )
    wishlist = result.scalar_one_or_none()
    if not wishlist:
        wishlist = Wishlist(user_id=user.id)
        db.add(wishlist)
        await db.flush()
    return wishlist


def _folder_to_response(folder: WishlistFolder, items_count: int) -> WishlistFolderResponse:
    return WishlistFolderResponse(
        id=folder.id,
        wishlist_id=folder.wishlist_id,
        name=folder.name,
        sort_order=folder.sort_order,
        items_count=items_count,
        created_at=folder.created_at,
        updated_at=folder.updated_at,
    )


def _wishlist_item_to_response(item: WishlistItem) -> WishlistItemResponse:
    return WishlistItemResponse(
        id=item.id,
        wishlist_id=item.wishlist_id,
        record_id=item.record_id,
        priority=item.priority,
        notes=item.notes,
        is_purchased=item.is_purchased,
        added_at=item.added_at,
        purchased_at=item.purchased_at,
        record=item.record,
        notify_mode=item.notify_mode,
        price_threshold_rub=item.price_threshold_rub,
        conditions=item.conditions,
        accept_alt=item.accept_alt,
        is_booked=item.gift_booking is not None,
        gift_booking=GiftBookingInfo(
            id=item.gift_booking.id,
            gifter_name=item.gift_booking.gifter_name,
            status=item.gift_booking.status,
            booked_at=item.gift_booking.booked_at,
        ) if item.gift_booking else None,
    )


@router.get("/folders", response_model=list[WishlistFolderResponse])
async def list_wishlist_folders(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Список папок текущего юзера с подсчётом items_count."""
    wishlist = await _get_or_create_wishlist(db, current_user)
    await db.commit()  # на случай свежесозданного вишлиста

    folders_q = await db.execute(
        select(
            WishlistFolder,
            func.count(wishlist_folder_items.c.wishlist_item_id),
        )
        .outerjoin(
            wishlist_folder_items,
            wishlist_folder_items.c.wishlist_folder_id == WishlistFolder.id,
        )
        .where(WishlistFolder.wishlist_id == wishlist.id)
        .group_by(WishlistFolder.id)
        .order_by(WishlistFolder.sort_order, WishlistFolder.created_at)
    )

    return [
        _folder_to_response(folder, count)
        for folder, count in folders_q.all()
    ]


@router.post(
    "/folders",
    response_model=WishlistFolderResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_wishlist_folder(
    data: WishlistFolderCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Создать новую папку. sort_order = max+1."""
    wishlist = await _get_or_create_wishlist(db, current_user)

    max_sort_q = await db.execute(
        select(func.coalesce(func.max(WishlistFolder.sort_order), -1))
        .where(WishlistFolder.wishlist_id == wishlist.id)
    )
    next_sort = max_sort_q.scalar_one() + 1

    folder = WishlistFolder(
        wishlist_id=wishlist.id,
        name=data.name,
        sort_order=next_sort,
    )
    db.add(folder)
    await db.commit()
    await db.refresh(folder)

    return _folder_to_response(folder, 0)


@router.get("/folders/{folder_id}", response_model=WishlistFolderWithItems)
async def get_wishlist_folder(
    folder_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Папка с её содержимым (с record + gift_booking)."""
    wishlist = await _get_or_create_wishlist(db, current_user)

    result = await db.execute(
        select(WishlistFolder)
        .where(
            WishlistFolder.id == folder_id,
            WishlistFolder.wishlist_id == wishlist.id,
        )
        .options(
            selectinload(WishlistFolder.items).selectinload(WishlistItem.record),
            selectinload(WishlistFolder.items).selectinload(WishlistItem.gift_booking),
        )
    )
    folder = result.scalar_one_or_none()
    if not folder:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Папка не найдена",
        )

    items = [_wishlist_item_to_response(item) for item in folder.items]

    return WishlistFolderWithItems(
        id=folder.id,
        wishlist_id=folder.wishlist_id,
        name=folder.name,
        sort_order=folder.sort_order,
        items_count=len(items),
        created_at=folder.created_at,
        updated_at=folder.updated_at,
        items=items,
    )


@router.put("/folders/{folder_id}", response_model=WishlistFolderResponse)
async def update_wishlist_folder(
    folder_id: UUID,
    data: WishlistFolderUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Переименование папки."""
    wishlist = await _get_or_create_wishlist(db, current_user)

    result = await db.execute(
        select(WishlistFolder).where(
            WishlistFolder.id == folder_id,
            WishlistFolder.wishlist_id == wishlist.id,
        )
    )
    folder = result.scalar_one_or_none()
    if not folder:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Папка не найдена",
        )

    if data.name is not None:
        folder.name = data.name

    await db.commit()
    await db.refresh(folder)

    count_q = await db.execute(
        select(func.count(wishlist_folder_items.c.wishlist_item_id))
        .where(wishlist_folder_items.c.wishlist_folder_id == folder.id)
    )
    return _folder_to_response(folder, count_q.scalar_one())


@router.delete("/folders/{folder_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_wishlist_folder(
    folder_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Удалить папку. WishlistItem остаются в вишлисте — FK CASCADE снимает только теги."""
    wishlist = await _get_or_create_wishlist(db, current_user)

    result = await db.execute(
        select(WishlistFolder).where(
            WishlistFolder.id == folder_id,
            WishlistFolder.wishlist_id == wishlist.id,
        )
    )
    folder = result.scalar_one_or_none()
    if not folder:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Папка не найдена",
        )

    await db.delete(folder)
    await db.commit()


@router.post(
    "/folders/{folder_id}/items",
    response_model=WishlistFolderResponse,
)
async def add_items_to_wishlist_folder(
    folder_id: UUID,
    data: WishlistFolderItemsAdd,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Идемпотентное добавление item(s) в папку.
    Фильтруем только items текущего вишлиста; дубликаты M2M пропускаем.
    """
    wishlist = await _get_or_create_wishlist(db, current_user)

    folder_q = await db.execute(
        select(WishlistFolder)
        .where(
            WishlistFolder.id == folder_id,
            WishlistFolder.wishlist_id == wishlist.id,
        )
        .options(selectinload(WishlistFolder.items))
    )
    folder = folder_q.scalar_one_or_none()
    if not folder:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Папка не найдена",
        )

    valid_items_q = await db.execute(
        select(WishlistItem).where(
            WishlistItem.id.in_(data.wishlist_item_ids),
            WishlistItem.wishlist_id == wishlist.id,
        )
    )
    valid_items = valid_items_q.scalars().all()

    existing_ids = {item.id for item in folder.items}
    for item in valid_items:
        if item.id not in existing_ids:
            folder.items.append(item)

    await db.commit()
    await db.refresh(folder)

    count_q = await db.execute(
        select(func.count(wishlist_folder_items.c.wishlist_item_id))
        .where(wishlist_folder_items.c.wishlist_folder_id == folder.id)
    )
    return _folder_to_response(folder, count_q.scalar_one())


@router.delete(
    "/folders/{folder_id}/items/{wishlist_item_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def remove_item_from_wishlist_folder(
    folder_id: UUID,
    wishlist_item_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Снять тег: убрать item из папки. Сам WishlistItem не трогаем."""
    wishlist = await _get_or_create_wishlist(db, current_user)

    folder_q = await db.execute(
        select(WishlistFolder)
        .where(
            WishlistFolder.id == folder_id,
            WishlistFolder.wishlist_id == wishlist.id,
        )
        .options(selectinload(WishlistFolder.items))
    )
    folder = folder_q.scalar_one_or_none()
    if not folder:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Папка не найдена",
        )

    item_in_folder = next(
        (i for i in folder.items if i.id == wishlist_item_id),
        None,
    )
    if item_in_folder is not None:
        folder.items.remove(item_in_folder)
        await db.commit()
