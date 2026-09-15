"""Накопленная обложка не может быть заменена худшей.

Зачем файл. Ветка апгрейда в download_and_store проверяла ОДНО: что лежащий
файл мельче порога мастера. Что новый кадр лучше старого — не проверял никто.
Источник с картинкой 199px спокойно затирал имеющиеся 475px, причём
безвозвратно: путь и ключ в бакете те же, прежних байтов после rename нет
нигде. В логах 14–15.09.2026 такие записи идут подряд — «stored below master
threshold (min_side=475)», следом «(min_side=199)».

База обложек — актив, который копится годами и только дорожает. Правило,
которое здесь фиксируется: качество по каждому пути может только расти.
"""
from io import BytesIO

import pytest
from PIL import Image

from app.services import cover_storage
from app.services.cover_storage import _encode_and_place


def _jpeg(side: int) -> bytes:
    """Квадрат side×side. Цвет неважен — меряется геометрия."""
    buf = BytesIO()
    Image.new("RGB", (side, side), (90, 60, 30)).save(buf, format="JPEG")
    return buf.getvalue()


@pytest.fixture()
def no_s3(monkeypatch):
    """Гасим dual-write и считаем обращения к нему.

    Отдельный список, а не мок целиком: заливка в бакет — это ВТОРАЯ
    необратимая запись (ключ тот же), и «файл не заменили, но в S3 отправили»
    было бы той же потерей, только через минуту.
    """
    calls: list = []
    monkeypatch.setattr(
        "app.services.s3_covers.schedule_upload", lambda p: calls.append(p),
    )
    return calls


def test_first_write_has_no_floor(tmp_path, no_s3):
    """Файла ещё нет — кладём что дали, даже мелкое.

    Мелкая обложка лучше серого квадрата; её потом догонит апгрейд.
    """
    dest = tmp_path / "1.jpg"
    placed = _encode_and_place(_jpeg(200), tmp_path / ".tmp", dest)
    assert placed.written is True
    assert placed.min_side == 200
    assert dest.exists()
    assert len(no_s3) == 1


def test_smaller_frame_never_replaces(tmp_path, no_s3):
    """199px не затирает 475px — ровно случай из прода."""
    dest = tmp_path / "2.jpg"
    _encode_and_place(_jpeg(475), tmp_path / ".tmp1", dest)
    before = dest.read_bytes()
    no_s3.clear()

    placed = _encode_and_place(
        _jpeg(199), tmp_path / ".tmp2", dest, replace_floor=475,
    )
    assert placed.written is False
    assert placed.min_side == 199
    assert dest.read_bytes() == before, "старые байты обязаны уцелеть"
    assert no_s3 == [], "в бакет тоже ничего не ушло"


def test_equal_size_does_not_replace(tmp_path, no_s3):
    """Равный размер — не улучшение.

    Перезапись «тем же самым» не бесплатна: это лишний PUT в бакет и новая
    версия объекта, а выигрыша ноль.
    """
    dest = tmp_path / "3.jpg"
    _encode_and_place(_jpeg(300), tmp_path / ".tmp1", dest)
    no_s3.clear()
    placed = _encode_and_place(
        _jpeg(300), tmp_path / ".tmp2", dest, replace_floor=300,
    )
    assert placed.written is False
    assert no_s3 == []


def test_bigger_frame_does_replace(tmp_path, no_s3):
    """Апгрейд обязан работать: 900px заменяет 300px."""
    dest = tmp_path / "4.jpg"
    _encode_and_place(_jpeg(300), tmp_path / ".tmp1", dest)
    small = dest.read_bytes()
    no_s3.clear()

    placed = _encode_and_place(
        _jpeg(900), tmp_path / ".tmp2", dest, replace_floor=300,
    )
    assert placed.written is True
    assert placed.min_side == 900
    assert dest.read_bytes() != small
    assert len(no_s3) == 1


def test_no_temp_file_left_behind(tmp_path, no_s3):
    """Отказ не должен оставлять мусор рядом с обложками.

    tmp лежит в той же папке, что и зеркала; забытые .tmp_* съедали бы место
    и попадали в обход LRU (она ходит по m*/{id}.jpg).
    """
    dest = tmp_path / "5.jpg"
    _encode_and_place(_jpeg(600), tmp_path / ".tmp1", dest)
    tmp = tmp_path / ".tmp2"
    _encode_and_place(_jpeg(100), tmp, dest, replace_floor=600)
    assert not tmp.exists()


def test_upscale_is_not_an_upgrade(tmp_path, no_s3):
    """Апскейла нет: _MAX_SIDE режет только вниз.

    Значит min_side честно отражает исходник, и «улучшение» нельзя подделать
    растягиванием мелкой картинки.
    """
    dest = tmp_path / "6.jpg"
    placed = _encode_and_place(_jpeg(cover_storage._MAX_SIDE + 500), tmp_path / ".t", dest)
    assert placed.min_side == cover_storage._MAX_SIDE
