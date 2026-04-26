"""
API для управления публичным профилем
"""
import time
from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.models.user import User
from app.models.record import Record
from app.models.collection import Collection, CollectionItem
from app.models.wishlist import Wishlist, WishlistItem
from app.models.follow import Follow
from app.models.profile_share import ProfileShare
from app.models.gift_booking import GiftBooking, GiftStatus
from app.api.auth import get_current_user
from app.schemas.profile import (
    ProfileShareSettings,
    ProfileShareUpdate,
    ProfileHighlightsUpdate,
    PublicProfileResponse,
    PublicProfileRecord,
)
from app.services.exchange import get_usd_rub_rate
from app.services.valuation import get_monthly_delta

router = APIRouter()


# In-memory кэш Новинок (общий для всех юзеров) на 1 час
_new_releases_cache: dict = {"data": None, "ts": 0.0}
_NEW_RELEASES_TTL = 3600


def _record_to_public(record: Record, is_booked: bool = False) -> PublicProfileRecord:
    return PublicProfileRecord(
        id=record.id,
        title=record.title,
        artist=record.artist,
        year=record.year,
        label=record.label,
        format_type=record.format_type,
        cover_image_url=record.cover_image_url,
        thumb_image_url=record.thumb_image_url,
        estimated_price_median=float(record.estimated_price_median) if record.estimated_price_median else None,
        price_currency=record.price_currency,
        is_booked=is_booked,
    )


async def _get_recent_additions(user_id: UUID, db: AsyncSession, limit: int = 10) -> list[PublicProfileRecord]:
    result = await db.execute(
        select(CollectionItem)
        .join(Collection)
        .where(Collection.user_id == user_id)
        .options(selectinload(CollectionItem.record))
        .order_by(CollectionItem.added_at.desc())
        .limit(limit)
    )
    items = result.scalars().all()
    return [_record_to_public(item.record) for item in items if item.record]


async def _get_new_releases(db: AsyncSession, limit: int = 12) -> list[PublicProfileRecord]:
    """Глобальный рейл свежих релизов: year >= current_year - 1, отсортирован по спросу в вишлистах."""
    now = time.time()
    if _new_releases_cache["data"] is not None and (now - _new_releases_cache["ts"]) < _NEW_RELEASES_TTL:
        return _new_releases_cache["data"][:limit]

    current_year = datetime.utcnow().year
    demand = func.count(WishlistItem.id).label("demand")
    stmt = (
        select(Record, demand)
        .outerjoin(WishlistItem, WishlistItem.record_id == Record.id)
        .where(Record.year >= current_year - 1)
        .group_by(Record.id)
        .order_by(demand.desc(), Record.year.desc())
        .limit(limit)
    )
    result = await db.execute(stmt)
    rows = result.all()
    data = [_record_to_public(row[0]) for row in rows]

    _new_releases_cache["data"] = data
    _new_releases_cache["ts"] = now
    return data


async def get_public_profile_payload(user: User, profile: ProfileShare, db: AsyncSession) -> PublicProfileResponse:
    """Общий helper, используется и API endpoint, и web-роутом."""
    collection_count = await db.scalar(
        select(func.count(CollectionItem.id))
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

    collection_value = None
    collection_value_rub = None
    monthly_delta = None
    if profile.show_collection_value:
        value_result = await db.scalar(
            select(func.sum(Record.estimated_price_median))
            .join(CollectionItem, CollectionItem.record_id == Record.id)
            .join(Collection)
            .where(Collection.user_id == user.id)
        )
        collection_value = float(value_result) if value_result else 0.0
        rate = await get_usd_rub_rate()
        collection_value_rub = round(collection_value * rate, 2)
        delta = await get_monthly_delta(user.id, db)
        monthly_delta = float(delta) if delta is not None else None

    # Highlights
    highlights: list[PublicProfileRecord] = []
    if profile.highlight_record_ids:
        for record_id in profile.highlight_record_ids:
            rec = await db.scalar(select(Record).where(Record.id == record_id))
            if rec:
                highlights.append(_record_to_public(rec))

    recent_additions = await _get_recent_additions(user.id, db, limit=10) if profile.show_collection else []
    new_releases = await _get_new_releases(db, limit=12)

    return PublicProfileResponse(
        username=user.username,
        display_name=user.display_name,
        avatar_url=user.avatar_url,
        bio=user.bio,
        custom_title=profile.custom_title,
        collection_count=collection_count,
        wishlist_count=wishlist_count,
        collection_value=collection_value,
        collection_value_rub=collection_value_rub,
        monthly_value_delta_rub=monthly_delta,
        followers_count=followers_count,
        show_collection=profile.show_collection,
        show_wishlist=profile.show_wishlist,
        show_record_year=profile.show_record_year,
        show_record_label=profile.show_record_label,
        show_record_format=profile.show_record_format,
        show_record_prices=profile.show_record_prices,
        highlights=highlights,
        recent_additions=recent_additions,
        new_releases=new_releases,
    )


@router.get("/settings", response_model=ProfileShareSettings)
async def get_profile_settings(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Получение настроек публичного профиля"""
    result = await db.execute(
        select(ProfileShare).where(ProfileShare.user_id == current_user.id)
    )
    profile = result.scalar_one_or_none()

    if not profile:
        return ProfileShareSettings()

    return ProfileShareSettings(
        is_active=profile.is_active,
        is_private_profile=profile.is_private_profile,
        show_collection=profile.show_collection,
        show_wishlist=profile.show_wishlist,
        custom_title=profile.custom_title,
        highlight_record_ids=profile.highlight_record_ids,
        show_record_year=profile.show_record_year,
        show_record_label=profile.show_record_label,
        show_record_format=profile.show_record_format,
        show_record_prices=profile.show_record_prices,
        show_collection_value=profile.show_collection_value,
    )


@router.put("/settings", response_model=ProfileShareSettings)
async def update_profile_settings(
    data: ProfileShareUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Обновление настроек публичного профиля"""
    result = await db.execute(
        select(ProfileShare).where(ProfileShare.user_id == current_user.id)
    )
    profile = result.scalar_one_or_none()

    if not profile:
        profile = ProfileShare(user_id=current_user.id)
        db.add(profile)

    update_fields = data.model_dump(exclude_unset=True)
    for field, value in update_fields.items():
        setattr(profile, field, value)

    await db.commit()
    await db.refresh(profile)

    return ProfileShareSettings(
        is_active=profile.is_active,
        is_private_profile=profile.is_private_profile,
        show_collection=profile.show_collection,
        show_wishlist=profile.show_wishlist,
        custom_title=profile.custom_title,
        highlight_record_ids=profile.highlight_record_ids,
        show_record_year=profile.show_record_year,
        show_record_label=profile.show_record_label,
        show_record_format=profile.show_record_format,
        show_record_prices=profile.show_record_prices,
        show_collection_value=profile.show_collection_value,
    )


@router.put("/highlights", response_model=ProfileShareSettings)
async def update_highlights(
    data: ProfileHighlightsUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Установка избранных пластинок (до 4)"""
    if len(data.record_ids) > 4:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Максимум 4 избранные пластинки"
        )

    for record_id in data.record_ids:
        result = await db.execute(
            select(CollectionItem)
            .join(Collection)
            .where(
                Collection.user_id == current_user.id,
                CollectionItem.record_id == record_id
            )
        )
        if not result.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Пластинка {record_id} не найдена в вашей коллекции"
            )

    result = await db.execute(
        select(ProfileShare).where(ProfileShare.user_id == current_user.id)
    )
    profile = result.scalar_one_or_none()

    if not profile:
        profile = ProfileShare(user_id=current_user.id)
        db.add(profile)

    profile.highlight_record_ids = data.record_ids

    await db.commit()
    await db.refresh(profile)

    return ProfileShareSettings(
        is_active=profile.is_active,
        is_private_profile=profile.is_private_profile,
        show_collection=profile.show_collection,
        show_wishlist=profile.show_wishlist,
        custom_title=profile.custom_title,
        highlight_record_ids=profile.highlight_record_ids,
        show_record_year=profile.show_record_year,
        show_record_label=profile.show_record_label,
        show_record_format=profile.show_record_format,
        show_record_prices=profile.show_record_prices,
        show_collection_value=profile.show_collection_value,
    )



@router.get("/public/new-releases", response_model=list[PublicProfileRecord])
async def get_new_releases(
    limit: int = 12,
    db: AsyncSession = Depends(get_db)
):
    """Глобальный рейл новинок по спросу в вишлистах."""
    return await _get_new_releases(db, limit=min(limit, 24))


@router.get("/public/{username}", response_model=PublicProfileResponse)
async def get_public_profile(
    username: str,
    db: AsyncSession = Depends(get_db)
):
    """Публичные данные профиля (JSON)"""
    result = await db.execute(
        select(User)
        .where(User.username == username, User.is_active == True)
        .options(selectinload(User.profile_share))
    )
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Пользователь не найден"
        )

    profile = user.profile_share
    if not profile or not profile.is_active:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Публичный профиль не активирован"
        )

    profile.view_count += 1
    await db.commit()

    return await get_public_profile_payload(user, profile, db)


@router.get("/public/{username}/recent-additions", response_model=list[PublicProfileRecord])
async def get_recent_additions(
    username: str,
    limit: int = 10,
    db: AsyncSession = Depends(get_db)
):
    """Последние добавленные пластинки в коллекцию пользователя."""
    user = await db.scalar(select(User).where(User.username == username, User.is_active == True))
    if not user:
        raise HTTPException(status_code=404, detail="Пользователь не найден")
    return await _get_recent_additions(user.id, db, limit=min(limit, 30))
