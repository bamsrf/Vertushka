"""Выселенная в бакет обложка защищена от даунгрейда так же, как лежащая на диске.

18.09.2026, алерт «доля мелких мастеров выросла на 2.4 п.п.». Причина — две
ошибки одного класса: «файла нет на диске» трактовалось как «обложки нет»,
хотя с 28.08 (S3) LRU выселяет локальную копию, оставляя cover_cached_at.

1. Защита от даунгрейда в download_and_store читала размер сохранённой
   обложки ТОЛЬКО внутри `if dest.exists()`. У выселенной порога не было, и
   любая картинка — хоть 270px-миниатюра skifmusic.ru — ложилась поверх и
   уезжала в бакет по тому же ключу. Хорошая обложка затиралась насовсем.
2. Добор магазинных обложек отбирал записи по `cover_local_path IS NULL`, то
   есть и выселенные тоже: 11 788 из 11 813 строк очереди (99.8%) уже лежали
   в бакете, добор гонял их по кругу ~1 000 раз в час.
"""
import inspect
from datetime import datetime
from io import BytesIO

import pytest
from PIL import Image

from app.services import cover_storage
from app.services.cover_storage import CoverStorageService


def _jpeg(side: int) -> bytes:
    buf = BytesIO()
    Image.new("RGB", (side, side), (10, 120, 200)).save(buf, format="JPEG")
    return buf.getvalue()


class _Resp:
    status_code = 200

    def __init__(self, content: bytes):
        self.content = content

    def raise_for_status(self):
        return None


class _Row:
    def __init__(self, cached_at, min_side):
        self.cover_cached_at = cached_at
        self.cover_min_side = min_side


class _DB:
    """Первый SELECT возвращает строку записи, всё прочее — пишет."""

    def __init__(self, row):
        self.row = row
        self.writes = 0

    async def execute(self, stmt, *a, **kw):
        if stmt.__class__.__name__ == "Select":
            return _Result(self.row)
        self.writes += 1
        return _Result(None)

    async def commit(self):
        return None


class _Result:
    def __init__(self, row):
        self.row = row

    def first(self):
        return self.row

    def scalars(self):
        return self


def _async(value):
    async def _coro():
        return value
    return _coro()


@pytest.fixture()
def env(tmp_path, monkeypatch):
    """S3 включён, бакет отвечает управляемо, скачивание считается."""
    monkeypatch.setenv("COVERS_DIR", str(tmp_path))
    from app import config
    config.get_settings.cache_clear()

    state = {"in_bucket": True, "downloads": 0, "uploads": [], "frame": 800}

    def fake_get(url, timeout=None):
        state["downloads"] += 1
        return _async(_Resp(_jpeg(state["frame"])))

    monkeypatch.setattr(cover_storage, "safe_image_get", fake_get)
    monkeypatch.setattr("app.services.s3_covers.enabled", lambda: True)
    monkeypatch.setattr(
        "app.services.s3_covers.cover_exists", lambda name: _async(state["in_bucket"]),
    )
    monkeypatch.setattr(
        "app.services.s3_covers.schedule_upload", lambda p: state["uploads"].append(p),
    )
    monkeypatch.setattr(
        "app.services.cover_demand.record_acquisition", lambda trigger: _async(None),
    )

    svc = CoverStorageService()
    monkeypatch.setattr(svc, "_acquire_lock", lambda did: _async(True))
    monkeypatch.setattr(svc, "_release_lock", lambda did: _async(None))
    state["svc"], state["dir"] = svc, tmp_path
    yield state
    config.get_settings.cache_clear()


STORE_THUMB = "https://skifmusic.ru/thumbs/a5/5e/270x270_1_normal_ec7e.webp"
CAA = "https://coverartarchive.org/release/x/front-1200.jpg"
STAMP = datetime(2026, 9, 17, 12, 0)


@pytest.mark.asyncio
async def test_good_evicted_cover_is_not_overwritten(env):
    """ГЛАВНОЕ. Обложка 600px выселена в бакет — миниатюра 270px её не трогает.

    И даже не скачивается: сеть и бюджет чужого CDN не тратятся.
    """
    env["frame"] = 270
    db = _DB(_Row(STAMP, 600))
    result = await env["svc"].download_and_store("4701865", STORE_THUMB, db)
    assert result == "covers/4701865.jpg"
    assert env["downloads"] == 0, "нормальную обложку не за чем перекачивать"
    assert env["uploads"] == [], "в бакет ничего не должно уйти — ключ тот же"
    assert db.writes == 0, "cover_cached_at трогать нельзя"
    assert not (env["dir"] / "4701865.jpg").exists()


@pytest.mark.asyncio
async def test_unmeasured_evicted_cover_is_left_alone(env):
    """cover_min_side NULL — «не мерили». Как и для файла на диске: не трогаем."""
    db = _DB(_Row(STAMP, None))
    await env["svc"].download_and_store("100", STORE_THUMB, db)
    assert env["downloads"] == 0
    assert env["uploads"] == []


@pytest.mark.asyncio
async def test_small_evicted_cover_still_upgrades(env):
    """Апгрейд обязан работать и для выселенных: 270px → 800px из CAA."""
    env["frame"] = 800
    db = _DB(_Row(STAMP, 270))
    result = await env["svc"].download_and_store("200", CAA, db)
    assert result == "covers/200.jpg"
    assert env["downloads"] == 1
    assert (env["dir"] / "200.jpg").exists()
    assert len(env["uploads"]) == 1


@pytest.mark.asyncio
async def test_small_evicted_cover_is_not_replaced_by_smaller(env):
    """Пол апгрейда: 270px в бакете, пришло 200px — остаётся 270px."""
    env["frame"] = 200
    db = _DB(_Row(STAMP, 270))
    await env["svc"].download_and_store("300", STORE_THUMB, db)
    assert env["uploads"] == [], "мелкое не должно затереть бакет"
    assert not (env["dir"] / "300.jpg").exists()


@pytest.mark.asyncio
async def test_marker_without_bucket_object_self_heals(env):
    """Метка есть, а файла в бакете нет — запись битая. Ей нужно самолечение,
    а не ранний выход: качаем как первую запись."""
    env["in_bucket"] = False
    env["frame"] = 700
    db = _DB(_Row(STAMP, 600))
    result = await env["svc"].download_and_store("400", CAA, db)
    assert result == "covers/400.jpg"
    assert env["downloads"] == 1
    assert (env["dir"] / "400.jpg").exists()


@pytest.mark.asyncio
async def test_never_mirrored_is_a_plain_first_write(env):
    """Метки нет — обычная первая запись, пола нет, кладём даже мелкое."""
    env["frame"] = 270
    db = _DB(_Row(None, None))
    result = await env["svc"].download_and_store("500", STORE_THUMB, db)
    assert result == "covers/500.jpg"
    assert (env["dir"] / "500.jpg").exists()


def test_store_backfill_skips_mirrored_records():
    """Очередь добора обязана исключать выселенные — иначе петля
    «выселил → перекачал → выселил», 99.8% очереди впустую."""
    from app.tasks import cover_drip_tasks
    src = inspect.getsource(cover_drip_tasks.backfill_store_covers)
    assert "r.cover_cached_at IS NULL" in src


def test_upgrade_sweep_sees_evicted_covers():
    """Ночной апгрейд обязан видеть выселенные мелкие обложки.

    Он отбирал по cover_local_path IS NOT NULL, а LRU выселяет за ~15 минут —
    то есть мелкая обложка из бакета не улучшалась никогда, и затёртые
    даунгрейдом не возвращались бы сами."""
    from app.tasks import cover_upgrade_tasks
    src = inspect.getsource(cover_upgrade_tasks.upgrade_low_res_covers)
    assert "WHERE cover_cached_at IS NOT NULL" in src
    assert "WHERE cover_local_path IS NOT NULL" not in src


def test_versions_and_suggest_find_mirror_by_cached_at():
    """Версии мастера и подсказки отдают адрес клиенту прямо из SQL.

    Прежний `CASE WHEN r.cover_local_path IS NOT NULL` для выселенной обложки
    проваливался дальше по COALESCE — на прямой i.discogs.com, недоступный из
    РФ. LRU выселяет за ~15 минут, то есть почти любую обложку."""
    import app.api.records as R
    frag = R._MIRROR_URL_SQL
    assert "r.cover_cached_at IS NOT NULL" in frag
    # Тот же путь и та же метка, что у витрины и схем — общий ключ кэша.
    assert "'/covers/' || r.discogs_id || '.jpg?v='" in frag
    assert "floor(extract(epoch from r.cover_cached_at))" in frag
    for fn in (R._suggest_local, R._fetch_versions_from_local_index):
        src = inspect.getsource(fn)
        assert "{_MIRROR_URL_SQL}" in src, fn.__name__
        assert 'f"""' in src, f"{fn.__name__}: без f-строки фрагмент уйдёт в SQL буквально"
        assert "CASE WHEN r.cover_local_path IS NOT NULL" not in src


def test_harvest_guard_treats_evicted_as_present():
    """Защитная проверка харвеста при матчинге магазина — тот же класс."""
    from app.services import cover_storage
    src = inspect.getsource(cover_storage)
    assert "row.cover_cached_at is None" in src


def test_market_health_does_not_count_evicted_as_missing():
    """Метрика «можно закрыть бесплатно» считала выселенные:
    11 813 вместо реальных 25, и рост значил работу LRU, а не поломку."""
    from app.services import market_health
    assert "r.cover_cached_at IS NULL" in str(market_health._COVERS_SQL)
