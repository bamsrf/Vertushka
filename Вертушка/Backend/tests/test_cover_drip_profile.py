"""Профиль дрипа обложек: бюджет прогона, границы конфига, защита очереди.

Зачем файл. До релиза дрип — главный канал добора обложек из Discogs
(~100% хитрейт), и его темп управляется тремя env-переменными. Ошибка в
арифметике бюджета в одну сторону глушит канал, в другую — устраивает burst,
который Discogs встречает постоянными 429 (2026-07-03). А значения за
границами разумного не просто медленные — они выжигают очередь: headroom
ниже INTERACTIVE_RESERVE лимитера заставляет дрип ловить таймауты и
помечать никогда не спрошенные строки как проверенные.
"""
import pytest
from pydantic import ValidationError

from app.config import Settings
from app.services.rate_limiter import TokenBucketRateLimiter
from app.tasks.cover_drip_tasks import _below_headroom, _run_budget

_DRIP_VARS = ("COVER_DRIP_HEADROOM", "COVER_DRIP_MAX_PER_RUN", "COVER_DRIP_PACE_SEC")


@pytest.fixture()
def drip_env(monkeypatch):
    """Чистый env + фабрика «Settings с такими COVER_DRIP_*».

    Значения инжектятся через env, а не kwargs: у Settings extra="ignore" и
    алиасы, kwargs по имени поля молча игнорируются — env и есть единственный
    настоящий путь, которым значения попадают на прод. Очистка нужна, чтобы
    test_profile_defaults не был красным ровно там, где конфиг корректен
    (scheduler-контейнер с прод-профилем в env, dev-копия .env.prod).
    """
    def make(**vals):
        for var in _DRIP_VARS:
            monkeypatch.delenv(var, raising=False)
        for var, v in vals.items():
            monkeypatch.setenv(var, str(v))
        return Settings(_env_file=None)
    return make


def test_budget_formula():
    # Токенов меньше/равно headroom — не работаем вовсе.
    assert _run_budget(None, 35, 10) == 0
    assert _run_budget(35, 35, 10) == 0
    assert _run_budget(20, 35, 10) == 0
    # Излишек тратится, но не больше капа.
    assert _run_budget(40, 35, 10) == 5
    assert _run_budget(55, 35, 10) == 10
    # Дробные токены усекаются вниз — не выпрашиваем лишний запрос.
    assert _run_budget(36.9, 35, 10) == 1


def test_gate_semantics_single_source():
    """None (Redis лёг) = не работаем; гейт общий для бюджета и цикла."""
    assert _below_headroom(None, 0)
    assert _below_headroom(10, 10)
    assert not _below_headroom(10.1, 10)


def test_profile_defaults_are_gentle(drip_env):
    """Дефолты = щадящий режим: убрал env — вернулся к ~10 req/min.

    Это и есть механизм отката перед релизом, он обязан оставаться таким.
    """
    s = drip_env()
    assert s.cover_drip_headroom == 35
    assert s.cover_drip_max_per_run == 10
    assert s.cover_drip_pace_sec == 2.0


def test_profile_reads_env(drip_env):
    s = drip_env(
        COVER_DRIP_HEADROOM=18, COVER_DRIP_MAX_PER_RUN=35, COVER_DRIP_PACE_SEC=1.0,
    )
    assert (s.cover_drip_headroom, s.cover_drip_max_per_run, s.cover_drip_pace_sec) == (18, 35, 1.0)


def test_pace_below_one_second_is_rejected(drip_env):
    """pace < 1.0 — это burst в скользящее окно Discogs, инцидент 2026-07-03.

    Инвариант закодирован (Field ge=1.0), а не оставлен комментарием:
    контейнер падает на старте вместо тихого шторма 429 на проде.
    """
    with pytest.raises(ValidationError):
        drip_env(COVER_DRIP_PACE_SEC=0.5)
    with pytest.raises(ValidationError):
        drip_env(COVER_DRIP_PACE_SEC=0)


def test_headroom_floor_covers_limiter_reserve(drip_env):
    """headroom обязан быть выше INTERACTIVE_RESERVE лимитера.

    При free <= INTERACTIVE_RESERVE лимитер вообще не обслуживает фоновый
    приоритет: дрип с headroom ниже резерва «стреляет в закрытую дверь»,
    ловит 30с-таймауты, а цикл помечал бы никогда не спрошенные строки
    cover_checked_at — навсегда выбрасывая их из очереди.
    """
    reserve = TokenBucketRateLimiter.INTERACTIVE_RESERVE
    with pytest.raises(ValidationError):
        drip_env(COVER_DRIP_HEADROOM=reserve)  # ровно резерв — всё ещё мало
    assert drip_env(COVER_DRIP_HEADROOM=reserve + 1).cover_drip_headroom == reserve + 1
    with pytest.raises(ValidationError):
        drip_env(COVER_DRIP_HEADROOM=-1)


def test_max_per_run_bounds(drip_env):
    with pytest.raises(ValidationError):
        drip_env(COVER_DRIP_MAX_PER_RUN=0)   # тихое выключение канала
    with pytest.raises(ValidationError):
        drip_env(COVER_DRIP_MAX_PER_RUN=56)  # больше ёмкости bucket'а
