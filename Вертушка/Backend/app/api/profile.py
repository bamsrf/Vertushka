"""
API для управления публичным профилем
"""
import logging
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

logger = logging.getLogger(__name__)

router = APIRouter()


def _record_to_public(
    record: Record,
    is_booked: bool = False,
    discogs_want: int | None = None,
    discogs_have: int | None = None,
) -> PublicProfileRecord:
    return PublicProfileRecord(
        id=record.id,
        title=record.title,
        artist=record.artist,
        year=record.year,
        label=record.label,
        format_type=record.format_type,
        cover_image_url=record.cover_image_url,
        thumb_image_url=record.thumb_image_url,
        estimated_price_median=float(record.estimated_price_median or record.estimated_price_min) if (record.estimated_price_median or record.estimated_price_min) else None,
        price_currency=record.price_currency,
        is_booked=is_booked,
        discogs_id=record.discogs_id,
        discogs_master_id=record.discogs_master_id,
        discogs_want=discogs_want,
        discogs_have=discogs_have,
        is_first_press=bool(record.is_first_press),
        is_canon=bool(record.is_canon),
        is_collectible=bool(record.is_collectible),
        is_limited=bool(record.is_limited),
        is_hot=bool(record.is_hot),
    )


async def _get_top_expensive(user_id: UUID, db: AsyncSession, limit: int = 12) -> list[PublicProfileRecord]:
    """Самые дорогие пластинки коллекции, отсортированные по цене убыванию."""
    result = await db.execute(
        select(CollectionItem)
        .join(Collection)
        .where(Collection.user_id == user_id)
        .options(selectinload(CollectionItem.record))
        .limit(300)
    )
    items = result.scalars().all()
    seen: set[UUID] = set()
    records: list[Record] = []
    for item in items:
        if not item.record or item.record.id in seen:
            continue
        seen.add(item.record.id)
        records.append(item.record)
    records.sort(
        key=lambda r: float(r.estimated_price_median or r.estimated_price_min or 0),
        reverse=True
    )
    return [_record_to_public(r) for r in records[:limit]]


async def _get_full_collection(user_id: UUID, db: AsyncSession, limit: int = 200) -> list[PublicProfileRecord]:
    """Полная коллекция пользователя с дедупом по record_id (по последнему added_at)."""
    result = await db.execute(
        select(CollectionItem)
        .join(Collection)
        .where(Collection.user_id == user_id)
        .options(selectinload(CollectionItem.record))
        .order_by(CollectionItem.added_at.desc())
        .limit(limit)
    )
    items = result.scalars().all()
    seen: set[UUID] = set()
    out: list[PublicProfileRecord] = []
    for item in items:
        if not item.record or item.record.id in seen:
            continue
        seen.add(item.record.id)
        out.append(_record_to_public(item.record))
    return out


async def _upsert_discogs_release(db: AsyncSession, payload: dict) -> Record | None:
    """Возвращает существующий Record по discogs_id или создаёт новый.
    Не коммитит — коммит ждёт общую транзакцию вызывающего."""
    discogs_id = payload.get("discogs_id")
    if not discogs_id:
        return None

    existing = await db.scalar(select(Record).where(Record.discogs_id == discogs_id))
    if existing:
        if not existing.discogs_master_id and payload.get("discogs_master_id"):
            existing.discogs_master_id = payload["discogs_master_id"]
        if not existing.cover_image_url and payload.get("cover_image_url"):
            existing.cover_image_url = payload["cover_image_url"]
        if not existing.thumb_image_url and payload.get("thumb_image_url"):
            existing.thumb_image_url = payload["thumb_image_url"]
        return existing

    record = Record(
        discogs_id=discogs_id,
        discogs_master_id=payload.get("discogs_master_id"),
        title=payload.get("title") or "Unknown",
        artist=payload.get("artist") or "Unknown",
        year=payload.get("year"),
        label=payload.get("label"),
        format_type=payload.get("format_type"),
        country=payload.get("country"),
        cover_image_url=payload.get("cover_image_url"),
        thumb_image_url=payload.get("thumb_image_url"),
    )
    db.add(record)
    try:
        await db.flush()
    except Exception:
        await db.rollback()
        return await db.scalar(select(Record).where(Record.discogs_id == discogs_id))
    return record


async def _get_new_releases(
    db: AsyncSession,
    limit: int = 12,
    user_id: UUID | None = None,
) -> list[PublicProfileRecord]:
    """Глобальный пул новинок с Discogs (`/database/search`, sort=want).

    Кэш — на стороне DiscogsService (Redis, 12ч). Здесь — апсерт в локальный Record
    (чтоб карточка имела стабильный UUID для модалки/экрана детали) и фильтрация
    по master_id из коллекции конкретного юзера.
    """
    from app.services.discogs import DiscogsService

    discogs = DiscogsService()
    pool = await discogs.search_new_releases(per_page=60)
    if not pool:
        return []

    excluded_master_ids: set[str] = set()
    excluded_discogs_ids: set[str] = set()
    if user_id is not None:
        rows = await db.execute(
            select(Record.discogs_id, Record.discogs_master_id)
            .join(CollectionItem, CollectionItem.record_id == Record.id)
            .join(Collection)
            .where(Collection.user_id == user_id)
        )
        for did, mid in rows.all():
            if mid:
                excluded_master_ids.add(str(mid))
            if did:
                excluded_discogs_ids.add(str(did))

    out: list[PublicProfileRecord] = []
    seen_master: set[str] = set()
    for item in pool:
        if len(out) >= limit:
            break
        mid = item.get("discogs_master_id")
        did = item.get("discogs_id")
        if mid and mid in excluded_master_ids:
            continue
        if did and did in excluded_discogs_ids:
            continue
        # Дедуп внутри пула по master_id (один альбом, разные прессы)
        if mid:
            if mid in seen_master:
                continue
            seen_master.add(mid)

        record = await _upsert_discogs_release(db, item)
        if record is None:
            continue
        out.append(_record_to_public(
            record,
            discogs_want=item.get("want"),
            discogs_have=item.get("have"),
        ))

    if out:
        try:
            await db.commit()
        except Exception:
            logger.exception("Failed to commit new_releases upserts")
            await db.rollback()

    return out


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
            select(func.sum(func.coalesce(Record.estimated_price_min, Record.estimated_price_median)))
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

    top_expensive = await _get_top_expensive(user.id, db, limit=12) if profile.show_collection else []
    collection_full = await _get_full_collection(user.id, db, limit=200) if profile.show_collection else []
    new_releases = await _get_new_releases(db, limit=24, user_id=user.id)

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
        collection=collection_full,
        top_expensive=top_expensive,
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
    """Глобальный рейл свежих релизов с Discogs (sort=want)."""
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


@router.get("/public/{username}/top-expensive", response_model=list[PublicProfileRecord])
async def get_top_expensive(
    username: str,
    limit: int = 12,
    db: AsyncSession = Depends(get_db)
):
    """Самые дорогие пластинки коллекции пользователя."""
    user = await db.scalar(select(User).where(User.username == username, User.is_active == True))
    if not user:
        raise HTTPException(status_code=404, detail="Пользователь не найден")
    return await _get_top_expensive(user.id, db, limit=min(limit, 30))
