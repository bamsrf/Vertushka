"""
Сервис для работы с Discogs API
"""
import asyncio
import re

import httpx
from typing import Any

from app.config import get_settings
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

settings = get_settings()


class DiscogsService:
    """Сервис для работы с Discogs API"""

    BASE_URL = "https://api.discogs.com"
    _semaphore = asyncio.Semaphore(5)
    _client: "httpx.AsyncClient | None" = None

    def __init__(self):
        self.api_key = settings.discogs_api_key
        self.api_secret = settings.discogs_api_secret
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

    async def _get(self, url: str, params: dict | None = None) -> dict:
        """GET с повторными попытками при 429/503 от Discogs."""
        client = self._get_shared_client()
        async with self._semaphore:
            last_response = None
            for attempt in range(3):
                last_response = await client.get(
                    url,
                    params=params,
                    headers=self._get_headers(),
                    timeout=30.0,
                )
                if last_response.status_code in (429, 503) and attempt < 2:
                    retry_after = int(last_response.headers.get("Retry-After", "2"))
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

    async def search(
        self,
        query: str,
        artist: str | None = None,
        year: int | None = None,
        label: str | None = None,
        page: int = 1,
        per_page: int = 20
    ) -> RecordSearchResponse:
        """
        Поиск пластинок в Discogs.
        
        Args:
            query: Поисковый запрос
            artist: Фильтр по артисту
            year: Фильтр по году
            label: Фильтр по лейблу
            page: Номер страницы
            per_page: Записей на страницу
        
        Returns:
            RecordSearchResponse с результатами поиска
        """
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
        
        data = await self._get(f"{self.BASE_URL}/database/search", params=params)
        
        results = []
        for item in data.get("results", []):
            # Парсим артиста и название
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
        
        return RecordSearchResponse(
            results=results,
            total=pagination.get("items", 0),
            page=pagination.get("page", page),
            per_page=pagination.get("per_page", per_page)
        )
    
    async def search_by_barcode(self, barcode: str) -> list[RecordSearchResult]:
        """
        Поиск пластинки по штрихкоду.
        
        Args:
            barcode: Штрихкод (EAN-13, UPC-A и т.д.)
        
        Returns:
            Список найденных пластинок
        """
        params = {
            "barcode": barcode,
            "type": "release",
        }
        
        data = await self._get(f"{self.BASE_URL}/database/search", params=params)
        
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
        
        return results
    
    async def get_release(self, release_id: str) -> dict[str, Any]:
        """
        Получение детальной информации о релизе.

        Args:
            release_id: ID релиза в Discogs

        Returns:
            Словарь с данными релиза
        """
        # Запускаем price_stats параллельно с основным запросом —
        # price_stats нужен только release_id, который у нас уже есть.
        stats_task = asyncio.create_task(self._get_price_stats(release_id))

        data = await self._get(f"{self.BASE_URL}/releases/{release_id}")

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
            pass  # Игнорируем ошибки получения цен
        
        return {
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
    
    async def search_masters(
        self,
        query: str,
        page: int = 1,
        per_page: int = 20
    ) -> MasterSearchResponse:
        """
        Поиск мастер-релизов в Discogs.

        Args:
            query: Поисковый запрос
            page: Номер страницы
            per_page: Записей на страницу

        Returns:
            MasterSearchResponse с результатами поиска
        """
        params = {
            "q": query,
            "type": "master",
            "page": page,
            "per_page": per_page,
        }

        data = await self._get(f"{self.BASE_URL}/database/search", params=params)

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

        return MasterSearchResponse(
            results=results,
            total=pagination.get("items", 0),
            page=pagination.get("page", page),
            per_page=pagination.get("per_page", per_page)
        )

    async def search_releases(
        self,
        query: str,
        format: str | None = None,
        country: str | None = None,
        year: int | None = None,
        page: int = 1,
        per_page: int = 20
    ) -> ReleaseSearchResponse:
        """
        Поиск конкретных релизов с фильтрами в Discogs.

        Args:
            query: Поисковый запрос
            format: Фильтр по формату (Vinyl, CD, Cassette и т.д.)
            country: Фильтр по стране
            year: Фильтр по году
            page: Номер страницы
            per_page: Записей на страницу

        Returns:
            ReleaseSearchResponse с результатами поиска
        """
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

        data = await self._get(f"{self.BASE_URL}/database/search", params=params)

        results = []
        for item in data.get("results", []):
            title = item.get("title", "")
            artist_name = "Unknown"
            album_title = title

            if " - " in title:
                parts = title.split(" - ", 1)
                artist_name = parts[0]
                album_title = parts[1] if len(parts) > 1 else title

            # Парсим формат
            format_list = item.get("format", [])
            format_str = ", ".join(format_list) if format_list else None

            # Парсим лейбл и каталожный номер
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

        return ReleaseSearchResponse(
            results=results,
            total=pagination.get("items", 0),
            page=pagination.get("page", page),
            per_page=pagination.get("per_page", per_page)
        )

    async def get_master(self, master_id: str) -> MasterRelease:
        """
        Получение информации о мастер-релизе.

        Args:
            master_id: ID мастер-релиза в Discogs

        Returns:
            MasterRelease с данными мастер-релиза
        """
        data = await self._get(f"{self.BASE_URL}/masters/{master_id}")

        artists = data.get("artists", [])
        artist_name = ", ".join([a.get("name", "") for a in artists]) if artists else "Unknown"
        # Получаем ID первого (главного) артиста для навигации
        artist_id = str(artists[0].get("id")) if artists else None

        # Получаем миниатюру артиста
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

        return MasterRelease(
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

    async def get_master_versions(
        self,
        master_id: str,
        page: int = 1,
        per_page: int = 50
    ) -> MasterVersionsResponse:
        """
        Получение всех версий (изданий) мастер-релиза.

        Args:
            master_id: ID мастер-релиза в Discogs
            page: Номер страницы
            per_page: Записей на страницу

        Returns:
            MasterVersionsResponse со списком версий
        """
        params = {
            "page": page,
            "per_page": per_page,
        }

        data = await self._get(f"{self.BASE_URL}/masters/{master_id}/versions", params=params)

        results = []
        for item in data.get("versions", []):
            format_info = item.get("format", "")
            label = item.get("label", "")
            catalog_number = item.get("catno", "")

            results.append(MasterVersion(
                release_id=str(item.get("id", "")),
                title=item.get("title", ""),
                label=label if label else None,
                catalog_number=catalog_number if catalog_number else None,
                country=item.get("country"),
                year=int(item.get("released")) if item.get("released") else None,
                format=format_info if format_info else None,
                thumb_image_url=item.get("thumb"),
            ))

        pagination = data.get("pagination", {})

        return MasterVersionsResponse(
            results=results,
            total=pagination.get("items", 0),
            page=pagination.get("page", page),
            per_page=pagination.get("per_page", per_page)
        )

    async def search_artists(
        self,
        query: str,
        page: int = 1,
        per_page: int = 20
    ) -> ArtistSearchResponse:
        """
        Поиск артистов в Discogs.

        Args:
            query: Поисковый запрос
            page: Номер страницы
            per_page: Записей на страницу

        Returns:
            ArtistSearchResponse с результатами поиска
        """
        params = {
            "q": query,
            "type": "artist",
            "page": page,
            "per_page": per_page,
        }

        data = await self._get(f"{self.BASE_URL}/database/search", params=params)

        results = []
        for item in data.get("results", []):
            results.append(ArtistSearchResult(
                artist_id=str(item.get("id", "")),
                name=item.get("title", "Unknown"),
                cover_image_url=item.get("cover_image"),
                thumb_image_url=item.get("thumb"),
            ))

        pagination = data.get("pagination", {})

        return ArtistSearchResponse(
            results=results,
            total=pagination.get("items", 0),
            page=pagination.get("page", page),
            per_page=pagination.get("per_page", per_page)
        )

    async def get_artist(self, artist_id: str) -> Artist:
        """
        Получение информации об артисте.

        Args:
            artist_id: ID артиста в Discogs

        Returns:
            Artist с данными артиста
        """
        data = await self._get(f"{self.BASE_URL}/artists/{artist_id}")

        images = data.get("images", [])
        image_urls = [img.get("uri") for img in images if img.get("uri")]

        return Artist(
            artist_id=str(data.get("id")),
            name=data.get("name", "Unknown"),
            profile=data.get("profile"),
            images=image_urls,
        )

    async def get_artist_releases(
        self,
        artist_id: str,
        page: int = 1,
        per_page: int = 50
    ) -> ReleaseSearchResponse:
        """
        Получение релизов артиста.

        Args:
            artist_id: ID артиста в Discogs
            page: Номер страницы
            per_page: Записей на страницу

        Returns:
            ReleaseSearchResponse со списком релизов
        """
        params = {
            "page": page,
            "per_page": per_page,
        }

        data = await self._get(f"{self.BASE_URL}/artists/{artist_id}/releases", params=params)

        results = []
        for item in data.get("releases", []):
            # Парсим название и артиста
            title = item.get("title", "")
            artist_name = item.get("artist", "Unknown")

            # Извлекаем год
            year = item.get("year")

            # Извлекаем формат
            format_info = item.get("format", "")

            # Извлекаем лейбл
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

        return ReleaseSearchResponse(
            results=results,
            total=pagination.get("items", 0),
            page=pagination.get("page", page),
            per_page=pagination.get("per_page", per_page)
        )

    async def _get_master_info(self, master_id: str) -> dict:
        """Получение обложки и типа релиза из master endpoint.
        Тип определяется по количеству треков в треклисте:
        1-3 → single, 4-6 → ep, 7+ → album.
        """
        try:
            data = await self._get(f"{self.BASE_URL}/masters/{master_id}")
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

            return {"cover": cover, "release_type": release_type}
        except Exception:
            return {"cover": None, "release_type": None}

    async def _get_artist_thumb(self, artist_id: str) -> str | None:
        """Получение миниатюры артиста по ID."""
        try:
            data = await self._get(f"{self.BASE_URL}/artists/{artist_id}")
            images = data.get("images", [])
            if images:
                return images[0].get("uri150") or images[0].get("uri")
        except Exception:
            pass
        return None

    async def get_artist_masters(
        self,
        artist_id: str,
        page: int = 1,
        per_page: int = 50
    ) -> MasterSearchResponse:
        """
        Получение только master releases артиста (альбомы, синглы, EP).
        Фильтрует релизы, оставляя только записи типа 'master'.
        Загружает обложки параллельно из отдельных master endpoints.

        Args:
            artist_id: ID артиста в Discogs
            page: Номер страницы
            per_page: Записей на страницу

        Returns:
            MasterSearchResponse со списком master releases
        """
        params = {
            "page": page,
            "per_page": per_page,
        }

        data = await self._get(f"{self.BASE_URL}/artists/{artist_id}/releases", params=params)

        # Собираем master releases
        masters_data = []
        for item in data.get("releases", []):
            release_type = item.get("type", "")
            role = item.get("role", "")

            # Показываем только masters где артист - Main
            if release_type == "master" and role == "Main":
                masters_data.append({
                    "master_id": str(item.get("id", "")),
                    "title": item.get("title", ""),
                    "artist": item.get("artist", "Unknown"),
                    "year": item.get("year"),
                    "main_release_id": str(item.get("main_release", "")),
                    "thumb": item.get("thumb"),
                    "release_type": item.get("format"),
                })

        # Параллельно загружаем обложки и определяем типы для всех masters
        info_tasks = [
            self._get_master_info(m["master_id"]) for m in masters_data
        ]
        infos = await asyncio.gather(*info_tasks, return_exceptions=True)

        # Формируем результаты с обложками и типами
        results = []
        for i, m in enumerate(masters_data):
            info = infos[i] if not isinstance(infos[i], Exception) else {}
            cover_url = info.get("cover") if isinstance(info, dict) else None
            release_type = info.get("release_type") if isinstance(info, dict) else None
            thumb = m["thumb"]

            results.append(MasterSearchResult(
                master_id=m["master_id"],
                title=m["title"],
                artist=m["artist"],
                year=int(m["year"]) if m["year"] else None,
                main_release_id=m["main_release_id"],
                cover_image_url=cover_url or self._thumb_to_cover(thumb),
                thumb_image_url=thumb if thumb else None,
                release_type=release_type,
            ))

        pagination = data.get("pagination", {})

        return MasterSearchResponse(
            results=results,
            total=pagination.get("items", len(results)),
            page=pagination.get("page", page),
            per_page=pagination.get("per_page", per_page)
        )

    async def _get_price_stats(self, release_id: str) -> dict | None:
        """Получение статистики цен для релиза"""
        try:
            client = self._get_shared_client()
            response = await client.get(
                f"{self.BASE_URL}/marketplace/stats/{release_id}",
                headers=self._get_headers(),
                timeout=10.0,
            )
            if response.status_code == 200:
                return response.json()
        except Exception:
            pass
        return None

