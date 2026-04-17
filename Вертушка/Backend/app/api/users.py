"""
API для работы с пользователями и социальными функциями
"""
import logging
from datetime import datetime, timedelta
from uuid import UUID

logger = logging.getLogger(__name__)

from fastapi import APIRouter, Depends, HTTPException, status, Query, UploadFile, File
from sqlalchemy import select, func, literal
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.models.user import User
from app.models.follow import Follow
from app.models.collection import Collection, CollectionItem
from app.models.wishlist import Wishlist, WishlistItem
from app.api.auth import get_current_user, get_current_user_optional
from app.schemas.user import (
    UserResponse, UserUpdate, UserPublicResponse, UserWithStats, UsernameCheckResponse,
    NotificationSettingsResponse, NotificationSettingsUpdate, PushTokenUpdate,
)
from app.schemas.collection import CollectionWithItems, CollectionItemResponse
from app.schemas.wishlist import WishlistPublicResponse, WishlistPublicItemResponse
from app.schemas.record import RecordBrief

router = APIRouter()


@router.get("/check-username/{username}", response_model=UsernameCheckResponse)
async def check_username(
    username: str,
    db: AsyncSession = Depends(get_db)
):
    """Проверка доступности username (без авторизации)"""
    import re

    if len(username) < 3:
        return UsernameCheckResponse(available=False, reason="too_short")

    if not re.match(r'^[a-z0-9_]{3,50}$', username):
        return UsernameCheckResponse(available=False, reason="invalid")

    result = await db.execute(
        select(User).where(func.lower(User.username) == username.lower())
    )
    existing = result.scalar_one_or_none()

    if existing:
        return UsernameCheckResponse(available=False, reason="taken")

    return UsernameCheckResponse(available=True)


@router.get("/search", response_model=list[UserWithStats])
async def search_users(
    q: str = Query(..., min_length=2, description="Поисковый запрос"),
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=50),
    current_user: User | None = Depends(get_current_user_optional),
    db: AsyncSession = Depends(get_db)
):
    """Поиск пользователей по имени или username"""
    offset = (page - 1) * per_page

    # Экранируем спецсимволы ILIKE
    safe_q = q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")

    # Subqueries для подсчёта статистики одним запросом
    followers_sub = (
        select(func.count(Follow.id))
        .where(Follow.following_id == User.id)
        .correlate(User)
        .scalar_subquery()
        .label("followers_count")
    )
    following_sub = (
        select(func.count(Follow.id))
        .where(Follow.follower_id == User.id)
        .correlate(User)
        .scalar_subquery()
        .label("following_count")
    )
    collection_sub = (
        select(func.count(CollectionItem.id))
        .join(Collection, CollectionItem.collection_id == Collection.id)
        .where(Collection.user_id == User.id)
        .correlate(User)
        .scalar_subquery()
        .label("collection_count")
    )

    # Subquery для is_following
    if current_user:
        is_following_sub = (
            select(literal(True))
            .where(
                Follow.follower_id == current_user.id,
                Follow.following_id == User.id
            )
            .correlate(User)
            .exists()
            .label("is_following")
        )
    else:
        is_following_sub = literal(False).label("is_following")

    result = await db.execute(
        select(
            User,
            followers_sub,
            following_sub,
            collection_sub,
            is_following_sub,
        )
        .where(
            User.is_active == True,
            (User.username.ilike(f"%{safe_q}%")) | (User.display_name.ilike(f"%{safe_q}%"))
        )
        .offset(offset)
        .limit(per_page)
    )
    rows = result.all()

    return [
        UserWithStats(
            id=user.id,
            username=user.username,
            display_name=user.display_name,
            avatar_url=user.avatar_url,
            bio=user.bio,
            created_at=user.created_at,
            followers_count=followers_count or 0,
            following_count=following_count or 0,
            collection_count=collection_count or 0,
            is_following=bool(is_following),
        )
        for user, followers_count, following_count, collection_count, is_following in rows
    ]


@router.get("/by-username/{username}", response_model=UserWithStats)
async def get_user_by_username(
    username: str,
    current_user: User | None = Depends(get_current_user_optional),
    db: AsyncSession = Depends(get_db)
):
    """Получение профиля пользователя по username"""
    result = await db.execute(
        select(User).where(User.username == username, User.is_active == True)
    )
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Пользователь не найден"
        )

    followers_count = await db.scalar(
        select(func.count(Follow.id)).where(Follow.following_id == user.id)
    )
    following_count = await db.scalar(
        select(func.count(Follow.id)).where(Follow.follower_id == user.id)
    )
    collection_count = await db.scalar(
        select(func.count(CollectionItem.id))
        .join(Collection)
        .where(Collection.user_id == user.id)
    )

    is_following = False
    if current_user:
        follow_check = await db.execute(
            select(Follow).where(
                Follow.follower_id == current_user.id,
                Follow.following_id == user.id
            )
        )
        is_following = follow_check.scalar_one_or_none() is not None

    return UserWithStats(
        id=user.id,
        username=user.username,
        display_name=user.display_name,
        avatar_url=user.avatar_url,
        bio=user.bio,
        created_at=user.created_at,
        followers_count=followers_count or 0,
        following_count=following_count or 0,
        collection_count=collection_count or 0,
        is_following=is_following
    )


@router.get("/by-username/{username}/wishlist/", response_model=WishlistPublicResponse)
async def get_user_wishlist_by_username(
    username: str,
    current_user: User | None = Depends(get_current_user_optional),
    db: AsyncSession = Depends(get_db)
):
    """
    Вишлист пользователя по username.
    Доступ: профиль открытый ИЛИ текущий пользователь — фолловер.
    """
    from app.models.gift_booking import GiftBooking

    result = await db.execute(
        select(User).where(User.username == username, User.is_active == True)
    )
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Пользователь не найден"
        )

    # Проверяем доступ: подписан ли текущий пользователь
    is_follower = False
    if current_user and current_user.id != user.id:
        follow_check = await db.execute(
            select(Follow).where(
                Follow.follower_id == current_user.id,
                Follow.following_id == user.id
            )
        )
        is_follower = follow_check.scalar_one_or_none() is not None

    is_owner = current_user and current_user.id == user.id

    # Получаем вишлист
    result = await db.execute(
        select(Wishlist)
        .where(Wishlist.user_id == user.id)
        .options(
            selectinload(Wishlist.items)
            .selectinload(WishlistItem.record),
            selectinload(Wishlist.items)
            .selectinload(WishlistItem.gift_booking)
        )
    )
    wishlist = result.scalar_one_or_none()

    if not wishlist:
        return WishlistPublicResponse(
            owner_name=user.display_name or user.username,
            owner_avatar=user.avatar_url,
            custom_message=None,
            items=[],
            total_items=0
        )

    # Доступ: вишлист публичный ИЛИ фолловер ИЛИ владелец
    if not wishlist.is_public and not is_follower and not is_owner:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Вишлист недоступен. Подпишитесь на пользователя."
        )

    public_items = []
    for item in wishlist.items:
        if not item.is_purchased:
            is_booked = item.gift_booking is not None
            gifter_name = None
            if is_booked and wishlist.show_gifter_names:
                gifter_name = item.gift_booking.gifter_name

            public_items.append(WishlistPublicItemResponse(
                id=item.id,
                record=RecordBrief.model_validate(item.record),
                priority=item.priority,
                notes=item.notes,
                is_booked=is_booked,
                gifter_name=gifter_name
            ))

    public_items.sort(key=lambda x: -x.priority)

    return WishlistPublicResponse(
        owner_name=user.display_name or user.username,
        owner_avatar=user.avatar_url,
        custom_message=wishlist.custom_message,
        items=public_items,
        total_items=len(public_items)
    )


@router.get("/me", response_model=UserResponse)
async def get_current_user_profile(
    current_user: User = Depends(get_current_user)
):
    """Получение профиля текущего пользователя"""
    return current_user


@router.put("/me", response_model=UserResponse)
async def update_current_user(
    data: UserUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Обновление профиля текущего пользователя"""
    if data.username is not None and data.username != current_user.username:
        # Проверяем уникальность
        result = await db.execute(
            select(User).where(
                func.lower(User.username) == data.username.lower(),
                User.id != current_user.id
            )
        )
        if result.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Username уже занят"
            )
        current_user.username = data.username

    if data.display_name is not None:
        current_user.display_name = data.display_name
    if data.bio is not None:
        current_user.bio = data.bio
    if data.avatar_url is not None:
        current_user.avatar_url = data.avatar_url

    await db.commit()
    await db.refresh(current_user)

    return current_user


@router.delete("/me", status_code=status.HTTP_200_OK)
async def delete_my_account(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Soft delete аккаунта текущего пользователя (30 дней на восстановление)"""
    current_user.is_active = False
    current_user.deleted_at = datetime.utcnow()
    current_user.scheduled_purge_at = datetime.utcnow() + timedelta(days=30)
    await db.commit()

    logger.info("account_deleted", extra={"user_id": str(current_user.id), "email": current_user.email})

    return {
        "message": "Аккаунт помечен на удаление. В течение 30 дней вы можете восстановить его, войдя снова.",
        "scheduled_purge_at": current_user.scheduled_purge_at.isoformat()
    }


@router.put("/me/push-token")
async def update_push_token(
    data: PushTokenUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Сохранение Expo push token"""
    current_user.push_token = data.push_token
    await db.commit()
    return {"status": "ok"}


@router.get("/me/notification-settings", response_model=NotificationSettingsResponse)
async def get_notification_settings(
    current_user: User = Depends(get_current_user),
):
    """Текущие настройки уведомлений"""
    return NotificationSettingsResponse(
        notify_new_follower=current_user.notify_new_follower,
        notify_gift_booked=current_user.notify_gift_booked,
        notify_app_updates=current_user.notify_app_updates,
    )


@router.put("/me/notification-settings", response_model=NotificationSettingsResponse)
async def update_notification_settings(
    data: NotificationSettingsUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Обновление настроек уведомлений"""
    if data.notify_new_follower is not None:
        current_user.notify_new_follower = data.notify_new_follower
    if data.notify_gift_booked is not None:
        current_user.notify_gift_booked = data.notify_gift_booked
    if data.notify_app_updates is not None:
        current_user.notify_app_updates = data.notify_app_updates

    await db.commit()
    await db.refresh(current_user)

    return NotificationSettingsResponse(
        notify_new_follower=current_user.notify_new_follower,
        notify_gift_booked=current_user.notify_gift_booked,
        notify_app_updates=current_user.notify_app_updates,
    )


@router.post("/me/avatar", response_model=UserResponse)
async def upload_avatar(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Загрузка аватарки пользователя"""
    import os
    from pathlib import Path
    from PIL import Image as PILImage
    import io

    if file.content_type not in ("image/jpeg", "image/png"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Только JPEG и PNG"
        )

    contents = await file.read()
    if len(contents) > 5 * 1024 * 1024:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Максимальный размер файла — 5 МБ"
        )

    # Проверка magic bytes (защита от переименованных исполняемых файлов)
    MAGIC_BYTES = {
        "image/jpeg": b"\xff\xd8\xff",
        "image/png": b"\x89PNG",
    }
    expected_magic = MAGIC_BYTES.get(file.content_type, b"")
    if not contents[:len(expected_magic)] == expected_magic:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Файл не является допустимым изображением"
        )

    img = PILImage.open(io.BytesIO(contents))
    img = img.convert("RGB")

    # Crop to square (center)
    w, h = img.size
    side = min(w, h)
    left = (w - side) // 2
    top = (h - side) // 2
    img = img.crop((left, top, left + side, top + side))
    img = img.resize((400, 400), PILImage.LANCZOS)

    avatars_dir = Path("uploads/avatars")
    avatars_dir.mkdir(parents=True, exist_ok=True)

    filename = f"{current_user.id}.jpg"
    filepath = avatars_dir / filename
    img.save(filepath, "JPEG", quality=85)

    current_user.avatar_url = f"/uploads/avatars/{filename}"
    await db.commit()
    await db.refresh(current_user)

    return current_user


@router.delete("/me/avatar", response_model=UserResponse)
async def delete_avatar(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Удаление аватарки пользователя"""
    from pathlib import Path

    filepath = Path(f"uploads/avatars/{current_user.id}.jpg")
    if filepath.exists():
        filepath.unlink()

    current_user.avatar_url = None
    await db.commit()
    await db.refresh(current_user)

    return current_user


@router.get("/me/following", response_model=list[UserPublicResponse])
async def get_following(
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=50),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Список подписок текущего пользователя"""
    offset = (page - 1) * per_page

    result = await db.execute(
        select(User)
        .join(Follow, Follow.following_id == User.id)
        .where(Follow.follower_id == current_user.id)
        .offset(offset)
        .limit(per_page)
    )
    users = result.scalars().all()

    return [UserPublicResponse(
        id=u.id,
        username=u.username,
        display_name=u.display_name,
        avatar_url=u.avatar_url,
        bio=u.bio,
        created_at=u.created_at
    ) for u in users]


@router.get("/me/followers", response_model=list[UserPublicResponse])
async def get_followers(
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=50),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Список подписчиков текущего пользователя"""
    offset = (page - 1) * per_page

    result = await db.execute(
        select(User)
        .join(Follow, Follow.follower_id == User.id)
        .where(Follow.following_id == current_user.id)
        .offset(offset)
        .limit(per_page)
    )
    users = result.scalars().all()

    return [UserPublicResponse(
        id=u.id,
        username=u.username,
        display_name=u.display_name,
        avatar_url=u.avatar_url,
        bio=u.bio,
        created_at=u.created_at
    ) for u in users]


@router.get("/feed", response_model=list[dict])
async def get_feed(
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=50),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Лента активности подписок.
    Показывает недавно добавленные пластинки в коллекции пользователей, на которых подписан.
    """
    offset = (page - 1) * per_page

    following_result = await db.execute(
        select(Follow.following_id).where(Follow.follower_id == current_user.id)
    )
    following_ids = [f[0] for f in following_result.all()]

    if not following_ids:
        return []

    result = await db.execute(
        select(CollectionItem)
        .join(Collection)
        .where(Collection.user_id.in_(following_ids))
        .options(
            selectinload(CollectionItem.record),
            selectinload(CollectionItem.collection).selectinload(Collection.user)
        )
        .order_by(CollectionItem.added_at.desc())
        .offset(offset)
        .limit(per_page)
    )
    items = result.scalars().all()

    return [{
        "type": "collection_add",
        "user": {
            "id": str(item.collection.user.id),
            "username": item.collection.user.username,
            "display_name": item.collection.user.display_name,
            "avatar_url": item.collection.user.avatar_url
        },
        "collection": {
            "id": str(item.collection.id),
            "name": item.collection.name
        },
        "record": {
            "id": str(item.record.id),
            "title": item.record.title,
            "artist": item.record.artist,
            "year": item.record.year,
            "cover_image_url": item.record.cover_image_url
        },
        "added_at": item.added_at.isoformat()
    } for item in items]


@router.get("/{user_id}", response_model=UserWithStats)
async def get_user_profile(
    user_id: UUID,
    current_user: User | None = Depends(get_current_user_optional),
    db: AsyncSession = Depends(get_db)
):
    """Получение публичного профиля пользователя"""
    result = await db.execute(
        select(User).where(User.id == user_id, User.is_active == True)
    )
    user = result.scalar_one_or_none()
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Пользователь не найден"
        )
    
    # Подсчёт статистики
    followers_count = await db.scalar(
        select(func.count(Follow.id)).where(Follow.following_id == user.id)
    )
    following_count = await db.scalar(
        select(func.count(Follow.id)).where(Follow.follower_id == user.id)
    )
    collection_count = await db.scalar(
        select(func.count(CollectionItem.id))
        .join(Collection)
        .where(Collection.user_id == user.id)
    )
    
    is_following = False
    if current_user:
        follow_check = await db.execute(
            select(Follow).where(
                Follow.follower_id == current_user.id,
                Follow.following_id == user.id
            )
        )
        is_following = follow_check.scalar_one_or_none() is not None
    
    return UserWithStats(
        id=user.id,
        username=user.username,
        display_name=user.display_name,
        avatar_url=user.avatar_url,
        bio=user.bio,
        created_at=user.created_at,
        followers_count=followers_count or 0,
        following_count=following_count or 0,
        collection_count=collection_count or 0,
        is_following=is_following
    )


@router.post("/{user_id}/follow", status_code=status.HTTP_201_CREATED)
async def follow_user(
    user_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Подписка на пользователя"""
    if user_id == current_user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Нельзя подписаться на себя"
        )
    
    # Проверяем существование пользователя
    result = await db.execute(
        select(User).where(User.id == user_id, User.is_active == True)
    )
    if not result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Пользователь не найден"
        )
    
    # Проверяем, не подписаны ли уже
    result = await db.execute(
        select(Follow).where(
            Follow.follower_id == current_user.id,
            Follow.following_id == user_id
        )
    )
    if result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Вы уже подписаны на этого пользователя"
        )
    
    follow = Follow(
        follower_id=current_user.id,
        following_id=user_id
    )
    db.add(follow)
    await db.commit()
    
    return {"status": "followed"}


@router.delete("/{user_id}/follow", status_code=status.HTTP_204_NO_CONTENT)
async def unfollow_user(
    user_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Отписка от пользователя"""
    result = await db.execute(
        select(Follow).where(
            Follow.follower_id == current_user.id,
            Follow.following_id == user_id
        )
    )
    follow = result.scalar_one_or_none()
    
    if not follow:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Вы не подписаны на этого пользователя"
        )
    
    await db.delete(follow)
    await db.commit()


@router.get("/{user_id}/collection", response_model=list[CollectionWithItems])
async def get_user_collection(
    user_id: UUID,
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=100),
    current_user: User | None = Depends(get_current_user_optional),
    db: AsyncSession = Depends(get_db)
):
    """Получение коллекции пользователя (для просмотра подписчиками)"""
    result = await db.execute(
        select(User).where(User.id == user_id, User.is_active == True)
    )
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Пользователь не найден"
        )

    result = await db.execute(
        select(Collection)
        .where(Collection.user_id == user_id)
        .order_by(Collection.sort_order)
    )
    collections = result.scalars().all()

    response = []
    for collection in collections:
        offset = (page - 1) * per_page
        items_result = await db.execute(
            select(CollectionItem)
            .where(CollectionItem.collection_id == collection.id)
            .options(selectinload(CollectionItem.record))
            .order_by(CollectionItem.added_at.desc())
            .offset(offset)
            .limit(per_page)
        )
        items = items_result.scalars().all()

        count_result = await db.execute(
            select(func.count(CollectionItem.id))
            .where(CollectionItem.collection_id == collection.id)
        )
        items_count = count_result.scalar() or 0

        response.append(CollectionWithItems(
            id=collection.id,
            user_id=collection.user_id,
            name=collection.name,
            description=collection.description,
            sort_order=collection.sort_order,
            created_at=collection.created_at,
            updated_at=collection.updated_at,
            items_count=items_count,
            items=[CollectionItemResponse(
                id=item.id,
                collection_id=item.collection_id,
                record_id=item.record_id,
                condition=item.condition,
                sleeve_condition=item.sleeve_condition,
                notes=item.notes,
                shelf_position=item.shelf_position,
                added_at=item.added_at,
                record=item.record
            ) for item in items]
        ))

    return response

