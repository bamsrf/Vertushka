"""
API для работы с вишлистами
"""
from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.models.user import User
from app.models.record import Record
from app.models.wishlist import Wishlist, WishlistItem, WishlistFolder, wishlist_folder_items
from app.models.gift_booking import GiftBooking, GiftStatus
from app.api.auth import get_current_user, get_current_user_optional
from app.services.cover_storage import ensure_cover_cached
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
            is_booked=item.gift_booking is not None,
            gift_booking=GiftBookingInfo(
                id=item.gift_booking.id,
                gifter_name=item.gift_booking.gifter_name,
                status=item.gift_booking.status,
                booked_at=item.gift_booking.booked_at
            ) if item.gift_booking else None
        ) for item in wishlist.items]
    )


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
        is_booked=item.gift_booking is not None,
        gift_booking=GiftBookingInfo(
            id=item.gift_booking.id,
            gifter_name=item.gift_booking.gifter_name,
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
        collection_item = await complete_gift_booking(
            booking=item.gift_booking,
            owner=current_user,
            db=db,
            collection=target_collection,
        )
        await db.commit()
        await db.refresh(collection_item)
        await send_pending_gift_email(collection_item)
    else:
        # Путь «сам купил» — без брони. Просто перенос.
        collection_item = CollectionItem(
            collection_id=target_collection.id,
            record_id=item.record_id,
        )
        db.add(collection_item)
        await db.delete(item)
        await db.commit()
        await db.refresh(collection_item)

    return CollectionItemResponse(
        id=collection_item.id,
        collection_id=collection_item.collection_id,
        record_id=collection_item.record_id,
        condition=collection_item.condition,
        sleeve_condition=collection_item.sleeve_condition,
        notes=collection_item.notes,
        shelf_position=collection_item.shelf_position,
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
