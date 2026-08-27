"""Профиль дрипа обложек: бюджет прогона и его источник — конфиг.

Зачем файл. До релиза дрип — главный канал добора обложек из Discogs
(~100% хитрейт), и его темп управляется тремя env-переменными. Ошибка в
арифметике бюджета в одну сторону глушит канал (0 вместо 45 req/min), в
другую — устраивает burst, который Discogs встречает постоянными 429
(уже случалось 2026-07-03). Тесты фиксируют и формулу, и то, что значения
приходят из Settings, а не из захардкоженных констант.
"""
from app.config import Settings
from app.tasks.cover_drip_tasks import _run_budget


def test_budget_formula():
    # Токенов меньше/равно headroom — не работаем вовсе.
    assert _run_budget(None, 35, 10) == 0
    assert _run_budget(35, 35, 10) == 0
    assert _run_budget(20, 35, 10) == 0
    # Излишек тратится, но не больше капа.
    assert _run_budget(40, 35, 10) == 5
    assert _run_budget(55, 35, 10) == 10
    # Агрессивный пре-релизный профиль: полный bucket → ровно кап.
    assert _run_budget(55, 10, 45) == 45
    # Дробные токены усекаются вниз — не выпрашиваем лишний запрос.
    assert _run_budget(36.9, 35, 10) == 1


def test_profile_defaults_are_gentle():
    """Дефолты = щадящий режим: убрал env — вернулся к ~10 req/min.

    Это и есть механизм отката перед релизом, он обязан оставаться таким.
    """
    s = Settings()
    assert s.cover_drip_headroom == 35
    assert s.cover_drip_max_per_run == 10
    assert s.cover_drip_pace_sec == 2.0


def test_profile_reads_env(monkeypatch):
    monkeypatch.setenv("COVER_DRIP_HEADROOM", "10")
    monkeypatch.setenv("COVER_DRIP_MAX_PER_RUN", "45")
    monkeypatch.setenv("COVER_DRIP_PACE_SEC", "1.0")
    s = Settings()
    assert (s.cover_drip_headroom, s.cover_drip_max_per_run, s.cover_drip_pace_sec) == (10, 45, 1.0)
