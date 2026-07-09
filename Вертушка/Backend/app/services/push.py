"""
Отправка push-уведомлений через Expo Push API.

Поддерживает:
- Single push (send_push) — для триггеров уровня одного пользователя.
- Batch send (send_pushes_batch) — для рассылки на много токенов (Expo требует
  чанки по ≤100 messages на запрос, см. https://docs.expo.dev/push-notifications/sending-notifications/).
- Retry с экспоненциальным backoff на 5xx / network errors.
- Frequency caps через Redis (cache.set_with_ttl) — 1 push на тип/час/юзера.
- Quiet hours / Do Not Disturb.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any
from uuid import UUID

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.services.cache import cache

logger = logging.getLogger(__name__)

EXPO_PUSH_URL = "https://exp.host/--/api/v2/push/send"
EXPO_CHUNK_SIZE = 100
PUSH_RETRY_DELAYS = (1.0, 2.0, 4.0)
FREQ_CAP_TTL_SECONDS = 60 * 60  # 1 час

# Маппинг типа Notification → имя флага User.notify_*
PUSH_PREFERENCE_FIELD = {
    "follow_request": "notify_follow_request",
    "new_follower": "notify_new_follower",
    "gift_booked": "notify_gift_booked",
    "gift_confirmed": "notify_gift_confirmed",
    "wishlist_in_stock": "notify_wishlist_in_stock",
    "wishlist_price_drop": "notify_wishlist_in_stock",
    "digest_wishlist_in_stock": "notify_wishlist_in_stock",
    "achievement_unlocked": "notify_achievement",
    "milestone_unlocked": "notify_milestone",
}


def _is_quiet_hours_now(user) -> bool:
    """Текущее время попадает в Quiet Hours юзера (UTC сравнение)."""
    if not user.quiet_hours_enabled or not user.quiet_hours_start or not user.quiet_hours_end:
        return False
    from datetime import datetime
    now = datetime.utcnow().time()
    start = user.quiet_hours_start
    end = user.quiet_hours_end
    if start == end:
        return False
    if start < end:
        return start <= now < end
    # Окно через полночь (например 22:00..08:00)
    return now >= start or now < end


def absolute_media_url(path: str | None) -> str | None:
    """Относительный `/uploads/...` → абсолютный https для push-картинок.

    Expo/APNs требует полный https-URL. Уже-абсолютные (http) отдаём как есть.
    """
    if not path:
        return None
    if path.startswith("http"):
        return path
    from app.config import get_settings
    base = get_settings().public_api_base
    return f"{base}{path if path.startswith('/') else '/' + path}"


def _looks_like_expo_token(token: str | None) -> bool:
    if not token:
        return False
    return token.startswith("ExponentPushToken[") or token.startswith("ExpoPushToken[")


async def send_push(
    db: AsyncSession,
    user_id: UUID,
    *,
    notification_type: str,
    title: str,
    body: str,
    data: dict[str, Any] | None = None,
    image: str | None = None,
    bypass_cap: bool = False,
    cap_key: str | None = None,
) -> bool:
    """Отправить push конкретному пользователю с учётом его настроек.

    `image` — абсолютный https-URL картинки (аватар отправителя): iOS показывает
    её в раскрытом уведомлении через richContent + mutableContent.
    `bypass_cap` — пропустить часовой freq-cap (для чатов, где 1/час недопустим).
    `cap_key` — переопределить ключ cap-слота (по умолчанию = notification_type),
    чтобы дедупить по диалогу, а не по типу.
    """
    user = await db.scalar(select(User).where(User.id == user_id))
    if not user or not user.is_active or user.deleted_at is not None:
        return False

    pref_field = PUSH_PREFERENCE_FIELD.get(notification_type)
    if pref_field and not getattr(user, pref_field, True):
        return False

    if _is_quiet_hours_now(user):
        logger.debug("Skipping push for user %s — quiet hours", user_id)
        return False

    token = user.push_token
    if not _looks_like_expo_token(token):
        return False

    # Frequency cap: не больше одного push того же типа в час на юзера.
    # Чаты минуют часовой cap (bypass_cap) — иначе теряются сообщения.
    if not bypass_cap and not await _try_acquire_cap(user_id, cap_key or notification_type):
        logger.debug("Skipping push for user %s — frequency cap (%s)", user_id, notification_type)
        return False

    message = {
        "to": token,
        "title": title,
        "body": body,
        "sound": "default",
        "priority": "high",
        "data": data or {},
    }
    if image:
        # Expo → iOS rich notification. mutableContent обязателен, чтобы
        # notification service extension подтянул картинку.
        message["richContent"] = {"image": image}
        message["mutableContent"] = True

    results = await _post_with_retry([message])
    if not results:
        return False
    ticket = results[0]
    if isinstance(ticket, dict) and ticket.get("status") == "error":
        details = ticket.get("details") or {}
        error_code = details.get("error")
        if error_code in ("DeviceNotRegistered", "InvalidCredentials"):
            logger.info("Push token invalid (%s) for user %s — clearing", error_code, user_id)
            user.push_token = None
            await db.commit()
        else:
            logger.warning("Expo push ticket error: %s", ticket)
        return False

    return True


async def send_pushes_batch(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    Отправить много push-сообщений в одно запрос Expo (чанками по 100, параллельно).

    Каждый message — готовый dict {to, title, body, data, ...}.
    Подразумевается, что вызывающий код уже отфильтровал по preferences/quiet hours/freq caps.
    Возвращает плоский список tickets от Expo (в том же порядке что messages).
    """
    if not messages:
        return []
    chunks = [messages[i:i + EXPO_CHUNK_SIZE] for i in range(0, len(messages), EXPO_CHUNK_SIZE)]
    chunk_results = await asyncio.gather(*(_post_with_retry(c) for c in chunks))
    flat: list[dict[str, Any]] = []
    for r in chunk_results:
        flat.extend(r)
    return flat


async def _post_with_retry(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """POST на Expo с retry на 5xx и network errors. Возвращает массив tickets."""
    payload: Any = messages[0] if len(messages) == 1 else messages

    last_exc: Exception | None = None
    for attempt, delay in enumerate([0.0, *PUSH_RETRY_DELAYS]):
        if delay > 0:
            await asyncio.sleep(delay)
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                r = await client.post(
                    EXPO_PUSH_URL,
                    json=payload,
                    headers={
                        "Accept": "application/json",
                        "Accept-Encoding": "gzip, deflate",
                        "Content-Type": "application/json",
                    },
                )
            if r.status_code >= 500:
                logger.warning("Expo 5xx (attempt %d): %s", attempt + 1, r.status_code)
                continue  # retry
            if r.status_code >= 400:
                logger.warning("Expo HTTP %s (no retry): %s", r.status_code, r.text[:200])
                return []
            body = r.json() or {}
            data = body.get("data")
            if isinstance(data, list):
                return data
            if isinstance(data, dict):
                return [data]
            return []
        except (httpx.TransportError, httpx.TimeoutException) as exc:
            last_exc = exc
            logger.warning("Expo transport error (attempt %d): %s", attempt + 1, exc)
            continue
        except Exception as exc:
            logger.warning("Expo unexpected error (no retry): %s", exc)
            return []

    if last_exc:
        logger.error("Expo push exhausted retries: %s", last_exc)
    return []


async def _try_acquire_cap(user_id: UUID, notification_type: str) -> bool:
    """
    Атомарно проверить + захватить frequency-cap слот для (user, type).
    Возвращает True, если push можно отправить (cap-слот свободен и теперь занят на час),
    False — если уже был push этого типа недавно.
    """
    if not cache.available:
        return True  # Без Redis — без freq caps. Лучше прислать, чем не прислать.
    try:
        acquired = await cache.set_nx(
            "push_cap",
            f"{user_id}:{notification_type}",
            "1",
            ttl=FREQ_CAP_TTL_SECONDS,
        )
        return bool(acquired)
    except Exception:
        return True
