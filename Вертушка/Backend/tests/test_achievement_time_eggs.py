"""Временные пасхалки серии random: условия — по МСК, таймстемпы в БД — UTC.

БД хранит naive UTC (datetime.utcnow), а тексты ачивок обещают «настенное»
время юзера («под куранты», «поздним вечером пятницы», «между тремя и
четырьмя ночи»). Аудитория — Россия, поэтому дефолт — Europe/Moscow (UTC+3,
без сезонных переходов с 2014 года). Здесь ловим именно сдвиг: моменты,
которые по МСК попадают в окно, а по UTC — нет, и наоборот.

Опорные даты: 09.01.2026 — пятница; 2028 — високосный год.
"""
from datetime import datetime

import pytest

from app.services.achievements.definitions import eggs as E


class _FakeResult:
    def __init__(self, values):
        self._values = values

    def scalars(self):
        return self

    def all(self):
        return self._values


class FakeSession:
    """Минимальный стаб AsyncSession: execute() отдаёт заранее заданный список."""

    def __init__(self, rows=None):
        self._rows = rows or []

    async def execute(self, *_args, **_kwargs):
        return _FakeResult(self._rows)


USER = "11111111-1111-1111-1111-111111111111"


# --- Конвертация -------------------------------------------------------------

def test_utc_to_msk_is_plus_three_hours():
    assert E._utc_to_msk(datetime(2026, 6, 1, 12, 0)) == datetime(2026, 6, 1, 15, 0)


# --- «Первая в году»: первые полчаса января по МСК ---------------------------

def test_new_year_under_kremlin_chimes_msk():
    # 00:15 МСК 1 января = 21:15 UTC 31 декабря — юзер добавил под куранты.
    assert E._is_new_year_moment(datetime(2025, 12, 31, 21, 15)) is True


def test_new_year_old_utc_window_no_longer_counts():
    # 00:15 UTC 1 января = 03:15 МСК — старое (битое) окно, куранты давно отбили.
    assert E._is_new_year_moment(datetime(2026, 1, 1, 0, 15)) is False


def test_new_year_half_hour_boundary_is_exclusive():
    # 00:30 МСК — первые полчаса уже кончились.
    assert E._is_new_year_moment(datetime(2025, 12, 31, 21, 30)) is False


# --- «Пятничный спин»: пятница 22:00 – суббота 01:59 по МСК ------------------

def test_friday_night_at_23_msk():
    # 23:00 МСК пятницы 09.01.2026 = 20:00 UTC той же пятницы.
    assert E._is_friday_night(datetime(2026, 1, 9, 20, 0)) is True


def test_friday_early_evening_msk_does_not_count():
    # 21:59 МСК пятницы = 18:59 UTC — окно ещё не открылось.
    assert E._is_friday_night(datetime(2026, 1, 9, 18, 59)) is False


def test_saturday_small_hours_msk_still_counts():
    # 01:30 МСК субботы = 22:30 UTC пятницы — ночь ещё пятничная.
    assert E._is_friday_night(datetime(2026, 1, 9, 22, 30)) is True


def test_saturday_after_two_msk_does_not_count():
    # 02:30 МСК субботы = 23:30 UTC пятницы — окно закрылось.
    assert E._is_friday_night(datetime(2026, 1, 9, 23, 30)) is False


# --- «29 февраля»: календарный день по МСК -----------------------------------

def test_leap_day_first_msk_hours():
    # 00:30 МСК 29.02.2028 = 21:30 UTC 28.02 — по UTC день ещё 28-е.
    assert E._is_leap_day(datetime(2028, 2, 28, 21, 30)) is True


def test_leap_day_utc_tail_is_already_march_msk():
    # 22:00 UTC 29.02 = 01:00 МСК 1 марта — день, которого нет, уже прошёл.
    assert E._is_leap_day(datetime(2028, 2, 29, 22, 0)) is False


# --- «Ночной диггинг»: клик между 03:00 и 04:00 по МСК -----------------------

@pytest.mark.asyncio
async def test_night_crate_click_at_0330_msk():
    # 03:30 МСК = 00:30 UTC.
    db = FakeSession(rows=[datetime(2026, 1, 10, 0, 30)])
    res = await E._evaluate_night_crate(db, USER, {}, set())
    assert res.unlocked is True


@pytest.mark.asyncio
async def test_night_crate_old_utc_hour_no_longer_counts():
    # 03:30 UTC = 06:30 МСК — раннее утро, а не «между тремя и четырьмя ночи».
    db = FakeSession(rows=[datetime(2026, 1, 10, 3, 30)])
    res = await E._evaluate_night_crate(db, USER, {}, set())
    assert res.unlocked is False


@pytest.mark.asyncio
async def test_night_crate_without_clicks_stays_locked():
    db = FakeSession(rows=[])
    res = await E._evaluate_night_crate(db, USER, {}, set())
    assert res.unlocked is False
