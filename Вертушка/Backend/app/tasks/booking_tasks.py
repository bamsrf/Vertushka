"""
Фоновые задачи для управления бронированиями подарков
"""
import logging
from datetime import datetime, timedelta

from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import async_session_maker
from app.models.gift_booking import GiftBooking, GiftStatus
from app.services.profile_cache import invalidate_profile_html_cache

logger = logging.getLogger(__name__)


async def _invalidate_profiles_by_recipient_ids(db: AsyncSession, recipient_ids: set) -> None:
    """Сбросить кэш публичных страниц владельцев освобождённых пунктов.

    Один SELECT username по всем затронутым получателям — и только когда
    есть что сбрасывать. Ошибки не роняют таску: инвалидация best-effort,
    без неё страница просто доживает свой TTL.
    """
    if not recipient_ids:
        return
    try:
        from app.models.user import User

        rows = await db.execute(
            select(User.username).where(User.id.in_(recipient_ids))
        )
        for (username,) in rows.all():
            await invalidate_profile_html_cache(username)
    except Exception:  # noqa: BLE001
        logger.warning("Не удалось сбросить кэш профилей после авто-таски", exc_info=True)


async def auto_cancel_unverified_bookings():
    """
    Отмена непрошедших email-верификацию бронирований.
    PENDING + expires_at <= now → CANCELLED, cancellation_reason='not_verified',
    wishlist_item_id обнуляется (пункт снова доступен).
    Запускается каждые 5 минут (если фича-флаг включён; если выключен — таска просто
    не находит PENDING-записей и завершается мгновенно).
    """
    async with async_session_maker() as db:
        try:
            now = datetime.utcnow()

            result = await db.execute(
                select(GiftBooking).where(
                    and_(
                        GiftBooking.status == GiftStatus.PENDING,
                        GiftBooking.expires_at != None,
                        GiftBooking.expires_at <= now,
                    )
                )
            )
            bookings = result.scalars().all()

            recipient_ids = set()
            for booking in bookings:
                # Пункт освобождается — публичная страница владельца не должна
                # держать «Забронировано» из кэша. recipient_user_id живёт на
                # самой брони, поэтому связи догружать не нужно.
                if booking.recipient_user_id is not None:
                    recipient_ids.add(booking.recipient_user_id)
                booking.status = GiftStatus.CANCELLED
                booking.cancelled_at = now
                booking.cancellation_reason = "not_verified"
                booking.wishlist_item_id = None
                booking.verify_token = None
                logger.info(f"Авто-cancel неподтверждённой брони: booking_id={booking.id}")

            if bookings:
                await db.commit()
                logger.info(f"Авто-отменено {len(bookings)} неподтверждённых бронирований")
                await _invalidate_profiles_by_recipient_ids(db, recipient_ids)
        except Exception as e:
            await db.rollback()
            logger.error(f"Ошибка в auto_cancel_unverified_bookings: {e}")


async def send_booking_reminders():
    """
    Отправка напоминаний дарителям за 7 дней до истечения брони.
    Запускается каждый день.
    """
    async with async_session_maker() as db:
        try:
            now = datetime.utcnow()
            reminder_threshold = now + timedelta(days=7)

            # Находим брони, которые истекают в ближайшие 7 дней
            # и напоминание ещё не отправлено
            result = await db.execute(
                select(GiftBooking).where(
                    and_(
                        GiftBooking.status == GiftStatus.BOOKED,
                        GiftBooking.expires_at != None,
                        GiftBooking.expires_at <= reminder_threshold,
                        GiftBooking.expires_at > now,
                        GiftBooking.reminder_sent_at == None,
                    )
                )
            )
            bookings = result.scalars().all()

            for booking in bookings:
                try:
                    from app.services.notifications import send_booking_reminder_email
                    await send_booking_reminder_email(booking)
                    booking.reminder_sent_at = now
                    logger.info(f"Напоминание отправлено: booking_id={booking.id}")
                except Exception as e:
                    logger.error(f"Ошибка отправки напоминания booking_id={booking.id}: {e}")

            await db.commit()
            logger.info(f"Обработано {len(bookings)} напоминаний")
        except Exception as e:
            await db.rollback()
            logger.error(f"Ошибка в send_booking_reminders: {e}")


async def auto_release_expired_bookings():
    """
    Автоматическое освобождение истёкших броней.
    BOOKED + expires_at < now() → CANCELLED, cancellation_reason='expired',
    wishlist_item_id обнуляется (бронь больше не блокирует пластинку).
    Дарителю уходит письмо «срок брони истёк».
    Запускается каждый час.
    """
    from sqlalchemy.orm import selectinload
    from app.models.wishlist import WishlistItem, Wishlist

    async with async_session_maker() as db:
        try:
            now = datetime.utcnow()

            result = await db.execute(
                select(GiftBooking)
                .where(
                    and_(
                        GiftBooking.status == GiftStatus.BOOKED,
                        GiftBooking.expires_at != None,
                        GiftBooking.expires_at <= now,
                    )
                )
                .options(
                    selectinload(GiftBooking.wishlist_item).selectinload(WishlistItem.record),
                    selectinload(GiftBooking.wishlist_item)
                    .selectinload(WishlistItem.wishlist)
                    .selectinload(Wishlist.user),
                )
            )
            bookings = result.scalars().all()

            email_payloads = []
            recipient_ids = set()
            for booking in bookings:
                if booking.recipient_user_id is not None:
                    recipient_ids.add(booking.recipient_user_id)
                if booking.gifter_email and booking.wishlist_item is not None:
                    item = booking.wishlist_item
                    record_title = item.record.title if item.record else None
                    owner = item.wishlist.user if item.wishlist else None
                    if record_title and owner:
                        email_payloads.append({
                            "gifter_email": booking.gifter_email,
                            "gifter_name": booking.gifter_name,
                            "record_title": record_title,
                            "owner_name": owner.display_name or owner.username,
                        })

                booking.status = GiftStatus.CANCELLED
                booking.cancelled_at = now
                booking.cancellation_reason = "expired"
                booking.wishlist_item_id = None
                logger.info(f"Авто-release брони: booking_id={booking.id}")

            await db.commit()
            logger.info(f"Авто-освобождено {len(bookings)} бронирований")
            await _invalidate_profiles_by_recipient_ids(db, recipient_ids)

            if email_payloads:
                from app.services.notifications import send_booking_auto_released_to_gifter
                for payload in email_payloads:
                    try:
                        await send_booking_auto_released_to_gifter(**payload)
                    except Exception as exc:
                        logger.warning(f"Не удалось отправить письмо об auto-release: {exc}")
        except Exception as e:
            await db.rollback()
            logger.error(f"Ошибка в auto_release_expired_bookings: {e}")
