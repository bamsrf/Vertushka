"""Серия «Истоки» (OG*) — пин «Первая сотня».

Выдаётся первой сотне зарегистрировавшихся: условие — сам факт создания
аккаунта, без требований к коллекции. Ранжирование по `User.created_at`
(tie-break по user_id) — значение неизменяемое, поэтому evaluator
детерминирован, идемпотентен и не зависит от порядка обработки событий.

Почему не «первая пластинка» (так было до 03.09.2026): две трети новых
аккаунтов до первого добавления не доходили, и пин — та самая награда за
раннее участие — им не доставался. Сместили к регистрации: приветствие
раннему юзеру, а не награда за активность.

Кто в зачёте (см. FOUNDER_ALLOWLIST / FOUNDERS_CUTOFF):
- живые бета-аккаунты из допуска — они занимают первые слоты;
- все аккаунты, созданные начиная с FOUNDERS_CUTOFF (сторовская волна).
Остальные ранние аккаунты — служебные/владельца, в зачёт не идут и слоты
не занимают.

Два независимых предела, оба обязаны выполниться:
1. РАНГ — сколько кандидатов зарегистрировалось раньше меня (< 100);
2. ПРЕДОХРАНИТЕЛЬ — сколько пинов уже выдано всего (< 100).
Ранга одного мало: удалённый аккаунт выпадает из подсчёта и сдвигает всех
позади на слот вперёд, а выданный пин мы не отбираем — суммарно ушло бы
больше сотни. Предохранитель даёт жёсткий потолок, ранг — справедливый
порядок.

Неактивные аккаунты слот НЕ освобождают: пин у них остаётся и продолжает
считаться выданным.

Серия гейтится в UI (GATE_CODE_BY_SERIES в formats.py): у тех, кто в сотню
не попал, полка не показывается вовсе — вечно залоченный пин в общем гриде
никому не нужен.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.models.user_achievement import UserAchievement
from app.services.achievements.events import DAILY_TICK, USER_REGISTERED
from app.services.achievements.registry import (
    AchievementDefinition,
    AchievementTier,
    EvalResult,
)

OG1_CODE = "OG1_first_hundred"

#: Живые бета-аккаунты, которые входят в «первую сотню» независимо от даты
#: регистрации. Сравнение по lower(username).
FOUNDER_ALLOWLIST = frozenset({"hhbbbgcdc7", "genia_pazla", "andrei", "xenon"})

#: Аккаунты, созданные с этого момента (UTC), попадают в зачёт автоматически.
#: Перед релизом в сторе можно сдвинуть на дату релиза — но помни: любой
#: тестовый аккаунт, созданный ПОСЛЕ отсечки, займёт слот и получит пин.
FOUNDERS_CUTOFF = datetime(2026, 8, 21)

#: Размер «первой сотни».
FOUNDERS_TARGET = 100


def is_founder_candidate(username: str | None, created_at: datetime | None) -> bool:
    """Входит ли аккаунт в зачёт «первой сотни» (без учёта наличия пластинок)."""
    if username and username.strip().lower() in FOUNDER_ALLOWLIST:
        return True
    return created_at is not None and created_at >= FOUNDERS_CUTOFF


async def _evaluate_first_hundred(
    db: AsyncSession,
    user_id: UUID,
    payload: dict[str, Any],
    unlocked_now: set[str],
) -> EvalResult:
    user = await db.scalar(select(User).where(User.id == user_id))
    if user is None or user.created_at is None:
        return EvalResult()
    if not is_founder_candidate(user.username, user.created_at):
        return EvalResult()

    # 1) Ранг: сколько кандидатов зарегистрировалось раньше меня. Ровно та же
    # пара условий кандидата, что в is_founder_candidate, но на стороне SQL.
    is_candidate = or_(
        func.lower(User.username).in_(sorted(FOUNDER_ALLOWLIST)),
        User.created_at >= FOUNDERS_CUTOFF,
    )
    ahead = await db.scalar(
        select(func.count())
        .select_from(User)
        .where(
            User.id != user_id,
            is_candidate,
            or_(
                User.created_at < user.created_at,
                and_(User.created_at == user.created_at, User.id < user_id),
            ),
        )
    )
    if int(ahead or 0) >= FOUNDERS_TARGET:
        return EvalResult()

    # 2) Предохранитель: сотня — это сотня выданных пинов. Себя исключаем,
    # иначе повторная оценка уже открытой ачивки считала бы собственный слот
    # занятым чужим.
    granted = await db.scalar(
        select(func.count())
        .select_from(UserAchievement)
        .where(
            UserAchievement.code == OG1_CODE,
            UserAchievement.is_unlocked.is_(True),
            UserAchievement.user_id != user_id,
        )
    )
    return EvalResult(unlocked=int(granted or 0) < FOUNDERS_TARGET)


DEFINITIONS: list[AchievementDefinition] = [
    AchievementDefinition(
        code=OG1_CODE,
        title_ru="Первая сотня",
        description_ru="Зарегистрируйся одним из первых ста пользователей Вертушки.",
        description_done_ru="Ты в первой сотне пользователей Вертушки.",
        series="origins",
        tier=AchievementTier.EPIC,
        is_hidden=False,
        triggers=(USER_REGISTERED, DAILY_TICK),
        evaluator=_evaluate_first_hundred,
        flavor_ru="Первый тираж. Его не допечатают.",
        icon_slug="og1_first_hundred",
    ),
]
