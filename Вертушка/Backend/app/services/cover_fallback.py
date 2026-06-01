"""Бесплатный fallback обложек: barcode → MusicBrainz MBID → Cover Art Archive.

Не трогает Discogs API / его rate-limit. Используется когда у записи нет
обложки от Discogs (холодные dump-релизы). MusicBrainz требует уникальный
User-Agent и лимит ≤1 req/s — соблюдаем модульным asyncio-локом.
"""
import asyncio
import logging
import re
import time

import httpx

from app.config import get_settings

logger = logging.getLogger(__name__)

_MB_URL = "https://musicbrainz.org/ws/2/release"
_CAA_FRONT = "https://coverartarchive.org/release/{mbid}/front-500"

# MusicBrainz: жёсткий лимит 1 req/s на IP. Глобальный троттл.
_mb_lock = asyncio.Lock()
_mb_last = 0.0
_MB_MIN_INTERVAL = 1.1


def _user_agent() -> str:
    # MusicBrainz требует контактный UA. Переиспользуем discogs_user_agent.
    return get_settings().discogs_user_agent


async def _mb_throttle() -> None:
    global _mb_last
    async with _mb_lock:
        wait = _MB_MIN_INTERVAL - (time.monotonic() - _mb_last)
        if wait > 0:
            await asyncio.sleep(wait)
        _mb_last = time.monotonic()


async def cover_url_by_barcode(barcode: str) -> str | None:
    """Возвращает URL обложки Cover Art Archive по barcode, либо None.

    1) MusicBrainz: barcode → release MBID.
    2) CAA: проверяем наличие front-обложки (HEAD редиректит на CDN).
    """
    digits = re.sub(r"\D", "", barcode or "")
    if len(digits) < 8:
        return None

    headers = {"User-Agent": _user_agent()}
    try:
        await _mb_throttle()
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(
                _MB_URL,
                params={"query": f"barcode:{digits}", "fmt": "json"},
                headers=headers,
            )
            resp.raise_for_status()
            releases = resp.json().get("releases", [])
            if not releases:
                return None
            mbid = releases[0].get("id")
            if not mbid:
                return None

            caa_url = _CAA_FRONT.format(mbid=mbid)
            # CAA отдаёт 307 на CDN если обложка есть, 404 если нет.
            head = await client.head(caa_url, follow_redirects=False)
            if head.status_code in (301, 302, 307):
                return caa_url
            return None
    except httpx.HTTPError:
        logger.debug("Cover Art Archive lookup failed for barcode %s", digits, exc_info=True)
        return None
