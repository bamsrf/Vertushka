"""Снятие с витрины позиций, которых больше нет в каталоге магазина.

До 13.08 это делал только `weekly_cleanup_stale` с порогом 30 дней, и
проданная пластинка висела «в наличии» до месяца: 3 633 видимых оффера
отсутствовали в каталогах больше суток, из них 3 517 у plastinka_com.

Опасность правила «нет в каталоге → снять» в том, что «нет» бывает двух
разных природ: позиция ушла из магазина ИЛИ наш обход не дошёл. Ночью 13.08
doctorhead взял 145 позиций из 3 572 и упал — по наивному правилу мы бы сняли
3 400 живых офферов. Оба предохранителя тестируются ниже.
"""
import inspect

from app.tasks import scraper_tasks


def _src() -> str:
    return inspect.getsource(scraper_tasks.daily_retire_vanished_listings)


def test_compares_with_last_successful_scrape_not_now():
    """Главный предохранитель: отсчёт от успешного обхода магазина, не от now().

    Если магазин падает третьи сутки, last_successful_scrape_at не двигается —
    и снимать нечего. Иначе сбой на стороне магазина стирал бы его витрину.
    """
    src = _src()
    assert "s.last_successful_scrape_at" in src
    assert "s.last_successful_scrape_at IS NOT NULL" in src
    # now() в условии отсечки быть не должно.
    cutoff = src.split("cutoff_expr", 1)[1].split(")", 1)[0]
    assert "now()" not in cutoff


def test_requires_two_missed_crawls():
    """25 часов при суточных обходах = позиция пропущена дважды подряд.

    Один пропуск бывает у частичного обхода, прошедшего smoke-порог (50%).
    """
    sig = inspect.signature(scraper_tasks.daily_retire_vanished_listings)
    grace = sig.parameters["grace_hours"].default
    assert 24 <= grace <= 48, "меньше суток — снимем по одному частичному обходу"


def test_does_not_touch_already_removed():
    src = _src()
    assert "StoreListing.status != ListingStatus.REMOVED" in src


def test_weekly_sweep_survives_as_backstop():
    """Дневное правило намеренно не трогает магазины без успешных обходов —
    их подбирает недельная чистка по возрасту."""
    assert hasattr(scraper_tasks, "weekly_cleanup_stale")
    doc = inspect.getdoc(scraper_tasks.weekly_cleanup_stale) or ""
    assert "одстраховка" in doc


def test_scheduled_after_the_night_crawl():
    """03:00 UTC — обход (02:00) уже закончился, он занимает ~23 минуты."""
    import app.main as main
    src = inspect.getsource(main)
    assert "id='retire_vanished'" in src
    assert "daily_retire_vanished_listings, 'cron', hour=3" in src
