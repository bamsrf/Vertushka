"""S3-подготовка обложек (services/s3_covers): контракт до появления бакета.

Что сторожим:
- выключенный флаг = полный no-op (ни тредов, ни очереди, ни импорта boto3);
- включённый флаг с неполным конфигом ведёт себя как выключенный (+error-лог),
  а НЕ роняет приложение и НЕ шлёт запросы;
- ключ в бакете повторяет rel_path зеркала (covers/<имя>) — на этом будет
  строиться read-путь imgproxy/S3;
- _encode_and_place действительно зовёт schedule_upload — единственную точку
  dual-write (иначе слой молча не работает, см. урок харвеста 22.07→12.08);
- boto3 заявлен в requirements — лениво импортируемую зависимость легко
  забыть.
"""
import logging
import sys
from io import BytesIO
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import Settings  # noqa: E402
from app.services import s3_covers  # noqa: E402


def _make_settings(monkeypatch, tmp_path, **env):
    monkeypatch.setenv("DEBUG", "true")
    monkeypatch.setenv("COVERS_DIR", str(tmp_path / "uploads" / "covers"))
    for key in (
        "COVERS_S3_ENABLED", "S3_ENDPOINT_URL", "S3_BUCKET_COVERS",
        "S3_ACCESS_KEY_ID", "S3_SECRET_ACCESS_KEY",
    ):
        monkeypatch.delenv(key, raising=False)
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    settings = Settings(_env_file=None)
    monkeypatch.setattr(s3_covers, "get_settings", lambda: settings)
    return settings


@pytest.fixture(autouse=True)
def _reset_module_state(monkeypatch):
    """Модульное состояние (флаг треда, очередь, error-лог) не должно течь
    между тестами."""
    monkeypatch.setattr(s3_covers, "_worker_started", False)
    monkeypatch.setattr(s3_covers, "_misconfig_logged", False)
    yield
    while not s3_covers._queue.empty():
        s3_covers._queue.get_nowait()


def test_disabled_is_full_noop(monkeypatch, tmp_path):
    _make_settings(monkeypatch, tmp_path)
    s3_covers.schedule_upload(tmp_path / "whatever.jpg")
    assert s3_covers._worker_started is False
    assert s3_covers._queue.empty()


def test_enabled_but_incomplete_config_behaves_disabled(monkeypatch, tmp_path, caplog):
    _make_settings(
        monkeypatch, tmp_path,
        COVERS_S3_ENABLED="true",
        S3_ENDPOINT_URL="https://s3.example.ru",
        # ключей нет
    )
    with caplog.at_level(logging.ERROR):
        s3_covers.schedule_upload(tmp_path / "x.jpg")
        s3_covers.schedule_upload(tmp_path / "y.jpg")
    assert s3_covers._worker_started is False
    assert s3_covers._queue.empty()
    # error ровно один: миллион строк за ночь никому не нужен
    errors = [r for r in caplog.records if "dual-write выключен" in r.message]
    assert len(errors) == 1
    assert "S3_ACCESS_KEY_ID" in errors[0].message


def test_s3_key_mirrors_local_rel_path(monkeypatch, tmp_path):
    _make_settings(monkeypatch, tmp_path)
    covers = tmp_path / "uploads" / "covers"
    covers.mkdir(parents=True)
    (covers / "123.jpg").write_bytes(b"x")
    (covers / "m456.jpg").write_bytes(b"x")
    assert s3_covers.s3_key_for(covers / "123.jpg") == "covers/123.jpg"
    assert s3_covers.s3_key_for(covers / "m456.jpg") == "covers/m456.jpg"
    with pytest.raises(ValueError):
        s3_covers.s3_key_for(tmp_path / "outside.jpg")


def test_schedule_upload_enqueues_when_enabled(monkeypatch, tmp_path):
    _make_settings(
        monkeypatch, tmp_path,
        COVERS_S3_ENABLED="true",
        S3_ENDPOINT_URL="https://s3.example.ru",
        S3_BUCKET_COVERS="vertushka-covers",
        S3_ACCESS_KEY_ID="key",
        S3_SECRET_ACCESS_KEY="secret",
    )
    # тред не поднимаем — интересна только постановка в очередь
    monkeypatch.setattr(s3_covers, "_worker_started", True)
    target = tmp_path / "uploads" / "covers" / "1.jpg"
    s3_covers.schedule_upload(target)
    assert s3_covers._queue.get_nowait() == target


def test_encode_and_place_calls_dual_write(monkeypatch, tmp_path):
    """_encode_and_place — единственная точка записи мастеров; если хук
    отвалится (рефакторинг, ранний return), S3-слой умрёт молча."""
    from PIL import Image
    from app.services.cover_storage import _encode_and_place

    raw_io = BytesIO()
    Image.new("RGB", (32, 20), color=(200, 10, 10)).save(raw_io, format="JPEG")

    seen: list[Path] = []
    monkeypatch.setattr(s3_covers, "schedule_upload", lambda p: seen.append(p))

    dest = tmp_path / "77.jpg"
    bhash, min_side = _encode_and_place(raw_io.getvalue(), tmp_path / ".tmp_77.jpg", dest)
    assert dest.exists()
    assert min_side == 20
    assert seen == [dest]


def test_boto3_pinned_in_requirements():
    req = (Path(__file__).resolve().parents[1] / "requirements.txt").read_text()
    assert "boto3==" in req
