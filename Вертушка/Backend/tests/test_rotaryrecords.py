"""Тесты разбора каталога Rotary Records (JSON-API магазина)."""
import json
from decimal import Decimal

import pytest

from app.services.scrapers.base import TransientParserError
from app.services.scrapers.shops.rotaryrecords import (
    RotaryRecordsParser,
    _parse_subtitle,
    _split_artist_album,
)

UUID = "60740323-7a12-11f1-0a80-0da4000f0192"


def _card(**over):
    base = {
        "id": UUID,
        "url": f"/record/{UUID}/various-smash-hits-the-80s",
        "title": "Various - Smash Hits The 80s",
        "subtitle": "Rhino Records • 2017",
        "styles": "Pop Rock, Synth-pop",
        "price": "5 900 ₽",
        "images": {"thumb": f"/images/discogs_synced/{UUID}_thumb.jpg",
                   "base": f"/images/discogs_synced/{UUID}_medium.jpg"},
    }
    base.update(over)
    return base


@pytest.fixture
def parser():
    return RotaryRecordsParser(http=object())


def test_parse_card_basic(parser):
    dto = parser.parse_card(_card())
    assert dto.external_id == UUID
    assert dto.artist_raw == "Various"
    assert dto.title_raw == "Smash Hits The 80s"
    assert dto.price_rub == Decimal("5900")
    assert dto.year_raw == 2017
    assert dto.format_raw == "LP"
    assert dto.status == "in_stock"
    assert dto.raw_payload["label"] == "Rhino Records"
    assert dto.url == f"https://rotaryrecords.store/record/{UUID}/various-smash-hits-the-80s"
    assert dto.image_url.startswith("https://rotaryrecords.store/images/")


def test_condition_is_store_wide_constant(parser):
    """«> VG+» — политика магазина, а не грейдинг экземпляра (13/13 в выборке)."""
    assert parser.parse_card(_card()).condition == "> VG+"


def test_no_fake_barcode(parser):
    """Внутренняя нумерация магазина (2000000041674) не должна уехать в barcode."""
    dto = parser.parse_card(_card())
    assert dto.barcode is None
    assert dto.catalog_number is None


@pytest.mark.parametrize("title, artist, album", [
    ("Various - Smash Hits The 80s", "Various", "Smash Hits The 80s"),
    # Сплит-релиз: слэши и в артисте, и в альбоме, но дефис-разделитель один.
    ("Dick Jordan/Jack Hammer - I Want Her Back/Twist In The Morning",
     "Dick Jordan/Jack Hammer", "I Want Her Back/Twist In The Morning"),
    # Дефис внутри имени не должен резать.
    ("Jay-Z - The Blueprint", "Jay-Z", "The Blueprint"),
    ("Без разделителя", None, "Без разделителя"),
])
def test_split_artist_album(title, artist, album):
    assert _split_artist_album(title) == (artist, album)


@pytest.mark.parametrize("subtitle, label, year", [
    ("Rhino Records • 2017", "Rhino Records", 2017),
    ("Virgin/Soma Quality Recordings • 2001", "Virgin/Soma Quality Recordings", 2001),
    ("", None, None),
])
def test_parse_subtitle(subtitle, label, year):
    assert _parse_subtitle(subtitle) == (label, year)


def test_card_without_price_is_on_request(parser):
    dto = parser.parse_card(_card(price=""))
    assert dto.price_rub is None
    assert dto.status == "on_request"


def test_card_without_url_skipped(parser):
    assert parser.parse_card(_card(url="")) is None


class _FakeHttp:
    def __init__(self, pages, fail_on=None):
        self.pages, self.fail_on, self.urls = pages, fail_on, []

    async def get_text(self, url, **kw):
        self.urls.append(url)
        offset = int(url.split("offset=")[1].split("&")[0])
        if self.fail_on == offset:
            raise RuntimeError("network error")
        return json.dumps(self.pages.get(offset, {"ok": True, "cards": [], "has_more": False}))


async def _collect(parser):
    return [d async for d in parser.crawl_full()]


@pytest.mark.asyncio
async def test_crawl_paginates_until_has_more_false():
    other = "aaaaaaaa-7a12-11f1-0a80-0da4000f0192"
    pages = {
        0: {"ok": True, "total": 2, "has_more": True, "cards": [_card()]},
        1: {"ok": True, "total": 2, "has_more": False,
            "cards": [_card(id=other, url=f"/record/{other}/x", title="B - C")]},
    }
    dtos = await _collect(RotaryRecordsParser(http=_FakeHttp(pages)))
    assert [d.external_id for d in dtos] == [UUID, other]


@pytest.mark.asyncio
async def test_single_bad_page_is_skipped_not_fatal():
    """Одно окно пропущено — теряем до 80 позиций, но не весь каталог."""
    other = "aaaaaaaa-7a12-11f1-0a80-0da4000f0192"
    pages = {
        0: {"ok": True, "total": 200, "has_more": True, "cards": [_card()]},
        # offset=1 сбоит → окно сдвигается на catalog_page_size (80) → 81.
        81: {"ok": True, "total": 200, "has_more": False,
             "cards": [_card(id=other, url=f"/record/{other}/x", title="B - C")]},
    }
    dtos = await _collect(RotaryRecordsParser(http=_FakeHttp(pages, fail_on=1)))
    assert [d.external_id for d in dtos] == [UUID, other]


@pytest.mark.asyncio
async def test_crawl_raises_when_api_is_down():
    """Сквозной обрыв API должен долететь до runner'а."""
    class _DeadHttp(_FakeHttp):
        async def get_text(self, url, **kw):
            offset = int(url.split("offset=")[1].split("&")[0])
            if offset == 0:
                return json.dumps(self.pages[0])
            raise RuntimeError("network error")

    pages = {0: {"ok": True, "total": 5000, "has_more": True, "cards": [_card()]}}
    with pytest.raises(TransientParserError, match="подряд"):
        await _collect(RotaryRecordsParser(http=_DeadHttp(pages)))


@pytest.mark.asyncio
async def test_refresh_marks_missing_as_removed():
    """Продан = пропал из выдачи; страницы товара живут и после продажи."""
    pages = {0: {"ok": True, "total": 1, "has_more": False, "cards": [_card()]}}
    parser = RotaryRecordsParser(http=_FakeHttp(pages))
    gone = "https://rotaryrecords.store/record/ffffffff-7a12-11f1-0a80-0da4000f0192/x"
    alive = f"https://rotaryrecords.store/record/{UUID}/various-smash-hits-the-80s"
    out = {url: dto async for url, dto in parser.refresh_urls([alive, gone])}
    assert out[alive] is not None
    assert out[gone] is None
