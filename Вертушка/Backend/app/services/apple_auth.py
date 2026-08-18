"""Sign in with Apple REST API — обмен authorization_code и отзыв токена.

Зачем: Apple требует, чтобы приложение, поддерживающее Sign in with Apple,
при удалении аккаунта отзывало выданные токены через /auth/revoke
(App Store Review Guideline 5.1.1(v), обязательно с 30.06.2022). Отозвать
можно только имея refresh_token — а его выдают в обмен на authorization_code,
который мобилка присылает ровно один раз, в момент входа. Поэтому обмен
делается сразу при входе, а не «когда понадобится»: второго шанса не будет.

Все функции здесь мягкие: если ключи не настроены или Apple ответил ошибкой,
мы логируем и возвращаем False/None. Вход и удаление аккаунта не должны
падать из-за недоступности стороннего сервиса — по той же логике Apple
(TN3194) разрешает завершить удаление и без успешного отзыва.
"""
import logging
import time

import httpx
import jwt as pyjwt

from app.config import get_settings

logger = logging.getLogger(__name__)

APPLE_TOKEN_URL = "https://appleid.apple.com/auth/token"
APPLE_REVOKE_URL = "https://appleid.apple.com/auth/revoke"

# Apple разрешает client_secret на срок до 6 месяцев. Берём час: секрет
# генерируется на каждый запрос, и долгоживущий JWT тут не даёт ничего,
# кроме лишнего окна на случай утечки логов.
_CLIENT_SECRET_TTL_SECONDS = 3600

_HTTP_TIMEOUT = httpx.Timeout(10.0)


def is_configured() -> bool:
    """Заведены ли ключи Sign in with Apple (Key ID + .p8 + Team ID)."""
    settings = get_settings()
    return bool(
        settings.apple_client_id
        and settings.apple_team_id
        and settings.apple_key_id
        and settings.apple_private_key.strip()
    )


def _private_key_pem() -> str:
    """Содержимое .p8 из окружения.

    В .env ключ обычно лежит одной строкой с экранированными переносами —
    PEM без настоящих \\n не парсится, поэтому разворачиваем.
    """
    return get_settings().apple_private_key.strip().replace("\\n", "\n")


def _client_secret() -> str:
    """JWT (ES256), которым мы представляемся Apple вместо пароля клиента."""
    settings = get_settings()
    now = int(time.time())
    return pyjwt.encode(
        {
            "iss": settings.apple_team_id,
            "iat": now,
            "exp": now + _CLIENT_SECRET_TTL_SECONDS,
            "aud": "https://appleid.apple.com",
            "sub": settings.apple_client_id,
        },
        _private_key_pem(),
        algorithm="ES256",
        headers={"kid": settings.apple_key_id},
    )


async def exchange_code_for_refresh_token(authorization_code: str) -> str | None:
    """authorization_code → refresh_token. None, если не вышло.

    redirect_uri не передаётся сознательно: для нативного клиента client_id
    равен bundle id, и Apple такой параметр в этом флоу не ждёт.
    """
    if not authorization_code or not is_configured():
        return None

    settings = get_settings()
    try:
        async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as client:
            response = await client.post(
                APPLE_TOKEN_URL,
                data={
                    "client_id": settings.apple_client_id,
                    "client_secret": _client_secret(),
                    "code": authorization_code,
                    "grant_type": "authorization_code",
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
        if response.status_code != 200:
            logger.warning(
                "apple_code_exchange_failed status=%s body=%s",
                response.status_code,
                response.text[:200],
            )
            return None
        return response.json().get("refresh_token")
    except Exception as e:  # noqa: BLE001 — вход важнее обмена токена
        logger.warning("apple_code_exchange_error: %s", e)
        return None


async def revoke_refresh_token(refresh_token: str) -> bool:
    """Отзывает refresh_token в Apple. True — Apple подтвердил отзыв."""
    if not refresh_token or not is_configured():
        return False

    settings = get_settings()
    try:
        async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as client:
            response = await client.post(
                APPLE_REVOKE_URL,
                data={
                    "client_id": settings.apple_client_id,
                    "client_secret": _client_secret(),
                    "token": refresh_token,
                    "token_type_hint": "refresh_token",
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
        if response.status_code == 200:
            return True
        logger.warning(
            "apple_revoke_failed status=%s body=%s",
            response.status_code,
            response.text[:200],
        )
        return False
    except Exception as e:  # noqa: BLE001 — удаление аккаунта важнее отзыва
        logger.warning("apple_revoke_error: %s", e)
        return False
