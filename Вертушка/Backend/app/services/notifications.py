"""
Сервис уведомлений (email + push)
"""
import logging
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

import httpx

from app.config import get_settings
from app.models.gift_booking import GiftBooking

logger = logging.getLogger(__name__)

RESEND_API_URL = "https://api.resend.com/emails"


async def _send_via_resend(to: str, subject: str, html_body: str) -> bool:
    """Отправка через Resend HTTP API. Возвращает True при успехе, False иначе."""
    settings = get_settings()
    payload = {
        "from": f"Вертушка <{settings.email_from}>",
        "to": [to],
        "subject": subject,
        "html": html_body,
    }
    headers = {
        "Authorization": f"Bearer {settings.resend_api_key}",
        "Content-Type": "application/json",
    }
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.post(RESEND_API_URL, json=payload, headers=headers)
        if r.status_code in (200, 201, 202):
            logger.info(f"Email отправлен через Resend: {subject} -> {to} (id={r.json().get('id')})")
            return True
        logger.error(f"Resend вернул {r.status_code}: {r.text} | {subject} -> {to}")
        return False
    except Exception as e:
        logger.error(f"Ошибка Resend API: {e}")
        return False


def _send_via_smtp(to: str, subject: str, html_body: str) -> bool:
    """Fallback на SMTP. Возвращает True при успехе, False иначе."""
    settings = get_settings()
    if not settings.smtp_user or not settings.smtp_password:
        return False

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = f"Вертушка <{settings.email_from}>"
    msg["To"] = to
    msg.attach(MIMEText(html_body, "html"))

    try:
        if settings.smtp_port == 465:
            with smtplib.SMTP_SSL(settings.smtp_host, settings.smtp_port) as server:
                server.login(settings.smtp_user, settings.smtp_password)
                server.sendmail(settings.email_from, to, msg.as_string())
        else:
            with smtplib.SMTP(settings.smtp_host, settings.smtp_port) as server:
                server.starttls()
                server.login(settings.smtp_user, settings.smtp_password)
                server.sendmail(settings.email_from, to, msg.as_string())
        logger.info(f"Email отправлен через SMTP: {subject} -> {to}")
        return True
    except Exception as e:
        logger.error(f"Ошибка отправки SMTP: {e}")
        return False


async def _send_email(to: str, subject: str, html_body: str):
    """Отправка email. Resend приоритетный, SMTP — fallback для dev/локалки."""
    settings = get_settings()
    if not settings.email_from:
        logger.warning(f"EMAIL_FROM не задан, пропускаем отправку: {subject} -> {to}")
        return

    if settings.resend_api_key:
        if await _send_via_resend(to, subject, html_body):
            return
        # Fall through на SMTP если Resend не сработал и есть SMTP-конфиг
        logger.warning("Resend не сработал — пробую SMTP fallback")

    if not _send_via_smtp(to, subject, html_body):
        logger.warning(f"Email не отправлен (нет рабочего канала): {subject} -> {to}")


async def send_booking_notification_to_owner(
    booking: GiftBooking,
    owner_email: str,
    record_title: str,
    gifter_name: str | None = None,
):
    """
    Уведомление владельцу вишлиста о новом бронировании.
    По умолчанию — анонимно. Если передано gifter_name (владелец явно
    включил reveal_gifter_to_owner на вишлисте), упоминаем дарителя.
    """
    if gifter_name:
        subject = f"{gifter_name} дарит тебе пластинку"
        anon_line = f"<p>Подарок забронировал(а) <strong>{gifter_name}</strong>.</p>"
    else:
        subject = "Кто-то хочет подарить тебе пластинку"
        anon_line = '<p style="color: #6B6B6B;">Кто именно — сюрприз! Вы узнаете, когда получите подарок.</p>'

    html_body = f"""
    <div style="font-family: Arial, sans-serif; max-width: 500px; margin: 0 auto;">
        <h2 style="color: #1A1A1A;">Кто-то забронировал подарок</h2>
        <p>Пластинка <strong>{record_title}</strong> из твоего вишлиста забронирована.</p>
        {anon_line}
        <hr style="border: none; border-top: 1px solid #E5E5E5; margin: 20px 0;">
        <p style="color: #9B9B9B; font-size: 12px;">Вертушка — твоя коллекция винила</p>
    </div>
    """
    await _send_email(owner_email, subject, html_body)


async def send_booking_confirmation_to_gifter(
    gifter_email: str,
    gifter_name: str,
    record_title: str,
    record_artist: str,
    cancel_url: str,
):
    """Подтверждение бронирования дарителю + ссылка для отмены."""
    subject = "Бронь подтверждена — Вертушка 🎵"
    html_body = f"""
    <div style="font-family:'Helvetica Neue',Arial,sans-serif;max-width:520px;margin:0 auto;background:#F4EEE6;border-radius:16px;overflow:hidden;">
      <div style="background:#1B1D26;padding:28px 32px;">
        <span style="color:#ffffff;font-size:18px;font-weight:700;letter-spacing:-0.3px;">Вертушка</span>
      </div>
      <div style="padding:32px;">
        <h2 style="margin:0 0 8px;color:#1B1D26;font-size:22px;font-weight:700;">Подарок забронирован!</h2>
        <p style="margin:0 0 24px;color:#6B7080;font-size:15px;">Привет, {gifter_name}!</p>
        <div style="background:#ffffff;border-radius:12px;padding:20px 24px;margin-bottom:24px;border:1px solid rgba(27,29,38,0.08);">
          <div style="font-size:12px;color:#6B7080;text-transform:uppercase;letter-spacing:0.8px;margin-bottom:4px;">{record_artist}</div>
          <div style="font-size:17px;color:#1B1D26;font-weight:600;">{record_title}</div>
        </div>
        <p style="color:#6B7080;font-size:14px;line-height:1.6;margin-bottom:28px;">
          Бронь действует <strong style="color:#1B1D26;">60 дней</strong>. Владелец увидит только метку «Забронировано» — анонимно. За 7 дней до истечения мы пришлём напоминание.
        </p>
        <a href="{cancel_url}" style="display:inline-block;color:#6B7080;font-size:13px;text-decoration:underline;">Хочу отменить бронь</a>
      </div>
      <div style="padding:16px 32px 24px;border-top:1px solid rgba(27,29,38,0.08);">
        <p style="margin:0;color:#9096A6;font-size:12px;">Вертушка — твоя коллекция винила</p>
      </div>
    </div>
    """
    await _send_email(gifter_email, subject, html_body)


async def send_gift_received_to_gifter(gifter_email: str, gifter_name: str, record_title: str, owner_name: str):
    """
    Email дарителю: подарок был получен!
    """
    subject = "Твой подарок получен"
    html_body = f"""
    <div style="font-family: Arial, sans-serif; max-width: 500px; margin: 0 auto;">
        <h2 style="color: #1A1A1A;">Подарок получен!</h2>
        <p>Привет, {gifter_name}!</p>
        <p><strong>{owner_name}</strong> добавил(а) пластинку <strong>{record_title}</strong> в свою коллекцию.</p>
        <p>Подарок оценён по достоинству.</p>
        <hr style="border: none; border-top: 1px solid #E5E5E5; margin: 20px 0;">
        <p style="color: #9B9B9B; font-size: 12px;">Вертушка — твоя коллекция винила</p>
    </div>
    """
    await _send_email(gifter_email, subject, html_body)


async def send_booking_verification_to_gifter(
    gifter_email: str,
    gifter_name: str,
    record_title: str,
    record_artist: str,
    confirm_url: str,
    window_hours: int = 24,
):
    """
    Письмо дарителю с просьбой подтвердить email и активировать бронь.
    Используется только при gift_booking_require_email_verification=True.
    """
    subject = "Подтвердите бронь — Вертушка 🎵"
    html_body = f"""
    <div style="font-family:'Helvetica Neue',Arial,sans-serif;max-width:520px;margin:0 auto;background:#F4EEE6;border-radius:16px;overflow:hidden;">
      <div style="background:#1B1D26;padding:28px 32px;">
        <span style="color:#ffffff;font-size:18px;font-weight:700;letter-spacing:-0.3px;">Вертушка</span>
      </div>
      <div style="padding:32px;">
        <h2 style="margin:0 0 8px;color:#1B1D26;font-size:22px;font-weight:700;">Подтверди бронь</h2>
        <p style="margin:0 0 24px;color:#6B7080;font-size:15px;">Привет, {gifter_name}!</p>
        <div style="background:#ffffff;border-radius:12px;padding:20px 24px;margin-bottom:24px;border:1px solid rgba(27,29,38,0.08);">
          <div style="font-size:12px;color:#6B7080;text-transform:uppercase;letter-spacing:0.8px;margin-bottom:4px;">{record_artist}</div>
          <div style="font-size:17px;color:#1B1D26;font-weight:600;">{record_title}</div>
        </div>
        <p style="color:#6B7080;font-size:14px;line-height:1.6;margin-bottom:24px;">
          Чтобы бронь стала активной, подтверди email — это шаг защиты от чужих бронирований по твоему адресу. После подтверждения у тебя будет <strong style="color:#1B1D26;">60 дней</strong> на покупку.
        </p>
        <a href="{confirm_url}" style="display:inline-block;background:#3A4BE0;color:#ffffff;text-decoration:none;padding:14px 28px;border-radius:10px;font-weight:600;font-size:15px;">Подтвердить бронь</a>
        <p style="color:#9096A6;font-size:12px;line-height:1.6;margin-top:24px;margin-bottom:0;">
          Если не подтвердишь за {window_hours}ч — бронь автоматически отменится, и пластинка снова станет доступна другим. Если ты не бронировал — просто проигнорируй письмо.
        </p>
      </div>
      <div style="padding:16px 32px 24px;border-top:1px solid rgba(27,29,38,0.08);">
        <p style="margin:0;color:#9096A6;font-size:12px;">Вертушка — твоя коллекция винила</p>
      </div>
    </div>
    """
    await _send_email(gifter_email, subject, html_body)


async def send_booking_cancelled_to_owner(owner_email: str, record_title: str):
    """
    Письмо владельцу при отмене брони дарителем по cancel-ссылке.
    Без раскрытия личности — просто «пункт снова свободен».
    """
    subject = "Бронь подарка снята"
    html_body = f"""
    <div style="font-family:'Helvetica Neue',Arial,sans-serif;max-width:520px;margin:0 auto;background:#F4EEE6;border-radius:16px;overflow:hidden;">
      <div style="background:#1B1D26;padding:28px 32px;">
        <span style="color:#ffffff;font-size:18px;font-weight:700;letter-spacing:-0.3px;">Вертушка</span>
      </div>
      <div style="padding:32px;">
        <h2 style="margin:0 0 8px;color:#1B1D26;font-size:22px;font-weight:700;">Бронь снята</h2>
        <p style="color:#6B7080;font-size:15px;line-height:1.6;margin:0 0 16px;">
          Пластинка <strong style="color:#1B1D26;">{record_title}</strong> снова доступна другим дарителям из твоего вишлиста.
        </p>
        <p style="color:#9096A6;font-size:13px;line-height:1.6;margin:0;">
          Имя того, кто бронировал, мы не раскрываем — это сюрприз останется сюрпризом.
        </p>
      </div>
      <div style="padding:16px 32px 24px;border-top:1px solid rgba(27,29,38,0.08);">
        <p style="margin:0;color:#9096A6;font-size:12px;">Вертушка — твоя коллекция винила</p>
      </div>
    </div>
    """
    await _send_email(owner_email, subject, html_body)


async def send_booking_auto_released_to_gifter(
    gifter_email: str,
    gifter_name: str,
    record_title: str,
    owner_name: str,
):
    """
    Письмо дарителю при auto-release брони (60-дневный срок истёк).
    Идёт после reminder-письма, которое было за 7 дней до этого.
    """
    subject = "Бронь подарка истекла"
    html_body = f"""
    <div style="font-family:'Helvetica Neue',Arial,sans-serif;max-width:520px;margin:0 auto;background:#F4EEE6;border-radius:16px;overflow:hidden;">
      <div style="background:#1B1D26;padding:28px 32px;">
        <span style="color:#ffffff;font-size:18px;font-weight:700;letter-spacing:-0.3px;">Вертушка</span>
      </div>
      <div style="padding:32px;">
        <h2 style="margin:0 0 8px;color:#1B1D26;font-size:22px;font-weight:700;">Срок брони истёк</h2>
        <p style="margin:0 0 24px;color:#6B7080;font-size:15px;">Привет, {gifter_name}!</p>
        <div style="background:#ffffff;border-radius:12px;padding:20px 24px;margin-bottom:24px;border:1px solid rgba(27,29,38,0.08);">
          <div style="font-size:17px;color:#1B1D26;font-weight:600;">{record_title}</div>
          <div style="font-size:13px;color:#6B7080;margin-top:6px;">для {owner_name}</div>
        </div>
        <p style="color:#6B7080;font-size:14px;line-height:1.6;margin-bottom:0;">
          Бронь висела 60 дней и автоматически снята. Пластинка снова доступна — если ещё хочешь подарить, можно забронировать заново.
        </p>
      </div>
      <div style="padding:16px 32px 24px;border-top:1px solid rgba(27,29,38,0.08);">
        <p style="margin:0;color:#9096A6;font-size:12px;">Вертушка — твоя коллекция винила</p>
      </div>
    </div>
    """
    await _send_email(gifter_email, subject, html_body)


async def send_wishlist_item_removed_to_gifter(
    gifter_email: str,
    gifter_name: str,
    record_title: str,
    owner_name: str,
):
    """
    Письмо дарителю, когда владелец удалил пункт вишлиста с активной бронью.
    """
    subject = "Подарок больше не нужен"
    html_body = f"""
    <div style="font-family:'Helvetica Neue',Arial,sans-serif;max-width:520px;margin:0 auto;background:#F4EEE6;border-radius:16px;overflow:hidden;">
      <div style="background:#1B1D26;padding:28px 32px;">
        <span style="color:#ffffff;font-size:18px;font-weight:700;letter-spacing:-0.3px;">Вертушка</span>
      </div>
      <div style="padding:32px;">
        <h2 style="margin:0 0 8px;color:#1B1D26;font-size:22px;font-weight:700;">Пункт убран из вишлиста</h2>
        <p style="margin:0 0 24px;color:#6B7080;font-size:15px;">Привет, {gifter_name}!</p>
        <div style="background:#ffffff;border-radius:12px;padding:20px 24px;margin-bottom:24px;border:1px solid rgba(27,29,38,0.08);">
          <div style="font-size:17px;color:#1B1D26;font-weight:600;">{record_title}</div>
          <div style="font-size:13px;color:#6B7080;margin-top:6px;">для {owner_name}</div>
        </div>
        <p style="color:#6B7080;font-size:14px;line-height:1.6;margin-bottom:0;">
          {owner_name} убрал(а) эту пластинку из вишлиста — возможно, уже нашёл(нашла) её сам(а). Бронь автоматически отменена, ничего покупать не нужно.
        </p>
      </div>
      <div style="padding:16px 32px 24px;border-top:1px solid rgba(27,29,38,0.08);">
        <p style="margin:0;color:#9096A6;font-size:12px;">Вертушка — твоя коллекция винила</p>
      </div>
    </div>
    """
    await _send_email(gifter_email, subject, html_body)


async def send_booking_rejected_to_gifter(
    gifter_email: str,
    gifter_name: str,
    record_title: str,
    owner_name: str,
):
    """
    Письмо дарителю, когда владелец вишлиста отклонил его бронь.
    Формулировка нейтральная: не «тебя забанили», а «бронь снята, пункт свободен».
    """
    subject = "Бронь подарка снята"
    html_body = f"""
    <div style="font-family:'Helvetica Neue',Arial,sans-serif;max-width:520px;margin:0 auto;background:#F4EEE6;border-radius:16px;overflow:hidden;">
      <div style="background:#1B1D26;padding:28px 32px;">
        <span style="color:#ffffff;font-size:18px;font-weight:700;letter-spacing:-0.3px;">Вертушка</span>
      </div>
      <div style="padding:32px;">
        <h2 style="margin:0 0 8px;color:#1B1D26;font-size:22px;font-weight:700;">Бронь снята</h2>
        <p style="margin:0 0 24px;color:#6B7080;font-size:15px;">Привет, {gifter_name}!</p>
        <div style="background:#ffffff;border-radius:12px;padding:20px 24px;margin-bottom:24px;border:1px solid rgba(27,29,38,0.08);">
          <div style="font-size:17px;color:#1B1D26;font-weight:600;">{record_title}</div>
          <div style="font-size:13px;color:#6B7080;margin-top:6px;">для {owner_name}</div>
        </div>
        <p style="color:#6B7080;font-size:14px;line-height:1.6;margin-bottom:0;">
          {owner_name} снял(а) эту бронь со своей стороны — покупать ничего не нужно.
          Если это недоразумение, свяжись с получателем напрямую.
        </p>
      </div>
      <div style="padding:16px 32px 24px;border-top:1px solid rgba(27,29,38,0.08);">
        <p style="margin:0;color:#9096A6;font-size:12px;">Вертушка — твоя коллекция винила</p>
      </div>
    </div>
    """
    await _send_email(gifter_email, subject, html_body)


async def send_booking_reminder_email(booking: GiftBooking):
    """
    Напоминание дарителю: бронирование истекает через 7 дней.
    """
    settings = get_settings()
    cancel_url = f"{settings.app_url}/api/gifts/{booking.id}/cancel?cancel_token={booking.cancel_token}"

    subject = "Бронь подарка истекает через неделю"
    html_body = f"""
    <div style="font-family: Arial, sans-serif; max-width: 500px; margin: 0 auto;">
        <h2 style="color: #1A1A1A;">Напоминание о бронировании</h2>
        <p>Привет, {booking.gifter_name}!</p>
        <p>Бронь подарка истекает через 7 дней.</p>
        <p>Если планы изменились — можно <a href="{cancel_url}">отменить бронирование</a>.</p>
        <p>Если ничего не делать, по истечении срока бронь будет автоматически освобождена, и пластинка снова станет доступна другим дарителям.</p>
        <hr style="border: none; border-top: 1px solid #E5E5E5; margin: 20px 0;">
        <p style="color: #9B9B9B; font-size: 12px;">Вертушка — твоя коллекция винила</p>
    </div>
    """
    await _send_email(booking.gifter_email, subject, html_body)
