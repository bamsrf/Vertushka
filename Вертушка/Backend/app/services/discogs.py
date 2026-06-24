"""
Сервис для работы с Discogs API.
Кэширование через Redis (graceful fallback на работу без кэша).
"""
import asyncio
import logging
import re
import time

import httpx
from typing import Any

from app.config import get_settings
from app.services.rate_limiter import discogs_limiter, Priority
from app.services.cache import (
    cache,
    search_cache_key,
    TTL_RELEASE,
    TTL_MASTER,
    TTL_ARTIST,
    TTL_ARTIST_THUMB,
    TTL_ARTIST_MASTERS,
    TTL_SEARCH,
    TTL_SUGGEST,
    TTL_PRICE_STATS,
    TTL_MASTER_VERSIONS,
    TTL_MASTER_INFO,
)
from app.services.search_cache_db import get_from_search_cache, save_to_search_cache
from app.services.artist_name import clean_artist_name
from app.schemas.record import (
    RecordSearchResult,
    RecordSearchResponse,
    MasterSearchResult,
    MasterSearchResponse,
    MasterRelease,
    MasterVersion,
    MasterVersionsResponse,
    ReleaseSearchResult,
    ReleaseSearchResponse,
    ArtistSearchResult,
    ArtistSearchResponse,
    Artist,
)

logger = logging.getLogger(__name__)

settings = get_settings()


def _build_year_query(
    query: str,
    year: int | None,
    year_min: int | None,
    year_max: int | None,
) -> tuple[str, int | None]:
    """Возвращает (q, year) для Discogs search.

    Discogs API параметр `year` — это точный год. Для декадных фильтров
    встраиваем lucene-range `year:[X TO Y]` в q-строку, оставляя сам
    параметр `year` пустым.
    """
    if year_min is not None and year_max is not None:
        if year_min == year_max:
            return query, year_min
        lo, hi = (year_min, year_max) if year_min <= year_max else (year_max, year_min)
        return f"{query} year:[{lo} TO {hi}]".strip(), None
    if year_min is not None:
        return query, year_min
    if year_max is not None:
        return query, year_max
    return query, year


class CircuitOpenError(Exception):
    """Raised when Discogs circuit breaker is OPEN — fast-fail без похода в сеть."""


class _CircuitBreaker:
    """Circuit breaker для Discogs.

    CLOSED → нормальная работа.
    OPEN  → 5 подряд 5xx/network → блокируем запросы на reset_after сек.
    HALF_OPEN → пускаем один пробный запрос. Успех → CLOSED, провал → OPEN.

    429 не считаем фейлом — это rate-limit, не падение сервиса.
    """

    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"

    def __init__(self, failure_threshold: int = 5, reset_after_sec: float = 60.0):
        self.failure_threshold = failure_threshold
        self.reset_after_sec = reset_after_sec
        self._state = self.CLOSED
        self._consecutive_failures = 0
        self._opened_at: float | None = None
        self._lock = asyncio.Lock()

    async def before_request(self) -> None:
        async with self._lock:
            if self._state == self.OPEN:
                assert self._opened_at is not None
                if time.monotonic() - self._opened_at >= self.reset_after_sec:
                    self._state = self.HALF_OPEN
                    logger.warning("Discogs circuit HALF_OPEN — probing")
                else:
                    raise CircuitOpenError("Discogs circuit is OPEN")

    async def record_success(self) -> None:
        async with self._lock:
            if self._state != self.CLOSED:
                logger.info("Discogs circuit CLOSED — service recovered")
            self._state = self.CLOSED
            self._consecutive_failures = 0
            self._opened_at = None

    async def record_failure(self) -> None:
        async with self._lock:
            self._consecutive_failures += 1
            if self._state == self.HALF_OPEN:
                self._state = self.OPEN
                self._opened_at = time.monotonic()
                logger.warning("Discogs probe failed — circuit OPEN again")
            elif self._consecutive_failures >= self.failure_threshold:
                if self._state != self.OPEN:
                    logger.warning(
                        "Discogs circuit OPEN after %d consecutive failures",
                        self._consecutive_failures,
                    )
                self._state = self.OPEN
                self._opened_at = time.monotonic()


discogs_circuit = _CircuitBreaker()

_CYRILLIC_RE = re.compile(r'[а-яёА-ЯЁ]')

_TRANSLIT: dict[str, str] = {
    'а': 'a',  'б': 'b',  'в': 'v',  'г': 'g',  'д': 'd',
    'е': 'e',  'ё': 'yo', 'ж': 'zh', 'з': 'z',  'и': 'i',
    'й': 'y',  'к': 'k',  'л': 'l',  'м': 'm',  'н': 'n',
    'о': 'o',  'п': 'p',  'р': 'r',  'с': 's',  'т': 't',
    'у': 'u',  'ф': 'f',  'х': 'kh', 'ц': 'ts', 'ч': 'ch',
    'ш': 'sh', 'щ': 'sch','ъ': '',   'ы': 'y',  'ь': '',
    'э': 'e',  'ю': 'yu', 'я': 'ya',
}


def _transliterate(text: str) -> str | None:
    """Транслитерирует кириллицу → латиницу. Возвращает None если кириллицы нет."""
    if not _CYRILLIC_RE.search(text):
        return None
    result = []
    for ch in text:
        lo = ch.lower()
        if lo in _TRANSLIT:
            t = _TRANSLIT[lo]
            result.append(t.upper() if ch.isupper() and t else t)
        else:
            result.append(ch)
    return ''.join(result)


class DiscogsService:
    """Сервис для работы с Discogs API"""

    BASE_URL = "https://api.discogs.com"
    _client: "httpx.AsyncClient | None" = None

    def __init__(self):
        self.api_key = settings.discogs_api_key
        self.api_secret = settings.discogs_api_secret
        self.token = settings.discogs_token
        self.user_agent = settings.discogs_user_agent

    @classmethod
    def _get_shared_client(cls) -> httpx.AsyncClient:
        """Переиспользуемый AsyncClient с connection pooling."""
        if cls._client is None or cls._client.is_closed:
            cls._client = httpx.AsyncClient(
                timeout=30.0,
                limits=httpx.Limits(
                    max_connections=10,
                    max_keepalive_connections=5,
                    keepalive_expiry=30.0,
                ),
            )
        return cls._client

    def _get_headers(self) -> dict:
        """Получение заголовков для запросов"""
        headers = {
            "User-Agent": self.user_agent,
        }
        if self.api_key:
            headers["Authorization"] = f"Discogs key={self.api_key}, secret={self.api_secret}"
        return headers

    async def _get(
        self,
        url: str,
        params: dict | None = None,
        headers: dict | None = None,
        priority: int = Priority.DETAIL,
        creds: "tuple[str, str] | None" = None,
    ) -> dict:
        """GET с token bucket rate limiter, circuit breaker и retry при 429/503.

        creds=(oauth_token, oauth_token_secret) — запрос идёт от имени юзера:
        его OAuth-подпись + его персональный rate-limit bucket. При 401 (токен
        отозван/протух) — прозрачный fallback на общий app-токен.
        """
        from app.services.rate_limiter import get_limiter

        await discogs_circuit.before_request()

        client = self._get_shared_client()
        if creds is not None:
            from app.services.discogs_oauth import sign_headers
            request_headers = sign_headers(creds[0], creds[1])
            limiter_key = creds[0]
        else:
            request_headers = headers or self._get_headers()
            limiter_key = "app"

        last_response = None
        for attempt in range(3):
            await get_limiter(limiter_key).acquire(priority=priority, timeout=30.0)
            try:
                last_response = await client.get(
                    url,
                    params=params,
                    headers=request_headers,
                    timeout=30.0,
                )
            except (httpx.HTTPError, asyncio.TimeoutError):
                await discogs_circuit.record_failure()
                if attempt < 2:
                    await asyncio.sleep(2)
                    continue
                raise

            # User-токен отозван/протух → fallback на app-токен, не валим запрос.
            if last_response.status_code == 401 and creds is not None:
                logger.warning("Discogs 401 on user token, falling back to app token")
                request_headers = self._get_headers()
                limiter_key = "app"
                creds = None
                continue

            status_code = last_response.status_code
            if status_code in (429, 503) and attempt < 2:
                retry_after = int(last_response.headers.get("Retry-After", "2"))
                logger.warning("Discogs %d, retry after %ds", status_code, retry_after)
                if status_code >= 500:
                    await discogs_circuit.record_failure()
                await asyncio.sleep(retry_after)
                continue

            if status_code >= 500:
                await discogs_circuit.record_failure()
            elif status_code < 400:
                await discogs_circuit.record_success()

            last_response.raise_for_status()
            return last_response.json()

        if last_response.status_code >= 500:
            await discogs_circuit.record_failure()
        last_response.raise_for_status()
        return last_response.json()

    @staticmethod
    def _thumb_to_cover(thumb_url: str | None) -> str | None:
        """Из URL CDN-миниатюры Discogs делает URL большего размера.
        Работает только для стабильных i.discogs.com CDN URL.
        Подписанные api-img.discogs.com URL возвращает как None — они истекают."""
        if not thumb_url or "api-img.discogs.com" in thumb_url:
            return None
        return re.sub(r'_\d+\.(jpg|jpeg|png)', r'_500.\1', thumb_url)

    async def _single_flight(
        self,
        namespace: str,
        key: str,
        loader,
        *,
        wait_total: float = 25.0,
        poll_interval: float = 0.2,
        lock_ttl: int = 30,
    ):
        """Single-flight: схлопывает параллельные запросы за одним ресурсом
        в один HTTP-вызов. Если lock не взят — polling кэша до wait_total
        секунд, потом fallback на собственный запрос.
        """
        got_lock = await cache.set_nx(f"inflight:{namespace}", key, 1, ttl=lock_ttl)
        if not got_lock:
            loop = asyncio.get_event_loop()
            deadline = loop.time() + wait_total
            while loop.time() < deadline:
                await asyncio.sleep(poll_interval)
                cached = await cache.get(namespace, key)
                if cached is not None:
                    return cached
        try:
            return await loader()
        finally:
            if got_lock:
                await cache.delete(f"inflight:{namespace}", key)

    # ------------------------------------------------------------------
    # Автодополнение (suggest)
    # ------------------------------------------------------------------

    async def suggest(
        self,
        query: str,
        per_page: int = 8,
        creds: "tuple[str, str] | None" = None,
    ) -> dict:
        """Автодополнение: один запрос к Discogs без type= (ищет всё),
        результаты разделяются по типу. 1 токен вместо 2."""
        # query передаётся в Discogs как есть (кириллица включительно) — тест без транслитерации
        params = {"q": query, "per_page": per_page}

        ck = search_cache_key({"suggest": True, **params})
        cached = await cache.get("suggest", ck)
        if cached is not None:
            return cached

        data = await self._get(
            f"{self.BASE_URL}/database/search",
            params=params,
            priority=Priority.SEARCH,
            creds=creds,
        )

        artists = []
        masters = []
        for item in data.get("results", []):
            item_type = item.get("type")
            if item_type == "artist":
                artists.append({
                    "artist_id": str(item.get("id", "")),
                    "name": item.get("title", ""),
                    "thumb": item.get("thumb"),
                })
            elif item_type == "master":
                title = item.get("title", "")
                artist_name, album_title = ("Unknown", title)
                if " - " in title:
                    parts = title.split(" - ", 1)
                    artist_name, album_title = parts[0], parts[1]
                masters.append({
                    "master_id": str(item.get("id", "")),
                    "title": album_title,
                    "artist": artist_name,
                    "year": int(item["year"]) if item.get("year") else None,
                    "thumb": item.get("thumb"),
                })

        result = {"artists": artists[:3], "masters": masters[:5]}
        # Пустую выдачу не кешируем на сутки — Discogs под rate-limit отдаёт
        # 200 с пустым results; короткий TTL чтобы не залипнуть.
        ttl = TTL_SUGGEST if (artists or masters) else TTL_SEARCH
        await cache.set("suggest", ck, result, ttl)
        return result

    # ------------------------------------------------------------------
    # Поиск (кэшируется на 10 мин)
    # ------------------------------------------------------------------

    async def search(
        self,
        query: str,
        artist: str | None = None,
        year: int | None = None,
        year_min: int | None = None,
        year_max: int | None = None,
        label: str | None = None,
        page: int = 1,
        per_page: int = 20,
        creds: "tuple[str, str] | None" = None,
    ) -> RecordSearchResponse:
        """Поиск пластинок в Discogs."""
        q_value, year_param = _build_year_query(query, year, year_min, year_max)
        params = {
            "q": q_value,
            "type": "release",
            "page": page,
            "per_page": per_page,
        }
        if artist:
            params["artist"] = artist
        if year_param is not None:
            params["year"] = year_param
        if label:
            params["label"] = label

        # Проверяем Redis-кэш
        ck = search_cache_key(params)
        cached = await cache.get("search_release", ck)
        if cached is not None:
            return RecordSearchResponse(**cached)

        # Fallback: PostgreSQL search_cache
        db_cached = await get_from_search_cache("release", params)
        if db_cached is not None:
            await cache.set("search_release", ck, db_cached, TTL_SEARCH)
            return RecordSearchResponse(**db_cached)

        data = await self._get(f"{self.BASE_URL}/database/search", params=params, priority=Priority.SEARCH, creds=creds)

        results = []
        for item in data.get("results", []):
            title = item.get("title", "")
            artist_name = "Unknown"
            album_title = title

            if " - " in title:
                parts = title.split(" - ", 1)
                artist_name = parts[0]
                album_title = parts[1] if len(parts) > 1 else title

            results.append(RecordSearchResult(
                discogs_id=str(item.get("id", "")),
                title=album_title,
                artist=artist_name,
                label=item.get("label", [None])[0] if item.get("label") else None,
                year=int(item.get("year")) if item.get("year") else None,
                country=item.get("country"),
                cover_image_url=item.get("cover_image"),
                thumb_image_url=item.get("thumb"),
                format_type=item.get("format", [None])[0] if item.get("format") else None,
            ))

        pagination = data.get("pagination", {})

        response = RecordSearchResponse(
            results=results,
            total=pagination.get("items", 0),
            page=pagination.get("page", page),
            per_page=pagination.get("per_page", per_page)
        )
        resp_dict = response.model_dump()
        await cache.set("search_release", ck, resp_dict, TTL_SEARCH)
        await save_to_search_cache("release", params, resp_dict)
        return response

    async def search_by_barcode(self, barcode: str) -> list[RecordSearchResult]:
        """Поиск пластинки по штрихкоду."""
        cached = await cache.get("barcode", barcode)
        if cached is not None:
            return [RecordSearchResult(**r) for r in cached]

        params = {
            "barcode": barcode,
            "type": "release",
        }

        db_cached = await get_from_search_cache("barcode", params)
        if db_cached is not None:
            await cache.set("barcode", barcode, db_cached, TTL_RELEASE)
            return [RecordSearchResult(**r) for r in db_cached]

        data = await self._get(f"{self.BASE_URL}/database/search", params=params, priority=Priority.SCAN)

        results = []
        for item in data.get("results", []):
            title = item.get("title", "")
            artist_name = "Unknown"
            album_title = title

            if " - " in title:
                parts = title.split(" - ", 1)
                artist_name = parts[0]
                album_title = parts[1] if len(parts) > 1 else title

            results.append(RecordSearchResult(
                discogs_id=str(item.get("id", "")),
                title=album_title,
                artist=artist_name,
                label=item.get("label", [None])[0] if item.get("label") else None,
                year=int(item.get("year")) if item.get("year") else None,
                country=item.get("country"),
                cover_image_url=item.get("cover_image"),
                thumb_image_url=item.get("thumb"),
                format_type=item.get("format", [None])[0] if item.get("format") else None,
            ))

        results_dicts = [r.model_dump() for r in results]
        await cache.set("barcode", barcode, results_dicts, TTL_RELEASE)
        await save_to_search_cache("barcode", params, results_dicts)
        return results

    # ------------------------------------------------------------------
    # Релизы (кэшируются на 7 дней)
    # ------------------------------------------------------------------

    # Пороги для is_hot — настраиваются здесь, не требуют миграции
    HOT_WANT_HAVE_RATIO = 1.5
    HOT_MIN_HAVE = 100

    # Пороги для is_collectible — комбо «дорогая + дефицит на маркете + не массовая»
    # Подобраны после анализа реальной коллекции (см. analyze_db_pricemin.py):
    # на 188 записях $50 покрывает 27% (слишком много), $100 — 14% (~1 из 7).
    COLLECTIBLE_MIN_PRICE_USD = 100.0
    COLLECTIBLE_MAX_FOR_SALE = 3
    COLLECTIBLE_MAX_HAVE = 200

    # Токены, по которым формат считается «лимиткой» (case-insensitive substring match
    # against каждого элемента formats[].descriptions из Discogs)
    LIMITED_TOKENS = (
        "test pressing",
        "promo",
        "promotional",
        "limited edition",
        "numbered",
        "ltd. ed.",
        "white label",
    )

    # Токены, по которым релиз явно помечен как оригинальный пресс
    # (используем как fallback для is_first_press, когда год не совпадает с master.year)
    FIRST_PRESS_TOKENS = (
        "first pressing",
        "first press",
        "original pressing",
        "original press",
    )

    @classmethod
    def _compute_rarity_flags(
        cls,
        release_data: dict[str, Any],
        master_data: "MasterRelease | None",
        master_versions_count: int | None = None,
        price_stats: dict | None = None,
    ) -> dict[str, bool]:
        """Compute four rarity flags from raw Discogs payloads.

        See Mobile/components/RarityAura.tsx.

        - is_canon: release is the master.main_release (community-edited canonical
          version per Discogs editors).
        - is_collectible: combo signal of actual market scarcity — высокая цена +
          мало на маркетплейсе + не массовая. Самый объективный сигнал «редкости».
        - is_limited: structural marker in formats[].descriptions
          (Limited Edition / Test Pressing / Promo / Numbered / White Label).
        - is_hot: high want/have ratio with non-trivial owner base.

        is_first_press пока НЕ вычисляется — слишком heuristic, без визуального
        осмотра matrix/runout мы не отличим оригинальный пресс от его репресса.
        Колонка в БД оставлена для безопасного rollback.
        """
        release_id = str(release_data.get("id") or "")
        is_canon = bool(
            master_data
            and master_data.main_release_id
            and release_id
            and release_id == str(master_data.main_release_id)
        )

        is_first_press = False  # тир закрыт — см. docstring

        # is_collectible: дорогая + дефицит на маркете + не массовая.
        # Цену берём median_price, при отсутствии — fallback на lowest_price
        # (median Discogs возвращает только если было ≥2 продаж — у редких
        # часто null, тогда lowest_price это «единственное предложение»).
        is_collectible = False
        community = release_data.get("community") or {}
        have = community.get("have") or 0

        def _price_value(stats: dict | None, key: str) -> float | None:
            if not stats:
                return None
            obj = stats.get(key)
            if isinstance(obj, dict):
                obj = obj.get("value")
            try:
                return float(obj) if obj is not None else None
            except (TypeError, ValueError):
                return None

        if price_stats:
            num_for_sale = price_stats.get("num_for_sale")
            try:
                num_for_sale_int = int(num_for_sale) if num_for_sale is not None else None
            except (TypeError, ValueError):
                num_for_sale_int = None
            price_usd = (
                _price_value(price_stats, "median_price")
                or _price_value(price_stats, "lowest_price")
            )

            if (
                price_usd is not None
                and num_for_sale_int is not None
                and price_usd >= cls.COLLECTIBLE_MIN_PRICE_USD
                and num_for_sale_int <= cls.COLLECTIBLE_MAX_FOR_SALE
                and have <= cls.COLLECTIBLE_MAX_HAVE
            ):
                is_collectible = True

        # is_limited: any structural marker in formats[].descriptions
        is_limited = False
        for fmt in release_data.get("formats") or []:
            for desc in fmt.get("descriptions") or []:
                if not desc:
                    continue
                lower = desc.lower()
                if any(tok in lower for tok in cls.LIMITED_TOKENS):
                    is_limited = True
                    break
            if is_limited:
                break

        # is_hot: high want/have ratio with non-trivial owner base
        is_hot = False
        want = community.get("want") or 0
        if have >= cls.HOT_MIN_HAVE and have > 0:
            ratio = want / have
            if ratio >= cls.HOT_WANT_HAVE_RATIO:
                is_hot = True

        return {
            "is_first_press": is_first_press,
            "is_canon": is_canon,
            "is_collectible": is_collectible,
            "is_limited": is_limited,
            "is_hot": is_hot,
        }

    async def get_release(self, release_id: str, priority: int = Priority.DETAIL) -> dict[str, Any]:
        """Получение детальной информации о релизе. Кэшируется в Redis.

        priority: позволяет вызывающему понизить приоритет для фоновых
        обогащений (Priority.ENRICHMENT/BATCH), чтобы они не тормозили
        UI-запросы юзера, ждущие токенов из общего бакета.
        """
        cached = await cache.get("release", release_id)
        if cached is not None:
            return cached
        return await self._single_flight(
            "release", release_id,
            lambda: self._fetch_release_uncached(release_id, priority),
        )

    async def _fetch_release_uncached(self, release_id: str, priority: int) -> dict[str, Any]:
        # Повторная проверка кэша — пока ждали lock, кто-то мог записать
        cached = await cache.get("release", release_id)
        if cached is not None:
            return cached

        # Запускаем price_stats параллельно с основным запросом
        stats_task = asyncio.create_task(self._get_price_stats(release_id))

        data = await self._get(f"{self.BASE_URL}/releases/{release_id}", priority=priority)

        # Извлекаем артистов
        artists = data.get("artists", [])
        artist_name = ", ".join([a.get("name", "") for a in artists]) if artists else "Unknown"
        artist_id = str(artists[0].get("id")) if artists else None

        # Получаем миниатюру артиста (price_stats уже идёт фоном)
        artist_thumb = None
        if artist_id:
            artist_thumb = await self._get_artist_thumb(artist_id)

        # Извлекаем лейбл
        labels = data.get("labels", [])
        label = labels[0].get("name") if labels else None
        catalog_number = labels[0].get("catno") if labels else None

        # Извлекаем жанры
        genres = data.get("genres", [])
        genre = ", ".join(genres) if genres else None

        styles = data.get("styles", [])
        style = ", ".join(styles) if styles else None

        # Извлекаем формат
        formats = data.get("formats", [])
        format_type = formats[0].get("name") if formats else None
        format_desc = ", ".join(formats[0].get("descriptions", [])) if formats else None
        vinyl_color_raw = formats[0].get("text") if formats else None

        # Извлекаем штрихкоды
        identifiers = data.get("identifiers", [])
        barcode = None
        for ident in identifiers:
            if ident.get("type") == "Barcode":
                barcode = ident.get("value")
                break

        # Извлекаем изображения
        images = data.get("images", [])
        cover_image = None
        thumb_image = None
        if images:
            cover_image = images[0].get("uri")
            thumb_image = images[0].get("uri150")

        # Извлекаем треклист
        tracklist = []
        for track in data.get("tracklist", []):
            tracklist.append({
                "position": track.get("position"),
                "title": track.get("title"),
                "duration": track.get("duration")
            })

        # Получаем ценовую статистику — к этому моменту уже должна быть готова
        price_min = None
        price_max = None
        price_median = None
        stats_response: dict | None = None
        try:
            stats_response = await stats_task
            if stats_response:
                price_min = stats_response.get("lowest_price", {}).get("value")
                price_max = stats_response.get("highest_price", {}).get("value")
                price_median = stats_response.get("median_price", {}).get("value")
        except Exception:
            logger.exception("Failed to get price stats for release %s", release_id)

        # Признаки редкости — мастер для is_canon, кол-во версий пока не нужно
        # (is_first_press закрыт), но оставляем — может пригодиться позже.
        master_data = None
        master_versions_count = None
        master_id_raw = data.get("master_id")
        if master_id_raw:
            mid = str(master_id_raw)
            try:
                master_data = await self.get_master(mid)
            except Exception:
                logger.exception(
                    "Failed to fetch master %s for rarity flags (release %s)",
                    mid, release_id,
                )
        rarity_flags = self._compute_rarity_flags(
            data,
            master_data,
            master_versions_count=master_versions_count,
            price_stats=stats_response,
        )

        result = {
            "id": str(data.get("id")),
            "master_id": str(data.get("master_id")) if data.get("master_id") else None,
            "title": data.get("title"),
            "artist": artist_name,
            "artist_id": artist_id,
            "artist_thumb_image_url": artist_thumb,
            "label": label,
            "catalog_number": catalog_number,
            "year": data.get("year"),
            "country": data.get("country"),
            "genre": genre,
            "style": style,
            "format": format_type,
            "format_description": format_desc,
            "vinyl_color_raw": vinyl_color_raw,
            "barcode": barcode,
            "cover_image": cover_image,
            "thumb_image": thumb_image,
            "tracklist": tracklist,
            "price_min": price_min,
            "price_max": price_max,
            "price_median": price_median,
            "notes": data.get("notes"),
            "data_quality": data.get("data_quality"),
            **rarity_flags,
        }
        await cache.set("release", release_id, result, TTL_RELEASE)
        return result

    # ------------------------------------------------------------------
    # Коллекция пользователя (для импорта)
    # ------------------------------------------------------------------

    async def get_collection_releases(
        self,
        username: str,
        creds: "tuple[str, str]",
        *,
        max_items: int = 3000,
    ) -> list[dict]:
        """Все релизы из коллекции юзера (folder 0 = All). Возвращает список
        basic_information dict'ов — их достаточно чтобы создать slim Record без
        per-release detail-вызова. Идёт под токеном юзера (его лимит 60/min).

        max_items — защита от гигантских коллекций; режем хвост.
        """
        per_page = 100
        page = 1
        out: list[dict] = []
        while True:
            data = await self._get(
                f"{self.BASE_URL}/users/{username}/collection/folders/0/releases",
                params={
                    "per_page": per_page,
                    "page": page,
                    "sort": "added",
                    "sort_order": "desc",
                },
                priority=Priority.DETAIL,
                creds=creds,
            )
            releases = data.get("releases", [])
            for entry in releases:
                basic = entry.get("basic_information")
                if basic:
                    out.append(basic)
                if len(out) >= max_items:
                    return out

            pagination = data.get("pagination", {})
            total_pages = pagination.get("pages", page)
            if page >= total_pages or not releases:
                break
            page += 1
        return out

    # ------------------------------------------------------------------
    # Мастер-релизы (кэшируются на 7 дней)
    # ------------------------------------------------------------------

    async def search_masters(
        self,
        query: str,
        page: int = 1,
        per_page: int = 20
    ) -> MasterSearchResponse:
        """Поиск мастер-релизов в Discogs."""
        # query передаётся в Discogs как есть (кириллица включительно) — тест без транслитерации
        params = {
            "q": query,
            "type": "master",
            "page": page,
            "per_page": per_page,
        }

        ck = search_cache_key(params)
        cached = await cache.get("search_master", ck)
        if cached is not None:
            return MasterSearchResponse(**cached)

        db_cached = await get_from_search_cache("master", params)
        if db_cached is not None:
            await cache.set("search_master", ck, db_cached, TTL_SEARCH)
            return MasterSearchResponse(**db_cached)

        data = await self._get(f"{self.BASE_URL}/database/search", params=params, priority=Priority.SEARCH)

        results = []
        for item in data.get("results", []):
            title = item.get("title", "")
            artist_name = "Unknown"
            album_title = title

            if " - " in title:
                parts = title.split(" - ", 1)
                artist_name = parts[0]
                album_title = parts[1] if len(parts) > 1 else title

            results.append(MasterSearchResult(
                master_id=str(item.get("id", "")),
                title=album_title,
                artist=artist_name,
                year=int(item.get("year")) if item.get("year") else None,
                main_release_id=str(item.get("main_release", "")),
                cover_image_url=item.get("cover_image"),
                thumb_image_url=item.get("thumb"),
            ))

        pagination = data.get("pagination", {})

        response = MasterSearchResponse(
            results=results,
            total=pagination.get("items", 0),
            page=pagination.get("page", page),
            per_page=pagination.get("per_page", per_page)
        )
        # Не кешируем пустую выдачу: Discogs под нагрузкой/rate-limit нередко
        # отдаёт 200 с пустым массивом вместо 429. Закешировав это, мы бы залипали
        # на «ничего не найдено» весь TTL даже после восстановления Discogs.
        if results:
            resp_dict = response.model_dump()
            await cache.set("search_master", ck, resp_dict, TTL_SEARCH)
            await save_to_search_cache("master", params, resp_dict)
        return response

    async def search_releases(
        self,
        query: str,
        format: str | None = None,
        country: str | None = None,
        year: int | None = None,
        year_min: int | None = None,
        year_max: int | None = None,
        page: int = 1,
        per_page: int = 20
    ) -> ReleaseSearchResponse:
        """Поиск конкретных релизов с фильтрами в Discogs."""
        q_value, year_param = _build_year_query(query, year, year_min, year_max)
        params = {
            "q": q_value,
            "type": "release",
            "page": page,
            "per_page": per_page,
        }
        if format:
            params["format"] = format
        if country:
            params["country"] = country
        if year_param is not None:
            params["year"] = year_param

        ck = search_cache_key(params)
        cached = await cache.get("search_releases", ck)
        if cached is not None:
            return ReleaseSearchResponse(**cached)

        db_cached = await get_from_search_cache("releases", params)
        if db_cached is not None:
            await cache.set("search_releases", ck, db_cached, TTL_SEARCH)
            return ReleaseSearchResponse(**db_cached)

        data = await self._get(f"{self.BASE_URL}/database/search", params=params, priority=Priority.SEARCH)

        results = []
        for item in data.get("results", []):
            title = item.get("title", "")
            artist_name = "Unknown"
            album_title = title

            if " - " in title:
                parts = title.split(" - ", 1)
                artist_name = parts[0]
                album_title = parts[1] if len(parts) > 1 else title

            format_list = item.get("format", [])
            format_str = ", ".join(format_list) if format_list else None

            label_list = item.get("label", [])
            label_str = label_list[0] if label_list else None

            catno_list = item.get("catno", []) if isinstance(item.get("catno"), list) else [item.get("catno")] if item.get("catno") else []
            catno_str = catno_list[0] if catno_list else None

            results.append(ReleaseSearchResult(
                release_id=str(item.get("id", "")),
                title=album_title,
                artist=artist_name,
                label=label_str,
                catalog_number=catno_str,
                country=item.get("country"),
                year=int(item.get("year")) if item.get("year") else None,
                format=format_str,
                cover_image_url=item.get("cover_image"),
                thumb_image_url=item.get("thumb"),
            ))

        pagination = data.get("pagination", {})

        response = ReleaseSearchResponse(
            results=results,
            total=pagination.get("items", 0),
            page=pagination.get("page", page),
            per_page=pagination.get("per_page", per_page)
        )
        # Не кешируем пустую выдачу (см. search_masters): защита от залипания на
        # пустом ответе Discogs при rate-limit/деградации.
        if results:
            resp_dict = response.model_dump()
            await cache.set("search_releases", ck, resp_dict, TTL_SEARCH)
            await save_to_search_cache("releases", params, resp_dict)
        return response

    async def get_master(self, master_id: str) -> MasterRelease:
        """Получение информации о мастер-релизе. Кэшируется в Redis."""
        cached = await cache.get("master", master_id)
        if cached is not None:
            return MasterRelease(**cached)
        result = await self._single_flight(
            "master", master_id,
            lambda: self._fetch_master_uncached(master_id),
        )
        if isinstance(result, MasterRelease):
            return result
        return MasterRelease(**result)

    async def _fetch_master_uncached(self, master_id: str) -> MasterRelease:
        # Повторная проверка кэша — пока ждали lock, кто-то мог записать
        cached = await cache.get("master", master_id)
        if cached is not None:
            return MasterRelease(**cached)

        data = await self._get(f"{self.BASE_URL}/masters/{master_id}", priority=Priority.DETAIL)

        artists = data.get("artists", [])
        artist_name = ", ".join([a.get("name", "") for a in artists]) if artists else "Unknown"
        artist_id = str(artists[0].get("id")) if artists else None

        artist_thumb = None
        if artist_id:
            artist_thumb = await self._get_artist_thumb(artist_id)

        images = data.get("images", [])
        cover_image = images[0].get("uri") if images else None

        tracklist = [
            {
                "position": track.get("position"),
                "title": track.get("title"),
                "duration": track.get("duration"),
            }
            for track in data.get("tracklist", [])
            if track.get("type_", "track") == "track"
        ]

        result = MasterRelease(
            master_id=str(data.get("id")),
            title=data.get("title", ""),
            artist=artist_name,
            artist_id=artist_id,
            artist_thumb_image_url=artist_thumb,
            year=data.get("year"),
            main_release_id=str(data.get("main_release")),
            genres=data.get("genres", []),
            styles=data.get("styles", []),
            cover_image_url=cover_image,
            tracklist=tracklist or None,
        )
        await cache.set("master", master_id, result.model_dump(), TTL_MASTER)
        return result

    async def get_master_versions(
        self,
        master_id: str,
        page: int = 1,
        per_page: int = 50,
        creds: "tuple[str, str] | None" = None,
    ) -> MasterVersionsResponse:
        """Получение всех версий (изданий) мастер-релиза. Кэшируется в Redis.

        creds — OAuth юзера: запрос идёт через его персональный bucket (60/min),
        а не общий app-bucket. Критично для inline-фетча обложек на экране версий:
        под нагрузкой app-bucket дренится и inline таймаутится → список без обложек.
        """
        ck = f"v2:{master_id}:p{page}:pp{per_page}"
        cached = await cache.get("master_versions", ck)
        if cached is not None:
            return MasterVersionsResponse(**cached)

        params = {
            "page": page,
            "per_page": per_page,
        }

        data = await self._get(f"{self.BASE_URL}/masters/{master_id}/versions", params=params, priority=Priority.DETAIL, creds=creds)

        results = []
        for item in data.get("versions", []):
            format_info = item.get("format", "")
            label = item.get("label", "")
            catalog_number = item.get("catno", "")

            major_formats = item.get("major_formats", [])

            # is_hot из stats.community прямо в master-versions response
            # (without N+1 на /releases/{id}). Discogs отдаёт in_collection
            # и in_wantlist по каждой версии.
            stats = item.get("stats") or {}
            community = stats.get("community") or {}
            have = int(community.get("in_collection") or 0)
            want = int(community.get("in_wantlist") or 0)
            is_hot = (
                have >= self.HOT_MIN_HAVE
                and have > 0
                and (want / have) >= self.HOT_WANT_HAVE_RATIO
            )

            results.append(MasterVersion(
                release_id=str(item.get("id", "")),
                title=item.get("title", ""),
                label=label if label else None,
                catalog_number=catalog_number if catalog_number else None,
                country=item.get("country"),
                year=int(item.get("released")) if item.get("released") else None,
                format=format_info if format_info else None,
                major_formats=major_formats if major_formats else [],
                thumb_image_url=item.get("thumb"),
                cover_image_url=self._thumb_to_cover(item.get("thumb")),
                is_hot=is_hot,
            ))

        pagination = data.get("pagination", {})

        response = MasterVersionsResponse(
            results=results,
            total=pagination.get("items", 0),
            page=pagination.get("page", page),
            per_page=pagination.get("per_page", per_page)
        )
        await cache.set("master_versions", ck, response.model_dump(), TTL_MASTER_VERSIONS)
        return response

    # ------------------------------------------------------------------
    # Артисты (кэшируются на 3 дня)
    # ------------------------------------------------------------------

    async def search_artists(
        self,
        query: str,
        page: int = 1,
        per_page: int = 20
    ) -> ArtistSearchResponse:
        """Поиск артистов в Discogs."""
        # query передаётся в Discogs как есть (кириллица включительно) — тест без транслитерации
        params = {
            "q": query,
            "type": "artist",
            "page": page,
            "per_page": per_page,
        }

        ck = search_cache_key(params)
        cached = await cache.get("search_artist", ck)
        if cached is not None:
            return ArtistSearchResponse(**cached)

        db_cached = await get_from_search_cache("artists", params)
        if db_cached is not None:
            await cache.set("search_artist", ck, db_cached, TTL_SEARCH)
            return ArtistSearchResponse(**db_cached)

        data = await self._get(f"{self.BASE_URL}/database/search", params=params, priority=Priority.SEARCH)

        results = []
        for item in data.get("results", []):
            thumb = item.get("thumb")
            if not thumb:
                continue
            results.append(ArtistSearchResult(
                artist_id=str(item.get("id", "")),
                name=item.get("title", "Unknown"),
                cover_image_url=item.get("cover_image"),
                thumb_image_url=thumb,
            ))

        # Фильтруем артистов, у которых уже известно что релизов нет (псевдонимы)
        if results:
            empty_flags = await asyncio.gather(
                *[cache.get("artist_empty", r.artist_id) for r in results]
            )
            results = [r for r, is_empty in zip(results, empty_flags) if not is_empty]

        pagination = data.get("pagination", {})

        response = ArtistSearchResponse(
            results=results,
            total=pagination.get("items", 0),
            page=pagination.get("page", page),
            per_page=pagination.get("per_page", per_page)
        )
        # Кешируем по сырому ответу Discogs, а не по отфильтрованным results:
        # results может легитимно опустеть после фильтра псевдонимов/без-thumb,
        # хотя Discogs реально что-то вернул — это валидно кешировать. Но если
        # Discogs отдал пустоту целиком (rate-limit/деградация) — не кешируем,
        # чтобы не залипать на «ничего не найдено».
        if data.get("results"):
            resp_dict = response.model_dump()
            await cache.set("search_artist", ck, resp_dict, TTL_SEARCH)
            await save_to_search_cache("artists", params, resp_dict)
        return response

    async def get_artist(self, artist_id: str) -> Artist:
        """Получение информации об артисте. Кэшируется в Redis."""
        cached = await cache.get("artist", artist_id)
        if cached is not None:
            return Artist(**cached)

        data = await self._get(f"{self.BASE_URL}/artists/{artist_id}", priority=Priority.DETAIL)

        images = data.get("images", [])
        image_urls = [img.get("uri") for img in images if img.get("uri")]

        result = Artist(
            artist_id=str(data.get("id")),
            name=data.get("name", "Unknown"),
            profile=data.get("profile"),
            images=image_urls,
        )
        await cache.set("artist", artist_id, result.model_dump(), TTL_ARTIST)
        return result

    async def get_artist_releases(
        self,
        artist_id: str,
        page: int = 1,
        per_page: int = 50
    ) -> ReleaseSearchResponse:
        """Получение релизов артиста."""
        ck = f"{artist_id}:p{page}:pp{per_page}"
        cached = await cache.get("artist_releases", ck)
        if cached is not None:
            return ReleaseSearchResponse(**cached)

        params = {
            "page": page,
            "per_page": per_page,
        }

        data = await self._get(f"{self.BASE_URL}/artists/{artist_id}/releases", params=params, priority=Priority.DETAIL)

        results = []
        for item in data.get("releases", []):
            title = item.get("title", "")
            artist_name = item.get("artist", "Unknown")
            year = item.get("year")
            format_info = item.get("format", "")
            label = item.get("label", "")

            thumb = item.get("thumb")
            results.append(ReleaseSearchResult(
                release_id=str(item.get("id", "")),
                title=title,
                artist=artist_name,
                label=label if label else None,
                catalog_number=None,
                country=None,
                year=int(year) if year else None,
                format=format_info if format_info else None,
                cover_image_url=self._thumb_to_cover(thumb),
                thumb_image_url=thumb,
            ))

        pagination = data.get("pagination", {})

        response = ReleaseSearchResponse(
            results=results,
            total=pagination.get("items", 0),
            page=pagination.get("page", page),
            per_page=pagination.get("per_page", per_page)
        )
        await cache.set("artist_releases", ck, response.model_dump(), TTL_ARTIST)
        return response

    # ------------------------------------------------------------------
    # Внутренние методы
    # ------------------------------------------------------------------

    async def _get_master_info(self, master_id: str) -> dict:
        """Обложка (`images[0].uri`, полноразмер) и тип релиза по track count
        для `/masters/{id}`. Используется как fallback на странице артиста,
        когда мастер не нашёлся в Search API.

        Без `asyncio.wait_for`: rate limiter уже даёт свой timeout (ENRICHMENT
        priority, 120с в очереди). Обёртка в 10с заставляла последние ~40 из
        100 запросов проваливаться по тайм-ауту ещё до HTTP и возвращать
        cover=None без кэширования → следующий заход падал в тот же цикл.

        Положительный результат кэшируется на TTL_MASTER_INFO (7 дней);
        отрицательный — на 1 час, чтобы не дёргать упавший мастер постоянно.
        """
        cached = await cache.get("master_info", master_id)
        if cached is not None:
            return cached

        try:
            data = await self._get(
                f"{self.BASE_URL}/masters/{master_id}",
                priority=Priority.ENRICHMENT,
            )
        except Exception:
            logger.exception("Failed to get master info for %s", master_id)
            neg = {"cover": None, "release_type": None}
            await cache.set("master_info", master_id, neg, 3600)
            return neg

        cover = None
        images = data.get("images", [])
        if images:
            cover = images[0].get("uri")

        tracklist = data.get("tracklist", [])
        track_count = sum(
            1 for t in tracklist if t.get("type_", "track") == "track"
        )

        if track_count <= 3:
            release_type = "single"
        elif track_count <= 6:
            release_type = "ep"
        else:
            release_type = "album"

        result = {"cover": cover, "release_type": release_type}
        await cache.set("master_info", master_id, result, TTL_MASTER_INFO)
        return result

    async def get_release_cover(self, release_id: str) -> str | None:
        """Только обложка релиза (`images[0].uri`), без фан-аута на artist
        thumb / price stats / master — 1 API-вызов вместо 4. Для фонового
        прогрева обложек dump-строк (cover_warm).

        Если полный payload уже в кэше release — берём оттуда бесплатно.
        Negative cache на 1 час.
        """
        cached_release = await cache.get("release", release_id)
        if cached_release is not None:
            return cached_release.get("cover_image")

        cached = await cache.get("release_cover", release_id)
        if cached is not None:
            return cached.get("cover") if isinstance(cached, dict) else None

        try:
            data = await self._get(
                f"{self.BASE_URL}/releases/{release_id}",
                priority=Priority.ENRICHMENT,
            )
        except Exception:
            logger.debug("get_release_cover failed for %s", release_id, exc_info=True)
            await cache.set("release_cover", release_id, {"cover": None}, 3600)
            return None

        images = data.get("images", [])
        cover = images[0].get("uri") if images else None
        ttl = TTL_RELEASE if cover else 3600
        await cache.set("release_cover", release_id, {"cover": cover}, ttl)
        return cover

    async def _get_artist_thumb(self, artist_id: str) -> str | None:
        """Получение миниатюры артиста по ID. Кэшируется в Redis на 30 дней.
        Negative cache на 404 — артисты без фото не дёргают Discogs повторно."""
        cached = await cache.get("artist_thumb", artist_id)
        if cached is not None:
            return cached
        if await cache.exists("artist_thumb_404", artist_id):
            return None

        try:
            data = await self._get(f"{self.BASE_URL}/artists/{artist_id}", priority=Priority.ENRICHMENT)
            images = data.get("images", [])
            if images:
                thumb = images[0].get("uri150") or images[0].get("uri")
                await cache.set("artist_thumb", artist_id, thumb, TTL_ARTIST_THUMB)
                return thumb
            await cache.set("artist_thumb_404", artist_id, True, TTL_ARTIST_THUMB)
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                await cache.set("artist_thumb_404", artist_id, True, TTL_ARTIST_THUMB)
            else:
                logger.exception("Failed to get artist thumb for %s", artist_id)
        except Exception:
            logger.exception("Failed to get artist thumb for %s", artist_id)
        return None

    @staticmethod
    def _guess_release_type(format_str: str | None) -> str | None:
        """Определение типа релиза по строке формата из Discogs releases endpoint.
        Discogs возвращает format как строку вида '12", Album' или 'CD, Single' и т.д.
        """
        if not format_str:
            return "album"
        fmt = format_str.lower()
        if "single" in fmt:
            return "single"
        if "ep" in fmt or "mini" in fmt:
            return "ep"
        if "album" in fmt or "lp" in fmt or "compilation" in fmt:
            return "album"
        return "album"

    async def get_artist_masters(
        self,
        artist_id: str,
        page: int = 1,
        per_page: int = 100,
        load_all: bool = False,
        sort_order: str = "desc",
        creds: "tuple[str, str] | None" = None,
    ) -> MasterSearchResponse:
        """Master releases артиста по `docs/plans/PRINCIPLES.md`.

        Список — канонический из `/artists/{id}/releases` (фильтр
        `type=master AND role=Main`: своя дискография, без appearances и
        featuring). Гарантирует точный artist_id без шума однофамильцев.

        Обложки — гибрид по принципам:
        1. Один batch-вызов Search API (`/database/search?type=master&artist={name}`)
           с exact-матчингом по master_id. Закрывает большинство популярных мастеров
           одним вызовом (~1с) вместо N вызовов `/masters/{id}`.
        2. Для непокрытых мастеров — параллельный fallback на `_get_master_info`
           (`/masters/{id}`, `images[0].uri`, полноразмер). Первый визит на нового
           артиста медленнее, дальше кэш TTL_MASTER_INFO (7 дней) делает мгновенно.
        3. `thumb` из `/artists/{id}/releases` как fallback **не используется** —
           150px пиксельно. Лучше `cover_image_url=None`, чем плохая обложка.

        Кэшируется в Redis на TTL_ARTIST_MASTERS.
        """
        sort_order = "asc" if sort_order == "asc" else "desc"
        ck = f"{artist_id}:v10:p{page}:pp{per_page}:{sort_order}"
        cached = await cache.get("artist_masters", ck)
        if cached is not None:
            return MasterSearchResponse(**cached)

        # Имя артиста — для поля `artist` в результатах и параметра Search API.
        artist_name = ""
        artist_data = await cache.get("artist", artist_id)
        if artist_data:
            artist_name = artist_data.get("name", "")
        if not artist_name:
            try:
                artist_obj = await self.get_artist(artist_id)
                artist_name = artist_obj.name
            except Exception:
                pass

        if not artist_name:
            return MasterSearchResponse(results=[], total=0, page=page, per_page=per_page)

        # 1) Канонический список master_id по этому artist_id.
        data = await self._get(
            f"{self.BASE_URL}/artists/{artist_id}/releases",
            params={
                "page": page,
                "per_page": per_page,
                "sort": "year",
                "sort_order": sort_order,
            },
            priority=Priority.SEARCH,
            creds=creds,
        )

        masters: list[dict] = []
        seen_ids: set[str] = set()
        # Release-only айтемы (role=Main, type=release) — у артиста нет master-
        # группировки (частый кейс японского/инди: мелкая дискография, синглы без
        # master). Без них экран артиста пуст, хотя на Discogs релизы есть.
        # Собираем отдельно и добавляем фолбэком, дедуп по нормализованному title.
        release_items: list[dict] = []
        master_titles: set[str] = set()
        for item in data.get("releases", []):
            if item.get("role") != "Main":
                continue
            item_id = str(item.get("id", ""))
            if not item_id or item_id in seen_ids:
                continue
            seen_ids.add(item_id)
            if item.get("type") == "master":
                masters.append(item)
                master_titles.add((item.get("title") or "").strip().lower())
            elif item.get("type") == "release":
                release_items.append(item)

        # 2) Обложки batch через Search API; exact match по master_id.
        search_by_id: dict[str, dict] = {}
        if masters:
            clean_name = clean_artist_name(artist_name)
            try:
                search_data = await self._get(
                    f"{self.BASE_URL}/database/search",
                    params={
                        "type": "master",
                        "artist": clean_name,
                        "page": page,
                        "per_page": 100,
                    },
                    priority=Priority.SEARCH,
                    creds=creds,
                )
                for s in search_data.get("results", []):
                    sid = str(s.get("id", ""))
                    if sid:
                        search_by_id[sid] = s
            except Exception:
                logger.exception("Search API for artist masters covers failed: %s", artist_id)

        # 3) Параллельный fallback /masters/{id} для тех, кого Search не покрыл.
        # Раньше этот gather блокировал весь ответ на N×/masters/{id} (до ~100
        # вызовов, ENRICHMENT-приоритет, до 120с в очереди каждый). Под нагрузкой
        # app-bucket'а эндпоинт висел >60с → axios timeout на клиенте, экран
        # артиста падал в «Ошибка загрузки релизов».
        # Теперь ограничиваем общим watchdog'ом: вернувшиеся обложки используем,
        # остаток — None (добьётся при следующем заходе, каждый _get_master_info
        # кэшируется индивидуально на 7 дней). covers_complete управляет TTL,
        # чтобы частичный ответ не залип надолго.
        missing_ids = [str(m["id"]) for m in masters if str(m["id"]) not in search_by_id]
        info_by_id: dict[str, dict] = {}
        covers_complete = True
        if missing_ids:
            tasks = {
                mid: asyncio.create_task(self._get_master_info(mid))
                for mid in missing_ids
            }
            done, pending = await asyncio.wait(tasks.values(), timeout=6)
            for mid, t in tasks.items():
                if t in done and not t.cancelled():
                    try:
                        res = t.result()
                        if isinstance(res, dict):
                            info_by_id[mid] = res
                    except Exception:
                        pass
            if pending:
                covers_complete = False
                for t in pending:
                    t.cancel()

        # 4) Сборка результатов: cover приоритет Search → master_info → None.
        all_results: list[MasterSearchResult] = []
        for item in masters:
            item_id = str(item["id"])
            s = search_by_id.get(item_id)
            info = info_by_id.get(item_id)

            cover_image_url: str | None = None
            thumb_image_url: str | None = None
            release_type: str | None = None

            if s:
                cover = s.get("cover_image")
                # cover_image от Search API — стабильный i.discogs.com URL (~500px).
                # Подписанные api-img.discogs.com URL отбрасываем — они истекают.
                if cover and "api-img.discogs.com" not in cover:
                    cover_image_url = cover
                thumb_image_url = s.get("thumb")
                formats = s.get("format", [])
                format_str = ", ".join(formats) if formats else None
                release_type = self._guess_release_type(format_str)

            if cover_image_url is None and info is not None:
                cover_image_url = info.get("cover")
                if release_type is None:
                    release_type = info.get("release_type")

            # Тип релиза fallback: строка format из /artists/{id}/releases.
            if release_type is None:
                release_type = self._guess_release_type(item.get("format"))

            try:
                year = int(item["year"]) if item.get("year") else None
            except (ValueError, TypeError):
                year = None

            all_results.append(MasterSearchResult(
                master_id=item_id,
                title=item.get("title", ""),
                artist=artist_name,
                year=year,
                main_release_id=item_id,
                cover_image_url=cover_image_url,
                thumb_image_url=thumb_image_url,
                release_type=release_type,
            ))

        # Release-only обложки (~500px) одним batch type=release Search, exact
        # match по release id. thumb из /artists/{id}/releases — 150px (пиксельно),
        # потому отдельный запрос как для masters. Падение — graceful, остаётся
        # thumb.
        release_cover_by_id: dict[str, str] = {}
        if release_items:
            try:
                rsearch = await self._get(
                    f"{self.BASE_URL}/database/search",
                    params={
                        "type": "release",
                        "artist": clean_artist_name(artist_name),
                        "page": page,
                        "per_page": 100,
                    },
                    priority=Priority.SEARCH,
                    creds=creds,
                )
                for s in rsearch.get("results", []):
                    sid = str(s.get("id", ""))
                    cover = s.get("cover_image")
                    if sid and cover and "api-img.discogs.com" not in cover:
                        release_cover_by_id[sid] = cover
            except Exception:
                logger.exception("Search API for artist release covers failed: %s", artist_id)

        # Release-only фолбэк: master_id="r{release_id}" (префикс) сигналит
        # бэкенду /masters/{id} синтезировать карточку из релиза, а main_release_id
        # несёт чистый discogs release id. Префикс нужен, чтобы СТАРЫЙ билд app
        # (роутит всё через /master/{master_id}) открывал такие айтемы — пустой
        # master_id давал путь /master/ → expo-router +not-found. Дедуп по title —
        # релиз, уже представленный мастером, не дублируем.
        for item in release_items:
            title = item.get("title", "")
            if title.strip().lower() in master_titles:
                continue
            item_id = str(item["id"])
            try:
                year = int(item["year"]) if item.get("year") else None
            except (ValueError, TypeError):
                year = None
            thumb = item.get("thumb") or None
            all_results.append(MasterSearchResult(
                master_id=f"r{item_id}",
                title=title,
                artist=artist_name,
                year=year,
                main_release_id=item_id,
                cover_image_url=release_cover_by_id.get(item_id) or thumb,
                thumb_image_url=thumb,
                release_type=self._guess_release_type(item.get("format")),
            ))

        pagination = data.get("pagination", {})
        total_items = pagination.get("items", len(all_results))
        total_pages = pagination.get("pages", 1)
        has_more = page < total_pages
        next_cursor = page + 1 if has_more else None

        # «Пустой артист» — только когда у artist_id вообще нет релизов.
        # Сохраняет фильтрацию пустых алиасов в search_artists.
        if page == 1 and pagination.get("items", 0) == 0:
            await cache.set("artist_empty", artist_id, True, 7 * 86400)

        response = MasterSearchResponse(
            results=all_results,
            total=total_items,
            page=page,
            per_page=per_page,
            has_more=has_more,
            next_cursor=next_cursor,
        )
        # Частичный ответ (covers ещё догружаются) кэшируем коротко, чтобы
        # следующий заход добрал недостающие обложки из per-master кэша.
        ttl = TTL_ARTIST_MASTERS if covers_complete else 90
        await cache.set("artist_masters", ck, response.model_dump(), ttl)
        return response

    # ------------------------------------------------------------------
    # Цены
    # ------------------------------------------------------------------

    def _get_token_headers(self) -> dict:
        """Заголовки с personal access token (нужен для median/highest price)"""
        headers = {"User-Agent": self.user_agent}
        if self.token:
            headers["Authorization"] = f"Discogs token={self.token}"
        elif self.api_key:
            headers["Authorization"] = f"Discogs key={self.api_key}, secret={self.api_secret}"
        return headers

    async def _get_master_versions_count(self, master_id: str) -> int | None:
        """Кол-во версий у мастера. Тянем минимум данных (per_page=1) и читаем
        pagination.items. Кэшируется на TTL_MASTER_VERSIONS."""
        cache_key = f"count:{master_id}"
        cached = await cache.get("master_versions", cache_key)
        if cached is not None:
            return cached.get("count") if isinstance(cached, dict) else None
        try:
            data = await self._get(
                f"{self.BASE_URL}/masters/{master_id}/versions",
                params={"page": 1, "per_page": 1},
                priority=Priority.ENRICHMENT,
            )
            count = (data.get("pagination") or {}).get("items")
            if count is not None:
                await cache.set(
                    "master_versions", cache_key, {"count": int(count)}, TTL_MASTER_VERSIONS,
                )
                return int(count)
        except Exception:
            logger.exception("Failed to get versions count for master %s", master_id)
        return None

    async def _get_price_stats(self, release_id: str) -> dict | None:
        """Получение статистики цен для релиза (всегда в USD).
        Кэшируется в Redis на 6 часов. Negative cache на 404."""
        cached = await cache.get("price_stats", release_id)
        if cached is not None:
            return cached
        if await cache.exists("price_stats_404", release_id):
            return None

        try:
            result = await self._get(
                f"{self.BASE_URL}/marketplace/stats/{release_id}",
                params={"curr_abbr": "USD"},
                headers=self._get_token_headers(),
                priority=Priority.ENRICHMENT,
            )
            await cache.set("price_stats", release_id, result, TTL_PRICE_STATS)
            return result
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                await cache.set("price_stats_404", release_id, True, TTL_PRICE_STATS)
            else:
                logger.exception("Failed to get price stats for release %s", release_id)
        except Exception:
            logger.exception("Failed to get price stats for release %s", release_id)
        return None

    # ------------------------------------------------------------------
    # Новинки — глобальный пул свежих релизов с Discogs
    # ------------------------------------------------------------------

    # Параметры гибрида витрины новинок (окно по дате × популярность).
    NEW_RELEASES_WINDOW_DAYS = 90       # «свежесть»: релизы за последние N дней
    NEW_RELEASES_POOL_PER_PAGE = 100    # размер want-пула на год (1 страница)
    NEW_RELEASES_MAX_ENRICH = 60        # cap detail-вызовов на холодный кэш
    NEW_RELEASES_TTL = 31 * 24 * 3600   # «снимок на месяц»

    @staticmethod
    def _parse_release_date(raw: str | None) -> "date | None":
        """Discogs `released`: 'YYYY-MM-DD' | 'YYYY-MM' | 'YYYY' | ''.

        Возвращает date только при ПОЛНОЙ дате (YYYY-MM-DD) — иначе нельзя
        достоверно сказать, попадает ли релиз в 90-дневное окно.
        """
        from datetime import date as _date
        if not raw:
            return None
        parts = raw.split("-")
        if len(parts) != 3:
            return None
        try:
            y, m, d = int(parts[0]), int(parts[1]), int(parts[2])
            if m == 0 or d == 0:
                return None
            return _date(y, m, d)
        except (ValueError, TypeError):
            return None

    @staticmethod
    def _simplify_search_item(item: dict, fallback_year: int) -> dict | None:
        """Сырой результат /database/search → упрощённый dict для апсерта."""
        release_id = item.get("id")
        if not release_id:
            return None
        full_title = item.get("title", "") or ""
        artist_name, album_title = "Unknown", full_title
        if " - " in full_title:
            parts = full_title.split(" - ", 1)
            artist_name, album_title = parts[0].strip(), parts[1].strip()
        community = item.get("community") or {}
        cover = item.get("cover_image") or item.get("thumb")
        master_id = item.get("master_id")
        label_list = item.get("label") or []
        format_list = item.get("format") or []
        return {
            "discogs_id": str(release_id),
            "discogs_master_id": str(master_id) if master_id else None,
            "title": album_title or full_title or "Unknown",
            "artist": artist_name or "Unknown",
            "year": int(item["year"]) if item.get("year") else fallback_year,
            "label": label_list[0] if label_list else None,
            "format_type": format_list[0] if format_list else None,
            "country": item.get("country"),
            "cover_image_url": cover,
            "thumb_image_url": item.get("thumb"),
            "want": int(community.get("want") or 0),
            "have": int(community.get("have") or 0),
        }

    async def search_new_releases(
        self,
        limit: int = 40,
        window_days: int | None = None,
    ) -> list[dict]:
        """Витрина новинок: гибрид «свежесть × популярность».

        Шаги:
          1. Тянем want-пул текущего года (`sort=want desc`), при необходимости
             добавляем прошлый год — если 90-дневное окно пересекает 1 января.
          2. Идём по want-порядку, обогащаем release-detail (`released`) и берём
             релизы, чья ПОЛНАЯ дата попадает в окно `[today - window, today]`.
             Detail-вызовы кэшируются (TTL_RELEASE), всего ≤ NEW_RELEASES_MAX_ENRICH.
          3. Fallback: если в окне набралось < limit — добиваем оставшимися по
             want-порядку, чтобы рейл не пустел (свежесть приоритетна, но не ценой
             пустой витрины).

        Want-порядок сохраняется внутри обеих групп. Кэш — namespace `new_releases`,
        TTL 31 день; принудительный сброс делает scheduled-задача refresh_new_releases.
        """
        from datetime import datetime as _dt, timedelta as _td

        window_days = window_days or self.NEW_RELEASES_WINDOW_DAYS
        today = _dt.utcnow().date()
        cutoff = today - _td(days=window_days)

        cache_key = f"hybrid_w{window_days}_l{limit}"
        cached = await cache.get("new_releases", cache_key)
        if cached is not None:
            return cached

        years = [today.year] if cutoff.year == today.year else [today.year, cutoff.year]

        candidates: list[dict] = []
        for yr in years:
            params = {
                "type": "release",
                "year": str(yr),
                "format": "Vinyl",
                "sort": "want",
                "sort_order": "desc",
                "per_page": self.NEW_RELEASES_POOL_PER_PAGE,
                "page": 1,
            }
            try:
                data = await self._get(
                    f"{self.BASE_URL}/database/search",
                    params=params,
                    headers=self._get_token_headers(),
                    priority=Priority.SEARCH,
                )
            except Exception:
                logger.exception("Failed to fetch new-releases pool for year %s", yr)
                continue
            for raw in data.get("results", []):
                simple = self._simplify_search_item(raw, yr)
                if simple:
                    candidates.append(simple)

        if not candidates:
            return []

        # Единый want-порядок по всему пулу (между годами).
        candidates.sort(key=lambda x: x["want"], reverse=True)

        in_window: list[dict] = []
        leftovers: list[dict] = []
        checked = 0
        for cand in candidates:
            if len(in_window) >= limit:
                leftovers.append(cand)
                continue
            if checked >= self.NEW_RELEASES_MAX_ENRICH:
                leftovers.append(cand)
                continue
            checked += 1
            try:
                detail = await self._get(
                    f"{self.BASE_URL}/releases/{cand['discogs_id']}",
                    headers=self._get_token_headers(),
                    priority=Priority.SEARCH,
                )
            except Exception:
                logger.debug("new-releases: detail fetch failed for %s", cand["discogs_id"])
                leftovers.append(cand)
                continue
            released = self._parse_release_date(detail.get("released"))
            if released is not None and cutoff <= released <= today:
                cand["released"] = released.isoformat()
                in_window.append(cand)
            else:
                leftovers.append(cand)

        # Свежие (в окне) первыми, затем fallback по want — до limit.
        out = in_window[:limit]
        if len(out) < limit:
            out += leftovers[: limit - len(out)]

        await cache.set("new_releases", cache_key, out, self.NEW_RELEASES_TTL)
        logger.info(
            "search_new_releases: %d in-window, %d total (window=%dd, checked=%d)",
            len(in_window), len(out), window_days, checked,
        )
        return out
