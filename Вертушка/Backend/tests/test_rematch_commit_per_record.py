"""WS-фикс 09.09: rematch_store_native коммитит по КАЖДОЙ записи.

Прод 09-09: смерть соединения в середине прогона роняла финальный db.commit()
(PendingRollbackError) и теряла подтверждения всех 1000 записей → merged годами
стоял на 424. Теперь коммит per-record + полный rollback на ошибке + обрыв по
подряд-ошибкам.
"""
import types
import pytest

from app.services import listing_matcher as lm

pytestmark = pytest.mark.asyncio


def _rec(rid, **kw):
    base = dict(
        id=rid, source="store", merged_into_id=None,
        barcode=None, catalog_number=None, artist=f"A{rid}", title=f"T{rid}",
        year=2024, discogs_id_candidate=None,
        discogs_id_candidate_confirmations=0, discogs_id_candidate_first_seen_at=None,
    )
    base.update(kw)
    return types.SimpleNamespace(**base)


class _Result:
    def __init__(self, rows): self._rows = rows
    def scalars(self): return self
    def all(self): return self._rows


class _FakeDB:
    def __init__(self, rows):
        self._rows = rows
        self.commits = 0
        self.rollbacks = 0

    async def __aenter__(self): return self
    async def __aexit__(self, *a): return False
    async def execute(self, *a, **k): return _Result(self._rows)
    async def commit(self): self.commits += 1
    async def rollback(self): self.rollbacks += 1


@pytest.fixture
def patch_env(monkeypatch):
    """Подменяем сессию-фабрику и fetch'и; safe_merge не понадобится (0 подтв.)."""
    def _make(rows):
        db = _FakeDB(rows)
        monkeypatch.setattr(lm, "async_session_maker", lambda: db)
        return db
    return _make


async def test_commit_per_record(monkeypatch, patch_env):
    rows = [_rec("1"), _rec("2"), _rec("3")]
    db = patch_env(rows)
    # каждый находит нового кандидата (discogs_id уникальный, id != rec.id)
    async def _fake_text(dbx, artist, title, year):
        return types.SimpleNamespace(id="disc-" + artist, discogs_id="d" + artist)
    monkeypatch.setattr(lm, "_try_discogs_fetch_by_text", _fake_text)

    out = await lm.rematch_store_native_batch(batch_size=10)
    assert out["processed"] == 3
    assert out["candidates_found"] == 3
    assert db.commits == 3          # ПО КАЖДОЙ записи, не один финальный
    assert db.rollbacks == 0


async def test_mid_batch_failure_persists_prior_and_continues(monkeypatch, patch_env):
    rows = [_rec("1"), _rec("2"), _rec("3")]
    db = patch_env(rows)

    async def _fake_text(dbx, artist, title, year):
        if title == "T2":
            raise RuntimeError("connection is closed")   # смерть соединения на 2-й
        return types.SimpleNamespace(id="disc-" + artist, discogs_id="d" + artist)
    monkeypatch.setattr(lm, "_try_discogs_fetch_by_text", _fake_text)

    out = await lm.rematch_store_native_batch(batch_size=10)
    assert out["processed"] == 3
    assert out["errors"] == 1
    assert out["candidates_found"] == 2       # rec1 и rec3 сохранены
    assert db.commits == 2                    # прогресс rec1/rec3 персистнут
    assert db.rollbacks == 1                  # полный rollback после rec2


async def test_consecutive_errors_break(monkeypatch, patch_env):
    rows = [_rec(str(i)) for i in range(30)]
    db = patch_env(rows)

    async def _boom(dbx, artist, title, year):
        raise RuntimeError("connection is closed")
    monkeypatch.setattr(lm, "_try_discogs_fetch_by_text", _boom)

    out = await lm.rematch_store_native_batch(batch_size=30)
    # обрыв на пороге, а не 30 одинаковых трейсбеков
    assert out["processed"] == lm._REMATCH_MAX_CONSECUTIVE_ERRORS
    assert out["errors"] == lm._REMATCH_MAX_CONSECUTIVE_ERRORS
