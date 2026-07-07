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
# front-1200 (не front-500): URL уходит в cover_image_url и показывается на
# detail-экране во всю ширину; зеркало в cover_storage ужмёт до 1000px.
_CAA_FRONT = "https://coverartarchive.org/release/{mbid}/front-1200"

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


def _fmt_dur_ms(ms: int | None) -> str | None:
    """Миллисекунды → 'M:SS' (формат треклиста Discogs)."""
    if not ms or ms <= 0:
        return None
    sec = ms // 1000
    return f"{sec // 60}:{sec % 60:02d}"


async def tracklist_by_mbid(mbid: str) -> list[dict] | None:
    """Треклист издания из MusicBrainz по MBID → [{position,title,duration}].

    Per-release (конкретное издание) — точнее Deezer: несёт винил-позиции
    (A1, B1), реальный порядок прессинга. Бесплатно, MB-троттл 1 req/s.
    """
    if not mbid:
        return None
    try:
        await _mb_throttle()
        async with httpx.AsyncClient(timeout=15.0) as client:
            r = await client.get(
                f"{_MB_URL}/{mbid}",
                params={"inc": "recordings", "fmt": "json"},
                headers={"User-Agent": _user_agent()},
            )
            r.raise_for_status()
            media = r.json().get("media", [])
    except (httpx.HTTPError, ValueError):
        logger.debug("MB tracklist failed for %s", mbid, exc_info=True)
        return None

    out: list[dict] = []
    for medium in media:
        for tr in medium.get("tracks", []):
            title = tr.get("title") or (tr.get("recording") or {}).get("title")
            if not title:
                continue
            out.append({
                "position": tr.get("number") or str(tr.get("position") or ""),
                "title": title,
                "duration": _fmt_dur_ms(tr.get("length") or (tr.get("recording") or {}).get("length")),
            })
    return out or None


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


async def cover_url_by_discogs_id(session, discogs_id: str) -> str | None:
    """CAA-обложка по офлайн-маппингу mb_discogs_map (без MusicBrainz API).

    Маппинг discogs_id → MBID импортирован из MB-дампа
    (ingest_mb_discogs_map.py). Один HEAD к CAA — ни Discogs-, ни
    MB-rate-limit не трогаем, троттл 1 rps не нужен.
    """
    from sqlalchemy import text

    if not str(discogs_id).isdigit():
        return None
    mbid = (await session.execute(
        text("SELECT mbid::text FROM mb_discogs_map WHERE discogs_id = :did"),
        {"did": int(discogs_id)},
    )).scalar()
    if not mbid:
        return None

    caa_url = _CAA_FRONT.format(mbid=mbid)
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            head = await client.head(
                caa_url, follow_redirects=False,
                headers={"User-Agent": _user_agent()},
            )
        if head.status_code in (301, 302, 307):
            return caa_url
        return None
    except httpx.HTTPError:
        logger.debug("CAA lookup failed for discogs_id %s", discogs_id, exc_info=True)
        return None


# ── iTunes Search API fallback ──────────────────────────────────────────
# Лимит ~20 req/min на IP (официально «approximately 20 calls per minute»).
# Троттлим глобальным локом как MusicBrainz. Картинки отдаёт mzstatic CDN —
# сами URL без лимита, зеркалятся в cover_storage как обычно.

_ITUNES_URL = "https://itunes.apple.com/search"
_itunes_lock = asyncio.Lock()
_itunes_last = 0.0
_ITUNES_MIN_INTERVAL = 3.1  # ~19 req/min

_NORM_RE = re.compile(r"[^\w\s]", re.UNICODE)


def _norm(s: str) -> str:
    return _NORM_RE.sub("", (s or "").casefold()).strip()


async def _itunes_throttle() -> None:
    global _itunes_last
    async with _itunes_lock:
        wait = _ITUNES_MIN_INTERVAL - (time.monotonic() - _itunes_last)
        if wait > 0:
            await asyncio.sleep(wait)
        _itunes_last = time.monotonic()


async def cover_url_by_artist_title(artist: str, title: str) -> str | None:
    """Обложка альбома из iTunes Search API по artist + title.

    Матч строгий: нормализованные artist И title должны совпасть
    (substring в обе стороны) — иначе рискуем прицепить чужую обложку.
    iTunes отдаёт artwork УРОВНЯ АЛЬБОМА (не конкретного издания) —
    поэтому это ПОСЛЕДНИЙ fallback после CAA и Discogs.
    """
    artist_n = _norm(artist)
    title_n = _norm(title)
    if not artist_n or not title_n or artist_n == "various":
        return None

    try:
        await _itunes_throttle()
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(
                _ITUNES_URL,
                params={
                    "term": f"{artist} {title}",
                    "entity": "album",
                    "limit": 5,
                },
                headers={"User-Agent": _user_agent()},
            )
            resp.raise_for_status()
            results = resp.json().get("results", [])
    except (httpx.HTTPError, ValueError):
        logger.debug("iTunes lookup failed for %s — %s", artist, title, exc_info=True)
        return None

    for item in results:
        item_artist = _norm(item.get("artistName", ""))
        item_title = _norm(item.get("collectionName", ""))
        artwork = item.get("artworkUrl100")
        if not artwork or not item_artist or not item_title:
            continue
        # Single/EP с тем же названием — чужой арт для альбома. Пропускаем,
        # если сам запрос не single/ep.
        for suffix in (" single", " ep"):
            if item_title.endswith(suffix) and not title_n.endswith(suffix):
                item_title = ""
                break
        if not item_title:
            continue
        artist_ok = artist_n in item_artist or item_artist in artist_n
        title_ok = title_n in item_title or item_title in title_n
        if artist_ok and title_ok:
            # 600x600 — документированный вариант размера у mzstatic
            # (в отличие от 3000x3000, который часто 403).
            return artwork.replace("100x100bb", "600x600bb")
    return None
