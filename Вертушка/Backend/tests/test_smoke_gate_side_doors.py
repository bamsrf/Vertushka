"""Боковые двери smoke-гейта обхода (adversarial-ревью 2026-08-23).

Smoke-check в runner.py сторожит главный вход — полный обход без limit. Ревью
нашло три обхода гейта, каждый из которых через daily_retire_vanished_listings
приводил к снятию живой витрины:

1. `mode="incremental"` снимал объёмные пороги, хотя ни один парсер не
   переопределяет `crawl_incremental` — дефолт в base.py зовёт `crawl_full`.
   Дневной прогон 14:00 был полным обходом БЕЗ проверки покрытия: смена
   вёрстки → 0 позиций → ok → last_successful двинулась → назавтра retire
   снял всё.
2. Ручной `crawl_store(slug, limit=50)` вызывал `_mark_success` и двигал
   last_successful → следующий retire снимал всё вне этих 50 позиций.
3. Знаменатель порога 50% считал ВСЕ листинги, включая removed. У б/у-магазинов
   проданное копится в removed → existing раздувается → здоровый обход
   переставал проходить порог.

Плюс сброс requires_browser при успехе: флаг был билетом в один конец
(_mark_needs_browser ставил навсегда, browser-путь фактически мёртв).
"""
import uuid
from datetime import datetime

from app.services.scrapers import runner
from app.services.scrapers.base import BaseStoreParser, ListingDTO


STORE_ID = uuid.UUID("11111111-1111-1111-1111-111111111111")


# ---- Фейковая обвязка для сквозного crawl_store -------------------------- #


class _Store:
    def __init__(self):
        self.id = STORE_ID
        self.slug = "smokeshop"
        self.domain = "smokeshop.ru"
        self.parser_class = "smokeshop"
        self.requires_browser = False
        self.last_successful_scrape_at = datetime(2026, 8, 22)
        self.last_error = None


class _StoreResult:
    def __init__(self, store):
        self._store = store

    def scalar_one_or_none(self):
        return self._store


class _Db:
    """Сессия: отдаёт магазин, считает листинги, копит UPDATE-ы."""

    def __init__(self, store, existing_live: int, existing_removed: int = 0):
        self.store = store
        self.existing_live = existing_live
        self.existing_removed = existing_removed
        self.updates: list[str] = []

    async def execute(self, stmt, params=None):
        sql = str(stmt).lower()
        if sql.lstrip().startswith("select") and "from stores" in sql:
            return _StoreResult(self.store)
        self.updates.append(sql)
        return None

    async def scalar(self, stmt):
        # Смок-знаменатель: фильтрует ли запрос removed-строки?
        values = {str(v) for v in stmt.compile().params.values()}
        if "removed" in values:
            return self.existing_live
        return self.existing_live + self.existing_removed

    async def commit(self):
        pass

    async def rollback(self):
        pass


class _SessionMaker:
    def __init__(self, db):
        self.db = db

    def __call__(self):
        return self

    async def __aenter__(self):
        return self.db

    async def __aexit__(self, *exc):
        return False


def _dto(i: int) -> ListingDTO:
    return ListingDTO(external_id=f"sku-{i}", url=f"https://smokeshop.ru/p/{i}", title_raw=f"LP {i}")


class _DefaultIncrementalShop(BaseStoreParser):
    """crawl_incremental НЕ переопределён — как у всех парсеров в проде."""

    slug = "smokeshop"
    base_url = "https://smokeshop.ru"
    yield_count = 0

    async def crawl_full(self, limit=None):
        for i in range(type(self).yield_count):
            yield _dto(i)


class _RealIncrementalShop(_DefaultIncrementalShop):
    """Настоящий инкремент: пустой результат — норма."""

    async def crawl_incremental(self, since, limit=None):
        for i in range(type(self).yield_count):
            yield _dto(i)


def _wire(monkeypatch, db, parser_cls):
    monkeypatch.setattr(runner, "async_session_maker", _SessionMaker(db))
    monkeypatch.setattr(runner, "get_parser", lambda name: parser_cls)

    async def _fake_upsert(db_, store_id, dto):
        return True

    monkeypatch.setattr(runner, "_upsert_listing", _fake_upsert)


# ---- Дверь 1: incremental без настоящего инкремента ---------------------- #


async def test_default_incremental_zero_discovered_fails_smoke(monkeypatch):
    """Смена вёрстки: дефолтный «инкремент» отдал 0 при живой БД → failed.

    До 2026-08-23 этот прогон помечался ok и двигал last_successful — назавтра
    daily_retire_vanished_listings снимал всю витрину.
    """
    _DefaultIncrementalShop.yield_count = 0
    db = _Db(_Store(), existing_live=3500)
    _wire(monkeypatch, db, _DefaultIncrementalShop)

    counters = await runner.crawl_store("smokeshop", mode="incremental")

    assert counters["status"] == "failed", counters
    assert not any("last_successful_scrape_at" in u for u in db.updates), (
        "битый прогон сдвинул last_successful_scrape_at"
    )
    assert any("last_error" in u for u in db.updates)


async def test_default_incremental_low_coverage_fails_smoke(monkeypatch):
    """Обрыв на четверти каталога в «инкременте» — тоже не успех."""
    _DefaultIncrementalShop.yield_count = 100
    db = _Db(_Store(), existing_live=1000)
    _wire(monkeypatch, db, _DefaultIncrementalShop)

    counters = await runner.crawl_store("smokeshop", mode="incremental")

    assert counters["status"] == "failed", counters
    assert not any("last_successful_scrape_at" in u for u in db.updates)


async def test_real_incremental_keeps_empty_result_ok(monkeypatch):
    """У переопределённого crawl_incremental пустой прогон — норма (новинок нет)."""
    _RealIncrementalShop.yield_count = 0
    db = _Db(_Store(), existing_live=3500)
    _wire(monkeypatch, db, _RealIncrementalShop)

    counters = await runner.crawl_store("smokeshop", mode="incremental")

    assert counters["status"] == "ok", counters
    assert any("last_successful_scrape_at" in u for u in db.updates)


# ---- Дверь 2: ручной прогон с limit не двигает last_successful ----------- #


async def test_limited_crawl_does_not_touch_last_successful(monkeypatch):
    """crawl_store(slug, limit=50) — отладочный срез, а не полный обход."""
    _DefaultIncrementalShop.yield_count = 200
    db = _Db(_Store(), existing_live=1000)
    _wire(monkeypatch, db, _DefaultIncrementalShop)

    counters = await runner.crawl_store("smokeshop", mode="full", limit=50)

    assert counters["status"] == "ok", counters
    assert counters["upserted"] == 50
    assert not any("last_successful_scrape_at" in u for u in db.updates), (
        "прогон с limit сдвинул last_successful_scrape_at — "
        "следующий retire снимет всё вне этих 50 позиций"
    )


async def test_full_crawl_still_marks_success(monkeypatch):
    """Контроль: полный здоровый обход без limit по-прежнему двигает отметку."""
    _DefaultIncrementalShop.yield_count = 900
    db = _Db(_Store(), existing_live=1000)
    _wire(monkeypatch, db, _DefaultIncrementalShop)

    counters = await runner.crawl_store("smokeshop", mode="full")

    assert counters["status"] == "ok", counters
    assert any("last_successful_scrape_at" in u for u in db.updates)


# ---- Дверь 3: знаменатель смока не должен считать removed ---------------- #


async def test_smoke_denominator_ignores_removed_listings(monkeypatch):
    """Б/у-магазин: 400 живых + 600 removed. Обход увидел 450 — это здоровье.

    До 2026-08-23 знаменатель был 1000 → 450 < 500 → здоровый обход помечался
    битым, и магазин навсегда терял зелёный статус.
    """
    _DefaultIncrementalShop.yield_count = 450
    db = _Db(_Store(), existing_live=400, existing_removed=600)
    _wire(monkeypatch, db, _DefaultIncrementalShop)

    counters = await runner.crawl_store("smokeshop", mode="full")

    assert counters["status"] == "ok", counters
    assert any("last_successful_scrape_at" in u for u in db.updates)


async def test_smoke_still_fails_on_low_live_coverage(monkeypatch):
    """Контроль: против живых листингов порог 50% продолжает работать."""
    _DefaultIncrementalShop.yield_count = 100
    db = _Db(_Store(), existing_live=400, existing_removed=600)
    _wire(monkeypatch, db, _DefaultIncrementalShop)

    counters = await runner.crawl_store("smokeshop", mode="full")

    assert counters["status"] == "failed", counters


# ---- requires_browser — не билет в один конец ---------------------------- #


async def test_mark_success_resets_requires_browser():
    """Успешный HTTP-обход доказывает, что браузер не нужен."""
    captured = {}

    class _CaptureDb:
        async def execute(self, stmt):
            captured["params"] = stmt.compile().params

    await runner._mark_success(_CaptureDb(), STORE_ID)

    params = captured["params"]
    assert params.get("requires_browser") is False, (
        "requires_browser не сбрасывается при успехе — флаг остаётся навсегда"
    )
    assert "last_successful_scrape_at" in params
