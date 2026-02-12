"""
API для управления публичным профилем
"""
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
from app.api.auth import get_current_user
from app.schemas.profile import (
    ProfileShareSettings,
    ProfileShareUpdate,
    ProfileHighlightsUpdate,
    PublicProfileResponse,
    PublicProfileRecord,
)

router = APIRouter()


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
        # Возвращаем дефолтные настройки
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

    # Обновляем только переданные поля
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

    # Проверяем, что все пластинки есть в коллекции пользователя
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

    # Инкремент просмотров
    profile.view_count += 1
    await db.commit()

    # Статистика
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

    # Стоимость коллекции (если разрешено показывать)
    collection_value = None
    if profile.show_collection_value:
        value_result = await db.scalar(
            select(func.sum(Record.estimated_price_median))
            .join(CollectionItem, CollectionItem.record_id == Record.id)
            .join(Collection)
            .where(Collection.user_id == user.id)
        )
        collection_value = float(value_result) if value_result else 0.0

    # Избранные пластинки
    highlights = []
    if profile.highlight_record_ids:
        for record_id in profile.highlight_record_ids:
            result = await db.execute(
                select(Record).where(Record.id == record_id)
            )
            record = result.scalar_one_or_none()
            if record:
                highlights.append(PublicProfileRecord(
                    id=record.id,
                    title=record.title,
                    artist=record.artist,
                    year=record.year,
                    label=record.label,
                    format_type=record.format_type,
                    cover_image_url=record.cover_image_url,
                    thumb_image_url=record.thumb_image_url,
                    estimated_price_median=float(record.estimated_price_median) if record.estimated_price_median else None,
                    price_currency=record.price_currency
                ))

    return PublicProfileResponse(
        username=user.username,
        display_name=user.display_name,
        avatar_url=user.avatar_url,
        bio=user.bio,
        custom_title=profile.custom_title,
        collection_count=collection_count,
        wishlist_count=wishlist_count,
        collection_value=collection_value,
        followers_count=followers_count,
        show_collection=profile.show_collection,
        show_wishlist=profile.show_wishlist,
        show_record_year=profile.show_record_year,
        show_record_label=profile.show_record_label,
        show_record_format=profile.show_record_format,
        show_record_prices=profile.show_record_prices,
        highlights=highlights,
    )
