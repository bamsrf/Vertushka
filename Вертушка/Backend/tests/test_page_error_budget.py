"""Бюджет ошибок постраничного обхода: пропускаем флак, но не теряем каталог."""
import pytest

from app.services.scrapers.base import (
    BaseStoreParser,
    PageErrorBudget,
    ParserBlocked,
    ParserNeedsBrowser,
    TransientParserError,
)


def _budget(**over) -> PageErrorBudget:
    kwargs = dict(max_error_ratio=0.05, min_allowance=3, max_consecutive=3)
    kwargs.update(over)
    return PageErrorBudget("testshop", **kwargs)


def test_single_failure_is_tolerated():
    """Инцидент 08-11: один HTTP 500 на 29-й странице стоил 2700 позиций."""
    b = _budget()
    for _ in range(28):
        b.record_success()
    b.record_failure("стр. 29", RuntimeError("HTTP 500"))  # не бросает
    assert b.failed == 1


def test_consecutive_failures_abort():
    b = _budget()
    b.record_success()
    b.record_failure("стр. 2", RuntimeError("boom"))
    b.record_failure("стр. 3", RuntimeError("boom"))
    with pytest.raises(TransientParserError, match="подряд"):
        b.record_failure("стр. 4", RuntimeError("boom"))


def test_success_resets_consecutive_counter():
    """Разрозненный флак не должен копиться как «сайт лёг»."""
    b = _budget(min_allowance=99)
    for i in range(10):
        b.record_failure(f"стр. {i}", RuntimeError("boom"))
        b.record_failure(f"стр. {i}b", RuntimeError("boom"))
        b.record_success()
    assert b.failed == 20


def test_ratio_abort_on_long_crawl():
    """На длинном обходе редкий флак копится и в какой-то момент рвёт обход.

    Порог плавающий (5% от пройденного), важно другое: рвётся на десятках
    пропусков, а не на сотнях — каталог не успевает потерять заметную долю.
    """
    b = _budget()
    for _ in range(200):
        b.record_success()
    with pytest.raises(TransientParserError, match="пропущено"):
        for i in range(100):
            b.record_failure(f"стр. {i}", RuntimeError("boom"))
            b.record_success()
    assert 10 <= b.failed <= 25


def test_min_allowance_protects_short_catalogs():
    """На каталоге rotaryrecords (24 запроса) ratio даёт 2 — берём min_allowance."""
    b = _budget()
    for _ in range(24):
        b.record_success()
    assert b.allowance == 3


# ---- fetch_page ---------------------------------------------------------- #

class _Shop(BaseStoreParser):
    slug = "testshop"
    base_url = "https://example.com"


class _Http:
    def __init__(self, script):
        self.script, self.calls = list(script), 0

    async def get_text(self, url, **kw):
        self.calls += 1
        item = self.script.pop(0) if self.script else "ok"
        if isinstance(item, Exception):
            raise item
        return item


@pytest.fixture(autouse=True)
def _no_sleep(monkeypatch):
    async def _instant(_):
        return None
    monkeypatch.setattr("app.services.scrapers.base.asyncio.sleep", _instant)


@pytest.mark.asyncio
async def test_fetch_page_second_chance_recovers():
    """Bitrix-овые 500 отпускают за секунды — вторая попытка спасает страницу."""
    http = _Http([RuntimeError("HTTP 500"), "<html>ok</html>"])
    parser, b = _Shop(http=http), _budget()
    assert await parser.fetch_page("https://example.com/1", b, page_label="стр. 1")
    assert http.calls == 2
    assert b.failed == 0


@pytest.mark.asyncio
async def test_fetch_page_returns_none_after_second_chance():
    http = _Http([RuntimeError("HTTP 500"), RuntimeError("HTTP 500")])
    parser, b = _Shop(http=http), _budget()
    assert await parser.fetch_page("https://example.com/1", b, page_label="стр. 1") is None
    assert b.failed == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("exc", [
    ParserBlocked("403"),
    ParserNeedsBrowser("cloudflare"),
])
async def test_blocked_is_not_swallowed(exc):
    """Смена режима доступа — не флак: её должен увидеть runner."""
    parser, b = _Shop(http=_Http([exc])), _budget()
    with pytest.raises(ParserBlocked):
        await parser.fetch_page("https://example.com/1", b, page_label="стр. 1")


@pytest.mark.asyncio
async def test_budget_exhaustion_propagates_from_fetch_page():
    parser, b = _Shop(http=_Http([])), _budget(max_consecutive=1)
    parser.http = _Http([RuntimeError("boom"), RuntimeError("boom")])
    with pytest.raises(TransientParserError):
        await parser.fetch_page("https://example.com/1", b, page_label="стр. 1")
