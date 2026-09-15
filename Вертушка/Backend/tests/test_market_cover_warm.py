"""Прогрев витрины Маркета: только бесплатное и только release-точное.

Зачем файл. У задачи два способа испортить продукт незаметно: залезть в
дневной бюджет картинок Discogs (800 на весь сервер, он же — причина серых
плиток) и подставить релизу чужую обложку ради экономии. Оба закрыты здесь.
"""
import inspect

import pytest
from pydantic import ValidationError

from app.config import Settings
from app.tasks import market_cover_warm_tasks as warm


@pytest.fixture()
def env(monkeypatch):
    def make(**vals):
        for var in ("MARKET_WARM_ENABLED", "MARKET_WARM_BATCH",
                    "MARKET_WARM_CAA_BATCH", "MARKET_WARM_PACE_SEC"):
            monkeypatch.delenv(var, raising=False)
        for k, v in vals.items():
            monkeypatch.setenv(k, str(v))
        return Settings(_env_file=None)
    return make


def test_free_queue_excludes_discogs_images():
    """Платный хост отсекается в самой выборке.

    Иначе задача упиралась бы ровно в тот бюджет, ради обхода которого и
    написана: 800 картинок в сутки на весь сервер.
    """
    assert "NOT LIKE '%i.discogs.com%'" in warm._FREE_URL_SQL


def test_free_queue_takes_only_unmirrored():
    """Уже зеркалированное перекачивать незачем — оно вечно лежит в бакете."""
    assert "cover_cached_at IS NULL" in warm._FREE_URL_SQL


def test_queue_is_ordered_by_demand():
    """Порядок — по свежести листинга, а не по id.

    Витрина это первый экран; греть надо то, что покажут сейчас, а не то, что
    оказалось раньше в таблице.
    """
    assert "ORDER BY max(sl.last_seen_at) DESC" in warm._FREE_URL_SQL
    assert "ORDER BY max(sl.last_seen_at) DESC" in warm._CAA_CANDIDATES_SQL


def test_caa_swap_is_release_accurate():
    """Бесплатная замена берётся ТОЛЬКО по офлайн-маппингу release↔MBID.

    mb_discogs_map связывает конкретный discogs-релиз с конкретным MBID, то
    есть картинка та же самая пластинка.
    """
    assert "mb_discogs_map" in warm._CAA_CANDIDATES_SQL
    assert "m.has_front" in warm._CAA_CANDIDATES_SQL


def test_master_cover_is_never_substituted():
    """Обложку МАСТЕРА вместо обложки пресса не подставляем.

    Соблазн есть: у 2 138 записей витрины своя картинка платная, а мастерская
    бесплатна. Но мастер — это другой пресс, и подмена релиза чужой обложкой
    уже приводила к инциденту 12.09.2026 (SVN/Dehd получили чужие картинки).
    Продуктовое решение прежнее: мастер обслуживает сетку артиста, экран
    версий — нет.
    """
    source = inspect.getsource(warm)
    code_only = "\n".join(
        line for line in source.splitlines()
        if not line.strip().startswith("#")
    )
    assert "discogs_master_covers" not in code_only


def test_defaults_and_bounds(env):
    s = env()
    assert s.market_warm_enabled is True
    assert s.market_warm_batch == 60
    with pytest.raises(ValidationError):
        env(MARKET_WARM_BATCH=0)
    with pytest.raises(ValidationError):
        env(MARKET_WARM_BATCH=10_000)


def test_caa_batch_can_be_zero(env):
    """Замены можно выключить отдельно, не трогая основной прогрев."""
    assert env(MARKET_WARM_CAA_BATCH=0).market_warm_caa_batch == 0


@pytest.mark.asyncio
async def test_disabled_does_nothing(monkeypatch):
    monkeypatch.setenv("MARKET_WARM_ENABLED", "false")
    from app import config
    config.get_settings.cache_clear()
    try:
        assert await warm.warm_market_covers_batch() == {"skipped": "disabled"}
    finally:
        config.get_settings.cache_clear()
