"""Discogs OAuth 1.0a (3-legged) — per-user подключение.

Discogs не поддерживает OAuth2. Подпись — PLAINTEXT (Discogs её поддерживает;
проще и устойчивее HMAC-SHA1, т.к. не требует строки-базы по RFC5849).
consumer_key/secret = настройки приложения (DISCOGS_API_KEY/SECRET).

Flow:
  1. build_authorize_url() — берёт request_token, возвращает URL авторизации
     + request_token_secret (его надо донести до callback).
  2. exchange() — меняет verifier на постоянные access token/secret + username.
  3. sign_headers() — Authorization для обычных API-запросов от имени юзера.
"""
import logging
import secrets
import time
from urllib.parse import parse_qsl, quote

import httpx

from app.config import get_settings

logger = logging.getLogger(__name__)

REQUEST_TOKEN_URL = "https://api.discogs.com/oauth/request_token"
AUTHORIZE_URL = "https://www.discogs.com/oauth/authorize"
ACCESS_TOKEN_URL = "https://api.discogs.com/oauth/access_token"
IDENTITY_URL = "https://api.discogs.com/oauth/identity"


def _quote(value: str) -> str:
    return quote(str(value), safe="~")


def _oauth_header(
    params: dict[str, str],
    token_secret: str = "",
) -> str:
    """Собирает строку Authorization: OAuth ... с PLAINTEXT подписью."""
    settings = get_settings()
    signature = f"{_quote(settings.discogs_api_secret)}&{_quote(token_secret)}"
    base_params = {
        "oauth_consumer_key": settings.discogs_api_key,
        "oauth_nonce": secrets.token_hex(16),
        "oauth_signature_method": "PLAINTEXT",
        "oauth_signature": signature,
        "oauth_timestamp": str(int(time.time())),
        "oauth_version": "1.0",
        **params,
    }
    return "OAuth " + ", ".join(
        f'{_quote(k)}="{_quote(v)}"' for k, v in base_params.items()
    )


def _headers(authorization: str) -> dict[str, str]:
    return {
        "Authorization": authorization,
        "User-Agent": get_settings().discogs_user_agent,
    }


async def build_authorize_url() -> tuple[str, str, str]:
    """Шаг 1: получить request token. Возвращает (authorize_url, oauth_token, oauth_token_secret)."""
    settings = get_settings()
    auth = _oauth_header({"oauth_callback": settings.discogs_oauth_callback_url})
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.get(REQUEST_TOKEN_URL, headers=_headers(auth))
        resp.raise_for_status()
    data = dict(parse_qsl(resp.text))
    token = data["oauth_token"]
    secret = data["oauth_token_secret"]
    return f"{AUTHORIZE_URL}?oauth_token={token}", token, secret


async def exchange(
    oauth_token: str,
    oauth_verifier: str,
    request_token_secret: str,
) -> tuple[str, str, str]:
    """Шаг 2: обменять verifier на access token. Возвращает (token, secret, username)."""
    auth = _oauth_header(
        {"oauth_token": oauth_token, "oauth_verifier": oauth_verifier},
        token_secret=request_token_secret,
    )
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(ACCESS_TOKEN_URL, headers=_headers(auth))
        resp.raise_for_status()
        data = dict(parse_qsl(resp.text))
        access_token = data["oauth_token"]
        access_secret = data["oauth_token_secret"]
        username = await _identity(client, access_token, access_secret)
    return access_token, access_secret, username


async def _identity(client: httpx.AsyncClient, token: str, secret: str) -> str:
    auth = _oauth_header({"oauth_token": token}, token_secret=secret)
    resp = await client.get(IDENTITY_URL, headers=_headers(auth))
    resp.raise_for_status()
    return resp.json().get("username", "")


def sign_headers(token: str, secret: str) -> dict[str, str]:
    """Authorization для обычного API-запроса от имени юзера."""
    auth = _oauth_header({"oauth_token": token}, token_secret=secret)
    return _headers(auth)


def user_creds(user) -> "tuple[str, str] | None":
    """Достаёт (oauth_token, расшифрованный secret) из User, либо None.

    Передаётся в DiscogsService.search/suggest, чтобы запрос шёл через токен
    юзера (его персональный rate-limit). None → используется app-токен.
    """
    from app.services.discogs_crypto import decrypt_secret

    if not user or not user.discogs_oauth_token or not user.discogs_oauth_token_secret:
        return None
    secret = decrypt_secret(user.discogs_oauth_token_secret)
    if secret is None:
        return None
    return user.discogs_oauth_token, secret
