"""
Сервис уведомлений (email + push)
"""
import logging
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

from app.config import get_settings
from app.models.gift_booking import GiftBooking

logger = logging.getLogger(__name__)


async def _send_email(to: str, subject: str, html_body: str):
    """Отправка email через SMTP"""
    settings = get_settings()

    if not settings.smtp_user or not settings.smtp_password:
        logger.warning(f"SMTP не настроен, пропускаем отправку email: {subject} -> {to}")
        return

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = f"Вертушка <{settings.email_from}>"
    msg["To"] = to
    msg.attach(MIMEText(html_body, "html"))

    try:
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port) as server:
            server.starttls()
            server.login(settings.smtp_user, settings.smtp_password)
            server.sendmail(settings.email_from, to, msg.as_string())
        logger.info(f"Email отправлен: {subject} -> {to}")
    except Exception as e:
        logger.error(f"Ошибка отправки email: {e}")


async def send_booking_notification_to_owner(booking: GiftBooking, owner_email: str, record_title: str):
    """
    Уведомление владельцу вишлиста о новом бронировании.
    Без имени дарителя — анонимно!
    """
    subject = "Кто-то хочет подарить вам пластинку!"
    html_body = f"""
    <div style="font-family: Arial, sans-serif; max-width: 500px; margin: 0 auto;">
        <h2 style="color: #1A1A1A;">Кто-то забронировал подарок</h2>
        <p>Пластинка <strong>{record_title}</strong> из вашего вишлиста была забронирована.</p>
        <p style="color: #6B6B6B;">Кто именно — сюрприз! Вы узнаете, когда получите подарок.</p>
        <hr style="border: none; border-top: 1px solid #E5E5E5; margin: 20px 0;">
        <p style="color: #9B9B9B; font-size: 12px;">Вертушка — ваша коллекция винила</p>
    </div>
    """
    await _send_email(owner_email, subject, html_body)


async def send_gift_received_to_gifter(gifter_email: str, gifter_name: str, record_title: str, owner_name: str):
    """
    Email дарителю: подарок был получен!
    """
    subject = "Ваш подарок был получен!"
    html_body = f"""
    <div style="font-family: Arial, sans-serif; max-width: 500px; margin: 0 auto;">
        <h2 style="color: #1A1A1A;">Подарок получен!</h2>
        <p>Привет, {gifter_name}!</p>
        <p><strong>{owner_name}</strong> добавил(а) пластинку <strong>{record_title}</strong> в свою коллекцию.</p>
        <p>Ваш подарок оценён по достоинству!</p>
        <hr style="border: none; border-top: 1px solid #E5E5E5; margin: 20px 0;">
        <p style="color: #9B9B9B; font-size: 12px;">Вертушка — ваша коллекция винила</p>
    </div>
    """
    await _send_email(gifter_email, subject, html_body)


async def send_booking_reminder_email(booking: GiftBooking):
    """
    Напоминание дарителю: бронирование истекает через 7 дней.
    """
    settings = get_settings()
    cancel_url = f"{settings.app_url}/api/gifts/{booking.id}/cancel?cancel_token={booking.cancel_token}"

    subject = "Напоминание: ваше бронирование подарка скоро истекает"
    html_body = f"""
    <div style="font-family: Arial, sans-serif; max-width: 500px; margin: 0 auto;">
        <h2 style="color: #1A1A1A;">Напоминание о бронировании</h2>
        <p>Привет, {booking.gifter_name}!</p>
        <p>Ваше бронирование подарка истекает через 7 дней.</p>
        <p>Если вы уже подарили пластинку — отлично, ничего делать не нужно, бронь продлится автоматически.</p>
        <p>Если планы изменились, вы можете <a href="{cancel_url}">отменить бронирование</a>.</p>
        <hr style="border: none; border-top: 1px solid #E5E5E5; margin: 20px 0;">
        <p style="color: #9B9B9B; font-size: 12px;">Вертушка — ваша коллекция винила</p>
    </div>
    """
    await _send_email(booking.gifter_email, subject, html_body)
