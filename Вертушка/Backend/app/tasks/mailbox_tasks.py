"""
Почта support@ → Telegram.

Ящик живёт на Beget (imap.beget.com), своего mail-сервера у нас нет.
Джоб раз в N минут забирает непрочитанное, отправляет в чат алармов и
только ПОСЛЕ успешной отправки помечает письмо прочитанным.

Почему состояние — во флагах ящика, а не в Redis: прод-Redis поднят с
`--maxmemory-policy allkeys-lru` и без volume, то есть курсор оттуда может
исчезнуть и от вытеснения, и от рестарта. Ящик переживает и то, и другое.

Плата: письмо, прочитанное руками в веб-морде Beget раньше бота, в
Telegram не придёт.

См. docs/plans/quality/TELEGRAM_ALERTS_PLAN.md §3.
"""
from __future__ import annotations

import asyncio
import email
import imaplib
import logging
from email.header import decode_header, make_header
from email.message import Message

from app.config import get_settings
from app.services import alerts

logger = logging.getLogger(__name__)

_IMAP_TIMEOUT_SECONDS = 20
# Сколько текста письма тащить в сообщение. Полотно в Telegram всё равно
# схлопнется, а ответить по сути хватает первого экрана.
_BODY_LIMIT = 1500


def _decode(raw: str | None) -> str:
    """Раскодировать MIME-заголовок (=?utf-8?B?...?=) в читаемый текст."""
    if not raw:
        return ""
    try:
        return str(make_header(decode_header(raw)))
    except Exception:
        # Кривой заголовок не повод терять письмо целиком.
        return raw


def _plain_text(message: Message) -> str:
    """Достать текстовую часть письма, по возможности без HTML-разметки."""
    if not message.is_multipart():
        return _decode_payload(message)

    html_fallback = ""
    for part in message.walk():
        if part.get_content_maintype() == "multipart":
            continue
        if part.get_filename():
            continue
        content_type = part.get_content_type()
        if content_type == "text/plain":
            return _decode_payload(part)
        if content_type == "text/html" and not html_fallback:
            html_fallback = _decode_payload(part)

    return html_fallback


def _decode_payload(part: Message) -> str:
    try:
        payload = part.get_payload(decode=True)
    except Exception:
        return ""
    if not payload:
        return ""
    charset = part.get_content_charset() or "utf-8"
    try:
        return payload.decode(charset, errors="replace")
    except LookupError:
        return payload.decode("utf-8", errors="replace")


def _fetch_unseen() -> list[tuple[bytes, str, str, str]]:
    """Забрать непрочитанные письма. Синхронный imaplib — вызывать в потоке.

    Возвращает [(uid, from, subject, body)]. Флаги НЕ трогает: пометка
    прочитанным — отдельный шаг после успешной отправки в Telegram.
    """
    settings = get_settings()
    result: list[tuple[bytes, str, str, str]] = []

    connection = imaplib.IMAP4_SSL(
        settings.mailbox_imap_host,
        settings.mailbox_imap_port,
        timeout=_IMAP_TIMEOUT_SECONDS,
    )
    try:
        connection.login(settings.mailbox_imap_user, settings.mailbox_imap_password)
        connection.select("INBOX")

        status, data = connection.search(None, "UNSEEN")
        if status != "OK" or not data or not data[0]:
            return result

        for uid in data[0].split()[: settings.mailbox_max_per_poll]:
            # PEEK, иначе сам факт чтения проставит \Seen и письмо пропадёт
            # из выборки ещё до того, как уедет в Telegram.
            status, payload = connection.fetch(uid, "(BODY.PEEK[])")
            if status != "OK" or not payload or not isinstance(payload[0], tuple):
                continue

            message = email.message_from_bytes(payload[0][1])
            result.append(
                (
                    uid,
                    _decode(message.get("From")),
                    _decode(message.get("Subject")) or "(без темы)",
                    _plain_text(message).strip(),
                )
            )
    finally:
        try:
            connection.logout()
        except Exception:
            pass

    return result


def _mark_seen(uid: bytes) -> None:
    """Пометить письмо прочитанным — отдельным соединением, после отправки."""
    settings = get_settings()
    connection = imaplib.IMAP4_SSL(
        settings.mailbox_imap_host,
        settings.mailbox_imap_port,
        timeout=_IMAP_TIMEOUT_SECONDS,
    )
    try:
        connection.login(settings.mailbox_imap_user, settings.mailbox_imap_password)
        connection.select("INBOX")
        connection.store(uid, "+FLAGS", "\\Seen")
    finally:
        try:
            connection.logout()
        except Exception:
            pass


async def poll_support_mailbox() -> None:
    """Проверить ящик поддержки и переслать новое в Telegram.

    Порядок «сначала отправить, потом пометить» выбран сознательно: при
    падении между шагами письмо придёт дважды. Дубль лучше пропажи — это
    канал жалоб, а не биллинг.
    """
    settings = get_settings()
    if not settings.mailbox_imap_user or not settings.mailbox_imap_password:
        return

    try:
        messages = await asyncio.to_thread(_fetch_unseen)
    except Exception:
        logger.warning("Не удалось прочитать ящик поддержки", exc_info=True)
        # Сама недоступность IMAP — тоже новость, но с троттлингом: сеть
        # у Beget моргает, и каждые 2 минуты об этом писать незачем.
        await alerts.send_alert(
            key="mailbox:imap_unreachable",
            title="Ящик поддержки недоступен",
            body="IMAP не отвечает — письма могут копиться незамеченными.",
            emoji="⚠️",
        )
        return

    for uid, sender, subject, body in messages:
        await alerts.send_notice(
            title=f"Письмо: {subject}",
            body=f"От: {sender}\n\n{body[:_BODY_LIMIT]}",
        )
        try:
            await asyncio.to_thread(_mark_seen, uid)
        except Exception:
            # Не пометилось — придёт ещё раз на следующем проходе. Мириться
            # с дублем дешевле, чем чинить это ретраями здесь.
            logger.warning("Письмо отправлено, но не помечено прочитанным", exc_info=True)

    if messages:
        logger.info("Переслано писем в Telegram: %d", len(messages))
