"""Инфраструктурная ошибка не должна сжигать 7-дневный кулдаун матчинга.

Диагноз 2026-08-23: `_try_discogs_fetch*` глотали любой Exception как
«Discogs не знает такого релиза» (`except Exception: return None`) —
httpx-таймаут, смерть соединения БД и MissingGreenlet выглядели как честный
промах. match_listing возвращал False, листинг попадал в attempted_ids →
UPDATE match_attempted_at → недельный кулдаун. За ночь 23.08 так заморожено
13 листингов, про которые Discogs ни разу не спросили.

Лечение — `_infra_blocked` (ContextVar, по образцу `_quota_blocked`):
инфра-ошибка оставляет листинг в голове очереди, честный 404/пусто сжигает
кулдаун как раньше.
"""
import asyncio

import httpx
import pytest
from sqlalchemy import Update
from sqlalchemy.exc import MissingGreenlet

from app.models.store_listing import StoreListing
from app.services import listing_matcher


# ---- Классификация _is_infra_error ------------------------------------- #


def _http_status_error(code: int) -> httpx.HTTPStatusError:
    req = httpx.Request("GET", "https://api.discogs.com/database/search")
    resp = httpx.Response(code, request=req)
    return httpx.HTTPStatusError(f"HTTP {code}", request=req, response=resp)


@pytest.mark.parametrize("exc", [
    httpx.ConnectError("dns умер"),
    httpx.ConnectTimeout("нет маршрута"),
    httpx.ReadTimeout("Discogs молчит 30с"),
    asyncio.TimeoutError(),
    MissingGreenlet("greenlet_spawn has not been called"),
    # 429 — квота Discogs: беда прогона, не листинга.
    _http_status_error(429),
])
def test_infra_errors_do_not_burn_cooldown(exc):
    assert listing_matcher._is_infra_error(exc) is True


@pytest.mark.parametrize("exc", [
    # Честный ответ Discogs «нет такого релиза» — кулдаун заслужен.
    _http_status_error(404),
    _http_status_error(400),
    # Прикладные ошибки: баг в наших данных, повтор через час бессмыслен.
    ValueError("кривой raw_payload"),
    KeyError("id"),
])
def test_application_errors_burn_cooldown(exc):
    assert listing_matcher._is_infra_error(exc) is False


def test_infra_flag_is_contextvar_not_global():
    """Матчер живёт в общем event loop — глобальный флаг протёк бы в чужие задачи."""
    from contextvars import ContextVar
    assert isinstance(listing_matcher._infra_blocked, ContextVar)
    assert listing_matcher._infra_blocked.get() is False


# ---- On-demand fetch'и ставят флаг -------------------------------------- #


@pytest.fixture
def reset_flags():
    listing_matcher._quota_blocked.set(False)
    listing_matcher._infra_blocked.set(False)
    yield
    listing_matcher._quota_blocked.set(False)
    listing_matcher._infra_blocked.set(False)


@pytest.mark.asyncio
async def test_barcode_fetch_infra_error_raises_flag(monkeypatch, reset_flags):
    from app.services.discogs import DiscogsService

    async def _dead(self, url, **kw):
        raise httpx.ConnectTimeout("Discogs недоступен")

    monkeypatch.setattr(DiscogsService, "_get", _dead)
    rec = await listing_matcher._try_discogs_fetch(None, barcode="602435973548", catalog=None)
    assert rec is None
    assert listing_matcher._infra_blocked.get() is True


@pytest.mark.asyncio
async def test_barcode_fetch_honest_empty_burns_cooldown(monkeypatch, reset_flags):
    """Пустой results — Discogs честно не знает релиза, попытка состоялась."""
    from app.services.discogs import DiscogsService

    async def _empty(self, url, **kw):
        return {"results": []}

    monkeypatch.setattr(DiscogsService, "_get", _empty)
    rec = await listing_matcher._try_discogs_fetch(None, barcode="602435973548", catalog=None)
    assert rec is None
    assert listing_matcher._infra_blocked.get() is False


@pytest.mark.asyncio
async def test_text_fetch_infra_error_raises_flag(monkeypatch, reset_flags):
    from app.services.discogs import DiscogsService

    async def _dead(self, url, **kw):
        raise httpx.ReadTimeout("Discogs молчит")

    monkeypatch.setattr(DiscogsService, "_get", _dead)
    rec = await listing_matcher._try_discogs_fetch_by_text(
        None, artist="Miles Davis", title="Kind Of Blue", year=1959,
    )
    assert rec is None
    assert listing_matcher._infra_blocked.get() is True


# ---- match_unmatched_batch: инфра-ошибка не попадает в attempted_ids ---- #


class _Result:
    def __init__(self, payload):
        self.payload = payload

    def scalars(self):
        return self

    def all(self):
        return self.payload

    def scalar(self):
        return self.payload


class _Savepoint:
    async def commit(self):
        pass

    async def rollback(self):
        pass


class _Session:
    """Стаб сессии: отдаёт заготовленные листинги, копит UPDATE-стейтменты."""

    def __init__(self, listings, updates):
        self._listings = listings
        self._updates = updates

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def begin_nested(self):
        return _Savepoint()

    async def execute(self, stmt):
        if isinstance(stmt, Update):
            self._updates.append(stmt)
            return _Result(None)
        if "count" in str(stmt).lower():
            return _Result(0)  # queue_left
        return _Result(self._listings)

    async def commit(self):
        pass

    async def rollback(self):
        pass


def _listing(listing_id: int = 1) -> StoreListing:
    return StoreListing(
        id=listing_id,
        artist_raw="Miles Davis",
        title_raw="Kind Of Blue",
        raw_payload={},
        status="in_stock",
    )


def _stamped_ids(updates) -> list:
    """id из UPDATE ... WHERE store_listings.id IN (attempted_ids)."""
    ids: list = []
    for stmt in updates:
        for crit in stmt._where_criteria:
            ids.extend(crit.right.value)
    return ids


async def _run_batch(monkeypatch, listings, match_fake):
    updates: list = []
    monkeypatch.setattr(
        listing_matcher, "async_session_maker", lambda: _Session(listings, updates),
    )
    monkeypatch.setattr(listing_matcher, "match_listing", match_fake)
    counters = await listing_matcher.match_unmatched_batch(batch_size=10)
    return counters, updates


@pytest.mark.asyncio
async def test_infra_blocked_listing_not_stamped(monkeypatch, reset_flags):
    """Фетч умер на инфраструктуре → листинг остаётся в голове очереди."""

    async def _miss_with_infra(listing, db):
        # То же, что делает _try_discogs_fetch при httpx-таймауте.
        listing_matcher._infra_blocked.set(True)
        return False

    counters, updates = await _run_batch(monkeypatch, [_listing(1)], _miss_with_infra)
    assert counters["infra_blocked"] == 1
    assert counters["unmatched"] == 1
    assert _stamped_ids(updates) == []


@pytest.mark.asyncio
async def test_honest_miss_is_stamped(monkeypatch, reset_flags):
    """Честный промах (404/пусто) сжигает кулдаун как раньше."""

    async def _honest_miss(listing, db):
        return False

    counters, updates = await _run_batch(monkeypatch, [_listing(1)], _honest_miss)
    assert counters["infra_blocked"] == 0
    assert _stamped_ids(updates) == [1]


@pytest.mark.asyncio
async def test_infra_exception_from_match_listing_not_stamped(monkeypatch, reset_flags):
    """Второй путь заморозки: инфра-исключение вылетает из самого match_listing.

    Комментарий «упавший листинг — попытка состоявшаяся» верен только для
    прикладных ошибок; MissingGreenlet — это про соединение, не про листинг.
    """

    async def _conn_dead(listing, db):
        raise MissingGreenlet("greenlet_spawn has not been called")

    counters, updates = await _run_batch(monkeypatch, [_listing(1)], _conn_dead)
    assert counters["errors"] == 1
    assert counters["infra_blocked"] == 1
    assert _stamped_ids(updates) == []


@pytest.mark.asyncio
async def test_application_exception_from_match_listing_is_stamped(monkeypatch, reset_flags):
    """Баг в наших данных — попытка состоявшаяся, кулдаун сжигается."""

    async def _our_bug(listing, db):
        raise ValueError("кривой raw_payload")

    counters, updates = await _run_batch(monkeypatch, [_listing(1)], _our_bug)
    assert counters["errors"] == 1
    assert counters["infra_blocked"] == 0
    assert _stamped_ids(updates) == [1]


@pytest.mark.asyncio
async def test_flags_reset_between_listings(monkeypatch, reset_flags):
    """Инфра-флаг первого листинга не должен спасать от кулдауна второй."""
    calls = {"n": 0}

    async def _first_infra_then_honest(listing, db):
        calls["n"] += 1
        if calls["n"] == 1:
            listing_matcher._infra_blocked.set(True)
        return False

    counters, updates = await _run_batch(
        monkeypatch, [_listing(1), _listing(2)], _first_infra_then_honest,
    )
    assert counters["infra_blocked"] == 1
    assert _stamped_ids(updates) == [2]
