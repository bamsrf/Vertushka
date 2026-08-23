"""
API для работы с пользователями и социальными функциями
"""
import logging
from datetime import datetime, timedelta
from uuid import UUID

logger = logging.getLogger(__name__)

from fastapi import APIRouter, Depends, HTTPException, status, Query, UploadFile, File
from sqlalchemy import select, func, literal, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.services import apple_auth
from app.services.blocking import is_user_blocked
from app.services.secret_crypto import decrypt_secret
from app.services.push import absolute_media_url
from app.models.user import User
from app.models.follow import Follow
from app.models.follow_request import FollowRequest, FollowRequestStatus
from app.models.profile_share import ProfileShare
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
from app.schemas.follow_request import (
    FollowRequestResponse,
    FollowRequestUser,
    FollowActionResponse,
)

router = APIRouter()


async def _is_profile_private(db: AsyncSession, user_id: UUID) -> bool:
    """Проверка приватности профиля по записи в profile_shares."""
    flag = await db.scalar(
        select(ProfileShare.is_private_profile).where(ProfileShare.user_id == user_id)
    )
    return bool(flag)


async def _collection_size(db: AsyncSession, user_id: UUID) -> int:
    """Сколько пластинок в коллекции — для body социальных пушей.

    DISTINCT record_id: папки — это копии записей основной коллекции,
    count(id) по всем коллекциям задваивал счёт."""
    total = await db.scalar(
        select(func.count(func.distinct(CollectionItem.record_id)))
        .join(Collection, CollectionItem.collection_id == Collection.id)
        .where(Collection.user_id == user_id)
    )
    return int(total or 0)


async def _pending_request_id(
    db: AsyncSession,
    requester_id: UUID,
    target_id: UUID,
) -> UUID | None:
    """Возвращает id pending-запроса от requester к target, либо None."""
    result = await db.execute(
        select(FollowRequest.id).where(
            FollowRequest.requester_id == requester_id,
            FollowRequest.target_id == target_id,
            FollowRequest.status == FollowRequestStatus.PENDING,
        )
    )
    return result.scalar_one_or_none()


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
        # DISTINCT record_id: папки дублируют записи, count(id) врал в поиске.
        select(func.count(func.distinct(CollectionItem.record_id)))
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
        has_pending_request_sub = (
            select(literal(True))
            .where(
                FollowRequest.requester_id == current_user.id,
                FollowRequest.target_id == User.id,
                FollowRequest.status == FollowRequestStatus.PENDING,
            )
            .correlate(User)
            .exists()
            .label("has_pending_request")
        )
    else:
        is_following_sub = literal(False).label("is_following")
        has_pending_request_sub = literal(False).label("has_pending_request")

    is_private_sub = (
        select(ProfileShare.is_private_profile)
        .where(ProfileShare.user_id == User.id)
        .correlate(User)
        .scalar_subquery()
        .label("is_private_profile")
    )

    result = await db.execute(
        select(
            User,
            followers_sub,
            following_sub,
            collection_sub,
            is_following_sub,
            has_pending_request_sub,
            is_private_sub,
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
            follow_request_status="pending" if bool(has_pending) else "none",
            is_private_profile=bool(is_private),
        )
        for user, followers_count, following_count, collection_count, is_following, has_pending, is_private in rows
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
        # DISTINCT record_id: папки дублируют записи основной коллекции.
        select(func.count(func.distinct(CollectionItem.record_id)))
        .join(Collection)
        .where(Collection.user_id == user.id)
    )

    is_following = False
    follow_request_status_value = "none"
    if current_user:
        follow_check = await db.execute(
            select(Follow).where(
                Follow.follower_id == current_user.id,
                Follow.following_id == user.id
            )
        )
        is_following = follow_check.scalar_one_or_none() is not None
        if not is_following:
            pending_id = await _pending_request_id(db, current_user.id, user.id)
            if pending_id:
                follow_request_status_value = "pending"

    is_private = await _is_profile_private(db, user.id)

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
        is_following=is_following,
        follow_request_status=follow_request_status_value,
        is_private_profile=is_private,
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
            # show_gifter_names — витрина для гостей («кто уже что дарит»).
            # Владельцу имя не показываем никогда, если он сам не включил
            # reveal_gifter_to_owner: иначе он читал бы его из собственного
            # публичного профиля в обход анонимности брони.
            reveal_to_viewer = (
                wishlist.reveal_gifter_to_owner if is_owner else wishlist.show_gifter_names
            )
            if is_booked and reveal_to_viewer:
                gifter_name = item.gift_booking.gifter_name

            public_items.append(WishlistPublicItemResponse(
                id=item.id,
                record=RecordBrief.model_validate(item.record),
                priority=item.priority,
                notes=item.notes,
                is_booked=is_booked,
                gifter_name=gifter_name,
                added_at=item.added_at,
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
    avatar_was_set = False
    if data.avatar_url is not None:
        current_user.avatar_url = data.avatar_url
        avatar_was_set = bool(data.avatar_url)

    await db.commit()
    await db.refresh(current_user)

    if avatar_was_set:
        from app.services.achievements import emit_event
        from app.services.achievements.events import AVATAR_SET
        await emit_event(db, current_user.id, AVATAR_SET, {})

    return current_user


async def _revoke_apple_access(user: User) -> None:
    """Отзывает Apple refresh_token и вычищает его из БД.

    Мягко: неудача Apple не должна мешать пользователю удалить аккаунт —
    TN3194 прямо разрешает завершить удаление и без успешного отзыва.

    При неудаче токен оставляем: purge-джоба через 30 дней попробует ещё раз,
    а потом снесёт строку целиком. Обнулить его здесь означало бы навсегда
    потерять единственную возможность отозвать доступ.
    """
    if not user.apple_refresh_token:
        return

    token = decrypt_secret(user.apple_refresh_token)
    if token is None:
        # Ключ шифрования сменился — расшифровать нечем, отзывать нечего.
        user.apple_refresh_token = None
        return

    revoked = await apple_auth.revoke_refresh_token(token)
    logger.info(
        "apple_token_revoke",
        extra={"user_id": str(user.id), "revoked": revoked},
    )
    if revoked:
        user.apple_refresh_token = None


@router.delete("/me", status_code=status.HTTP_200_OK)
async def delete_my_account(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Soft delete аккаунта текущего пользователя (30 дней на восстановление)"""
    # Sign in with Apple: Apple требует отозвать выданный токен в момент, когда
    # пользователь удаляет аккаунт (Guideline 5.1.1(v)). Отзываем здесь, а не в
    # purge-джобе через 30 дней: пользователь нажал «удалить» сейчас, и связь с
    # Apple ID должна рваться сейчас. Если он вернётся в окно восстановления,
    # повторный вход через Apple выдаст новый токен и перезапишет поле.
    await _revoke_apple_access(current_user)

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
    """Сохранение Expo push token.

    Токен уникален на девайс: снимаем его со всех ДРУГИХ юзеров, иначе после
    смены аккаунта на этом устройстве старый юзер продолжает получать пуши
    (push_token у него остаётся тем же). Девайс принадлежит последнему вошедшему.
    """
    if data.push_token:
        await db.execute(
            update(User)
            .where(User.push_token == data.push_token, User.id != current_user.id)
            .values(push_token=None)
        )
    current_user.push_token = data.push_token
    await db.commit()
    return {"status": "ok"}


@router.delete("/me/push-token")
async def clear_push_token(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Сброс push-токена (вызывается при логауте до стирания auth-токена).

    Без этого юзер продолжает получать пуши на устройство после выхода.
    """
    current_user.push_token = None
    await db.commit()
    return {"status": "ok"}


def _serialize_settings(user: User) -> NotificationSettingsResponse:
    return NotificationSettingsResponse(
        notify_new_follower=user.notify_new_follower,
        notify_gift_booked=user.notify_gift_booked,
        notify_gift_confirmed=user.notify_gift_confirmed,
        notify_app_updates=user.notify_app_updates,
        notify_follow_request=user.notify_follow_request,
        notify_wishlist_in_stock=user.notify_wishlist_in_stock,
        notify_achievement=user.notify_achievement,
        notify_milestone=user.notify_milestone,
        quiet_hours_enabled=user.quiet_hours_enabled,
        quiet_hours_start=user.quiet_hours_start.strftime("%H:%M") if user.quiet_hours_start else None,
        quiet_hours_end=user.quiet_hours_end.strftime("%H:%M") if user.quiet_hours_end else None,
    )


def _parse_hhmm(value: str) -> "time":  # type: ignore[name-defined]
    from datetime import time as _time
    parts = value.split(":")
    if len(parts) != 2:
        raise HTTPException(status_code=400, detail="Bad time format, expected HH:MM")
    try:
        h = int(parts[0])
        m = int(parts[1])
    except ValueError:
        raise HTTPException(status_code=400, detail="Bad time format, expected HH:MM")
    if not (0 <= h < 24 and 0 <= m < 60):
        raise HTTPException(status_code=400, detail="Bad time range")
    return _time(hour=h, minute=m)


@router.get("/me/notification-settings", response_model=NotificationSettingsResponse)
async def get_notification_settings(
    current_user: User = Depends(get_current_user),
):
    """Текущие настройки уведомлений"""
    return _serialize_settings(current_user)


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
    if data.notify_gift_confirmed is not None:
        current_user.notify_gift_confirmed = data.notify_gift_confirmed
    if data.notify_app_updates is not None:
        current_user.notify_app_updates = data.notify_app_updates
    if data.notify_follow_request is not None:
        current_user.notify_follow_request = data.notify_follow_request
    if data.notify_wishlist_in_stock is not None:
        current_user.notify_wishlist_in_stock = data.notify_wishlist_in_stock
    if data.notify_achievement is not None:
        current_user.notify_achievement = data.notify_achievement
    if data.notify_milestone is not None:
        current_user.notify_milestone = data.notify_milestone

    if data.quiet_hours_enabled is not None:
        current_user.quiet_hours_enabled = data.quiet_hours_enabled
    if data.quiet_hours_start is not None:
        current_user.quiet_hours_start = _parse_hhmm(data.quiet_hours_start)
    if data.quiet_hours_end is not None:
        current_user.quiet_hours_end = _parse_hhmm(data.quiet_hours_end)

    await db.commit()
    await db.refresh(current_user)

    return _serialize_settings(current_user)


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

    from app.services.achievements import emit_event
    from app.services.achievements.events import AVATAR_SET
    await emit_event(db, current_user.id, AVATAR_SET, {})

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
        # DISTINCT record_id: папки дублируют записи основной коллекции.
        select(func.count(func.distinct(CollectionItem.record_id)))
        .join(Collection)
        .where(Collection.user_id == user.id)
    )
    
    is_following = False
    follow_request_status_value = "none"
    if current_user:
        follow_check = await db.execute(
            select(Follow).where(
                Follow.follower_id == current_user.id,
                Follow.following_id == user.id
            )
        )
        is_following = follow_check.scalar_one_or_none() is not None
        if not is_following:
            pending_id = await _pending_request_id(db, current_user.id, user.id)
            if pending_id:
                follow_request_status_value = "pending"

    is_private = await _is_profile_private(db, user.id)

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
        is_following=is_following,
        follow_request_status=follow_request_status_value,
        is_private_profile=is_private,
    )


@router.post(
    "/{user_id}/follow",
    status_code=status.HTTP_201_CREATED,
    response_model=FollowActionResponse,
)
async def follow_user(
    user_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Подписка на пользователя.

    - Публичный профиль (is_private_profile=false): моментальный Follow → status='followed'.
    - Приватный профиль: создаётся FollowRequest pending → status='requested'.
      После approve хостом → автоматически создаётся Follow.
    """
    if user_id == current_user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Нельзя подписаться на себя"
        )

    # Блокировка режет подписку в обе стороны. Без этой проверки «заблокировать»
    # означало только «не получать личные сообщения»: заблокированный спокойно
    # подписывался и продолжал присылать пуши. См. SECURITY_AUDIT_PRERELEASE §S6.
    # 404, а не 403: существование блокировки — не та вещь, которую стоит
    # подтверждать тому, кого заблокировали.
    if await is_user_blocked(db, current_user.id, user_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Пользователь не найден",
        )

    # Проверяем существование пользователя
    result = await db.execute(
        select(User).where(User.id == user_id, User.is_active == True)
    )
    target = result.scalar_one_or_none()
    if not target:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Пользователь не найден"
        )

    # Уже подписан?
    existing_follow = await db.execute(
        select(Follow).where(
            Follow.follower_id == current_user.id,
            Follow.following_id == user_id,
        )
    )
    if existing_follow.scalar_one_or_none():
        return FollowActionResponse(status="already_following")

    is_private = await _is_profile_private(db, user_id)

    if is_private:
        # Приватный профиль → создаём/возвращаем заявку
        existing_pending = await _pending_request_id(db, current_user.id, user_id)
        if existing_pending:
            return FollowActionResponse(
                status="already_requested",
                follow_request_id=existing_pending,
            )

        # Чистим старую rejected/approved-запись (если есть) — её UniqueConstraint блокирует повторный insert
        await db.execute(
            FollowRequest.__table__.delete().where(
                FollowRequest.requester_id == current_user.id,
                FollowRequest.target_id == user_id,
            )
        )

        request = FollowRequest(
            requester_id=current_user.id,
            target_id=user_id,
            status=FollowRequestStatus.PENDING,
        )
        db.add(request)
        await db.flush()

        from app.services.notification_service import create_notification
        from app.services import push_copy
        actor_name = current_user.display_name or current_user.username
        push_title, push_body = push_copy.follow_request(
            name=actor_name,
            username=current_user.username,
            collection_count=await _collection_size(db, current_user.id),
        )
        await create_notification(
            db,
            user_id=user_id,
            actor_id=current_user.id,
            type="follow_request",
            entity_type="follow_request",
            entity_id=str(request.id),
            data={
                "actor_username": current_user.username,
                "actor_display_name": current_user.display_name,
            },
            push_title=push_title,
            push_body=push_body,
            push_image=absolute_media_url(current_user.avatar_url),
        )

        await db.commit()
        await db.refresh(request)
        return FollowActionResponse(
            status="requested",
            follow_request_id=request.id,
        )

    # Публичный профиль → моментальный Follow
    follow = Follow(
        follower_id=current_user.id,
        following_id=user_id,
    )
    db.add(follow)
    await db.flush()

    from app.services.notification_service import create_notification
    from app.services import push_copy
    actor_name = current_user.display_name or current_user.username
    push_title, push_body = push_copy.new_follower(
        name=actor_name,
        username=current_user.username,
        collection_count=await _collection_size(db, current_user.id),
    )
    await create_notification(
        db,
        user_id=user_id,
        actor_id=current_user.id,
        type="new_follower",
        entity_type="user",
        entity_id=str(current_user.id),
        data={
            "actor_username": current_user.username,
            "actor_display_name": current_user.display_name,
        },
        push_title=push_title,
        push_body=push_body,
        push_image=absolute_media_url(current_user.avatar_url),
    )

    await db.commit()

    # Эмиссия событий ачивок (K-серия)
    from app.services.achievements import emit_event
    from app.services.achievements.events import FOLLOW_CREATED, FOLLOW_RECEIVED
    await emit_event(
        db,
        current_user.id,
        FOLLOW_CREATED,
        {"following_id": user_id},
    )
    await emit_event(
        db,
        user_id,
        FOLLOW_RECEIVED,
        {"follower_id": current_user.id},
    )

    return FollowActionResponse(status="followed")


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


# ==================== Follow requests ====================

def _request_to_response(req: FollowRequest, requester: User, target: User) -> FollowRequestResponse:
    return FollowRequestResponse(
        id=req.id,
        requester=FollowRequestUser(
            id=requester.id,
            username=requester.username,
            display_name=requester.display_name,
            avatar_url=requester.avatar_url,
        ),
        target=FollowRequestUser(
            id=target.id,
            username=target.username,
            display_name=target.display_name,
            avatar_url=target.avatar_url,
        ),
        status=req.status.value,
        created_at=req.created_at,
        resolved_at=req.resolved_at,
    )


@router.get("/me/follow-requests/incoming", response_model=list[FollowRequestResponse])
async def list_incoming_follow_requests(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Список входящих pending-заявок на подписку (мне)."""
    result = await db.execute(
        select(FollowRequest, User)
        .join(User, User.id == FollowRequest.requester_id)
        .where(
            FollowRequest.target_id == current_user.id,
            FollowRequest.status == FollowRequestStatus.PENDING,
        )
        .order_by(FollowRequest.created_at.desc())
    )
    rows = result.all()
    return [_request_to_response(req, requester, current_user) for req, requester in rows]


@router.get("/me/follow-requests/outgoing", response_model=list[FollowRequestResponse])
async def list_outgoing_follow_requests(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Список исходящих pending-заявок (которые я отправил)."""
    result = await db.execute(
        select(FollowRequest, User)
        .join(User, User.id == FollowRequest.target_id)
        .where(
            FollowRequest.requester_id == current_user.id,
            FollowRequest.status == FollowRequestStatus.PENDING,
        )
        .order_by(FollowRequest.created_at.desc())
    )
    rows = result.all()
    return [_request_to_response(req, current_user, target) for req, target in rows]


@router.get("/me/follow-requests/incoming/count")
async def count_incoming_follow_requests(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Счётчик pending-заявок для бейджа."""
    count = await db.scalar(
        select(func.count(FollowRequest.id)).where(
            FollowRequest.target_id == current_user.id,
            FollowRequest.status == FollowRequestStatus.PENDING,
        )
    )
    return {"count": int(count or 0)}


@router.post(
    "/me/follow-requests/{request_id}/approve",
    response_model=FollowActionResponse,
)
async def approve_follow_request(
    request_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Одобрить заявку — создаётся Follow + status=approved."""
    result = await db.execute(
        select(FollowRequest).where(FollowRequest.id == request_id)
    )
    req = result.scalar_one_or_none()
    if not req:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Заявка не найдена",
        )
    if req.target_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Нет доступа к этой заявке",
        )
    if req.status != FollowRequestStatus.PENDING:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Заявка уже обработана",
        )

    # Создаём Follow, если ещё нет (на случай гонок)
    existing = await db.execute(
        select(Follow).where(
            Follow.follower_id == req.requester_id,
            Follow.following_id == current_user.id,
        )
    )
    if not existing.scalar_one_or_none():
        db.add(Follow(
            follower_id=req.requester_id,
            following_id=current_user.id,
        ))

    req.status = FollowRequestStatus.APPROVED
    req.resolved_at = datetime.utcnow()
    await db.flush()

    from app.services.notification_service import create_notification
    from app.services import push_copy
    approver_name = current_user.display_name or current_user.username
    _approved_title, _approved_body = push_copy.follow_approved(name=approver_name)
    await create_notification(
        db,
        user_id=req.requester_id,
        actor_id=current_user.id,
        type="new_follower",
        entity_type="user",
        entity_id=str(current_user.id),
        data={
            "actor_username": current_user.username,
            "actor_display_name": current_user.display_name,
            "approved": True,
        },
        push_title=_approved_title,
        push_body=_approved_body,
        push_image=absolute_media_url(current_user.avatar_url),
    )

    await db.commit()

    # Эмиссия событий ачивок (K-серия) — как при обычном follow
    from app.services.achievements import emit_event
    from app.services.achievements.events import FOLLOW_CREATED, FOLLOW_RECEIVED
    await emit_event(
        db,
        req.requester_id,
        FOLLOW_CREATED,
        {"following_id": current_user.id},
    )
    await emit_event(
        db,
        current_user.id,
        FOLLOW_RECEIVED,
        {"follower_id": req.requester_id},
    )

    return FollowActionResponse(status="followed", follow_request_id=req.id)


@router.post("/me/follow-requests/{request_id}/reject", status_code=status.HTTP_204_NO_CONTENT)
async def reject_follow_request(
    request_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Отклонить заявку. Запись удаляется, чтобы requester мог повторно подать в будущем."""
    result = await db.execute(
        select(FollowRequest).where(FollowRequest.id == request_id)
    )
    req = result.scalar_one_or_none()
    if not req:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Заявка не найдена",
        )
    if req.target_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Нет доступа к этой заявке",
        )
    if req.status != FollowRequestStatus.PENDING:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Заявка уже обработана",
        )
    await db.delete(req)
    await db.commit()


@router.delete("/{user_id}/follow-request", status_code=status.HTTP_204_NO_CONTENT)
async def cancel_follow_request(
    user_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Отменить свою исходящую заявку на подписку на пользователя user_id.
    Удобный shortcut: не нужен id заявки, только id таргета.
    """
    result = await db.execute(
        select(FollowRequest).where(
            FollowRequest.requester_id == current_user.id,
            FollowRequest.target_id == user_id,
            FollowRequest.status == FollowRequestStatus.PENDING,
        )
    )
    req = result.scalar_one_or_none()
    if not req:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Активная заявка не найдена",
        )
    await db.delete(req)
    await db.commit()

