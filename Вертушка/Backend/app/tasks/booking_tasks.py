"""
Фоновые задачи для управления бронированиями подарков
"""
import logging
from datetime import datetime, timedelta

from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import async_session_maker
from app.models.gift_booking import GiftBooking, GiftStatus

logger = logging.getLogger(__name__)


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


async def auto_extend_expired_bookings():
    """
    Автопродление истёкших броней на 30 дней (если не отменены).
    Запускается каждый час.
    """
    async with async_session_maker() as db:
        try:
            now = datetime.utcnow()

            result = await db.execute(
                select(GiftBooking).where(
                    and_(
                        GiftBooking.status == GiftStatus.BOOKED,
                        GiftBooking.expires_at != None,
                        GiftBooking.expires_at <= now,
                    )
                )
            )
            bookings = result.scalars().all()

            for booking in bookings:
                booking.expires_at = now + timedelta(days=30)
                booking.reminder_sent_at = None  # Сбрасываем для нового напоминания
                logger.info(f"Автопродление: booking_id={booking.id}, new_expires={booking.expires_at}")

            await db.commit()
            logger.info(f"Автопродлено {len(bookings)} бронирований")
        except Exception as e:
            await db.rollback()
            logger.error(f"Ошибка в auto_extend_expired_bookings: {e}")
