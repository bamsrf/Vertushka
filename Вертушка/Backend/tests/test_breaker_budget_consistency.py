"""Брейкер домена не должен срабатывать раньше бюджета страниц.

Два механизма решают одну задачу — «когда прекращать обход», — и до 14.08 они
были несогласованы. `fetch_page` делает две ступени, каждая при исчерпании
ретраев отмечает брейкеру свой провал: одна сбойная страница = две отметки.
При пороге 5 брейкер открывался на второй-третьей флакующей странице, хотя
`PageErrorBudget` терпит три подряд.

Итог: doctorhead упал две ночи подряд (13.08 — 145 позиций из 3572, 14.08 —
261), оба раза «circuit OPEN after 5 failures», и оба раза сайт через час
отвечал за секунду.
"""
import inspect

from app.services.scrapers import http_client
from app.services.scrapers.base import BaseStoreParser, PageErrorBudget


def test_breaker_threshold_exceeds_budget_cost():
    """Порог брейкера должен покрывать полный бюджет страниц с запасом.

    Бюджет разрешает `max_consecutive` страниц подряд, каждая стоит до двух
    отметок брейкера. Если порог ниже — решение принимает брейкер, а он не
    знает ни про долю пропусков, ни про то, сколько страниц уже пройдено.
    """
    budget = PageErrorBudget("test")
    cost_per_page = 2  # две ступени fetch_page
    max_budget_cost = budget.max_consecutive * cost_per_page
    assert http_client._CRAWL_FAILURE_THRESHOLD > max_budget_cost, (
        f"брейкер откроется на {http_client._CRAWL_FAILURE_THRESHOLD} отметках, "
        f"а бюджет допускает {max_budget_cost} — решать будет не он"
    )


def test_fetch_page_really_has_two_stages():
    """Если ступень станет одна, оценка выше поедет — тест это заметит."""
    src = inspect.getsource(BaseStoreParser.fetch_page)
    assert "for is_second_chance in (False, True):" in src


def test_configure_domain_applies_the_threshold():
    """Порог должен доезжать до брейкера, а не остаться константой в модуле."""
    client = http_client.ScraperHttpClient()
    client.configure_domain("shop.example", rate_per_sec=0.5, burst=2)
    assert client._breakers["shop.example"].failure_threshold == \
        http_client._CRAWL_FAILURE_THRESHOLD


def test_fallback_breaker_also_uses_it():
    """Домен без configure_domain (прямой вызов get_text) не должен получить 5."""
    src = inspect.getsource(http_client.ScraperHttpClient.get_text)
    assert "_CircuitBreaker(" in src
    assert "failure_threshold=_CRAWL_FAILURE_THRESHOLD" in src


def test_discogs_breaker_untouched():
    """У Discogs свой брейкер — послабление для магазинов его не касается."""
    from app.services import discogs
    assert "_CRAWL_FAILURE_THRESHOLD" not in inspect.getsource(discogs)
