"""Детект краулеров и превью-ботов по User-Agent.

Зачем: публичные страницы профиля/вишлиста содержат ссылки редиректора
`/go/l/{listing_id}`. Telegram, WhatsApp, Slack и поисковые боты дёргают их,
чтобы отрисовать превью — это не переходы людей, и в отчётах для магазина
они бы завышали трафик.

Важно, чем это НЕ является: это не гейт. Редирект отдаём всем, включая ботов
(ломать превью незачем), просто помечаем клик `is_bot=true` и не отправляем
хит в Метрику. Список маркеров заведомо неполон — новый краулер появится
раньше, чем мы про него узнаем, поэтому цифры для магазина всегда считаем
как «не-бот И redirected_at IS NOT NULL», а не «всё, что не в списке».
"""
from __future__ import annotations

# Только нижний регистр — сверяем с ua.lower().
_BOT_UA_MARKERS = (
    "bot",              # покрывает TelegramBot, Slackbot, Googlebot, bingbot, YandexBot…
    "crawler",
    "spider",
    "preview",
    "facebookexternalhit",
    "whatsapp",
    "skypeuripreview",
    "vkshare",
    "twitterbot",
    "discordbot",
    "embedly",
    "quora link preview",
    "curl/",
    "wget/",
    "python-requests",
    "go-http-client",
    "headlesschrome",
)


def is_bot_ua(user_agent: str | None) -> bool:
    """True если UA похож на краулер/превью-бот/скрипт.

    Пустой UA тоже считаем ботом: живой браузер всегда его присылает, а вот
    накрутка через curl без флагов — нет.
    """
    if not user_agent:
        return True
    ua = user_agent.lower()
    return any(marker in ua for marker in _BOT_UA_MARKERS)
