"""
API для работы с подарками (бронирование из вишлиста)
"""
import logging
from datetime import datetime, timedelta
from uuid import UUID

logger = logging.getLogger(__name__)

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.models.user import User
from app.models.wishlist import Wishlist, WishlistItem
from app.models.gift_booking import GiftBooking, GiftStatus
from app.api.auth import get_current_user, get_current_user_optional
from app.schemas.wishlist import (
    GiftBookingCreate,
    GiftBookingResponse,
    GiftBookingOwnerResponse,
    GiftGivenResponse,
    GiftRecipientInfo,
)
from app.schemas.record import RecordBrief
from app.utils.security import generate_random_token

router = APIRouter()


@router.post("/book", response_model=GiftBookingResponse, status_code=status.HTTP_201_CREATED)
async def book_gift(
    data: GiftBookingCreate,
    current_user: User | None = Depends(get_current_user_optional),
    db: AsyncSession = Depends(get_db)
):
    """
    Бронирование подарка из вишлиста.
    Не требует авторизации - может быть выполнено любым человеком по ссылке.
    """
    # Получаем элемент вишлиста
    result = await db.execute(
        select(WishlistItem)
        .where(WishlistItem.id == data.wishlist_item_id)
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
            detail="Элемент вишлиста не найден"
        )
    
    # Проверяем, что вишлист публичный
    if not item.wishlist.is_public:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Вишлист недоступен"
        )
    
    # Проверяем, что ещё не забронировано
    if item.gift_booking:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Этот подарок уже забронирован"
        )
    
    # Проверяем, что не куплено
    if item.is_purchased:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Эта пластинка уже куплена"
        )
    
    # Создаём бронирование
    cancel_token = generate_random_token(24)
    
    booking = GiftBooking(
        wishlist_item_id=item.id,
        booked_by_user_id=current_user.id if current_user else None,
        gifter_name=data.gifter_name,
        gifter_email=data.gifter_email,
        gifter_phone=data.gifter_phone,
        gifter_message=data.gifter_message,
        status=GiftStatus.BOOKED,
        cancel_token=cancel_token,
        expires_at=datetime.utcnow() + timedelta(days=60)
    )
    db.add(booking)
    await db.commit()
    await db.refresh(booking)

    logger.info(
        "gift_booked",
        extra={
            "booking_id": str(booking.id),
            "wishlist_item_id": str(booking.wishlist_item_id),
            "gifter_email": booking.gifter_email,
            "gifter_name": booking.gifter_name,
        }
    )

    # Отправляем уведомление владельцу вишлиста (анонимно)
    try:
        from app.services.notifications import send_booking_notification_to_owner
        owner_result = await db.execute(
            select(User).where(User.id == item.wishlist.user_id)
        )
        owner = owner_result.scalar_one_or_none()
        if owner:
            await send_booking_notification_to_owner(
                booking=booking,
                owner_email=owner.email,
                record_title=item.record.title,
            )
    except Exception:
        pass  # Не блокируем основной flow
    
    return GiftBookingResponse(
        id=booking.id,
        wishlist_item_id=booking.wishlist_item_id,
        gifter_name=booking.gifter_name,
        gifter_email=booking.gifter_email,
        gifter_phone=booking.gifter_phone,
        gifter_message=booking.gifter_message,
        status=booking.status,
        cancel_token=booking.cancel_token,
        booked_at=booking.booked_at,
        record=RecordBrief.model_validate(item.record),
    )


@router.get("/{booking_id}", response_model=GiftBookingResponse)
async def get_booking(
    booking_id: UUID,
    db: AsyncSession = Depends(get_db)
):
    """Получение информации о бронировании"""
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
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Бронирование не найдено"
        )
    
    return GiftBookingResponse(
        id=booking.id,
        wishlist_item_id=booking.wishlist_item_id,
        gifter_name=booking.gifter_name,
        gifter_email=booking.gifter_email,
        gifter_phone=booking.gifter_phone,
        gifter_message=booking.gifter_message,
        status=booking.status,
        cancel_token="",  # Не показываем токен при просмотре
        booked_at=booking.booked_at,
        record=RecordBrief.model_validate(booking.wishlist_item.record),
    )


@router.put("/{booking_id}/cancel")
async def cancel_booking(
    booking_id: UUID,
    cancel_token: str,
    db: AsyncSession = Depends(get_db)
):
    """
    Отмена бронирования.
    Требуется cancel_token, который был выдан при бронировании.
    """
    result = await db.execute(
        select(GiftBooking).where(GiftBooking.id == booking_id)
    )
    booking = result.scalar_one_or_none()
    
    if not booking:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Бронирование не найдено"
        )
    
    if booking.cancel_token != cancel_token:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Неверный токен отмены"
        )
    
    if booking.status == GiftStatus.COMPLETED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Нельзя отменить завершённое бронирование"
        )
    
    if booking.status == GiftStatus.CANCELLED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Бронирование уже отменено"
        )
    
    booking.status = GiftStatus.CANCELLED
    booking.cancelled_at = datetime.utcnow()
    await db.commit()
    
    return {"status": "cancelled"}


@router.get("/my-bookings/by-email")
async def get_my_bookings_by_email(
    email: str,
    db: AsyncSession = Depends(get_db)
):
    """
    Получение списка бронирований по email.
    Для дарителей без регистрации.
    """
    result = await db.execute(
        select(GiftBooking)
        .where(GiftBooking.gifter_email == email)
        .options(
            selectinload(GiftBooking.wishlist_item)
            .selectinload(WishlistItem.record),
            selectinload(GiftBooking.wishlist_item)
            .selectinload(WishlistItem.wishlist)
            .selectinload(Wishlist.user)
        )
        .order_by(GiftBooking.booked_at.desc())
    )
    bookings = result.scalars().all()
    
    return [{
        "id": b.id,
        "record": {
            "title": b.wishlist_item.record.title,
            "artist": b.wishlist_item.record.artist,
            "cover_image_url": b.wishlist_item.record.cover_image_url,
        },
        "for_user": b.wishlist_item.wishlist.user.display_name or b.wishlist_item.wishlist.user.username,
        "status": b.status,
        "booked_at": b.booked_at,
    } for b in bookings]


@router.get("/me/given", response_model=list[GiftGivenResponse])
async def get_given_bookings(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Получение списка бронирований, сделанных текущим пользователем (секция 'Я дарю')"""
    result = await db.execute(
        select(GiftBooking)
        .where(
            or_(
                GiftBooking.booked_by_user_id == current_user.id,
                GiftBooking.gifter_email == current_user.email,
            ),
            GiftBooking.status.in_([GiftStatus.BOOKED, GiftStatus.COMPLETED])
        )
        .options(
            selectinload(GiftBooking.wishlist_item)
            .selectinload(WishlistItem.record),
            selectinload(GiftBooking.wishlist_item)
            .selectinload(WishlistItem.wishlist)
            .selectinload(Wishlist.user)
        )
        .order_by(GiftBooking.booked_at.desc())
    )
    bookings = result.scalars().all()

    return [GiftGivenResponse(
        id=b.id,
        status=b.status,
        cancel_token=b.cancel_token,
        booked_at=b.booked_at,
        completed_at=b.completed_at,
        record=RecordBrief.model_validate(b.wishlist_item.record),
        for_user=GiftRecipientInfo(
            username=b.wishlist_item.wishlist.user.username,
            display_name=b.wishlist_item.wishlist.user.display_name,
            avatar_url=b.wishlist_item.wishlist.user.avatar_url
        )
    ) for b in bookings]


@router.get("/me/received", response_model=list[GiftBookingOwnerResponse])
async def get_received_bookings(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Получение списка бронирований для владельца вишлиста"""
    # Получаем вишлист пользователя
    result = await db.execute(
        select(Wishlist).where(Wishlist.user_id == current_user.id)
    )
    wishlist = result.scalar_one_or_none()
    
    if not wishlist:
        return []
    
    # Получаем все бронирования
    result = await db.execute(
        select(GiftBooking)
        .join(WishlistItem)
        .where(WishlistItem.wishlist_id == wishlist.id)
        .options(
            selectinload(GiftBooking.wishlist_item)
            .selectinload(WishlistItem.record)
        )
        .order_by(GiftBooking.booked_at.desc())
    )
    bookings = result.scalars().all()
    
    # Анонимность: владелец видит только статус, без имени/email/телефона дарителя
    return [GiftBookingOwnerResponse(
        id=b.id,
        wishlist_item_id=b.wishlist_item_id,
        gifter_name="",
        gifter_email="",
        gifter_phone=None,
        gifter_message=None,
        status=b.status,
        booked_at=b.booked_at,
        completed_at=b.completed_at,
        cancelled_at=b.cancelled_at,
        record=RecordBrief.model_validate(b.wishlist_item.record),
    ) for b in bookings if b.wishlist_item is not None]


@router.put("/me/received/{booking_id}/complete")
async def complete_booking(
    booking_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Отметка подарка как полученного"""
    result = await db.execute(
        select(GiftBooking)
        .where(GiftBooking.id == booking_id)
        .options(
            selectinload(GiftBooking.wishlist_item)
            .selectinload(WishlistItem.wishlist)
        )
    )
    booking = result.scalar_one_or_none()
    
    if not booking:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Бронирование не найдено"
        )
    
    if booking.wishlist_item.wishlist.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Нет доступа"
        )
    
    booking.status = GiftStatus.COMPLETED
    booking.completed_at = datetime.utcnow()
    booking.wishlist_item.is_purchased = True
    booking.wishlist_item.purchased_at = datetime.utcnow()
    
    await db.commit()
    
    return {"status": "completed"}

