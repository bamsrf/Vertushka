"""Первая запись зеркала: скачали — значит положили.

Зачем файл. 15.09.2026 гейт деградации (PR #243) добавил в путь скачивания
чтение `needs_upgrade`, а объявлена эта переменная была только внутри ветки
`if dest.exists()`. Когда файла нет — то есть в ОСНОВНОМ случае, первой записи
зеркала — обращение падало UnboundLocalError. Исключение съедал общий except
вокруг скачивания, и наружу это выглядело как «не удалось скачать обложку»:
картинка уже была получена по сети, но на диск не попадала никогда.

Прод простоял так полдня. Видимых ошибок не было — были следствия: ни одного
нового зеркала, 100% отказов у зеркалирования мастеров, холодные обложки
уходили редиректом на Discogs, оттуда 429, размыкание circuit breaker и 503
живым пользователям.

Мои тесты на гейт проверяли только сам кодировщик, в обход download_and_store.
Здесь закрыт именно сквозной путь.
"""
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


class _FakeDB:
    """Принимает любые execute/commit — путь первой записи только пишет."""

    def __init__(self):
        self.executed = 0

    async def execute(self, *a, **kw):
        self.executed += 1
        return self

    async def commit(self):
        return None

    def scalars(self):
        return self

    def first(self):
        return None


@pytest.fixture()
def service(tmp_path, monkeypatch):
    monkeypatch.setenv("COVERS_DIR", str(tmp_path))
    from app import config
    config.get_settings.cache_clear()

    monkeypatch.setattr(
        cover_storage, "safe_image_get",
        lambda url, timeout=None: _async(_Resp(_jpeg(800))),
    )
    monkeypatch.setattr("app.services.s3_covers.schedule_upload", lambda p: None)

    svc = CoverStorageService()
    monkeypatch.setattr(svc, "_acquire_lock", lambda did: _async(True))
    monkeypatch.setattr(svc, "_release_lock", lambda did: _async(None))
    yield svc
    config.get_settings.cache_clear()


def _async(value):
    async def _coro():
        return value
    return _coro()


@pytest.mark.asyncio
async def test_first_write_returns_path_and_creates_file(service, tmp_path, monkeypatch):
    """Ровно тот случай, который был сломан: файла нет, качаем, кладём."""
    monkeypatch.setattr(
        "app.services.cover_demand.record_acquisition", lambda trigger: _async(None),
    )
    result = await service.download_and_store(
        "m4186140", "https://cdn-images.dzcdn.net/images/cover/x/1000x1000.jpg", _FakeDB(),
    )
    assert result == "covers/m4186140.jpg", "вернуть путь, а не None"
    assert (tmp_path / "m4186140.jpg").is_file(), "файл обязан лечь на диск"


@pytest.mark.asyncio
async def test_master_id_without_records_row_still_stored(service, tmp_path, monkeypatch):
    """У мастера (m{id}) строки в records нет вовсе.

    Зеркалирование мастеров ходит именно так, и отсутствие строки не должно
    мешать положить файл: сетку артиста обслуживает файл, а не запись в БД.
    """
    monkeypatch.setattr(
        "app.services.cover_demand.record_acquisition", lambda trigger: _async(None),
    )
    result = await service.download_and_store(
        "m999999", "https://coverartarchive.org/release/x/front-1200.jpg", _FakeDB(),
    )
    assert result is not None
    assert (tmp_path / "m999999.jpg").is_file()
