"""Обход не должен зависеть от живости ORM-объекта `store`.

Ночь 08-12: stoprobotvinyl отвечал ~10 минут на одну AJAX-страницу. Сессия БД
всё это время простояла без запросов, соединение умерло, SQLAlchemy пометил
`store` протухшим — и `store.id` внутри цикла ушёл в ленивую перечитку.
В async-контексте это MissingGreenlet, и он повторился на каждом из 8 956
листингов: `{'discovered': 8956, 'upserted': 0, 'errors': 8957}`.
"""
import ast
import inspect
import textwrap

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


# ---- Финал обхода тоже не должен трогать ORM-объект --------------------- #
#
# Ночь 08-17, doctorhead. Страница не уложилась в 120 c, за это время умерло
# соединение → один upsert упал → обработчик сделал `db.rollback()` → `store`
# протух. Цикл это пережил (скалярный `store_id` завезли 08-12), а вот финал —
# нет: `_smoke_check` читал `store.id`, получил MissingGreenlet, и магазин с
# 3 358 записанными позициями из 3 359 был помечен провалившимся.
#
# Первая починка этого класса бага (08-12) закрыла только цикл. Тесты ниже
# сторожат хвост: smoke-check и обе отметки статуса.


def _code_lines(fn) -> str:
    """Тело функции без докстроки — в комментариях `store.id` упоминается."""
    tree = ast.parse(textwrap.dedent(_source(fn))).body[0]
    body = tree.body[1:] if ast.get_docstring(tree) else tree.body
    return "\n".join(ast.unparse(node) for node in body)


def test_smoke_check_takes_scalar_id_not_orm_object():
    """Сигнатура — главный барьер: с ORM-объектом баг воспроизводим снова."""
    params = list(inspect.signature(runner._smoke_check).parameters)
    assert params[1] == "store_id", f"ожидали скаляр, получили {params[1]}"
    assert "store.id" not in _code_lines(runner._smoke_check)


def test_mark_success_takes_scalar_id_not_orm_object():
    params = list(inspect.signature(runner._mark_success).parameters)
    assert params[1] == "store_id"


def test_no_orm_attribute_access_after_the_crawl_loop():
    """В хвосте `crawl_store` не должно остаться ни одного `store.<attr>`."""
    src = _source(runner.crawl_store)
    _, _, tail = src.partition("async for dto in iterator")
    leftovers = [
        line.strip() for line in tail.splitlines()
        if "store." in line and "store_id" not in line and "store_slug" not in line
        and not line.strip().startswith("#")
    ]
    assert not leftovers, f"ORM-атрибуты после цикла: {leftovers}"


class _DeadAfterRollback:
    """Сессия, которая после `rollback()` протухляет переданный ORM-объект."""

    def __init__(self, store, existing_listings: int):
        self.store = store
        self.existing = existing_listings
        self.updates = []

    async def rollback(self):
        self.store.alive = False

    async def commit(self):
        pass

    async def scalar(self, stmt):
        return self.existing

    async def execute(self, stmt):
        self.updates.append(str(stmt).lower())


@pytest.mark.asyncio
async def test_crawl_finale_survives_dead_orm_object():
    """Сквозная проверка: rollback убил `store`, финал всё равно доходит.

    Ровно ночной сценарий doctorhead: почти весь каталог записан, одна запись
    упала. Обход обязан получить честный статус, а не крэш в обработчике.
    """
    store = _Store()
    db = _DeadAfterRollback(store, existing_listings=3613)

    await db.rollback()          # сбойный upsert → сессия откачена, store протух
    assert not store.alive

    counters = {"discovered": 3359, "upserted": 3358, "errors": 1, "skipped": 0}
    smoke = await runner._smoke_check(db, STORE_ID, counters, "full", None)
    assert smoke is None, f"здоровый обход признан битым: {smoke}"

    await runner._mark_success(db, STORE_ID)
    assert any(u.startswith("update stores") for u in db.updates)
    assert any("last_successful_scrape_at" in u for u in db.updates)


@pytest.mark.asyncio
async def test_mark_needs_browser_writes_by_id():
    store = _Store()
    db = _DeadAfterRollback(store, existing_listings=0)
    await runner._mark_needs_browser(db, STORE_ID, "deadshop", "Cloudflare challenge")

    assert not store.alive, "перед записью нужен rollback — сессия могла быть битой"
    stmt = db.updates[0]
    assert stmt.startswith("update stores")
    assert "requires_browser" in stmt
    assert "last_error" in stmt
