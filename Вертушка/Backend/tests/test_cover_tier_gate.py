"""Зеркало не должно принимать мелкую картинку за мастер.

Регрессия: 150px-thumb из `/masters/{id}/versions` укладывался на диск как
мастер (порога размера не было), imgproxy честно резал из него, деталь-экран
получал апскейл ×8. Файл при этом не перекачивался никогда — `dest.exists()`
делал безусловный short-circuit.

Здесь сторожим три вещи: пре-фильтр по URL срабатывает ДО сети, энкодер
возвращает реальный размер уложенного файла, и мелкая картинка не апскейлится
до порога (то есть min_side честно остаётся маленьким, а не подгоняется).
"""
import asyncio
from io import BytesIO
from pathlib import Path

import pytest
from PIL import Image

from app.services.cover_quality import MASTER_MIN_SIDE
from app.services.cover_storage import CoverStorageService, _encode_and_place

_THUMB_150 = (
    "https://i.discogs.com/abc/rs:fit/g:sm/q:40/h:150/w:150/czM6Ly9kaXNjb2dz.jpeg"
)


def _jpeg_bytes(width: int, height: int) -> bytes:
    buf = BytesIO()
    Image.new("RGB", (width, height), (10, 120, 200)).save(buf, format="JPEG")
    return buf.getvalue()


class _ExplodingSession:
    """Любое обращение к БД — провал теста: гейт обязан отработать раньше."""

    def __getattr__(self, name):  # pragma: no cover — вызов = баг
        raise AssertionError(f"DB touched before the tier gate: .{name}")


def test_thumb_grade_url_never_reaches_network_or_db():
    service = CoverStorageService()
    result = asyncio.run(
        service.download_and_store("736788", _THUMB_150, _ExplodingSession())
    )
    assert result is None


def test_encoder_reports_min_side_of_stored_file(tmp_path: Path):
    dest = tmp_path / "cover.jpg"
    tmp = tmp_path / ".tmp_cover.jpg"

    _bhash, min_side = _encode_and_place(_jpeg_bytes(1400, 1400), tmp, dest)

    # Мастер капится 1000px по большей стороне ⇒ меньшая тоже 1000.
    assert min_side == 1000
    assert dest.is_file()


def test_encoder_does_not_upscale_small_source(tmp_path: Path):
    """Мелкое остаётся мелким: апскейла нет, и min_side это показывает.

    Именно на этом значении построен демоут — файл кладём (база обложек
    накапливается, ничего не удаляем), но помечаем размером, и апгрейд-ветка
    пускает перекачку с лучшего источника.
    """
    dest = tmp_path / "cover.jpg"
    tmp = tmp_path / ".tmp_cover.jpg"

    _bhash, min_side = _encode_and_place(_jpeg_bytes(150, 150), tmp, dest)

    assert min_side == 150
    assert min_side < MASTER_MIN_SIDE
    with Image.open(dest) as img:
        assert img.size == (150, 150)


def test_encoder_uses_shorter_side_for_non_square(tmp_path: Path):
    """Разворот 400×300: тир решает меньшая сторона, иначе высота пикселила бы."""
    dest = tmp_path / "cover.jpg"
    tmp = tmp_path / ".tmp_cover.jpg"

    _bhash, min_side = _encode_and_place(_jpeg_bytes(400, 300), tmp, dest)

    assert min_side == 300
