"""
API для работы с подарками (бронирование из вишлиста)
"""
import hashlib
import logging
from datetime import datetime, timedelta
from uuid import UUID

logger = logging.getLogger(__name__)

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import get_settings
from app.database import get_db
from app.utils.request_ip import get_client_ip
from app.models.blocked_contact import BlockedContact, BlockedContactKind
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


def _extract_client_ip(request: Request) -> str | None:
    """Реальный IP клиента за nginx (не подделываемый через X-Forwarded-For).

    Раньше брался первый хоп XFF — он формируется клиентом и тривиально
    подменяется, что обходило анти-фрод лимит на бронирование. Теперь IP берётся
    из X-Real-IP (его nginx перезаписывает реальным $remote_addr). См.
    app/utils/request_ip.py.
    """
    ip = get_client_ip(request)
    return ip if ip != "unknown" else None


def _hash_user_agent(request: Request) -> str | None:
    ua = request.headers.get("user-agent")
    if not ua:
        return None
    return hashlib.sha256(ua.encode("utf-8", errors="ignore")).hexdigest()


async def _is_blocked(db: AsyncSession, *, email: str | None, ip: str | None) -> bool:
    conditions = []
    if email:
        conditions.append(
            (BlockedContact.kind == BlockedContactKind.EMAIL)
            & (func.lower(BlockedContact.value) == email.strip().lower())
        )
    if ip:
        conditions.append(
            (BlockedContact.kind == BlockedContactKind.IP)
            & (BlockedContact.value == ip)
        )
    if not conditions:
        return False
    result = await db.execute(
        select(BlockedContact.id).where(or_(*conditions)).limit(1)
    )
    return result.scalar_one_or_none() is not None


async def _check_rate_limits(
    db: AsyncSession,
    *,
    email: str,
    ip: str | None,
) -> None:
    """
    Проверяет лимиты на бронирование. Бросает HTTPException 429 если превышены.
    """
    settings = get_settings()
    now = datetime.utcnow()

    # Per-IP: ≤ N броней за окно (любой статус, считаем как попытки)
    if ip and settings.gift_booking_per_ip_limit > 0:
        window_start = now - timedelta(minutes=settings.gift_booking_per_ip_window_minutes)
        ip_count = await db.scalar(
            select(func.count(GiftBooking.id))
            .where(
                GiftBooking.gifter_ip == ip,
                GiftBooking.booked_at >= window_start,
            )
        ) or 0
        if ip_count >= settings.gift_booking_per_ip_limit:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=(
                    "Слишком много бронирований за короткое время. "
                    "Подожди немного — если ошибка, напиши в поддержку."
                ),
            )

    # Per-email: ≤ M активных одновременно (только BOOKED, не считая PENDING)
    if settings.gift_booking_per_email_active_limit > 0:
        active_count = await db.scalar(
            select(func.count(GiftBooking.id))
            .where(
                func.lower(GiftBooking.gifter_email) == email.strip().lower(),
                GiftBooking.status == GiftStatus.BOOKED,
            )
        ) or 0
        if active_count >= settings.gift_booking_per_email_active_limit:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=(
                    f"У тебя уже {active_count} активных броней — заверши или отмени их, "
                    "прежде чем бронировать новые."
                ),
            )


@router.post("/book", response_model=GiftBookingResponse, status_code=status.HTTP_201_CREATED)
async def book_gift(
    data: GiftBookingCreate,
    request: Request,
    current_user: User | None = Depends(get_current_user_optional),
    db: AsyncSession = Depends(get_db)
):
    """
    Бронирование подарка из вишлиста.
    Не требует авторизации - может быть выполнено любым человеком по ссылке.
    """
    settings = get_settings()
    client_ip = _extract_client_ip(request)
    ua_hash = _hash_user_agent(request)

    # Блок-лист (email/IP) — раньше всех остальных проверок
    if await _is_blocked(db, email=data.gifter_email, ip=client_ip):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Бронирование недоступно. Если это ошибка, напиши в поддержку.",
        )

    # Получаем элемент вишлиста
    result = await db.execute(
        select(WishlistItem)
        .where(WishlistItem.id == data.wishlist_item_id)
        .options(
            selectinload(WishlistItem.wishlist).selectinload(Wishlist.user),
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

    # Запрещаем самобронь — владелец не может бронировать пункты из собственного вишлиста
    owner = item.wishlist.user
    SELF_BOOKING_DETAIL = "Самому забронировать себе подарок нельзя. Дай волю это сделать друзьям и близким"

    if current_user and current_user.id == item.wishlist.user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=SELF_BOOKING_DETAIL
        )

    # Анонимная самобронь по совпадению email
    if owner and data.gifter_email and owner.email \
            and data.gifter_email.strip().lower() == owner.email.strip().lower():
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=SELF_BOOKING_DETAIL
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

    # Анти-фрод лимиты (после всех правил, но до создания записи)
    await _check_rate_limits(db, email=data.gifter_email, ip=client_ip)

    # Создаём бронирование
    cancel_token = generate_random_token(24)
    require_verification = settings.gift_booking_require_email_verification
    verify_token = generate_random_token(24) if require_verification else None

    if require_verification:
        # PENDING + короткий expires_at до подтверждения email.
        # После подтверждения статус → BOOKED и expires_at пересчитывается на 60 дней.
        booking_status = GiftStatus.PENDING
        booking_expires_at = datetime.utcnow() + timedelta(
            hours=settings.gift_booking_verification_window_hours
        )
    else:
        booking_status = GiftStatus.BOOKED
        booking_expires_at = datetime.utcnow() + timedelta(days=60)

    booking = GiftBooking(
        wishlist_item_id=item.id,
        booked_by_user_id=current_user.id if current_user else None,
        recipient_user_id=owner.id if owner else None,
        gifter_name=data.gifter_name,
        gifter_email=data.gifter_email,
        gifter_phone=data.gifter_phone,
        gifter_message=data.gifter_message,
        status=booking_status,
        cancel_token=cancel_token,
        verify_token=verify_token,
        expires_at=booking_expires_at,
        gifter_ip=client_ip,
        gifter_user_agent_hash=ua_hash,
    )
    db.add(booking)
    try:
        await db.commit()
        await db.refresh(booking)
    except IntegrityError:
        # Race: параллельный запрос успел забронировать тот же wishlist_item_id
        # раньше нас. UNIQUE-constraint на колонке защитил от двойной брони,
        # но клиенту нужно отдать понятную ошибку, а не 500.
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Этот подарок только что забронировал кто-то другой"
        )

    logger.info(
        "gift_booked",
        extra={
            "booking_id": str(booking.id),
            "wishlist_item_id": str(booking.wishlist_item_id),
            "gifter_email": booking.gifter_email,
            "gifter_name": booking.gifter_name,
            "gifter_ip": booking.gifter_ip,
            "status": booking.status.value if hasattr(booking.status, "value") else booking.status,
        }
    )

    # Эмиссия события ачивок — только для аутентифицированных дарителей
    # (анонимная бронь не должна засчитываться на чужой аккаунт).
    if booking.booked_by_user_id is not None:
        from app.services.achievements import emit_event
        from app.services.achievements.events import GIFT_BOOKED
        await emit_event(
            db,
            booking.booked_by_user_id,
            GIFT_BOOKED,
            {"booking_id": booking.id},
        )

    CANCEL_BASE = settings.app_url or "https://vinyl-vertushka.ru"
    cancel_url = f"{CANCEL_BASE}/cancel/{booking.id}?token={booking.cancel_token}"
    confirm_url = (
        f"{CANCEL_BASE}/confirm/{booking.id}?token={booking.verify_token}"
        if booking.verify_token else None
    )

    # Подтверждение/верификация дарителю
    try:
        if require_verification and confirm_url:
            from app.services.notifications import send_booking_verification_to_gifter
            await send_booking_verification_to_gifter(
                gifter_email=booking.gifter_email,
                gifter_name=booking.gifter_name,
                record_title=item.record.title,
                record_artist=item.record.artist,
                confirm_url=confirm_url,
                window_hours=settings.gift_booking_verification_window_hours,
            )
        else:
            from app.services.notifications import send_booking_confirmation_to_gifter
            await send_booking_confirmation_to_gifter(
                gifter_email=booking.gifter_email,
                gifter_name=booking.gifter_name,
                record_title=item.record.title,
                record_artist=item.record.artist,
                cancel_url=cancel_url,
            )
    except Exception:
        pass

    # Уведомление владельцу — только когда бронь уже подтверждена (BOOKED).
    # Для PENDING ждём верификацию email.
    if booking.status == GiftStatus.BOOKED:
        try:
            from app.services.notifications import send_booking_notification_to_owner
            if owner:
                reveal_name = (
                    booking.gifter_name if item.wishlist.reveal_gifter_to_owner else None
                )
                await send_booking_notification_to_owner(
                    booking=booking,
                    owner_email=owner.email,
                    record_title=item.record.title,
                    gifter_name=reveal_name,
                )
        except Exception:
            pass

        # In-app + push владельцу — анонимно (если не reveal_gifter_to_owner)
        if owner:
            try:
                from app.services.notification_service import create_notification
                reveal_gifter = item.wishlist.reveal_gifter_to_owner
                push_body = (
                    f"{booking.gifter_name} забронировал(а) «{item.record.title}»"
                    if reveal_gifter
                    else f"Кто-то забронировал «{item.record.title}» из твоего вишлиста"
                )
                await create_notification(
                    db,
                    user_id=owner.id,
                    actor_id=booking.booked_by_user_id if reveal_gifter else None,
                    type="gift_booked",
                    entity_type="gift_booking",
                    entity_id=str(booking.id),
                    data={
                        "record_id": str(item.record.id),
                        "record_title": item.record.title,
                        "record_artist": item.record.artist,
                        "cover_url": item.record.cover_image_url,
                        "anonymous": not reveal_gifter,
                    },
                    push_title="Подарок забронирован",
                    push_body=push_body,
                )
                await db.commit()
            except Exception:
                logger.exception("Failed to create gift_booked notification")
    
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


@router.put("/{booking_id}/confirm")
async def confirm_booking(
    booking_id: UUID,
    token: str,
    db: AsyncSession = Depends(get_db)
):
    """
    Подтверждение бронирования по email-токену.
    Используется только когда включён флаг gift_booking_require_email_verification.
    Переводит PENDING → BOOKED, expires_at = confirmed_at + 60 дней.
    Идемпотентно: повторный вызов на BOOKED — 200, на CANCELLED — 400.
    """
    result = await db.execute(
        select(GiftBooking)
        .where(GiftBooking.id == booking_id)
        .options(
            selectinload(GiftBooking.wishlist_item).selectinload(WishlistItem.record),
            selectinload(GiftBooking.wishlist_item)
            .selectinload(WishlistItem.wishlist)
            .selectinload(Wishlist.user),
        )
    )
    booking = result.scalar_one_or_none()

    if not booking:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Бронирование не найдено"
        )

    if not booking.verify_token or booking.verify_token != token:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Неверный токен подтверждения"
        )

    if booking.status == GiftStatus.BOOKED:
        return {"status": "booked"}

    if booking.status in (GiftStatus.CANCELLED, GiftStatus.COMPLETED):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Бронь уже завершена или отменена"
        )

    # PENDING → BOOKED + полный 60-дневный срок от момента подтверждения
    booking.status = GiftStatus.BOOKED
    booking.expires_at = datetime.utcnow() + timedelta(days=60)
    # verify_token больше не нужен — обнуляем чтобы повторно не использовать
    booking.verify_token = None
    await db.commit()

    # Сейчас можно уведомить владельца — ждали именно этого момента
    if booking.wishlist_item and booking.wishlist_item.wishlist and booking.wishlist_item.wishlist.user:
        try:
            from app.services.notifications import send_booking_notification_to_owner
            owner = booking.wishlist_item.wishlist.user
            wishlist = booking.wishlist_item.wishlist
            reveal_name = booking.gifter_name if wishlist.reveal_gifter_to_owner else None
            await send_booking_notification_to_owner(
                booking=booking,
                owner_email=owner.email,
                record_title=booking.wishlist_item.record.title,
                gifter_name=reveal_name,
            )
        except Exception:
            pass

    return {"status": "booked"}


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
        select(GiftBooking)
        .where(GiftBooking.id == booking_id)
        .options(
            selectinload(GiftBooking.wishlist_item).selectinload(WishlistItem.record),
            selectinload(GiftBooking.wishlist_item)
            .selectinload(WishlistItem.wishlist)
            .selectinload(Wishlist.user),
        )
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

    # Снимок данных для письма владельцу — берём до обнуления связи
    item = booking.wishlist_item
    owner_email = None
    record_title = None
    if item is not None:
        record_title = item.record.title if item.record else None
        if item.wishlist and item.wishlist.user:
            owner_email = item.wishlist.user.email

    booking.status = GiftStatus.CANCELLED
    booking.cancelled_at = datetime.utcnow()
    booking.cancellation_reason = "cancelled_by_gifter"
    booking.wishlist_item_id = None  # освобождаем пункт сразу — иначе уникальный индекс держит его «занятым»
    await db.commit()

    # Уведомляем владельца, что пункт снова свободен (анонимно)
    if owner_email and record_title:
        try:
            from app.services.notifications import send_booking_cancelled_to_owner
            await send_booking_cancelled_to_owner(owner_email, record_title)
        except Exception:
            pass

    return {"status": "cancelled"}


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
            GiftBooking.status.in_([GiftStatus.BOOKED, GiftStatus.COMPLETED]),
            GiftBooking.wishlist_item_id.is_not(None),
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
    ) for b in bookings if b.wishlist_item is not None]


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

    # Если владелец явно включил «хочу знать имя сразу» — отдаём поля дарителя.
    # Иначе — анонимизируем как раньше (дефолтное поведение).
    reveal = bool(wishlist.reveal_gifter_to_owner)

    return [GiftBookingOwnerResponse(
        id=b.id,
        wishlist_item_id=b.wishlist_item_id,
        gifter_name=(b.gifter_name if reveal else ""),
        gifter_email=(b.gifter_email if reveal else ""),
        gifter_phone=(b.gifter_phone if reveal else None),
        gifter_message=(b.gifter_message if reveal else None),
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
    """
    Отметка подарка как полученного.
    Атомарно: бронь → COMPLETED, пластинка добавляется в коллекцию владельца,
    дарителю уходит письмо «подарок получен».
    """
    result = await db.execute(
        select(GiftBooking)
        .where(GiftBooking.id == booking_id)
        .options(
            selectinload(GiftBooking.wishlist_item).selectinload(WishlistItem.record),
            selectinload(GiftBooking.wishlist_item)
            .selectinload(WishlistItem.wishlist)
            .selectinload(Wishlist.user),
        )
    )
    booking = result.scalar_one_or_none()

    if not booking:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Бронирование не найдено"
        )

    if booking.wishlist_item is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Бронирование уже завершено или отменено"
        )

    if booking.wishlist_item.wishlist.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Нет доступа"
        )

    if booking.status == GiftStatus.COMPLETED:
        return {"status": "completed"}

    from app.services.gifts import (
        complete_gift_booking,
        emit_gift_completion_events,
        send_pending_gift_email,
    )

    record = booking.wishlist_item.record if booking.wishlist_item else None
    gifter_user_id = booking.booked_by_user_id
    booking_id_done = booking.id

    collection_item = await complete_gift_booking(
        booking=booking,
        owner=current_user,
        db=db,
    )

    # In-app + push дарителю (если это зарегистрированный пользователь)
    if gifter_user_id is not None and record is not None:
        try:
            from app.services.notification_service import create_notification
            owner_name = current_user.display_name or current_user.username
            await create_notification(
                db,
                user_id=gifter_user_id,
                actor_id=current_user.id,
                type="gift_confirmed",
                entity_type="gift_booking",
                entity_id=str(booking.id),
                data={
                    "record_id": str(record.id),
                    "record_title": record.title,
                    "record_artist": record.artist,
                    "cover_url": record.cover_image_url,
                },
                push_title="Подарок получен 🎁",
                push_body=f"{owner_name} получил(а) твой подарок «{record.title}»",
            )
        except Exception:
            logger.exception("Failed to create gift_confirmed notification")

    await db.commit()
    await send_pending_gift_email(collection_item)

    # Ачивки серии «Дарящая рука» + сезонные (после commit, в своей транзакции)
    await emit_gift_completion_events(
        db,
        gifter_user_id=gifter_user_id,
        recipient_user_id=current_user.id,
        booking_id=booking_id_done,
    )

    return {"status": "completed"}

