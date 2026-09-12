"""Ре-фетч цвета пресса: отбор кандидатов и решение «снести или оставить».

Сети и БД у теста нет — проверяем ровно те две развилки, где скрипт может
навредить молча:

  1. отбор в мусор. Ошибка в одну сторону — гоняем Discogs по здоровым записям,
     в другую — оставляем «Red Labels» в поле цвета навсегда;
  2. различение «Discogs говорит, что цвета нет» и «запрос не доехал». Спутать
     их — значит сносить цвет у записей при первом же сетевом сбое.
"""
import pytest

from app.scripts.refetch_vinyl_colors import _fresh_color, _is_junk


# ---- Отбор кандидатов ----------------------------------------------------- #

@pytest.mark.parametrize("junk", [
    "Gatefold",                 # 100 записей на проде
    "180 Gram",                 # 28
    "180g",
    "Pitman Pressing",          # завод
    "Terre Haute Pressing",
    "256 kbps",
    "Fifth Pressing",
    "10 Year Anniversary",
])
def test_noise_is_junk(junk):
    assert _is_junk(junk) is True


@pytest.mark.parametrize("packaging", [
    "Red Labels",               # 29 записей, сейчас выводится как red
    "White Labels",             # 23 — как white
    "Blue Labels",              # 13 — как blue
    "Pink Labels",
    "Gold Inner Sleeve",
    "Green Case",
    "АЗГ Pressing, Red Labels",
])
def test_packaging_colour_is_junk(packaging):
    """Худший класс: не просто мусор, а ЛОЖНЫЙ цвет.

    Эти значения сейчас дают семью цвета и идут в «Радугу» и в счётчик
    цветных в профиле, хотя описывают этикетку или конверт.
    """
    assert _is_junk(packaging) is True


@pytest.mark.parametrize("real", [
    "Red Translucent", "Blue Marbled", "Emerald Green", "Black",
    "Orange With Black Splatter", "Clear", "Coloured Vinyl",
    "Glow In The Dark", "Splatter",
])
def test_real_colours_and_markers_are_not_junk(real):
    """Здоровые записи в выборку не попадают — иначе зря жжём лимит Discogs.

    Неспецифичные маркеры (Clear, Glow, Splatter) тоже здоровые: семьи у них
    нет, но на них держатся фильтр Маркета и пасхалка «Светится в темноте».
    """
    assert _is_junk(real) is False


def test_empty_is_junk():
    """Пустое значение бракуется — им занимается --mode missing."""
    assert _is_junk(None) is True
    assert _is_junk("") is True


# ---- SQL скрипта не должен таить лишних bind-параметров ------------------- #

def test_sql_has_exactly_the_intended_binds():
    """Урок соседнего PR: лишнее двоеточие в SQL = именованный bind-параметр.

    Там regex `(?:ый|…)` уехал в text() и уронил запрос с «A value is required
    for bind parameter 'ый'». Здесь SQL пишется руками, так что фиксируем
    ожидаемый набор параметров — молчаливого лишнего не будет.
    """
    from sqlalchemy import text

    from app.scripts import refetch_vinyl_colors as R

    expected = {
        R._SELECT_WITH_COLOR: set(),
        R._SELECT_MISSING: {"lim"},
        R._UPDATE_SET: {"id", "color", "now"},
        R._UPDATE_CLEAR: {"id", "now"},
    }
    for sql, params in expected.items():
        assert set(text(sql).compile().params) == params


# ---- «Цвета нет» против «не доехали» -------------------------------------- #

class _FakeCache:
    def __init__(self):
        self.deleted = []

    async def delete(self, ns, key):
        self.deleted.append((ns, key))


def _patch(monkeypatch, *, result=None, boom=None):
    """Подменяем cache и DiscogsService внутри _fresh_color (импорт ленивый)."""
    import app.services.cache as cache_mod
    import app.services.discogs as discogs_mod

    fake_cache = _FakeCache()
    monkeypatch.setattr(cache_mod, "cache", fake_cache)

    class _FakeService:
        async def get_release(self, release_id, priority=None):
            if boom is not None:
                raise boom
            return result

    monkeypatch.setattr(discogs_mod, "DiscogsService", _FakeService)
    return fake_cache


@pytest.mark.asyncio
async def test_network_failure_is_not_an_empty_colour(monkeypatch):
    """Сбой обязан вернуть ok=False, иначе скрипт сотрёт живой цвет."""
    _patch(monkeypatch, boom=RuntimeError("503 from discogs"))
    color, ok = await _fresh_color("12345")
    assert ok is False
    assert color is None


@pytest.mark.asyncio
async def test_discogs_says_no_colour(monkeypatch):
    """А вот это — законный повод снести ключ."""
    _patch(monkeypatch, result={"vinyl_color_raw": None, "title": "X"})
    color, ok = await _fresh_color("12345")
    assert ok is True
    assert color is None


@pytest.mark.asyncio
async def test_fresh_colour_is_returned(monkeypatch):
    _patch(monkeypatch, result={"vinyl_color_raw": "Red Translucent"})
    color, ok = await _fresh_color("12345")
    assert (color, ok) == ("Red Translucent", True)


@pytest.mark.asyncio
async def test_release_cache_is_invalidated_before_fetch(monkeypatch):
    """В кэше payload, разобранный СТАРЫМ парсером.

    Без сброса скрипт бы прилежно «перезаписал» то же самое битое значение и
    отчитался, что всё хорошо.
    """
    fake_cache = _patch(monkeypatch, result={"vinyl_color_raw": "Blue"})
    await _fresh_color("777")
    assert ("release", "777") in fake_cache.deleted


@pytest.mark.asyncio
async def test_broken_cache_does_not_block_the_fetch(monkeypatch):
    """Redis лёг — это не повод отменять ре-фетч."""
    import app.services.cache as cache_mod
    import app.services.discogs as discogs_mod

    class _DeadCache:
        async def delete(self, ns, key):
            raise ConnectionError("redis down")

    class _Svc:
        async def get_release(self, release_id, priority=None):
            return {"vinyl_color_raw": "Yellow"}

    monkeypatch.setattr(cache_mod, "cache", _DeadCache())
    monkeypatch.setattr(discogs_mod, "DiscogsService", _Svc)

    assert await _fresh_color("42") == ("Yellow", True)
