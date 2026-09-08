"""
Внутренние ручки для внешних систем мониторинга.

Сейчас здесь один потребитель — GlitchTip, который шлёт webhook на каждый
новый крэш. Он не умеет кастомные заголовки, поэтому привычный
X-Internal-Token не подходит и секрет уезжает в path.

См. docs/plans/quality/TELEGRAM_ALERTS_PLAN.md §1.
"""
from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Request

from app.config import get_settings
from app.services import alerts

logger = logging.getLogger(__name__)

router = APIRouter()

# Сколько символов тела крэша тащить в сообщение. Дальше — по ссылке в
# GlitchTip: стектрейс в Telegram всё равно нечитаем.
_BODY_LIMIT = 600


def _extract(payload: dict[str, Any]) -> tuple[str, str]:
    """Вытащить (заголовок, тело) из Slack-совместимого payload GlitchTip.

    Формат недокументирован и менялся между версиями, поэтому парсер
    терпимый: чего нет — того нет, но сообщение уйдёт в любом случае.
    Молчащий аларм хуже кривого.
    """
    attachments = payload.get("attachments")
    if not isinstance(attachments, list) or not attachments:
        text = payload.get("text") or "Событие без описания"
        return str(text)[:200], ""

    first = attachments[0] if isinstance(attachments[0], dict) else {}
    title = str(first.get("title") or payload.get("text") or "Крэш")[:200]

    parts: list[str] = []
    body = first.get("text")
    if body:
        parts.append(str(body))

    fields = first.get("fields")
    if isinstance(fields, list):
        for field in fields:
            if isinstance(field, dict) and field.get("title") and field.get("value"):
                parts.append(f"{field['title']}: {field['value']}")

    link = first.get("title_link")
    if link:
        parts.append(str(link))

    return title, "\n".join(parts)


@router.post("/glitchtip/{secret}", include_in_schema=False)
async def glitchtip_webhook(secret: str, request: Request) -> dict:
    """Принять крэш из GlitchTip и переложить в Telegram-канал алармов.

    Всегда отвечает 200 при верном секрете — даже на мусорный payload.
    GlitchTip на ошибку ретраит, а после серии ошибок отключает webhook,
    и канал умирает молча.
    """
    settings = get_settings()
    if not settings.glitchtip_webhook_secret or secret != settings.glitchtip_webhook_secret:
        # 404, а не 403: чужому сканеру незачем знать, что ручка существует.
        raise HTTPException(status_code=404, detail="Not found")

    try:
        payload = await request.json()
    except Exception:
        logger.warning("GlitchTip webhook: тело не разобралось как JSON")
        return {"ok": True}

    if not isinstance(payload, dict):
        return {"ok": True}

    title, body = _extract(payload)

    # Ключ троттла — заголовок ошибки: шторм одного и того же исключения
    # схлопывается в одно сообщение, разные ошибки едут независимо.
    await alerts.send_alert(
        key=f"glitchtip:{title}",
        title=title,
        body=body[:_BODY_LIMIT],
        emoji="💥",
    )
    return {"ok": True}
