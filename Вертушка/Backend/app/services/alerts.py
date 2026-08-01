"""
Алармы в Telegram — узнать о падении раньше, чем напишут пользователи.

Пустой TELEGRAM_BOT_TOKEN → graceful no-op (как spotify_*): локальная
разработка не должна спамить боевой чат.

Троттлинг обязателен: 500-я на горячем эндпоинте — это не одна ошибка, а
сотня в минуту. Без него бот словит flood-limit и замолчит именно тогда,
когда нужен. Ключ троттла — тип аларма, а не текст, чтобы шторм одинаковых
ошибок схлопнулся в одно сообщение.

См. docs/plans/APPSTORE_LAUNCH_PLAN.md §4.2.
"""
from __future__ import annotations

import asyncio
import html
import logging
import time

import httpx

from app.config import get_settings

logger = logging.getLogger(__name__)

_TELEGRAM_API = "https://api.telegram.org/bot{token}/sendMessage"
_SEND_TIMEOUT_SECONDS = 5.0

# key → monotonic-время последней отправки
_last_sent: dict[str, float] = {}
# Сколько алармов проглотил троттл с момента последней отправки, по ключу.
_suppressed: dict[str, int] = {}


def _enabled() -> bool:
    s = get_settings()
    return bool(s.telegram_bot_token and s.telegram_alert_chat_id)


def _should_send(key: str) -> tuple[bool, int]:
    """Пропускать ли аларм. Возвращает (отправлять, сколько подавлено до него)."""
    throttle = get_settings().telegram_alert_throttle_seconds
    now = time.monotonic()
    last = _last_sent.get(key)

    if last is not None and now - last < throttle:
        _suppressed[key] = _suppressed.get(key, 0) + 1
        return False, 0

    _last_sent[key] = now
    return True, _suppressed.pop(key, 0)


async def send_alert(key: str, title: str, body: str = "") -> None:
    """Отправить аларм. Никогда не бросает исключение наружу.

    key — идентификатор класса проблемы («http_500:/api/records»), по нему
    работает троттлинг. title/body — что показать человеку.
    """
    if not _enabled():
        return

    allowed, suppressed = _should_send(key)
    if not allowed:
        return

    settings = get_settings()
    text = f"🔴 <b>{html.escape(title)}</b>"
    if body:
        text += f"\n\n<pre>{html.escape(body[:1500])}</pre>"
    if suppressed:
        text += f"\n\n<i>+{suppressed} таких же за окно троттлинга</i>"

    try:
        async with httpx.AsyncClient(timeout=_SEND_TIMEOUT_SECONDS) as client:
            response = await client.post(
                _TELEGRAM_API.format(token=settings.telegram_bot_token),
                json={
                    "chat_id": settings.telegram_alert_chat_id,
                    "text": text,
                    "parse_mode": "HTML",
                    "disable_web_page_preview": True,
                },
            )
            if response.status_code != 200:
                logger.warning(
                    "Telegram alert не доставлен: %s %s",
                    response.status_code,
                    response.text[:200],
                )
    except Exception:
        # Аларм-канал не имеет права ронять запрос, который его вызвал.
        logger.warning("Ошибка отправки Telegram alert", exc_info=True)


def fire_and_forget(key: str, title: str, body: str = "") -> None:
    """Отправить аларм, не дожидаясь результата.

    Для вызова из обработчиков запросов: пользователь не должен ждать,
    пока мы сходим в Telegram.
    """
    if not _enabled():
        return
    try:
        task = asyncio.create_task(send_alert(key, title, body))
        # Держим ссылку, иначе GC может забрать таску до завершения.
        _background_tasks.add(task)
        task.add_done_callback(_background_tasks.discard)
    except RuntimeError:
        # Нет активного event loop — значит вызвали не из async-контекста.
        logger.warning("fire_and_forget вне event loop, аларм пропущен: %s", key)


_background_tasks: set[asyncio.Task] = set()
