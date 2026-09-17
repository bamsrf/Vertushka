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


# --- Зеркало в бакете: cover_local_path пуст, cover_cached_at жив -----------
#
# 17.09.2026. Карточка релиза отдавала `cover_url=/covers/2115210.jpg` БЕЗ
# метки версии, хотя витрина на ту же запись отдавала
# `/covers/w/640/2115210.jpg?v=…`. Причина — эвикция LRU: с S3 она гасит
# только `cover_local_path`, файл остаётся в бакете. `build_cover_url`
# возвращал None, и запасной мост метку не ставил вовсе. Следствия: неделя
# кэша вместо года, другой ключ кэша, чем у плитки (одна картинка качается
# дважды), а для CAA/Deezer-зеркал без `cover_image_url` — вообще None и
# уход клиента на недоступный из РФ i.discogs.com.

EVICTED_STAMP = datetime(2026, 9, 17, 9, 30, tzinfo=timezone.utc)
EVICTED_V = f"?v={int(EVICTED_STAMP.timestamp())}"


def test_evicted_to_bucket_is_bridged_with_version():
    rb = brief(cover_local_path=None, cover_cached_at=EVICTED_STAMP)
    assert rb.cover_url == f"/covers/123456.jpg{EVICTED_V}"


def test_evicted_bridge_ignores_tier_gate_and_missing_source():
    # Файл в бакете уже прошёл тир-гейт при записи. Каким был внешний URL —
    # мелким (CAA отдала лучше) или пустым (Deezer/ручная заливка) — к
    # содержимому файла отношения не имеет.
    for src in (DISCOGS_150, None):
        rb = brief(
            cover_image_url=src, cover_local_path=None, cover_cached_at=EVICTED_STAMP
        )
        assert rb.cover_url == f"/covers/123456.jpg{EVICTED_V}", src


def test_evicted_bridge_matches_market_url_after_sizing():
    # Ключевое: витрина строит тот же путь + ту же метку (_COVER_BRIDGE в
    # api/market.py), а клиент дописывает ступень ширины. Совпадение строк —
    # это и есть общий кэш вместо двух скачиваний одной картинки.
    rb = brief(cover_local_path=None, cover_cached_at=EVICTED_STAMP)
    assert rb.cover_url == f"/covers/{rb.discogs_id}.jpg{EVICTED_V}"


def test_unmirrored_still_has_no_version():
    # Метки взяться неоткуда: файла ещё нет. URL уйдёт без неё и получит
    # консервативный Cache-Control (неделя), как и было.
    assert brief().cover_url == "/covers/123456.jpg"


def test_local_path_wins_over_bridge():
    # Пока локальная копия на месте — отдаём её, мост не вмешивается.
    rb = brief(cover_local_path="covers/123456.jpg", cover_cached_at=EVICTED_STAMP)
    assert rb.cover_url == f"/uploads/covers/123456.jpg{EVICTED_V}"
