"""Инвалидация кэша HTML публичной страницы профиля (/@{username}).

Страница целиком кэшируется в Redis (см. app/web/routes.py,
public_profile_page) на PROFILE_HTML_TTL секунд. В HTML вшита сетка вишлиста
с бейджем «Забронировано», поэтому любое изменение состояния брони или
пунктов вишлиста обязано сбрасывать этот кэш — иначе гость до 2 минут видит
устаревшее «свободно/занято» и упирается в «уже забронировано» на клике.

Модуль намеренно отдельный, а не часть app.web.routes: инвалидацию зовут
API-ручки (gifts, wishlists) и фоновые таски, а web.routes сам тянет пол-API
(app.api.profile и т.д.) — импорт оттуда завёл бы циклы.
"""
import logging

from app.services.cache import cache

logger = logging.getLogger(__name__)

PROFILE_HTML_NS = "web_profile_html"
PROFILE_HTML_TTL = 120

# Ключи кэша — {username}:{tab}, вкладок ровно две (web/routes.py).
_PROFILE_TABS = ("collection", "wishlist")


async def invalidate_profile_html_cache(username: str | None) -> None:
    """Сбросить кэшированный HTML обеих вкладок публичного профиля.

    Best-effort: ошибка Redis не должна ронять основной запрос — при живом
    TTL в 120 секунд несработавшая инвалидация деградирует до старого
    поведения, а не до потери данных (истина всегда в БД).
    """
    if not username:
        return
    try:
        for tab in _PROFILE_TABS:
            await cache.delete(PROFILE_HTML_NS, f"{username}:{tab}")
    except Exception:  # noqa: BLE001
        logger.warning(
            "Не удалось сбросить кэш публичного профиля @%s", username,
            exc_info=True,
        )
