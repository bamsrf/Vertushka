"""Deezer как бесплатный источник обложек альбомов.

Почему Deezer:
- cover_xl — 1000×1000 (иногда 1400), выше iTunes 600 и большинства Discogs.
- URL публичные и СТАБИЛЬНЫЕ (e-cdns-images.dzcdn.net/.../1000x1000-000000-80-0-0.jpg),
  в отличие от подписанных i.discogs.com — зеркалятся в cover_storage насовсем,
  не «грузятся заново».
- API без ключа: https://api.deezer.com/search/album?q=... Лимит ~50 req/5s на IP.

Матчинг критично зависит от нормализации метаданных: у Discogs в названии часто
мусор ((Remastered), [Japan], feat.), у Deezer — чистое имя альбома. Приводим
обе стороны к единому ключу, затем fuzzy-совпадение + опциональная проверка года.
"""
import asyncio
import logging
import re
import time
from dataclasses import dataclass

import httpx

logger = logging.getLogger(__name__)

_SEARCH_URL = "https://api.deezer.com/search/album"
_ALBUM_URL = "https://api.deezer.com/album/{album_id}"

# Глобальный троттл: Deezer ~50 запросов / 5с на IP. Держим ~8 req/s с запасом.
_lock = asyncio.Lock()
_last = 0.0
_MIN_INTERVAL = 0.13

# Мусор в скобках/квадратах — пресинги и издания, не различающие обложку альбома.
_EDITION_NOISE = re.compile(
    r"[\(\[][^\)\]]*\b("
    r"remaster(ed)?|deluxe|expanded|anniversary|edition|reissue|re-issue|"
    r"mono|stereo|explicit|clean|bonus|special|limited|super\s*deluxe|"
    r"japan(ese)?|uk|us|eu|import|digipak|remastered\s*\d{2,4}|"
    r"\d{2,4}\s*remaster|version"
    r")\b[^\)\]]*[\)\]]",
    re.IGNORECASE,
)
# feat. / ft. / featuring … до конца строки или до закрывающей скобки.
_FEAT = re.compile(r"\s*[\(\[]?\s*(feat\.?|ft\.?|featuring)\s+[^\)\]]*[\)\]]?", re.IGNORECASE)
_PUNCT = re.compile(r"[^\w\s]", re.UNICODE)
_WS = re.compile(r"\s+")


def normalize_title(title: str) -> str:
    """Нормализованный ключ названия альбома для матчинга.

    Убирает издательский мусор, feat.-хвосты, пунктуацию, схлопывает пробелы,
    casefold. НЕ трогает remix/live — они меняют сам релиз, а не издание.
    """
    if not title:
        return ""
    s = _EDITION_NOISE.sub(" ", title)
    s = _FEAT.sub(" ", s)
    s = _PUNCT.sub(" ", s)
    s = _WS.sub(" ", s).strip().casefold()
    return s


def normalize_artist(artist: str) -> str:
    """Ключ артиста: снять discogs-суффикс `(2)`, feat., пунктуацию."""
    if not artist:
        return ""
    s = re.sub(r"\s*\(\d+\)\s*$", "", artist)  # Discogs-дизамбиг "Nirvana (2)"
    s = _FEAT.sub(" ", s)
    s = _PUNCT.sub(" ", s)
    s = _WS.sub(" ", s).strip().casefold()
    return s


def _query_clean(s: str, *, is_artist: bool = False) -> str:
    """Читаемая очистка для строки запроса Deezer: снять издательский мусор,
    feat., discogs-суффикс `(2)` — но сохранить регистр/пробелы (в отличие от
    normalize_*, которая ещё режет пунктуацию и casefold'ит для матч-гейта)."""
    if not s:
        return ""
    if is_artist:
        s = re.sub(r"\s*\(\d+\)\s*$", "", s)
    s = _EDITION_NOISE.sub(" ", s)
    s = _FEAT.sub(" ", s)
    s = _WS.sub(" ", s).strip()
    return s


def _year_of(date_str: str | None) -> int | None:
    if not date_str or len(date_str) < 4 or not date_str[:4].isdigit():
        return None
    return int(date_str[:4])


@dataclass
class DeezerCover:
    url: str            # cover_xl — стабильный публичный URL
    md5_image: str      # для будущего resize/дедупа
    album_id: int       # внешний ключ Deezer


async def _throttle() -> None:
    global _last
    async with _lock:
        wait = _MIN_INTERVAL - (time.monotonic() - _last)
        if wait > 0:
            await asyncio.sleep(wait)
        _last = time.monotonic()


def _fmt_dur_sec(sec: int | None) -> str | None:
    """Секунды → 'M:SS' (формат треклиста Discogs)."""
    if not sec or sec <= 0:
        return None
    return f"{sec // 60}:{sec % 60:02d}"


async def tracklist_by_album_id(album_id: int | str) -> list[dict] | None:
    """Треклист альбома из Deezer `/album/{id}` → [{position,title,duration}].

    ВАЖНО: это стриминг-издание (album-level), НЕ конкретный винил-прессинг —
    позиции числовые (1,2,3), не A1/B1; бонусы/порядок могут отличаться. Годится
    как «достаточно хороший» fallback, точный прессинг — MB (per-release)/Discogs.
    """
    try:
        await _throttle()
        async with httpx.AsyncClient(timeout=15.0) as client:
            r = await client.get(_ALBUM_URL.format(album_id=album_id))
            r.raise_for_status()
            tracks = (r.json().get("tracks") or {}).get("data", [])
    except (httpx.HTTPError, ValueError):
        logger.debug("Deezer tracklist failed for album %s", album_id, exc_info=True)
        return None

    out: list[dict] = []
    for i, t in enumerate(tracks, 1):
        title = t.get("title")
        if not title:
            continue
        out.append({
            "position": str(t.get("track_position") or i),
            "title": title,
            "duration": _fmt_dur_sec(t.get("duration")),
        })
    return out or None


async def cover_by_meta(
    artist: str,
    title: str,
    year: int | None = None,
    label: str | None = None,
    *,
    year_tolerance: int = 1,
) -> DeezerCover | None:
    """Лучший матч обложки альбома в Deezer по нормализованным метаданным.

    Матч: нормализованные artist И title совпадают (substring в обе стороны).
    При наличии year — один добор /album/{id} за release_date и отсев кандидатов
    дальше year_tolerance лет (защита от одноимённых альбомов/сборников).
    Возвращает cover_xl или None.
    """
    artist_n = normalize_artist(artist)
    title_n = normalize_title(title)
    if not artist_n or not title_n or artist_n == "various":
        return None

    async def _search(q: str) -> list:
        await _throttle()
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(_SEARCH_URL, params={"q": q, "limit": 5})
            resp.raise_for_status()
            return resp.json().get("data", [])

    # В запрос идёт ОЧИЩЕННЫЙ title (без (Remastered)/[Japan]/feat.) — иначе
    # строгий album:"..." с мусором ничего не находит. Артист — тоже очищенный.
    q_title = _query_clean(title)
    q_artist = _query_clean(artist, is_artist=True)
    try:
        # Строгий запрос по полям — точнее; при пустом ответе плоский concat.
        # Гейт на нормализованный artist+title ниже защищает от ложных матчей.
        results = await _search(f'artist:"{q_artist}" album:"{q_title}"')
        if not results:
            results = await _search(f"{q_artist} {q_title}")
    except (httpx.HTTPError, ValueError):
        logger.debug("Deezer lookup failed for %s — %s", artist, title, exc_info=True)
        return None

    candidates = []
    for item in results:
        item_artist = normalize_artist((item.get("artist") or {}).get("name", ""))
        item_title = normalize_title(item.get("title", ""))
        if not item_artist or not item_title or not item.get("cover_xl"):
            continue
        artist_ok = artist_n in item_artist or item_artist in artist_n
        title_ok = title_n in item_title or item_title in title_n
        if artist_ok and title_ok:
            candidates.append(item)

    if not candidates:
        return None

    best = candidates[0]  # Deezer уже ранжирует по релевантности

    # Год — МЯГКИЙ тайбрейк, НЕ фильтр. Ремастеры на Deezer несут дату переиздания
    # (Dark Side 1973 → альбом 2011), обложка та же — жёсткий year-гейт зря резал
    # бы. Добираем /album только при НЕСКОЛЬКИХ кандидатах, чтобы выбрать ближе к
    # году; единственный матч возвращаем как есть.
    if year is not None and len(candidates) > 1:
        best_diff = None
        for item in candidates:
            try:
                await _throttle()
                async with httpx.AsyncClient(timeout=15.0) as client:
                    d = await client.get(_ALBUM_URL.format(album_id=item["id"]))
                    d.raise_for_status()
                    ry = _year_of(d.json().get("release_date"))
            except (httpx.HTTPError, ValueError, KeyError):
                ry = None
            diff = abs(ry - year) if ry is not None else 999
            if best_diff is None or diff < best_diff:
                best_diff, best = diff, item

    return DeezerCover(
        url=best["cover_xl"],
        md5_image=best.get("md5_image", ""),
        album_id=int(best["id"]),
    )
