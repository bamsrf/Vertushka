"""
Сервис для работы с Discogs API.
Кэширование через Redis (graceful fallback на работу без кэша).
"""
import asyncio
import logging
import re

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
    TTL_PRICE_STATS,
    TTL_MASTER_VERSIONS,
    TTL_MASTER_INFO,
)
from app.services.search_cache_db import get_from_search_cache, save_to_search_cache
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
    ) -> dict:
        """GET с token bucket rate limiter и retry при 429/503."""
        client = self._get_shared_client()
        request_headers = headers or self._get_headers()

        last_response = None
        for attempt in range(3):
            await discogs_limiter.acquire(priority=priority, timeout=30.0)
            last_response = await client.get(
                url,
                params=params,
                headers=request_headers,
                timeout=30.0,
            )
            if last_response.status_code in (429, 503) and attempt < 2:
                retry_after = int(last_response.headers.get("Retry-After", "2"))
                logger.warning("Discogs %d, retry after %ds", last_response.status_code, retry_after)
                await asyncio.sleep(retry_after)
                continue
            last_response.raise_for_status()
            return last_response.json()
        last_response.raise_for_status()
        return last_response.json()

    @staticmethod
    def _thumb_to_cover(thumb_url: str | None) -> str | None:
        """Из URL CDN-миниатюры Discogs делает URL большего размера.
        Discogs CDN: https://i.discogs.com/[hash]_[size].ext"""
        if not thumb_url:
            return None
        return re.sub(r'_\d+\.(jpg|jpeg|png)', r'_500.\1', thumb_url)

    # ------------------------------------------------------------------
    # Поиск (кэшируется на 10 мин)
    # ------------------------------------------------------------------

    async def search(
        self,
        query: str,
        artist: str | None = None,
        year: int | None = None,
        label: str | None = None,
        page: int = 1,
        per_page: int = 20
    ) -> RecordSearchResponse:
        """Поиск пластинок в Discogs."""
        params = {
            "q": query,
            "type": "release",
            "page": page,
            "per_page": per_page,
        }
        if artist:
            params["artist"] = artist
        if year:
            params["year"] = year
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

    async def get_release(self, release_id: str) -> dict[str, Any]:
        """Получение детальной информации о релизе. Кэшируется в Redis."""
        cached = await cache.get("release", release_id)
        if cached is not None:
            return cached

        # Запускаем price_stats параллельно с основным запросом
        stats_task = asyncio.create_task(self._get_price_stats(release_id))

        data = await self._get(f"{self.BASE_URL}/releases/{release_id}", priority=Priority.DETAIL)

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
        try:
            stats_response = await stats_task
            if stats_response:
                price_min = stats_response.get("lowest_price", {}).get("value")
                price_max = stats_response.get("highest_price", {}).get("value")
                price_median = stats_response.get("median_price", {}).get("value")
        except Exception:
            logger.exception("Failed to get price stats for release %s", release_id)

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
            "barcode": barcode,
            "cover_image": cover_image,
            "thumb_image": thumb_image,
            "tracklist": tracklist,
            "price_min": price_min,
            "price_max": price_max,
            "price_median": price_median,
            "notes": data.get("notes"),
            "data_quality": data.get("data_quality"),
        }
        await cache.set("release", release_id, result, TTL_RELEASE)
        return result

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
        page: int = 1,
        per_page: int = 20
    ) -> ReleaseSearchResponse:
        """Поиск конкретных релизов с фильтрами в Discogs."""
        params = {
            "q": query,
            "type": "release",
            "page": page,
            "per_page": per_page,
        }
        if format:
            params["format"] = format
        if country:
            params["country"] = country
        if year:
            params["year"] = year

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
        resp_dict = response.model_dump()
        await cache.set("search_releases", ck, resp_dict, TTL_SEARCH)
        await save_to_search_cache("releases", params, resp_dict)
        return response

    async def get_master(self, master_id: str) -> MasterRelease:
        """Получение информации о мастер-релизе. Кэшируется в Redis."""
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
        per_page: int = 50
    ) -> MasterVersionsResponse:
        """Получение всех версий (изданий) мастер-релиза. Кэшируется в Redis."""
        ck = f"{master_id}:p{page}:pp{per_page}"
        cached = await cache.get("master_versions", ck)
        if cached is not None:
            return MasterVersionsResponse(**cached)

        params = {
            "page": page,
            "per_page": per_page,
        }

        data = await self._get(f"{self.BASE_URL}/masters/{master_id}/versions", params=params, priority=Priority.DETAIL)

        results = []
        for item in data.get("versions", []):
            format_info = item.get("format", "")
            label = item.get("label", "")
            catalog_number = item.get("catno", "")

            major_formats = item.get("major_formats", [])

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
            results.append(ArtistSearchResult(
                artist_id=str(item.get("id", "")),
                name=item.get("title", "Unknown"),
                cover_image_url=item.get("cover_image"),
                thumb_image_url=item.get("thumb"),
            ))

        pagination = data.get("pagination", {})

        response = ArtistSearchResponse(
            results=results,
            total=pagination.get("items", 0),
            page=pagination.get("page", page),
            per_page=pagination.get("per_page", per_page)
        )
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
        """Получение обложки и типа релиза из master endpoint.
        Тип определяется по количеству треков в треклисте:
        1-3 → single, 4-6 → ep, 7+ → album.
        Таймаут 10с чтобы не блокировать весь список.
        """
        cached = await cache.get("master_info", master_id)
        if cached is not None:
            return cached

        try:
            data = await asyncio.wait_for(
                self._get(f"{self.BASE_URL}/masters/{master_id}", priority=Priority.ENRICHMENT),
                timeout=10.0,
            )
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
        except Exception:
            logger.exception("Failed to get master info for %s", master_id)
            return {"cover": None, "release_type": None}

    async def _get_artist_thumb(self, artist_id: str) -> str | None:
        """Получение миниатюры артиста по ID. Кэшируется в Redis на 30 дней."""
        cached = await cache.get("artist_thumb", artist_id)
        if cached is not None:
            return cached

        try:
            data = await self._get(f"{self.BASE_URL}/artists/{artist_id}", priority=Priority.ENRICHMENT)
            images = data.get("images", [])
            if images:
                thumb = images[0].get("uri150") or images[0].get("uri")
                await cache.set("artist_thumb", artist_id, thumb, TTL_ARTIST_THUMB)
                return thumb
        except Exception:
            logger.exception("Failed to get artist thumb for %s", artist_id)
        return None

    @staticmethod
    def _guess_release_type(format_str: str | None) -> str | None:
        """Определение типа релиза по строке формата из Discogs releases endpoint.
        Discogs возвращает format как строку вида '12", Album' или 'CD, Single' и т.д.
        """
        if not format_str:
            return None
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
    ) -> MasterSearchResponse:
        """Получение master releases артиста (альбомы, синглы, EP).
        При load_all=True загружает все страницы последовательно (max 10 страниц).
        Результат кэшируется в Redis."""
        ck = f"{artist_id}:all" if load_all else f"{artist_id}:p{page}:pp{per_page}"
        cached = await cache.get("artist_masters", ck)
        if cached is not None:
            return MasterSearchResponse(**cached)

        all_results: list[MasterSearchResult] = []
        current_page = page
        total_items = 0
        max_pages = 10 if load_all else 1

        for _ in range(max_pages):
            params = {
                "page": current_page,
                "per_page": per_page,
                "sort": "year",
                "sort_order": "asc",
            }

            data = await self._get(f"{self.BASE_URL}/artists/{artist_id}/releases", params=params, priority=Priority.BATCH)

            for item in data.get("releases", []):
                if item.get("type") != "master" or item.get("role") != "Main":
                    continue

                thumb = item.get("thumb")
                release_type = self._guess_release_type(item.get("format"))

                all_results.append(MasterSearchResult(
                    master_id=str(item.get("id", "")),
                    title=item.get("title", ""),
                    artist=item.get("artist", "Unknown"),
                    year=int(item["year"]) if item.get("year") else None,
                    main_release_id=str(item.get("main_release", "")),
                    cover_image_url=self._thumb_to_cover(thumb),
                    thumb_image_url=thumb if thumb else None,
                    release_type=release_type,
                ))

            pagination = data.get("pagination", {})
            total_items = pagination.get("items", len(all_results))
            total_pages = pagination.get("pages", 1)

            if not load_all or current_page >= total_pages:
                break

            current_page += 1
            await asyncio.sleep(1.0)  # Rate limit: 60 req/min

        response = MasterSearchResponse(
            results=all_results,
            total=total_items,
            page=1 if load_all else page,
            per_page=total_items if load_all else per_page,
        )
        await cache.set("artist_masters", ck, response.model_dump(), TTL_ARTIST_MASTERS)
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

    async def _get_price_stats(self, release_id: str) -> dict | None:
        """Получение статистики цен для релиза (всегда в USD).
        Кэшируется в Redis на 6 часов."""
        cached = await cache.get("price_stats", release_id)
        if cached is not None:
            return cached

        try:
            result = await self._get(
                f"{self.BASE_URL}/marketplace/stats/{release_id}",
                params={"curr_abbr": "USD"},
                headers=self._get_token_headers(),
                priority=Priority.ENRICHMENT,
            )
            await cache.set("price_stats", release_id, result, TTL_PRICE_STATS)
            return result
        except Exception:
            logger.exception("Failed to get price stats for release %s", release_id)
        return None
