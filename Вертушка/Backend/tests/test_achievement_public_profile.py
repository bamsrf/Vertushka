"""A4 «Распахнул» — по факту отправки ссылки, а не по тумблеру публичности.

Регрессия: ачивка висела на событии profile_shared_enabled, которое эмитилось
только при переходе ProfileShare.is_active false → true. С тех пор как профиль
создаётся публичным (server_default="true"), такого перехода не бывает ни у
кого — щёлкать было нечем, и A4 не выдавалась никому вообще.

Теперь условие — profile_shares.shared_at, который ставит POST /profile/share
из кнопок «Поделиться» и «Копировать ссылку». Живой БД у тестов нет: evaluator
ходит в неё одним scalar() за настройками профиля, его подменяет FakeSession.
"""
import pytest

from app.services.achievements.definitions.series import foundation as F
from app.services.achievements.events import PROFILE_SHARED_ENABLED
from app.services.achievements.registry import (
    get_definition,
    get_definitions_for_event,
)

USER = "00000000-0000-0000-0000-0000000000a4"


class _Share:
    def __init__(self, is_active=True, shared_at=None):
        self.is_active = is_active
        self.shared_at = shared_at


class FakeSession:
    """Стаб под evaluator: отдаёт ProfileShare (или его отсутствие)."""

    def __init__(self, share):
        self._share = share

    async def scalar(self, *_args, **_kwargs):
        return self._share


async def _a4(share):
    return await F._evaluate_a4(FakeSession(share), USER, {}, set())


@pytest.mark.asyncio
async def test_public_by_default_alone_does_not_unlock():
    # Ровно состояние свежего аккаунта: профиль публичен, ссылку не отправляли.
    result = await _a4(_Share(is_active=True, shared_at=None))
    assert result.unlocked is False


@pytest.mark.asyncio
async def test_shared_link_unlocks():
    from datetime import datetime

    result = await _a4(_Share(is_active=True, shared_at=datetime.utcnow()))
    assert result.unlocked is True


@pytest.mark.asyncio
async def test_shared_link_counts_even_if_profile_later_hidden():
    # Публичность выключили после того, как поделились: событие уже случилось,
    # отбирать ачивку задним числом нельзя.
    from datetime import datetime

    result = await _a4(_Share(is_active=False, shared_at=datetime.utcnow()))
    assert result.unlocked is True


@pytest.mark.asyncio
async def test_missing_profile_row_does_not_unlock():
    result = await _a4(None)
    assert result.unlocked is False


def test_a4_registered_on_shared_event():
    defn = get_definition(F.A4_CODE)
    assert defn is not None
    assert defn.series == "foundation"
    assert set(defn.triggers) == {PROFILE_SHARED_ENABLED}
    codes = {d.code for d in get_definitions_for_event(PROFILE_SHARED_ENABLED)}
    assert F.A4_CODE in codes
    # META серии обязана перепроверяться на том же событии, иначе «На борту»
    # не закроется до следующего действия из A-серии.
    assert F.META_CODE in codes
