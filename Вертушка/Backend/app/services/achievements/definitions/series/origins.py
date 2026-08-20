"""Серия «Истоки» (OG*) — пин «Первая сотня».

Выдаётся первой сотне коллекционеров: юзер попадает в зачёт, когда у него
появляется первая пластинка. Ранжирование — по моменту ПЕРВОГО CollectionItem
(tie-break по user_id), а не по «сколько уже выдали»: ранг считается из
неизменяемых данных, поэтому evaluator детерминирован, идемпотентен и не
зависит от порядка обработки конкурирующих событий.

Кто в зачёте (см. FOUNDER_ALLOWLIST / FOUNDERS_CUTOFF):
- три живых бета-аккаунта из допуска — они занимают первые слоты;
- все аккаунты, созданные начиная с FOUNDERS_CUTOFF (сторовская волна).
Остальные ранние аккаунты — служебные/владельца, в зачёт не идут и слоты
не занимают.

Неактивные аккаунты слот НЕ освобождают: ранг заморожен по created_at /
first added_at, иначе бан юзера #37 задним числом «довыдавал» бы пин юзеру
#101 — грид у людей менялся бы сам по себе.

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

from app.models.collection import Collection, CollectionItem
from app.models.user import User
from app.services.achievements.events import COLLECTION_ITEM_ADDED, DAILY_TICK
from app.services.achievements.registry import (
    AchievementDefinition,
    AchievementTier,
    EvalResult,
)

OG1_CODE = "OG1_first_hundred"

#: Живые бета-аккаунты, которые входят в «первую сотню» независимо от даты
#: регистрации. Сравнение по lower(username).
FOUNDER_ALLOWLIST = frozenset({"hhbbbgcdc7", "genia_pazla", "andrei"})

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
    if user is None or not is_founder_candidate(user.username, user.created_at):
        return EvalResult()

    my_first = await db.scalar(
        select(func.min(CollectionItem.added_at))
        .join(Collection, Collection.id == CollectionItem.collection_id)
        .where(Collection.user_id == user_id)
    )
    if my_first is None:
        return EvalResult()

    first_items = (
        select(
            Collection.user_id.label("uid"),
            func.min(CollectionItem.added_at).label("first_at"),
        )
        .join(CollectionItem, CollectionItem.collection_id == Collection.id)
        .group_by(Collection.user_id)
        .subquery()
    )
    ahead = await db.scalar(
        select(func.count())
        .select_from(first_items)
        .join(User, User.id == first_items.c.uid)
        .where(
            first_items.c.uid != user_id,
            or_(
                func.lower(User.username).in_(sorted(FOUNDER_ALLOWLIST)),
                User.created_at >= FOUNDERS_CUTOFF,
            ),
            or_(
                first_items.c.first_at < my_first,
                and_(
                    first_items.c.first_at == my_first,
                    first_items.c.uid < user_id,
                ),
            ),
        )
    )
    return EvalResult(unlocked=int(ahead or 0) < FOUNDERS_TARGET)


DEFINITIONS: list[AchievementDefinition] = [
    AchievementDefinition(
        code=OG1_CODE,
        title_ru="Первая сотня",
        description_ru="Попади в первую сотню коллекционеров Вертушки.",
        description_done_ru="Ты в первой сотне коллекционеров Вертушки.",
        series="origins",
        tier=AchievementTier.EPIC,
        is_hidden=False,
        triggers=(COLLECTION_ITEM_ADDED, DAILY_TICK),
        evaluator=_evaluate_first_hundred,
        flavor_ru="Ты был здесь, когда полки только начинались.",
        icon_slug="og1_first_hundred",
    ),
]
