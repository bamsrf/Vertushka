"""
Spotify enrichment для user-submitted records (source='user').

Auth: Client Credentials (без юзер-логина) — token-cache с авто-refresh, как в
discogs.py. Spotify НЕ отдаёт прессинги/каталожные номера/страну — эти поля юзер
вводит руками. Отсюда берём: название, год, обложку-кандидат, треклист, жанры.

Если креды (SPOTIFY_CLIENT_ID/SECRET) пустые — сервис в no-op режиме: все методы
возвращают пусто, фронт показывает только ручной ввод. См.
docs/plans/collection/USER_SUBMITTED_RECORDS.md §3.
"""
import base64
import logging
import time

import httpx

from app.config import get_settings

logger = logging.getLogger(__name__)

_TOKEN_URL = "https://accounts.spotify.com/api/token"
_API_BASE = "https://api.spotify.com/v1"


def _ms_to_duration(ms: int | None) -> str | None:
    """1000ms → '0:01' (формат tracklist как у discogs)."""
    if not ms or ms < 0:
        return None
    total = ms // 1000
    return f"{total // 60}:{total % 60:02d}"


class SpotifyService:
    """Singleton-ish сервис: токен и httpx-клиент шарятся между запросами."""

    _client: "httpx.AsyncClient | None" = None
    _token: str | None = None
    _token_expires_at: float = 0.0

    def __init__(self) -> None:
        settings = get_settings()
        self._client_id = settings.spotify_client_id
        self._client_secret = settings.spotify_client_secret

    @property
    def enabled(self) -> bool:
        return bool(self._client_id and self._client_secret)

    @classmethod
    def _get_shared_client(cls) -> httpx.AsyncClient:
        if cls._client is None:
            # Spotify гео-блокирует api.spotify.com по IP (РФ → 403 "Spotify is
            # unavailable in this country"). SPOTIFY_PROXY_URL пускает запросы
            # через прокси в разрешённой стране. Пусто → прямое соединение.
            proxy = get_settings().spotify_proxy_url or None
            cls._client = httpx.AsyncClient(
                timeout=httpx.Timeout(15.0),
                limits=httpx.Limits(max_connections=10, max_keepalive_connections=5),
                proxy=proxy,
            )
        return cls._client

    async def _get_token(self) -> str | None:
        """Client Credentials token с кэшем (refresh за 60с до истечения)."""
        if not self.enabled:
            return None
        if self._token and time.monotonic() < self._token_expires_at - 60:
            return self._token

        basic = base64.b64encode(
            f"{self._client_id}:{self._client_secret}".encode()
        ).decode()
        client = self._get_shared_client()
        try:
            resp = await client.post(
                _TOKEN_URL,
                data={"grant_type": "client_credentials"},
                headers={"Authorization": f"Basic {basic}"},
            )
            resp.raise_for_status()
        except httpx.HTTPError as e:
            logger.warning("Spotify token fetch failed: %s", e)
            return None

        data = resp.json()
        SpotifyService._token = data.get("access_token")
        SpotifyService._token_expires_at = time.monotonic() + data.get("expires_in", 3600)
        return SpotifyService._token

    async def _get(self, path: str, params: dict | None = None) -> dict | None:
        token = await self._get_token()
        if not token:
            return None
        client = self._get_shared_client()
        try:
            resp = await client.get(
                f"{_API_BASE}{path}",
                params=params,
                headers={"Authorization": f"Bearer {token}"},
            )
            resp.raise_for_status()
        except httpx.HTTPError as e:
            logger.warning("Spotify GET %s failed: %s", path, e)
            return None
        return resp.json()

    async def search_album(
        self, artist: str, title: str, limit: int = 8
    ) -> list[dict]:
        """
        Top-N кандидатов-альбомов. Каждый кандидат:
            {id, name, artist, year, cover_url, image_url}
        Пустой список если creds нет или ничего не нашлось.
        """
        if not self.enabled:
            return []
        q = " ".join(p for p in (artist, title) if p).strip()
        if not q:
            return []
        data = await self._get(
            "/search",
            {"q": q, "type": "album", "limit": min(limit, 50)},
        )
        if not data:
            return []
        out: list[dict] = []
        for item in data.get("albums", {}).get("items", []):
            images = item.get("images") or []
            cover = images[0].get("url") if images else None
            thumb = images[-1].get("url") if images else None
            year = None
            rel = item.get("release_date") or ""
            if rel[:4].isdigit():
                year = int(rel[:4])
            out.append({
                "id": item.get("id"),
                "name": item.get("name"),
                "artist": ", ".join(
                    a.get("name", "") for a in item.get("artists", [])
                ).strip(", "),
                "year": year,
                "cover_url": cover,
                "image_url": thumb,
            })
        return out

    async def get_album_tracks(self, album_id: str) -> list[dict]:
        """Треклист альбома в формате Record.tracklist: {position, title, duration}."""
        if not self.enabled or not album_id:
            return []
        data = await self._get(f"/albums/{album_id}/tracks", {"limit": 50})
        if not data:
            return []
        tracks: list[dict] = []
        for t in data.get("items", []):
            tracks.append({
                "position": str(t.get("track_number") or ""),
                "title": t.get("name"),
                "duration": _ms_to_duration(t.get("duration_ms")),
            })
        return tracks

    async def get_album(self, album_id: str) -> dict | None:
        """Полный альбом (для enrichment-merge на бэке): сырой Spotify-ответ."""
        if not self.enabled or not album_id:
            return None
        return await self._get(f"/albums/{album_id}")

    async def get_artist(self, artist_id: str) -> dict | None:
        """Имя/жанры/фото артиста → в user_submitted_data."""
        if not self.enabled or not artist_id:
            return None
        return await self._get(f"/artists/{artist_id}")


spotify_service = SpotifyService()
