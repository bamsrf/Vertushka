"""Мост зеркала в схемах записи: `cover_url` для незазеркаленной обложки.

Инцидент 10.09.2026, реальный Android (realme, Wi-Fi, свежая установка):
коллекция из 71 записи минутами висела серыми blurhash-заглушками, загрузились
2–3. По логам nginx за всю сессию телефон не запросил НИ ОДНОЙ обложки
коллекции — и не должен был: зеркало было у 5 записей из 71, остальные 66
схема отдавала с `cover_url=None`, и клиент шёл напрямую на i.discogs.com,
который из РФ не отвечает. Поиск/скан/маркет уже давно ходят через
`/covers/{discogs_id}.jpg` (self-healing: статика → 302 + фоновое
зеркалирование); коллекция и вишлист были единственными списками мимо моста.
"""
from datetime import datetime, timezone
from uuid import uuid4

from app.schemas.record import RecordBrief, RecordResponse, bridge_cover_url

DISCOGS_600 = (
    "https://i.discogs.com/abc/rs:fit/g:sm/q:90/h:600/w:600/czM6Ly9kaXNjb2dz.jpeg"
)
DISCOGS_150 = (
    "https://i.discogs.com/abc/rs:fit/g:sm/q:40/h:150/w:150/czM6Ly9kaXNjb2dz.jpeg"
)


def brief(**kw) -> RecordBrief:
    base = dict(
        id=uuid4(), discogs_id="123456", title="T", artist="A", year=1990,
        cover_image_url=DISCOGS_600, thumb_image_url=DISCOGS_150,
        estimated_price_median=None, price_currency="USD",
    )
    base.update(kw)
    return RecordBrief(**base)


def test_unmirrored_discogs_cover_goes_through_bridge():
    assert brief().cover_url == "/covers/123456.jpg"


def test_mirrored_cover_keeps_uploads_path_with_stamp():
    stamp = datetime(2026, 9, 10, 12, 0, tzinfo=timezone.utc)
    rb = brief(cover_local_path="covers/123456.jpg", cover_cached_at=stamp)
    assert rb.cover_url == f"/uploads/covers/123456.jpg?v={int(stamp.timestamp())}"


def test_explicit_cover_url_is_not_overridden():
    rb = brief(cover_url="/uploads/user_photos/x.jpg")
    assert rb.cover_url == "/uploads/user_photos/x.jpg"


def test_thumb_grade_source_is_not_bridged():
    # Tier-гейт зеркала не примет 150px → /covers/{id}.jpg был бы вечным
    # холодным 302; клиент оставляет прямой URL.
    assert brief(cover_image_url=DISCOGS_150).cover_url is None


def test_no_source_or_non_numeric_id_is_not_bridged():
    assert brief(cover_image_url=None).cover_url is None
    assert brief(discogs_id=None, source="store").cover_url is None
    assert bridge_cover_url("m123", DISCOGS_600) is None
    assert bridge_cover_url("123", "spacer.gif") is None


def test_record_response_bridges_too():
    rr = RecordResponse(
        id=uuid4(), discogs_id="777", discogs_master_id=None, title="T",
        artist="A", label=None, catalog_number=None, year=None, country=None,
        genre=None, style=None, format_type=None, format_description=None,
        barcode=None, estimated_price_min=None, estimated_price_max=None,
        estimated_price_median=None, price_currency="USD",
        cover_image_url=DISCOGS_600, thumb_image_url=None, tracklist=None,
        created_at=datetime.now(timezone.utc), updated_at=datetime.now(timezone.utc),
    )
    assert rr.cover_url == "/covers/777.jpg"
