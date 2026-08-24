"""Фоновые задачи системы ачивок.

Phase 0 — одна задача: daily_tick. Прогоняет evaluator-ы, которые зависят от
времени (например, R_thirty_three с 24h cooldown, B1/B2 с антифарм-задержкой
24h), для всех активных пользователей.

Реализовано «лениво» — итерируемся по пользователям, у которых есть хотя бы
одна запись в коллекции; пропускаем тех, у кого ВСЕ ачивки в зоне daily_tick
уже разблокированы.
"""
from __future__ import annotations

import logging
from datetime import datetime

from sqlalchemy import distinct, func, select
from sqlalchemy.exc import SQLAlchemyError

from app.database import async_session_maker
from app.models.collection import Collection, CollectionItem
from app.models.user import User
from app.models.user_achievement import UserAchievement
from app.services.achievements import emit_event
from app.services.achievements.definitions.eggs import (
    EXACT_COUNT_ACHIEVEMENTS,
    EXACT_COUNT_COOLDOWN,
)
from app.services.achievements.events import COOLDOWN_TICK, DAILY_TICK
from app.services.achievements.registry import (
    AchievementDefinition,
    all_definitions,
)

logger = logging.getLogger(__name__)


def _daily_tick_codes() -> set[str]:
    return {d.code for d in all_definitions() if DAILY_TICK in d.triggers}


async def daily_tick_achievements() -> None:
    """Фоновая задача. Запускается раз в сутки через APScheduler.

    Идёт по всем пользователям с непустой коллекцией и прогоняет emit_event(
    DAILY_TICK). Идемпотентность гарантируется ядром.
    """
    codes_to_check = _daily_tick_codes()
    if not codes_to_check:
        logger.info("achievements_daily_tick_skipped: no codes registered")
        return

    processed = 0
    failed = 0

    async with async_session_maker() as db:
        # Берём id пользователей, у которых есть хотя бы одна коллекция
        result = await db.execute(
            select(User.id)
            .join(Collection, Collection.user_id == User.id)
            .where(User.is_active.is_(True))
            .distinct()
        )
        user_ids = [row[0] for row in result.all()]

    logger.info(
        "achievements_daily_tick_start",
        extra={"total_users": len(user_ids), "codes": sorted(codes_to_check)},
    )

    for user_id in user_ids:
        try:
            # Каждый юзер — в своей сессии: ошибка одного не валит остальных.
            async with async_session_maker() as db:
                await emit_event(db, user_id, DAILY_TICK, {})
            processed += 1
        except SQLAlchemyError:
            failed += 1
            logger.exception(
                "achievements_daily_tick_user_failed",
                extra={"user_id": str(user_id)},
            )
        except Exception:  # noqa: BLE001
            failed += 1
            logger.exception(
                "achievements_daily_tick_user_unexpected",
                extra={"user_id": str(user_id)},
            )

    logger.info(
        "achievements_daily_tick_done",
        extra={"processed": processed, "failed": failed},
    )


async def _exact_count_candidates() -> list:
    """Юзеры, которые прямо сейчас сидят ровно на пороге и сутки молчат.

    Один запрос вместо прогона evaluator-а по всем юзерам: считаем уникальные
    пластинки ОСНОВНОЙ коллекции (папки — отдельные Collection с копиями, в
    счёт не идут) и последнее добавление в неё же.
    """
    targets = sorted(set(EXACT_COUNT_ACHIEVEMENTS.values()))
    codes = sorted(EXACT_COUNT_ACHIEVEMENTS)
    cutoff = datetime.utcnow() - EXACT_COUNT_COOLDOWN

    # Основная коллекция каждого юзера: минимальный sort_order, при равенстве —
    # самая ранняя. Тот же порядок, что в _default_collection_id пасхалок.
    main = (
        select(
            Collection.id.label("collection_id"),
            Collection.user_id.label("user_id"),
        )
        .distinct(Collection.user_id)
        .order_by(Collection.user_id, Collection.sort_order, Collection.created_at)
        .subquery()
    )
    agg = (
        select(
            main.c.user_id.label("user_id"),
            func.count(distinct(CollectionItem.record_id)).label("uniq"),
            func.max(CollectionItem.added_at).label("last_added"),
        )
        .join(CollectionItem, CollectionItem.collection_id == main.c.collection_id)
        .group_by(main.c.user_id)
        .subquery()
    )
    # Кто уже собрал ВСЕ пасхалки этого класса — больше не кандидат. Именно
    # все, а не любую: закрывший «69» может позже сесть на следующий порог.
    done = (
        select(UserAchievement.user_id)
        .where(
            UserAchievement.code.in_(codes),
            UserAchievement.is_unlocked.is_(True),
        )
        .group_by(UserAchievement.user_id)
        .having(func.count(distinct(UserAchievement.code)) == len(codes))
    )

    async with async_session_maker() as db:
        result = await db.execute(
            select(agg.c.user_id)
            .join(User, User.id == agg.c.user_id)
            .where(
                User.is_active.is_(True),
                agg.c.uniq.in_(targets),
                agg.c.last_added <= cutoff,
                agg.c.user_id.not_in(done),
            )
        )
        return [row[0] for row in result.all()]


async def cooldown_tick_achievements() -> None:
    """Ежечасный тик для пасхалок «ровно N пластинок и сутки тишины».

    Такие пасхалки не выдаются на COLLECTION_ITEM_ADDED: добавление само
    обнуляет кулдаун, так что в момент события условие невыполнимо по
    построению. Оставался только daily_tick в 6:00 UTC — и юзер, набравший
    порог вечером, ждал не заявленные сутки, а почти двое. Здесь берём узкую
    выборку кандидатов одним запросом и эмитим событие только им.
    """
    if not EXACT_COUNT_ACHIEVEMENTS:
        return

    try:
        user_ids = await _exact_count_candidates()
    except SQLAlchemyError:
        logger.exception("achievements_cooldown_tick_query_failed")
        return

    if not user_ids:
        return

    processed = 0
    failed = 0
    for user_id in user_ids:
        try:
            async with async_session_maker() as db:
                await emit_event(db, user_id, COOLDOWN_TICK, {})
            processed += 1
        except SQLAlchemyError:
            failed += 1
            logger.exception(
                "achievements_cooldown_tick_user_failed",
                extra={"user_id": str(user_id)},
            )
        except Exception:  # noqa: BLE001
            failed += 1
            logger.exception(
                "achievements_cooldown_tick_user_unexpected",
                extra={"user_id": str(user_id)},
            )

    logger.info(
        "achievements_cooldown_tick_done",
        extra={"processed": processed, "failed": failed},
    )
