"""WS-фикс 06.09: doctorhead переживает нагрузочные HTTP 500 их Bitrix.

Их сервер под нагрузкой отдаёт 500 пачками на соседних страницах и оживает
через минуты. Дефолтный PageErrorBudget (3 подряд / 5%) рвал обход на коротком
«плохом окне» — магазин падал третьи сутки. Терпим дольше (6 подряд / 8%) и
даём длинную вторую попытку.
"""
import ast
import inspect
import textwrap

import pytest

from app.services.scrapers.base import PageErrorBudget, TransientParserError
from app.services.scrapers.shops.doctorhead import DoctorHeadParser


def _crawl_source() -> str:
    return textwrap.dedent(inspect.getsource(DoctorHeadParser.crawl_full))


# ---- Сторож параметров устойчивости в crawl_full ------------------------- #

def test_budget_is_tolerant_to_load_spikes():
    src = _crawl_source()
    tree = ast.parse(src)
    # Находим вызов PageErrorBudget(...) и проверяем kwargs.
    budget_calls = [
        n for n in ast.walk(tree)
        if isinstance(n, ast.Call)
        and getattr(n.func, "id", None) == "PageErrorBudget"
    ]
    assert budget_calls, "crawl_full больше не строит PageErrorBudget"
    kwargs = {k.arg: k.value for k in budget_calls[0].keywords}
    assert "max_consecutive" in kwargs and ast.literal_eval(kwargs["max_consecutive"]) >= 5, \
        "max_consecutive должен быть повышен (их 500-ки идут пачками)"
    assert "max_error_ratio" in kwargs and ast.literal_eval(kwargs["max_error_ratio"]) >= 0.06


def test_fetch_page_uses_long_second_chance():
    src = _crawl_source()
    assert "second_chance_delay" in src, "нужна длинная вторая попытка после спайка"
    assert "retries=" in src, "нужно больше ретраев на нагрузочные 500"


# ---- Поведение бюджета: терпит 5 подряд, рвёт на 6-й --------------------- #

def test_budget_survives_five_consecutive_then_recovers():
    # 80 успехов — как в реальном каталоге на 115 страниц: allowance по ratio
    # ≈7, поэтому связывающим ограничением становится именно consecutive.
    b = PageErrorBudget("doctorhead", max_consecutive=6, max_error_ratio=0.08)
    for _ in range(80):
        b.record_success()
    # 5 подряд сбойных — в пределах max_consecutive
    for i in range(5):
        b.record_failure(f"стр {i}", RuntimeError("500"))
    # шестой подряд — сайт лёг
    with pytest.raises(TransientParserError):
        b.record_failure("стр 6", RuntimeError("500"))


def test_budget_recovers_after_short_bad_window():
    b = PageErrorBudget("doctorhead", max_consecutive=6, max_error_ratio=0.08)
    for _ in range(50):
        b.record_success()
    # короткое окно из 3 сбоев, затем успех — consecutive сбрасывается
    for i in range(3):
        b.record_failure(f"стр {i}", RuntimeError("500"))
    b.record_success()          # оживание — не должно бросить
    b.record_success()
    assert b.consecutive == 0
