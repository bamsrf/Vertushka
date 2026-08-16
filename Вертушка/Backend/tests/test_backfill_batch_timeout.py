"""Батч bulk-backfill'а: таймаут не должен закрывать неопрошенных мастеров.

Регрессия, которую сторожит файл. `_gather_batch` оборачивал ВЕСЬ батч в один
`asyncio.wait_for(_BATCH_TIMEOUT)`, а на таймауте возвращал все элементы,
проставив недостающим `cover = None`. Вызывающий помечает `done = TRUE` всё,
что получил, — то есть мастера, до которых очередь внутри батча не дошла,
закрывались навсегда без единого запроса. Worklist их больше не отдаёт.

Для Deezer (0.13 с/запрос) и Yandex (0.25 с) баг спал: батч из 200 укладывается
в 26-50 с. У iTunes троттл 3.1 с/запрос, батч из 200 требует 620 с — таймаут
срабатывал бы КАЖДЫЙ раз, съедая ~60% очереди из 1.33 млн мастеров вхолостую.
"""
import asyncio

import pytest

from app.scripts import backfill_covers as bc


def _provider(interval: float, lookup) -> bc.Provider:
    return bc.Provider(
        name="test", lookup=lookup, concurrency=2,
        marker="/nonexistent", min_interval=interval,
    )


def test_safe_batch_fits_itunes_throttle_into_timeout():
    """Батч iTunes ужимается так, чтобы успеть до таймаута."""
    prov = bc.PROVIDERS["itunes"]
    batch = bc._safe_batch(prov, 200)
    assert batch * prov.min_interval < bc._BATCH_TIMEOUT
    assert batch == 61


def test_safe_batch_leaves_fast_providers_alone():
    """Yandex укладывается и так — ужимать нечего, батч остаётся запрошенным."""
    assert bc._safe_batch(bc.PROVIDERS["yandex"], 200) == 200


def test_safe_batch_never_returns_zero():
    """Даже у абсурдно медленного источника батч не должен схлопнуться в 0 —
    иначе SELECT ... LIMIT 0 вернёт пусто и проход завершится «очередь пуста»."""
    assert bc._safe_batch(_provider(10_000, None), 200) == 1


@pytest.mark.asyncio
async def test_timeout_returns_only_attempted_items(monkeypatch):
    """Главный тест: на таймауте наружу идут ТОЛЬКО опрошенные.

    Остальные обязаны вернуться в очередь — вызывающий закрывает `done` ровно
    по тому, что получил отсюда.
    """
    monkeypatch.setattr(bc, "_BATCH_TIMEOUT", 1)

    async def slow_lookup(artist, title, year):
        await asyncio.sleep(0.3)
        return f"https://example.test/{title}.jpg"

    prov = _provider(0.3, slow_lookup)
    items = [{"master_id": i, "artist": "A", "title": f"T{i}"} for i in range(50)]

    results = await bc._gather_batch(prov, items, asyncio.Semaphore(2))

    assert 0 < len(results) < len(items), "таймаут обязан отсечь часть батча"
    assert all(r.get("attempted") for r in results)
    # Ключевое: неопрошенные не получили cover=None и не попадут в done_ids.
    returned_ids = {r["master_id"] for r in results}
    untouched = [it for it in items if it["master_id"] not in returned_ids]
    assert untouched, "неопрошенные должны остаться"
    assert all("cover" not in it for it in untouched)


@pytest.mark.asyncio
async def test_full_batch_within_timeout_returns_everything():
    """Без таймаута поведение прежнее — весь батч закрывается разом."""
    async def fast_lookup(artist, title, year):
        return None

    prov = _provider(0.01, fast_lookup)
    items = [{"master_id": i, "artist": "A", "title": f"T{i}"} for i in range(20)]

    results = await bc._gather_batch(prov, items, asyncio.Semaphore(2))

    assert len(results) == 20
    assert all(r["cover"] is None and r["attempted"] for r in results)
