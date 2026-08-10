"""Скрытая дорожка (E-серия): проверяем, что жесты реально трекаются.

Живой БД у тестов нет, поэтому сессию подменяем стабом: эвалюаторы этой серии
ходят в базу ровно двумя способами — `scalar()` за состоянием/фактом и
`execute()` за списком цветов. Стаб отдаёт заранее заданный ответ, а вся
интересная логика (стрик, скользящее окно суток, циклы add/remove, окно
годовщины) живёт в Python и проверяется по-настоящему.

Главное, что здесь ловится: пасхалка не должна открываться раньше времени.
"""
from datetime import datetime, timedelta

import pytest

from app.services.achievements.definitions import eggs_interaction as E


class _FakeResult:
    def __init__(self, values):
        self._values = values

    def scalars(self):
        return self

    def all(self):
        return self._values


class FakeSession:
    """Минимальный стаб AsyncSession под эвалюаторы серии E."""

    def __init__(self, *, scalar=None, rows=None):
        self._scalar = scalar
        self._rows = rows or []

    async def scalar(self, *_args, **_kwargs):
        return self._scalar

    async def execute(self, *_args, **_kwargs):
        return _FakeResult(self._rows)


USER = "11111111-1111-1111-1111-111111111111"


# --- Оцифровщик: стрик сканов ------------------------------------------------

@pytest.mark.asyncio
async def test_digitizer_unlocks_on_tenth_scan_in_a_row():
    db = FakeSession(scalar={"streak": E.DIGITIZER_STREAK - 1})
    res = await E._evaluate_digitizer(db, USER, {"via_scan": True}, set())
    assert res.unlocked is True


@pytest.mark.asyncio
async def test_digitizer_does_not_unlock_one_scan_early():
    db = FakeSession(scalar={"streak": E.DIGITIZER_STREAK - 2})
    res = await E._evaluate_digitizer(db, USER, {"via_scan": True}, set())
    assert res.unlocked is False
    assert res.progress == E.DIGITIZER_STREAK - 1


@pytest.mark.asyncio
async def test_digitizer_streak_resets_on_manual_add():
    """Добавление руками рвёт «подряд» — иначе это «десять раз когда-нибудь»."""
    db = FakeSession(scalar={"streak": 9})
    res = await E._evaluate_digitizer(db, USER, None, set())
    assert res.unlocked is False
    assert res.metadata == {"streak": 0}


# --- Не та фотка: 5 смен аватара за сутки ------------------------------------

@pytest.mark.asyncio
async def test_photo_shy_unlocks_on_fifth_change_within_a_day():
    recent = [(datetime.utcnow() - timedelta(hours=h)).isoformat() for h in (5, 4, 3, 2)]
    db = FakeSession(scalar={"stamps": recent})
    res = await E._evaluate_photo_shy(db, USER, None, set())
    assert res.unlocked is True


@pytest.mark.asyncio
async def test_photo_shy_ignores_changes_older_than_a_day():
    """Четыре смены вчера + одна сегодня — это не «пять за сутки»."""
    stale = [(datetime.utcnow() - timedelta(days=2, hours=h)).isoformat() for h in range(4)]
    db = FakeSession(scalar={"stamps": stale})
    res = await E._evaluate_photo_shy(db, USER, None, set())
    assert res.unlocked is False
    assert res.progress == 1


# --- Сомнения: циклы добавил-удалил ------------------------------------------

@pytest.mark.asyncio
async def test_second_thoughts_unlocks_on_third_removal_of_same_record():
    db = FakeSession(scalar={"cycles": {"rec-a": 2}})
    res = await E._evaluate_second_thoughts(db, USER, {"record_id": "rec-a"}, set())
    assert res.unlocked is True


@pytest.mark.asyncio
async def test_second_thoughts_counts_per_record_not_in_total():
    """Три разные пластинки по разу — это не сомнения, а обычная уборка."""
    db = FakeSession(scalar={"cycles": {"rec-a": 1, "rec-b": 1}})
    res = await E._evaluate_second_thoughts(db, USER, {"record_id": "rec-c"}, set())
    assert res.unlocked is False
    assert res.progress == 1


@pytest.mark.asyncio
async def test_second_thoughts_without_record_id_is_noop():
    db = FakeSession(scalar={})
    res = await E._evaluate_second_thoughts(db, USER, None, set())
    assert res.unlocked is False
    assert res.metadata is None


# --- Радуга: шесть семей цвета ------------------------------------------------

@pytest.mark.asyncio
async def test_rainbow_unlocks_on_six_distinct_colour_families():
    db = FakeSession(rows=["Red", "Blue", "Green", "Yellow", "Pink", "Purple"])
    res = await E._evaluate_rainbow(db, USER, None, set())
    assert res.unlocked is True


@pytest.mark.asyncio
async def test_rainbow_ignores_black_and_non_colour_noise():
    """«180 Gram» и «Gatefold» — не цвета, чёрный — не «цветной винил»."""
    db = FakeSession(rows=["Black", "180 Gram", "Gatefold", "Red", "Blue", "Clear"])
    res = await E._evaluate_rainbow(db, USER, None, set())
    assert res.unlocked is False
    assert res.progress == 2  # red + blue


@pytest.mark.asyncio
async def test_rainbow_counts_family_not_raw_string():
    """«Red», «Red Translucent», «Dark Red» — один цвет, а не три."""
    db = FakeSession(rows=["Red", "Red Translucent", "Dark Red"])
    res = await E._evaluate_rainbow(db, USER, None, set())
    assert res.progress == 1


# --- Год спустя ---------------------------------------------------------------

@pytest.mark.asyncio
async def test_anniversary_unlocks_within_window():
    created = datetime.utcnow().replace(year=datetime.utcnow().year - 1)
    db = FakeSession(scalar=created)
    res = await E._evaluate_anniversary(db, USER, None, set())
    assert res.unlocked is True


@pytest.mark.asyncio
async def test_anniversary_silent_far_from_the_date():
    now = datetime.utcnow()
    created = (now - timedelta(days=200)).replace(year=now.year - 1)
    db = FakeSession(scalar=created)
    res = await E._evaluate_anniversary(db, USER, None, set())
    assert res.unlocked is False


@pytest.mark.asyncio
async def test_anniversary_not_on_the_first_day():
    """Зарегистрировался сегодня — никакой годовщины ещё нет."""
    db = FakeSession(scalar=datetime.utcnow())
    res = await E._evaluate_anniversary(db, USER, None, set())
    assert res.unlocked is False


# --- Светится в темноте -------------------------------------------------------

@pytest.mark.asyncio
async def test_glow_unlocks_when_collection_has_glow_vinyl():
    assert (await E._evaluate_glow(FakeSession(scalar=1), USER, None, set())).unlocked is True
    assert (await E._evaluate_glow(FakeSession(scalar=0), USER, None, set())).unlocked is False


# --- Клиентские жесты ---------------------------------------------------------

@pytest.mark.asyncio
async def test_client_gestures_unlock_on_their_event():
    """Спиннер, pull-to-refresh и промах скана считает клиент — событие уже итог."""
    for evaluator in (E._evaluate_spin, E._evaluate_pull_78, E._evaluate_glass_eye):
        assert (await evaluator(FakeSession(), USER, None, set())).unlocked is True


# --- Контракт серии -----------------------------------------------------------

def test_series_contract_holds():
    """Все скрытые, все 🌸+, серия random, у каждой свой icon_slug и триггер."""
    slugs = set()
    for defn in E.DEFINITIONS:
        assert defn.is_hidden, defn.code
        assert defn.series == "random", defn.code
        assert defn.tier.value in ("rare", "epic", "legend"), defn.code
        assert defn.triggers, defn.code
        assert defn.icon_slug and defn.icon_slug not in slugs, defn.code
        slugs.add(defn.icon_slug)
    assert len(E.DEFINITIONS) == 9
