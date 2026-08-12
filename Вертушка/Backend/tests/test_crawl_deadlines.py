"""Потолки времени: ни одна страница и ни один магазин не держат ночное окно.

Ночь 08-12: одна AJAX-страница stoprobotvinyl отвечала ~10 минут — клиентский
таймаут 90 c помножился на ретраи и вторую попытку. Ночное окно 3 часа делится
между магазинами, поэтому нужны два независимых потолка: на страницу и на
обход целиком.
"""
import asyncio

import pytest

from app.services.scrapers.base import (
    BaseStoreParser,
    PageErrorBudget,
    TransientParserError,
)
from app.services.scrapers.registry import all_parsers


class _Shop(BaseStoreParser):
    slug = "testshop"
    base_url = "https://example.com"


class _SlowHttp:
    """Отвечает медленнее любого разумного дедлайна."""

    def __init__(self, delay=999.0):
        self.delay, self.calls = delay, 0

    async def get_text(self, url, **kw):
        self.calls += 1
        await asyncio.sleep(self.delay)
        return "<html>поздно</html>"


@pytest.mark.asyncio
async def test_slow_page_is_cut_by_deadline():
    http = _SlowHttp()
    parser, budget = _Shop(http=http), PageErrorBudget("testshop")
    out = await parser.fetch_page(
        "https://example.com/1", budget, page_label="стр. 1", deadline_sec=0.05,
        second_chance_delay=0,
    )
    assert out is None
    assert budget.failed == 1
    # Дедлайн ставится на каждую ступень: первая попытка + вторая попытка.
    assert http.calls == 2


@pytest.mark.asyncio
async def test_deadline_message_is_readable():
    """В last_error магазина должно быть видно, что случилось именно время."""
    parser = _Shop(http=_SlowHttp())
    budget = PageErrorBudget("testshop", max_consecutive=1)
    with pytest.raises(TransientParserError, match="не уложилась"):
        await parser.fetch_page(
            "https://example.com/1", budget, page_label="стр. 1",
            deadline_sec=0.05, second_chance_delay=0,
        )


@pytest.mark.asyncio
async def test_fast_page_untouched_by_deadline():
    """Дедлайн не должен вмешиваться в нормальный обход."""
    class _FastHttp:
        async def get_text(self, url, **kw):
            return "<html>ok</html>"

    parser, budget = _Shop(http=_FastHttp()), PageErrorBudget("testshop")
    out = await parser.fetch_page("https://example.com/1", budget, page_label="стр. 1")
    assert out == "<html>ok</html>"
    assert budget.failed == 0


def test_every_parser_has_sane_budgets():
    """Потолки должны быть с запасом к реальным замерам, иначе сломаем рабочее.

    Замеры 08-12 (elapsed_sec с прода): skifmusic 1372 c / 20 621 позиция —
    самый долгий обход; stoprobotvinyl 185 c / 8 956. Самая тяжёлая страница —
    plastinka, 200 карточек (~317 KB), секунды.
    """
    for slug, cls in all_parsers().items():
        assert cls.page_deadline_sec >= 60, f"{slug}: слишком жёсткий потолок страницы"
        assert cls.max_crawl_seconds >= 1800, f"{slug}: потолок обхода меньше часа запаса"
        # И при этом не бесконечность — иначе смысла в потолке нет.
        assert cls.max_crawl_seconds <= 4 * 3600, f"{slug}: потолок обхода бесполезно велик"


def test_store_deadline_checked_inside_crawl_loop():
    """Проверка времени обязана стоять в цикле, а не только до/после него."""
    import inspect

    from app.services.scrapers import runner

    src = inspect.getsource(runner.crawl_store)
    _, _, loop = src.partition("async for dto in iterator")
    assert "time.monotonic() > deadline" in loop
