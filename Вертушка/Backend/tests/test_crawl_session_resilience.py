"""Обход не должен зависеть от живости ORM-объекта `store`.

Ночь 08-12: stoprobotvinyl отвечал ~10 минут на одну AJAX-страницу. Сессия БД
всё это время простояла без запросов, соединение умерло, SQLAlchemy пометил
`store` протухшим — и `store.id` внутри цикла ушёл в ленивую перечитку.
В async-контексте это MissingGreenlet, и он повторился на каждом из 8 956
листингов: `{'discovered': 8956, 'upserted': 0, 'errors': 8957}`.
"""
import inspect

import pytest
from sqlalchemy.exc import MissingGreenlet, SQLAlchemyError

from app.services.scrapers import runner


STORE_ID = "11111111-1111-1111-1111-111111111111"


class _Store:
    """ORM-объект, атрибуты которого падают после «смерти» соединения."""

    def __init__(self):
        self.slug = "deadshop"
        self.domain = "deadshop.ru"
        self.parser_class = "deadshop"
        self.requires_browser = False
        self.last_successful_scrape_at = None
        self.last_error = None
        self.alive = True

    @property
    def id(self):
        if not self.alive:
            raise MissingGreenlet("greenlet_spawn has not been called")
        return STORE_ID


def _source(fn) -> str:
    return inspect.getsource(fn)


def test_crawl_reads_store_id_before_the_loop():
    """`store.id` читается один раз до `async for`, дальше — только скаляр."""
    src = _source(runner.crawl_store)
    head, _, loop = src.partition("async for dto in iterator")
    assert "store_id = store.id" in head
    assert "store.id" not in loop, "ORM-атрибут внутри цикла обхода"


def test_refresh_reads_store_id_before_the_loop():
    src = _source(runner.refresh_store_listings)
    head, _, loop = src.partition("async for url, dto in")
    assert "store_id = store.id" in head
    assert "store.id" not in loop


def test_scalar_id_survives_dead_orm_object():
    """Ровно то, что спасает обход: скаляр живёт, ORM-атрибут — нет."""
    store = _Store()
    store_id = store.id      # как в crawl_store — до цикла
    store.alive = False      # соединение умерло посреди обхода
    assert store_id == STORE_ID
    with pytest.raises(MissingGreenlet):
        _ = store.id


@pytest.mark.asyncio
async def test_mark_error_writes_by_id_not_by_attribute():
    """`_mark_error` вызывается когда всё сломалось — он обязан работать."""
    executed = []

    class _Db:
        async def rollback(self):
            executed.append("rollback")

        async def execute(self, stmt):
            executed.append(stmt)

    await runner._mark_error(_Db(), STORE_ID, "boom")

    # Сначала откат (сессия могла остаться в failed-состоянии), потом UPDATE.
    assert executed[0] == "rollback"
    stmt = str(executed[1]).lower()
    assert stmt.startswith("update stores")
    assert "last_error" in stmt


@pytest.mark.asyncio
async def test_mark_error_truncates_long_message():
    captured = {}

    class _Db:
        async def rollback(self):
            pass

        async def execute(self, stmt):
            captured["params"] = stmt.compile().params

    await runner._mark_error(_Db(), STORE_ID, "x" * 5000)
    assert len(captured["params"]["last_error"]) == 1000


def test_consecutive_error_cap_is_bounded():
    """Отсечка должна быть заметно меньше типового каталога (тысячи позиций)."""
    assert 1 < runner._CRAWL_MAX_CONSECUTIVE_ERRORS <= 50
    assert "consecutive_errors >= _CRAWL_MAX_CONSECUTIVE_ERRORS" in _source(runner.crawl_store)


def test_upsert_errors_do_not_loop_forever():
    """Счётчик сбрасывается на успехе — редкие сбои не копятся как «сессия мертва»."""
    src = _source(runner.crawl_store)
    assert "consecutive_errors = 0" in src
    assert SQLAlchemyError.__name__ in src
