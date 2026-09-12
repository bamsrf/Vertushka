"""Гейт названия при матчинге обложек по метаданным (Deezer / iTunes).

Регресс 12.09.2026: подстрочный матч в обе стороны подменил обложки в
коллекции — «SVN» прицепил «SVN Session #3» чужого SVN, «Flower of Devotion»
(прессинг 2024) получил «Flower of Devotion Remixed», потому что год ремиксов
оказался ближе к году переиздания.
"""
import pytest

from app.services import cover_fallback, deezer
from app.services.deezer import artists_match, titles_match


@pytest.mark.parametrize("ours,theirs,ok", [
    ("SVN", "SVN Session #3", False),
    ("Flower of Devotion", "Flower of Devotion Remixed", False),
    ("Flower Of Devotion", "Flower of Devotion", True),
    ("Nevermind (Remastered)", "Nevermind", True),
    ("Nevermind", "Nevermind (Deluxe Edition)", True),
    ("Abbey Road", "Abbey Road (Live)", False),
    ("", "SVN", False),
])
def test_titles_match_requires_equality(ours, theirs, ok):
    assert titles_match(ours, theirs) is ok


def test_artists_match_keeps_substring_rules():
    assert artists_match("SVN (2)", "SVN")
    assert artists_match("Tyler, The Creator", "Tyler The Creator")
    assert not artists_match("Dehd", "Dead")


class _Resp:
    def __init__(self, payload):
        self._p = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self._p


class _Client:
    """Фейковый httpx.AsyncClient: поиск отдаёт заданный список, /album — даты."""
    search: list = []
    albums: dict = {}

    def __init__(self, *a, **kw):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def get(self, url, params=None):
        if url == deezer._SEARCH_URL:
            return _Resp({"data": self.search})
        album_id = int(url.rsplit("/", 1)[1])
        return _Resp({"release_date": self.albums[album_id]})


def _album(aid, artist, title, date):
    _Client.albums[aid] = date
    return {"id": aid, "title": title, "artist": {"name": artist},
            "cover_xl": f"https://cdn/{aid}.jpg", "md5_image": "x"}


@pytest.fixture
def fake_deezer(monkeypatch):
    monkeypatch.setattr(deezer.httpx, "AsyncClient", _Client)
    monkeypatch.setattr(deezer, "_throttle", _noop)
    _Client.search = []
    _Client.albums = {}
    return _Client


async def _noop():
    return None


@pytest.mark.asyncio
async def test_deezer_rejects_foreign_album_with_extra_words(fake_deezer):
    fake_deezer.search = [_album(1, "SVN", "SVN Session #3", "2024-01-01")]
    assert await deezer.cover_by_meta("SVN (2)", "SVN", year=2021) is None


@pytest.mark.asyncio
async def test_deezer_reissue_year_does_not_pull_remix_album(fake_deezer):
    fake_deezer.search = [
        _album(61, "Dehd", "Flower of Devotion", "2020-07-17"),
        _album(111, "Dehd", "Flower of Devotion Remixed", "2021-09-17"),
    ]
    got = await deezer.cover_by_meta("Dehd", "Flower of Devotion", year=2024)
    assert got is not None and got.album_id == 61


@pytest.mark.asyncio
async def test_itunes_rejects_remixed_for_original(monkeypatch):
    async def fake_throttle():
        return None

    class _IClient(_Client):
        async def get(self, url, params=None, headers=None):
            return _Resp({"results": [{
                "artistName": "Dehd",
                "collectionName": "Flower of Devotion Remixed",
                "artworkUrl100": "https://mzstatic/100x100bb.jpg",
            }]})

    monkeypatch.setattr(cover_fallback.httpx, "AsyncClient", _IClient)
    monkeypatch.setattr(cover_fallback, "_itunes_throttle", fake_throttle)
    assert await cover_fallback.cover_url_by_artist_title("Dehd", "Flower of Devotion") is None
