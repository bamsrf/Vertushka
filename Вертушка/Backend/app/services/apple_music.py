"""Apple Music API: обложки альбомов по UPC (канал #5 из COVERS_STRATEGY).

Зачем при живом iTunes Search: тот троттлится ~19 req/min и ищет по имени
(угадывание). Здесь — точный ключ UPC и авторизованный API без публичного
душения: MusicKit developer token (JWT ES256 из .p8-ключа) даёт стабильный
темп на порядки выше. Артворк альбом-левел, до 3000px — качеством выше
любого нашего мастера.

Как получить ключ (одноразово, аккаунт разработчика, Team G47JLHB869):
developer.apple.com → Certificates, Identifiers & Profiles → Keys → «+» →
имя произвольное → галка Media Services (MusicKit) → Register → Download
(.p8 скачивается ОДИН раз). В .env.prod:
  APPLE_MUSIC_TEAM_ID=G47JLHB869
  APPLE_MUSIC_KEY_ID=<Key ID со страницы ключа>
  APPLE_MUSIC_PRIVATE_KEY_B64=$(base64 -i AuthKey_XXXXXX.p8)

Форма UPC: как у Deezer (инцидент 18.08.2026 с ведущим нулём), совпадение
точное. Лечится бесплатно: filter[upc] принимает список через запятую —
спрашиваем обе формы (с нулём и без) одним запросом.
"""
import asyncio
import base64
import logging
import time

import httpx

from app.config import get_settings

logger = logging.getLogger(__name__)

_API = "https://api.music.apple.com/v1/catalog/{storefront}/albums"
# US — самый полный каталог; RU-витрина мертва с 2022.
_STOREFRONT = "us"
_ARTWORK_SIZE = 1200

# Пейсинг: у Apple лимит не публикуется. Замер 31.08.2026: последовательные
# запросы с шагом 0.5-2с — стабильные 200, а 4 воркера с шагом 0.25с
# (in-flight burst) выхватили 429 на десятом запросе. Держим 2 rps.
_MIN_INTERVAL_S = 0.5
_token_cache: tuple[str, float] | None = None  # (jwt, годен_до_monotonic)
_TOKEN_TTL_S = 11 * 3600  # сам токен подписываем на 12ч — час запаса на часы
_pace_lock = asyncio.Lock()
_last_request_at = 0.0

_client: httpx.AsyncClient | None = None


class AppleMusicQuotaExceeded(Exception):
    """429 или систематический отказ (401/403) — волну надо прервать."""


def configured() -> bool:
    s = get_settings()
    return bool(s.apple_music_team_id and s.apple_music_key_id
                and s.apple_music_private_key_b64)


def _developer_token() -> str:
    """MusicKit developer token: ES256 JWT, kid в заголовке, iss=Team ID."""
    global _token_cache
    now = time.monotonic()
    if _token_cache and _token_cache[1] > now:
        return _token_cache[0]
    import jwt as pyjwt
    s = get_settings()
    key_pem = base64.b64decode(s.apple_music_private_key_b64)
    epoch = int(time.time())
    token = pyjwt.encode(
        {"iss": s.apple_music_team_id, "iat": epoch, "exp": epoch + 12 * 3600},
        key_pem,
        algorithm="ES256",
        headers={"kid": s.apple_music_key_id},
    )
    _token_cache = (token, now + _TOKEN_TTL_S)
    return token


def upc_variants(upc: str) -> list[str]:
    """Обе формы кода одним списком: EAN-13 с ведущим нулём и 12-значный UPC-A.

    Дедуп с сохранением порядка; невалидные формы не порождаются.
    """
    variants = [upc]
    if len(upc) == 13 and upc.startswith("0"):
        variants.append(upc[1:])
    elif len(upc) == 12:
        variants.append("0" + upc)
    seen: set[str] = set()
    return [v for v in variants if not (v in seen or seen.add(v))]


def artwork_from_payload(payload: dict, size: int = _ARTWORK_SIZE) -> str | None:
    """URL артворка из ответа /albums. Шаблон Apple несёт литеральные {w}/{h}."""
    for album in payload.get("data") or []:
        art = (album.get("attributes") or {}).get("artwork") or {}
        template = art.get("url")
        if not template:
            continue
        width = min(size, art.get("width") or size)
        height = min(size, art.get("height") or size)
        return template.replace("{w}", str(width)).replace("{h}", str(height))
    return None


def _get_client() -> httpx.AsyncClient:
    global _client
    if _client is None:
        _client = httpx.AsyncClient(timeout=15.0)
    return _client


async def cover_by_upc(upc: str) -> str | None:
    """Обложка альбома по штрихкоду. None — не нашли. Не зовётся без configured().

    AppleMusicQuotaExceeded: 429 (флуд) и 401/403 (ключ протух/отозван) — оба
    случая систематические, продолжать волну бессмысленно.
    """
    global _last_request_at
    async with _pace_lock:
        wait = _MIN_INTERVAL_S - (time.monotonic() - _last_request_at)
        if wait > 0:
            await asyncio.sleep(wait)
        _last_request_at = time.monotonic()

    resp = await _get_client().get(
        _API.format(storefront=_STOREFRONT),
        params={"filter[upc]": ",".join(upc_variants(upc))},
        headers={"Authorization": f"Bearer {_developer_token()}"},
    )
    if resp.status_code == 429:
        raise AppleMusicQuotaExceeded("429 rate limited")
    if resp.status_code in (401, 403):
        # Не квота, а сломанная авторизация: без остановки волна пометила бы
        # done всю очередь с нулём попаданий.
        raise AppleMusicQuotaExceeded(f"auth failed: {resp.status_code}")
    if resp.status_code == 404:
        return None
    resp.raise_for_status()
    return artwork_from_payload(resp.json())
