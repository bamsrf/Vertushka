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


# Винил/издательский шум в метаданных магазина, которого нет в названии альбома
# на Yandex: «(2LP, цветной винил)», «(моно)», «Виниловая пластинка», «Спектакль».
# Чистим И строку запроса (иначе Yandex по мусору не находит), И перед normalize.
_RU_NOISE = re.compile(
    r"\b("
    r"виниловая\s+пластинка|пластинк\w*|винил\w*|"
    r"цветн\w+|прозрачн\w+|"
    r"моно|стерео|переиздани\w+|спектакль|коллекци\w+|"
    r"\d+\s*lp|lp|ep"
    r")\b",
    re.IGNORECASE,
)
_BRACKETS = re.compile(r"[\(\[][^\)\]]*[\)\]]")


def _strip_noise(s: str) -> str:
    """Снять винил/издательский шум для строки запроса Yandex. Скобочные группы
    у store-листингов почти всегда шум ((2LP, цветной винил)/(моно)) — режем."""
    if not s:
        return s
    s = _BRACKETS.sub(" ", s)
    s = _RU_NOISE.sub(" ", s)
    return re.sub(r"\s+", " ", s).strip()


def _forms(norm_str: str, norm_fn) -> set[str]:
    """Формы для сравнения: сама нормализованная строка + её транслит (если в
    ней кириллица). Даёт общее латинское пространство для сопоставления."""
    forms = {norm_str}
    if _HAS_CYR.search(norm_str):
        forms.add(norm_fn(_translit(norm_str)))
    return {f for f in forms if f}


def _matches(query_norm: str, cand_raw: str, *, is_artist: bool) -> bool:
    """substring-гейт в обе стороны, ДВУСТОРОННИЙ транслит: обе стороны сводим к
    формам {кириллица, латиница}. Ловит и «Наутилус Помпилиус» (запрос) vs
    «Nautilus Pompilius» (Yandex), и обратный случай."""
    norm = normalize_artist if is_artist else normalize_title
    qf = _forms(query_norm, norm)
    cf = _forms(norm(cand_raw), norm)
    return any(q in c or c in q for q in qf for c in cf)


@dataclass
class YandexCover:
    url: str  # 1000x1000 публичный avatars.yandex.net URL


@dataclass
class YandexAlbum:
    album_id: int
    url: str | None            # обложка 1000x1000
    year: int | None
    genre: str | None
    tracklist: list[dict]      # [{position, title, duration}] — album-level


_ALBUM_URL = "https://api.music.yandex.net/albums/{album_id}/with-tracks"


def _fmt_dur_ms(ms: int | None) -> str | None:
    """Миллисекунды → 'M:SS' (формат треклиста как в Discogs/Deezer)."""
    if not ms or ms <= 0:
        return None
    sec = ms // 1000
    return f"{sec // 60}:{sec % 60:02d}"


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


async def _best_album_match(
    artist: str, title: str, year: int | None, *, require_cover: bool,
) -> dict | None:
    """Лучший альбом-кандидат Yandex по нормализованным метаданным, либо None.

    Матч: artist И title проходят substring-гейт (напрямую или через транслит).
    При нескольких кандидатах год — мягкий тайбрейк (у переизданий release-дата
    отличается, обложка та же). require_cover — отсеять кандидатов без coverUri.
    """
    # Чистим винил/издательский шум ДО запроса и нормализации: у store-листингов
    # title типа «Золотой Век (2LP, цветной винил)» — по такому Yandex молчит.
    artist_c = _strip_noise(artist)
    title_c = _strip_noise(title)
    artist_n = normalize_artist(artist_c)
    title_n = normalize_title(title_c)
    if not artist_n or not title_n or artist_n == "various":
        return None

    params = {"text": f"{artist_c} {title_c}", "type": "album", "page": "0"}
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
        if require_cover and not _cover_url(item.get("coverUri")):
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
    return best


async def cover_by_meta(
    artist: str,
    title: str,
    year: int | None = None,
    *,
    year_tolerance: int = 1,
) -> YandexCover | None:
    """Обложка альбома Yandex (1000x1000 URL) по метаданным, либо None."""
    best = await _best_album_match(artist, title, year, require_cover=True)
    if not best:
        return None
    url = _cover_url(best.get("coverUri"))
    return YandexCover(url=url) if url else None


async def _tracklist_by_album_id(album_id: int) -> list[dict]:
    """Треклист album-level из /albums/{id}/with-tracks → [{position,title,duration}].

    ВАЖНО: это стриминг-издание (album-level), НЕ конкретный винил-прессинг —
    позиции числовые, бонусы/порядок могут отличаться. «Достаточно хороший»
    fallback для релизов вне Discogs. На ошибку/пусто — [].
    """
    try:
        await _throttle()
        async with httpx.AsyncClient(timeout=15.0) as client:
            r = await client.get(_ALBUM_URL.format(album_id=album_id), headers={"User-Agent": _UA})
            r.raise_for_status()
            volumes = (r.json().get("result") or {}).get("volumes") or []
    except (httpx.HTTPError, ValueError):
        logger.debug("Yandex tracklist failed for album %s", album_id, exc_info=True)
        return []

    out: list[dict] = []
    pos = 1
    for vol in volumes:
        for tr in vol:
            title = tr.get("title")
            if not title:
                continue
            out.append({
                "position": str(pos),
                "title": title,
                "duration": _fmt_dur_ms(tr.get("durationMs")),
            })
            pos += 1
    return out


async def album_by_meta(
    artist: str, title: str, year: int | None = None,
) -> YandexAlbum | None:
    """Полный альбом Yandex (обложка + год + жанр + треклист) для обогащения
    записей вне Discogs. Матч — как в cover_by_meta. На промах — None."""
    best = await _best_album_match(artist, title, year, require_cover=False)
    if not best:
        return None
    album_id = int(best["id"])
    return YandexAlbum(
        album_id=album_id,
        url=_cover_url(best.get("coverUri")),
        year=_album_year(best),
        genre=best.get("genre"),
        tracklist=await _tracklist_by_album_id(album_id),
    )
