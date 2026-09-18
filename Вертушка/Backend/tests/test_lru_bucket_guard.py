"""LRU не удаляет локальную обложку, пока не убедится, что она в бакете.

18.09.2026. Обложка попадает в S3 асинхронно: запись на диск → очередь в памяти
→ тред-заливщик. Очередь пропадает при перезапуске процесса (scheduler за сутки
перезапускался autoheal'ом 6 раз) и выбрасывает пути при переполнении, а
обещанного в коде «реконсилера» не существовало. LRU при этом удалял файл, не
спрашивая бакет, и оставлял cover_cached_at — то есть объявлял обложку живущей
в S3. Потерянная заливка = обложка пропала насовсем.

Замер в тот день: 0 из 300 выселенных не пропало. Спасало время (LRU берёт
старейшие файлы, заливка давно прошла), а не код. Здесь — код.
"""
import asyncio
import os
from pathlib import Path

import pytest

from app.services import s3_covers


class _NotFound(Exception):
    def __str__(self):
        return "An error occurred (404) when calling the HeadObject operation: Not Found"


class _FakeBucket:
    """head_object/upload_file как у boto, с управляемыми сбоями."""

    def __init__(self, present=(), head_error=None, upload_error=None):
        self.present = set(present)
        self.head_error = head_error
        self.upload_error = upload_error
        self.uploaded: list[str] = []

    def head_object(self, Bucket, Key):
        if self.head_error:
            raise self.head_error
        if Key not in self.present:
            raise _NotFound()
        return {}

    def upload_file(self, filename, bucket, key, ExtraArgs=None):
        if self.upload_error:
            raise self.upload_error
        self.uploaded.append(key)
        self.present.add(key)


@pytest.fixture
def covers(tmp_path, monkeypatch):
    d = tmp_path / "uploads" / "covers"
    d.mkdir(parents=True)
    from app.config import get_settings
    monkeypatch.setattr(get_settings(), "covers_dir", str(d), raising=False)
    return d


def _file(covers: Path, name: str) -> Path:
    p = covers / name
    p.write_bytes(b"\xff\xd8jpeg")
    return p


def test_already_in_bucket_is_safe_without_upload(covers):
    p = _file(covers, "1.jpg")
    bucket = _FakeBucket(present={"covers/1.jpg"})
    assert s3_covers.ensure_in_bucket_sync(p, bucket) is True
    assert bucket.uploaded == []


def test_missing_from_bucket_is_uploaded_before_it_may_go(covers):
    """Главный сценарий: заливка потерялась при перезапуске — догоняем здесь."""
    p = _file(covers, "2.jpg")
    bucket = _FakeBucket()
    assert s3_covers.ensure_in_bucket_sync(p, bucket) is True
    assert bucket.uploaded == ["covers/2.jpg"]


def test_bucket_unreachable_means_keep_the_file(covers):
    """Обратное правило, чем у exists_sync: сбой сети ≠ «файл есть»."""
    p = _file(covers, "3.jpg")
    bucket = _FakeBucket(head_error=ConnectionError("timeout"))
    assert s3_covers.ensure_in_bucket_sync(p, bucket) is False
    assert bucket.uploaded == []


def test_failed_upload_means_keep_the_file(covers):
    p = _file(covers, "4.jpg")
    bucket = _FakeBucket(upload_error=ConnectionError("reset"))
    assert s3_covers.ensure_in_bucket_sync(p, bucket) is False


def test_nested_store_path_keeps_its_key(covers):
    """covers/store/… тоже зеркалится — ключ обязан повторять путь."""
    (covers / "store").mkdir()
    p = _file(covers, "store/abc.jpg")
    bucket = _FakeBucket()
    assert s3_covers.ensure_in_bucket_sync(p, bucket) is True
    assert bucket.uploaded == ["covers/store/abc.jpg"]


def test_batch_returns_only_confirmed(covers, monkeypatch):
    ok, bad = _file(covers, "5.jpg"), _file(covers, "6.jpg")

    class _Half(_FakeBucket):
        def head_object(self, Bucket, Key):
            if Key.endswith("6.jpg"):
                raise ConnectionError("timeout")
            return super().head_object(Bucket, Key)

    monkeypatch.setattr(s3_covers, "_get_restore_client", lambda: _Half(present={"covers/5.jpg"}))
    assert s3_covers.ensure_many_in_bucket_sync([ok, bad]) == {ok}


# --- сам LRU ---------------------------------------------------------------


class _Row:
    def __init__(self, id, discogs_id, cover_local_path):
        self.id, self.discogs_id, self.cover_local_path = id, discogs_id, cover_local_path


class _FakeDB:
    """Первый execute — выборка кандидатов, дальше — UPDATE указателей."""

    def __init__(self, rows):
        self.rows = rows
        self.calls = 0
        self.updates = []

    async def execute(self, stmt, *a, **kw):
        self.calls += 1
        if self.calls == 1:
            rows = self.rows

            class _R:
                def all(self_inner):
                    return rows
            return _R()
        self.updates.append(stmt)
        return None

    async def commit(self):
        return None


def test_lru_keeps_file_the_bucket_did_not_confirm(tmp_path, monkeypatch):
    """Сквозная проверка: подтверждённый файл выселен, неподтверждённый — на месте,
    и указатель в БД снят ТОЛЬКО у выселенного."""
    from app.services import cover_storage
    from app.services.cover_storage import CoverStorageService

    monkeypatch.chdir(tmp_path)
    d = tmp_path / "uploads" / "covers"
    d.mkdir(parents=True)
    old, young = d / "10.jpg", d / "11.jpg"
    for f in (old, young):
        f.write_bytes(b"x" * 1024 * 1024)  # 1 МБ
    os.utime(old, (1, 1))  # старейший — первый в очереди на выселение
    os.utime(young, (2, 2))

    svc = CoverStorageService.__new__(CoverStorageService)
    monkeypatch.setattr(svc, "_get_cache_size_mb", lambda: 100.0, raising=False)

    async def no_masters(db):
        return []
    monkeypatch.setattr(svc, "_master_orphan_candidates", no_masters, raising=False)

    monkeypatch.setattr(s3_covers, "enabled", lambda: True)
    # Бакет подтверждает только старший файл.
    monkeypatch.setattr(
        s3_covers, "ensure_many_in_bucket_sync",
        lambda paths: {p for p in paths if p.name == "10.jpg"},
    )

    import uuid
    r10, r11 = uuid.uuid4(), uuid.uuid4()
    db = _FakeDB([_Row(r10, "10", "covers/10.jpg"), _Row(r11, "11", "covers/11.jpg")])
    deleted = asyncio.run(svc.cleanup_lru(1, db))

    assert not old.exists(), "подтверждённый бакетом файл должен уйти"
    assert young.exists(), "неподтверждённый обязан остаться на диске"
    assert deleted == 1
    # UPDATE снимает указатель только у r10
    assert db.updates, "указатель выселенного должен быть снят"
    params = db.updates[0].compile().params
    ids = [v for v in params.values() if isinstance(v, (list, tuple))]
    flat = {x for group in ids for x in group}
    assert r10 in flat and r11 not in flat
