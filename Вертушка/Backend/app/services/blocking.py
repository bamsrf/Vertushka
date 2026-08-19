"""Блокировка пользователей — общая проверка для всех точек контакта.

Раньше `is_user_blocked` жила в `services/messaging.py` и звалась только оттуда.
Из-за этого «заблокировать» означало «перестать получать личные сообщения», но
не мешало заблокированному подписаться на вас и присылать пуши. Для человека
блокировка — это «он исчез», а не «исчез из одного экрана из четырёх»; заодно
это то, что смотрят на ревью флоу блокировки (Guideline 1.2).
См. docs/plans/SECURITY_AUDIT_PRERELEASE.md §S6.

Проверка двусторонняя намеренно: неважно, кто кого заблокировал — контакта не
должно быть ни в одну сторону.
"""
from collections.abc import Iterable
from uuid import UUID

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user_block import UserBlock


async def is_user_blocked(db: AsyncSession, a_id: UUID, b_id: UUID) -> bool:
    """True если кто-то из пары заблокировал другого (в любую сторону).

    Оба поля user_blocks проиндексированы, запрос упирается в индекс — звать
    можно на горячем пути (в том числе на каждое уведомление с актором).
    """
    if a_id == b_id:
        return False
    row = await db.execute(
        select(UserBlock.id)
        .where(
            or_(
                and_(UserBlock.blocker_id == a_id, UserBlock.blocked_id == b_id),
                and_(UserBlock.blocker_id == b_id, UserBlock.blocked_id == a_id),
            )
        )
        .limit(1)
    )
    return row.scalar_one_or_none() is not None


async def blocked_partner_ids(
    db: AsyncSession, user_id: UUID, partner_ids: Iterable[UUID],
) -> set[UUID]:
    """Кто из partner_ids в блокировке с user_id (в любую сторону) — одним
    запросом. Для списков (диалоги, подписчики): вызов is_user_blocked на
    каждый элемент — это N запросов на экран, здесь их схлопывает один IN.
    """
    ids = {pid for pid in partner_ids if pid != user_id}
    if not ids:
        return set()
    rows = await db.execute(
        select(UserBlock.blocker_id, UserBlock.blocked_id).where(
            or_(
                and_(UserBlock.blocker_id == user_id, UserBlock.blocked_id.in_(ids)),
                and_(UserBlock.blocked_id == user_id, UserBlock.blocker_id.in_(ids)),
            )
        )
    )
    blocked: set[UUID] = set()
    for blocker_id, blocked_id in rows.all():
        blocked.add(blocked_id if blocker_id == user_id else blocker_id)
    return blocked
