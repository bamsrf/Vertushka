"""
Сервис отправки email через SMTP (Yandex)
"""
import logging
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

import aiosmtplib

from app.config import get_settings

logger = logging.getLogger(__name__)


async def send_reset_code_email(to_email: str, code: str) -> bool:
    """Отправка кода сброса пароля на email."""
    settings = get_settings()

    if not settings.smtp_user or not settings.smtp_password:
        logger.error("SMTP credentials not configured")
        return False

    subject = "Вертушка — код для сброса пароля"

    html_body = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
    </head>
    <body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background-color: #FAFBFF; margin: 0; padding: 40px 20px;">
        <div style="max-width: 420px; margin: 0 auto; background: white; border-radius: 16px; padding: 40px 32px; box-shadow: 0 2px 12px rgba(59, 75, 245, 0.08);">
            <div style="text-align: center; margin-bottom: 32px;">
                <div style="width: 64px; height: 64px; background: linear-gradient(135deg, #3B4BF5, #8B9CF7); border-radius: 50%; margin: 0 auto 16px; display: flex; align-items: center; justify-content: center;">
                    <span style="font-size: 28px; line-height: 64px;">💿</span>
                </div>
                <h1 style="color: #0A0B3B; font-size: 24px; margin: 0;">Вертушка</h1>
            </div>

            <p style="color: #5A5F8A; font-size: 16px; line-height: 24px; margin-bottom: 24px;">
                Вы запросили сброс пароля. Введите этот код в приложении:
            </p>

            <div style="background: #F0F2FA; border-radius: 12px; padding: 20px; text-align: center; margin-bottom: 24px;">
                <span style="font-size: 36px; font-weight: 800; letter-spacing: 8px; color: #3B4BF5;">{code}</span>
            </div>

            <p style="color: #9A9EBF; font-size: 14px; line-height: 20px; margin-bottom: 0;">
                Код действителен 15 минут. Если вы не запрашивали сброс пароля, проигнорируйте это письмо.
            </p>
        </div>
    </body>
    </html>
    """

    msg = MIMEMultipart("alternative")
    msg["From"] = settings.email_from or settings.smtp_user
    msg["To"] = to_email
    msg["Subject"] = subject
    msg.attach(MIMEText(f"Ваш код для сброса пароля: {code}\n\nКод действителен 15 минут.", "plain", "utf-8"))
    msg.attach(MIMEText(html_body, "html", "utf-8"))

    try:
        await aiosmtplib.send(
            msg,
            hostname=settings.smtp_host,
            port=settings.smtp_port,
            username=settings.smtp_user,
            password=settings.smtp_password,
            use_tls=True,
        )
        logger.info("Reset code email sent to %s", to_email)
        return True
    except Exception as e:
        logger.error("Failed to send email to %s: %s", to_email, e)
        return False
