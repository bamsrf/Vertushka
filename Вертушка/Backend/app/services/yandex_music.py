"""Yandex Music как бесплатный источник обложек — закрывает русский/советский хвост.

Почему именно Yandex:
- Хвост дампа на 98% латиница, но в живых данных приложения (records/store_listings)
  кириллица ~10-12% — плюс транслитерированный СССР-слой («Kino», «Pugacheva»),
  которого структурно нет ни в Discogs, ни в Deezer/iTunes. Yandex — лучший
  каталог именно этого пласта.
- Публичный `api.music.yandex.net/search` отдаёт JSON без ключа/OAuth.
- coverUri (avatars.yandex.net/get-music-content/.../%%) — стабильный публичный
  URL, зеркалится в cover_storage как обычно.

КЛЮЧЕВОЕ про матчинг: Discogs хранит русских артистов в транслите («Kino»),
а Yandex отдаёт кириллицу («КИНО»). Прямой substring-гейт («kino» in «кино»)
провалил бы ровно целевой кейс. Поэтому сравниваем И напрямую, И через
транслит кириллицы кандидата в латиницу — матч засчитывается, если проходит
любая из сторон. Это сохраняет точность (substring в обе стороны) и включает
транслит-мост.
"""
import asyncio
import logging
import re
import time
from dataclasses import dataclass

import httpx

from app.services.deezer import normalize_artist, normalize_title

logger = logging.getLogger(__name__)

_SEARCH_URL = "https://api.music.yandex.net/search"
_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
)

# Троттл: публичный, но неофициальный API. Консервативные ~4 req/s глобальным
# локом, чтобы не ловить бан по IP.
_lock = asyncio.Lock()
_last = 0.0
_MIN_INTERVAL = 0.25

# Кириллица → латиница (GOST-подобно) для сопоставления транслита Discogs
# с кириллицей Yandex. Результат ещё проходит normalize_* (снимет пунктуацию).
_TRANSLIT = {
    "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ё": "e",
    "ж": "zh", "з": "z", "и": "i", "й": "i", "к": "k", "л": "l", "м": "m",
    "н": "n", "о": "o", "п": "p", "р": "r", "с": "s", "т": "t", "у": "u",
    "ф": "f", "х": "h", "ц": "c", "ч": "ch", "ш": "sh", "щ": "sch",
    "ъ": "", "ы": "y", "ь": "", "э": "e", "ю": "yu", "я": "ya",
}
_HAS_CYR = re.compile(r"[а-яё]")


def _translit(s: str) -> str:
    """Кириллицу в латиницу по _TRANSLIT; латиница проходит без изменений."""
    return "".join(_TRANSLIT.get(ch, ch) for ch in s)


def _matches(query_norm: str, cand_raw: str, *, is_artist: bool) -> bool:
    """substring-гейт в обе стороны: напрямую ИЛИ через транслит кандидата."""
    norm = normalize_artist if is_artist else normalize_title
    cand_norm = norm(cand_raw)
    if cand_norm and (query_norm in cand_norm or cand_norm in query_norm):
        return True
    if _HAS_CYR.search(cand_norm):
        cand_tr = norm(_translit(cand_norm))
        if cand_tr and (query_norm in cand_tr or cand_tr in query_norm):
            return True
    return False


@dataclass
class YandexCover:
    url: str  # 1000x1000 публичный avatars.yandex.net URL


def _cover_url(cover_uri: str | None) -> str | None:
    """coverUri вида `avatars.yandex.net/.../%%` → полноразмерный https-URL."""
    if not cover_uri:
        return None
    uri = cover_uri.replace("%%", "1000x1000")
    return uri if uri.startswith("http") else f"https://{uri}"


async def _throttle() -> None:
    global _last
    async with _lock:
        wait = _MIN_INTERVAL - (time.monotonic() - _last)
        if wait > 0:
            await asyncio.sleep(wait)
        _last = time.monotonic()


def _album_year(item: dict) -> int | None:
    y = item.get("year")
    try:
        return int(y) if y else None
    except (TypeError, ValueError):
        return None


async def cover_by_meta(
    artist: str,
    title: str,
    year: int | None = None,
    *,
    year_tolerance: int = 1,
) -> YandexCover | None:
    """Лучший матч обложки альбома в Yandex Music по нормализованным метаданным.

    Матч: artist И title проходят substring-гейт (напрямую или через транслит).
    При нескольких кандидатах год — мягкий тайбрейк (у переизданий release-дата
    отличается, обложка та же). Возвращает 1000x1000 URL или None.
    """
    artist_n = normalize_artist(artist)
    title_n = normalize_title(title)
    if not artist_n or not title_n or artist_n == "various":
        return None

    params = {"text": f"{artist} {title}", "type": "album", "page": "0"}
    try:
        await _throttle()
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(_SEARCH_URL, params=params, headers={"User-Agent": _UA})
            resp.raise_for_status()
            data = resp.json()
    except (httpx.HTTPError, ValueError):
        logger.debug("Yandex lookup failed for %s — %s", artist, title, exc_info=True)
        return None

    items = (((data.get("result") or {}).get("albums") or {}).get("results")) or []

    candidates: list[dict] = []
    for item in items:
        artists = item.get("artists") or []
        item_artist = artists[0].get("name", "") if artists else ""
        if not _cover_url(item.get("coverUri")):
            continue
        if _matches(artist_n, item_artist, is_artist=True) and \
           _matches(title_n, item.get("title", ""), is_artist=False):
            candidates.append(item)

    if not candidates:
        return None

    best = candidates[0]  # Yandex ранжирует по релевантности
    if year is not None and len(candidates) > 1:
        best_diff = None
        for item in candidates:
            ry = _album_year(item)
            diff = abs(ry - year) if ry is not None else 999
            if best_diff is None or diff < best_diff:
                best_diff, best = diff, item

    url = _cover_url(best.get("coverUri"))
    return YandexCover(url=url) if url else None
