"""Read-путь S3 и освобождение LRU: контракты, которые нельзя молча потерять.

- restore_sync принимает только имена, которые раздаёт /covers/ (m?\\d+):
  всё пришедшее из URL и не похожее на них — отказ, а не запись на диск;
- restore выключен → False без единого сетевого вызова;
- restore пишет атомарно (tmp → rename) и возвращает True, при отсутствии
  в бакете — False и никакого файла;
- новый исход s3_restore заявлен в реестре исходов холодного пути;
- уборка LRU: при включённом S3 из фильтров уходят защиты Маркета/библиотек/
  discogs.com (остаётся только user), а cover_cached_at ПЕРЕЖИВАЕТ эвикцию —
  по нему market-enrich отличает «выселено, лежит в S3» от «никогда не было»;
- у enrich_market_covers цель сужена условием cover_cached_at IS NULL —
  иначе выселение возвращает июльский churn «скачал-выбросил-скачал».
"""
import inspect
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import Settings  # noqa: E402
from app.services import s3_covers  # noqa: E402


def _settings(monkeypatch, tmp_path, enabled=True):
    monkeypatch.setenv("DEBUG", "true")
    monkeypatch.setenv("COVERS_DIR", str(tmp_path / "uploads" / "covers"))
    env = {
        "COVERS_S3_ENABLED": "true" if enabled else "false",
        "S3_ENDPOINT_URL": "https://s3.example.ru",
        "S3_BUCKET_COVERS": "bucket",
        "S3_ACCESS_KEY_ID": "key",
        "S3_SECRET_ACCESS_KEY": "secret",
    }
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    settings = Settings(_env_file=None)
    monkeypatch.setattr(s3_covers, "get_settings", lambda: settings)
    (tmp_path / "uploads" / "covers").mkdir(parents=True, exist_ok=True)
    return settings


class _FakeClient:
    """download_file пишет файл; бросает, если ключа «нет в бакете»."""

    def __init__(self, existing_keys):
        self.existing = set(existing_keys)
        self.calls = []

    def download_file(self, bucket, key, dest):
        self.calls.append(key)
        if key not in self.existing:
            raise Exception("An error occurred (404) Not Found")
        Path(dest).write_bytes(b"jpegdata")


@pytest.fixture(autouse=True)
def _reset(monkeypatch):
    monkeypatch.setattr(s3_covers, "_restore_client", None)
    monkeypatch.setattr(s3_covers, "_misconfig_logged", False)


def test_restore_rejects_foreign_names(monkeypatch, tmp_path):
    _settings(monkeypatch, tmp_path)
    fake = _FakeClient({"covers/1.jpg"})
    monkeypatch.setattr(s3_covers, "_get_restore_client", lambda: fake)
    for bad in ("../../etc/passwd", "user/abc", "m", "12a", "", "1.jpg"):
        assert s3_covers.restore_sync(bad) is False
    assert fake.calls == []  # ни одного похода в сеть


def test_restore_disabled_is_noop(monkeypatch, tmp_path):
    _settings(monkeypatch, tmp_path, enabled=False)
    fake = _FakeClient({"covers/1.jpg"})
    monkeypatch.setattr(s3_covers, "_get_restore_client", lambda: fake)
    assert s3_covers.restore_sync("1") is False
    assert fake.calls == []


def test_restore_downloads_and_places(monkeypatch, tmp_path):
    settings = _settings(monkeypatch, tmp_path)
    fake = _FakeClient({"covers/123.jpg"})
    monkeypatch.setattr(s3_covers, "_get_restore_client", lambda: fake)

    assert s3_covers.restore_sync("123") is True
    dest = Path(settings.covers_dir) / "123.jpg"
    assert dest.read_bytes() == b"jpegdata"
    # повторный вызов — короткое замыкание по существующему файлу
    assert s3_covers.restore_sync("123") is True
    assert fake.calls == ["covers/123.jpg"]

    # в бакете нет → False, файла и tmp-мусора нет
    assert s3_covers.restore_sync("999") is False
    assert not (Path(settings.covers_dir) / "999.jpg").exists()
    assert not list(Path(settings.covers_dir).glob(".tmp_*"))


def test_master_names_supported(monkeypatch, tmp_path):
    settings = _settings(monkeypatch, tmp_path)
    fake = _FakeClient({"covers/m42.jpg"})
    monkeypatch.setattr(s3_covers, "_get_restore_client", lambda: fake)
    assert s3_covers.restore_sync("m42") is True
    assert (Path(settings.covers_dir) / "m42.jpg").exists()


def test_s3_restore_outcome_registered():
    from app.services import cover_demand
    assert cover_demand.OUTCOME_S3_RESTORE == "s3_restore"
    src = inspect.getsource(cover_demand)
    assert src.count("OUTCOME_S3_RESTORE") >= 2  # константа + реестр


def test_cleanup_lru_liberated_only_under_s3():
    """Форма кода: защиты снимаются ТОЛЬКО под флагом S3, user-фото — никогда,
    cover_cached_at при S3 переживает эвикцию."""
    from app.services.cover_storage import CoverStorageService
    src = inspect.getsource(CoverStorageService.cleanup_lru)
    assert "s3_on = _s3_enabled()" in src
    assert "if not s3_on:" in src  # старые защиты живут в ветке без S3
    assert 'is_distinct_from("user")' in src  # безусловная защита user-фото
    # cover_cached_at очищается только в без-S3-ветке
    assert '{"cover_local_path": None} if s3_on' in src


def test_market_enrich_skips_evicted():
    """Цель enrich_market_covers обязана исключать выселенное (cached_at жив),
    иначе цикл «скачал-выбросил-скачал» жжёт квоту get_master."""
    from app.tasks.discogs_tasks import enrich_market_covers
    src = inspect.getsource(enrich_market_covers)
    assert "Record.cover_cached_at.is_(None)" in src


def test_covers_endpoint_tries_s3_first():
    """Холодный путь обязан спросить вечный слой ДО редиректов на внешние
    источники — иначе restore-ветка мертва (урок харвеста 22.07)."""
    import app.api.covers as covers_api
    src = inspect.getsource(covers_api.get_cover)
    restore_pos = src.find("restore_cover(")
    first_redirect = src.find("RedirectResponse(url=")
    assert 0 < restore_pos < first_redirect
    assert "OUTCOME_S3_RESTORE" in src
