"""Матчинг подарка: какую бронь предложить, когда пластинка уехала в коллекцию.

Даритель бронирует конкретный прессинг, а дарит часто другой — тот же альбом,
другое издание. Здесь проверяем ранжирование кандидатов: точная запись должна
побеждать мастер, мастер — название, а чужой альбом не должен давать поп-ап
вообще (ложный вопрос «это подарок?» хуже, чем его отсутствие).

Живой БД у тестов нет, поэтому сессию подменяем стабом: find_gift_match ходит
в базу ровно одним execute() за списком пунктов вишлиста с активной бронью.
Отбор по статусу и match_dismissed_at живёт в SQL: сами кандидаты приходят
стабом, поэтому наличие этих фильтров проверяем отдельно по тексту запроса.
Вся интересная логика приоритетов — на Python, её гоняем по-настоящему.
"""
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.services.gift_match import (
    MATCH_EXACT,
    MATCH_FUZZY,
    MATCH_MASTER,
    find_gift_match,
)


class _FakeResult:
    def __init__(self, values):
        self._values = values

    def scalars(self):
        return self

    def unique(self):
        return self

    def all(self):
        return self._values


class FakeSession:
    """Минимальный стаб AsyncSession: отдаёт заранее заданных кандидатов."""

    def __init__(self, items):
        self._items = items
        self.last_statement = None

    async def execute(self, statement, *_args, **_kwargs):
        self.last_statement = statement
        return _FakeResult(self._items)


USER = uuid4()


def make_record(*, artist, title, master=None, record_id=None):
    return SimpleNamespace(
        id=record_id or uuid4(),
        artist=artist,
        title=title,
        discogs_master_id=master,
    )


def make_item(record):
    """Пункт вишлиста с активной бронью — так его отдаёт запрос из find_gift_match."""
    booking = SimpleNamespace(id=uuid4())
    return SimpleNamespace(id=uuid4(), record=record, gift_booking=booking)


@pytest.mark.asyncio
async def test_exact_record_wins_over_master():
    """Та же самая запись важнее другого прессинга, даже если тот шёл первым."""
    scanned = make_record(artist="King Gizzard", title="Omnium Gatherum", master="m1")
    other_pressing = make_item(
        make_record(artist="King Gizzard", title="Omnium Gatherum", master="m1")
    )
    same_record = make_item(scanned)

    db = FakeSession([other_pressing, same_record])
    match = await find_gift_match(db, user_id=USER, record=scanned)

    assert match is not None
    assert match.match_kind == MATCH_EXACT
    assert match.wishlist_item is same_record


@pytest.mark.asyncio
async def test_different_pressing_matches_by_master():
    """Главный сценарий: подарили другое издание того же альбома."""
    scanned = make_record(artist="King Gizzard", title="Omnium Gatherum", master="m1")
    wished = make_item(
        make_record(artist="King Gizzard", title="Omnium Gatherum (2023)", master="m1")
    )

    db = FakeSession([wished])
    match = await find_gift_match(db, user_id=USER, record=scanned)

    assert match is not None
    assert match.match_kind == MATCH_MASTER
    assert match.booking is wished.gift_booking


@pytest.mark.asyncio
async def test_fuzzy_matches_when_master_missing_on_both_sides():
    """У разных прессингов мастер часто просто не заполнен — тогда артист+название."""
    scanned = make_record(artist="King Gizzard", title="Omnium Gatherum")
    wished = make_item(make_record(artist="king gizzard!", title="Omnium  Gatherum."))

    db = FakeSession([wished])
    match = await find_gift_match(db, user_id=USER, record=scanned)

    assert match is not None
    assert match.match_kind == MATCH_FUZZY


@pytest.mark.asyncio
async def test_master_beats_fuzzy():
    """Совпадение по мастеру надёжнее совпадения по названию — берём его."""
    scanned = make_record(artist="King Gizzard", title="Omnium Gatherum", master="m1")
    by_title = make_item(make_record(artist="King Gizzard", title="Omnium Gatherum"))
    by_master = make_item(make_record(artist="Другой артист", title="Другой альбом", master="m1"))

    db = FakeSession([by_title, by_master])
    match = await find_gift_match(db, user_id=USER, record=scanned)

    assert match is not None
    assert match.match_kind == MATCH_MASTER
    assert match.wishlist_item is by_master


@pytest.mark.asyncio
async def test_unrelated_album_gives_no_popup():
    """Ложный вопрос «это подарок?» хуже отсутствия вопроса."""
    scanned = make_record(artist="King Gizzard", title="Omnium Gatherum", master="m1")
    wished = make_item(make_record(artist="Radiohead", title="In Rainbows", master="m2"))

    db = FakeSession([wished])
    assert await find_gift_match(db, user_id=USER, record=scanned) is None


@pytest.mark.asyncio
async def test_no_active_bookings_gives_no_popup():
    scanned = make_record(artist="King Gizzard", title="Omnium Gatherum", master="m1")
    assert await find_gift_match(FakeSession([]), user_id=USER, record=scanned) is None


@pytest.mark.asyncio
async def test_same_artist_different_album_does_not_match():
    """Одного артиста мало: у King Gizzard два десятка альбомов в год."""
    scanned = make_record(artist="King Gizzard", title="Omnium Gatherum")
    wished = make_item(make_record(artist="King Gizzard", title="Flying Microtonal Banana"))

    db = FakeSession([wished])
    assert await find_gift_match(db, user_id=USER, record=scanned) is None


@pytest.mark.asyncio
async def test_item_without_record_is_skipped():
    """Битая связь не должна ронять добавление пластинки в коллекцию."""
    scanned = make_record(artist="King Gizzard", title="Omnium Gatherum", master="m1")
    broken = SimpleNamespace(id=uuid4(), record=None, gift_booking=SimpleNamespace(id=uuid4()))
    good = make_item(make_record(artist="King Gizzard", title="Omnium Gatherum", master="m1"))

    db = FakeSession([broken, good])
    match = await find_gift_match(db, user_id=USER, record=scanned)

    assert match is not None
    assert match.wishlist_item is good


@pytest.mark.asyncio
async def test_query_filters_out_dismissed_and_unconfirmed_bookings():
    """Отбор кандидатов живёт в SQL — проверяем, что фильтры оттуда не исчезли.

    Без match_dismissed_at поп-ап всплывал бы снова после «нет, купил сам»,
    а без фильтра по статусу — предлагал бы закрыть бронь, которую даритель
    ещё не подтвердил по email.
    """
    scanned = make_record(artist="King Gizzard", title="Omnium Gatherum")
    db = FakeSession([])

    await find_gift_match(db, user_id=USER, record=scanned)

    sql = str(db.last_statement)
    assert "match_dismissed_at IS NULL" in sql
    assert "gift_bookings.status" in sql
