"""Ядро системы ачивок.

emit_event() — единая точка входа из API-обработчиков. Принимает имя события
и опциональный payload, прогоняет все evaluator-ы, реагирующие на это событие,
персистит изменения, возвращает список свежеоткрытых ачивок.

Контракт: никогда не пробрасывает исключения наружу. Любая ошибка логируется
и проглатывается — отказ системы ачивок не должен ронять основной API.
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user_achievement import UserAchievement
from app.services.achievements.registry import (
    AchievementDefinition,
    EvalResult,
    get_definitions_for_event,
)

logger = logging.getLogger(__name__)


async def emit_event(
    db: AsyncSession,
    user_id: UUID,
    event: str,
    payload: dict[str, Any] | None = None,
) -> list[str]:
    """Эмитирует событие.

    Возвращает список свежеоткрытых ачивок (коды). Если что-то пошло не так,
    возвращает [] и логирует — основной API не пострадает.
    """
    payload = payload or {}
    try:
        return await _emit_impl(db, user_id, event, payload)
    except Exception:  # noqa: BLE001
        logger.exception(
            "achievement_emit_failed",
            extra={"user_id": str(user_id), "event": event},
        )
        try:
            await db.rollback()
        except Exception:  # noqa: BLE001
            pass
        return []


async def _emit_impl(
    db: AsyncSession,
    user_id: UUID,
    event: str,
    payload: dict[str, Any],
) -> list[str]:
    defs = get_definitions_for_event(event)
    if not defs:
        return []

    # Текущее состояние ачивок этого юзера по релевантным кодам
    relevant_codes = [d.code for d in defs]
    existing_rows = await db.execute(
        select(UserAchievement).where(
            UserAchievement.user_id == user_id,
            UserAchievement.code.in_(relevant_codes),
        )
    )
    existing_by_code: dict[str, UserAchievement] = {
        ua.code: ua for ua in existing_rows.scalars().all()
    }

    unlocked_now: set[str] = set()

    for defn in defs:
        ua = existing_by_code.get(defn.code)
        if ua is not None and ua.is_unlocked:
            continue

        try:
            result = await defn.evaluator(db, user_id, payload, unlocked_now)
        except Exception:  # noqa: BLE001
            logger.exception(
                "achievement_evaluator_failed",
                extra={
                    "user_id": str(user_id),
                    "event": event,
                    "code": defn.code,
                },
            )
            continue

        await _persist(db, user_id, defn, ua, result)
        if result.unlocked:
            unlocked_now.add(defn.code)

    await db.commit()

    if unlocked_now:
        logger.info(
            "achievements_unlocked",
            extra={
                "user_id": str(user_id),
                "event": event,
                "codes": sorted(unlocked_now),
            },
        )

        try:
            from app.services.notification_service import create_notification
            from app.services.achievements.registry import get_definition
            from app.services import push_copy
            for code in sorted(unlocked_now):
                defn = get_definition(code)
                title = defn.title_ru if defn else code
                push_title, push_body = push_copy.achievement_unlocked(
                    title_ru=title,
                    flavor_ru=getattr(defn, "flavor_ru", "") if defn else "",
                )
                await create_notification(
                    db,
                    user_id=user_id,
                    type="achievement_unlocked",
                    entity_type="achievement",
                    entity_id=code,
                    data={
                        "code": code,
                        "icon_slug": defn.icon_slug if defn else "",
                        "title": title,
                    },
                    push_title=push_title,
                    push_body=push_body,
                    # Cap по умолчанию — один push на тип в час, и весь батч
                    # ачивок схлопывался в одну: юзер открывал пять штук, а
                    # узнавал про первую. Слот на КОД: разные ачивки друг друга
                    # не глушат, повтор той же — по-прежнему режется.
                    push_cap_key=f"achievement_unlocked:{code}",
                )
            await db.commit()
        except Exception:
            logger.exception("Failed to create achievement_unlocked notification")
            try:
                await db.rollback()
            except Exception:
                pass

        # Уровень архетипа мог перешагнуть порог — это отдельное событие с
        # собственным пушем. Не смешиваем с ачивкой: она про «что сделал»,
        # уровень — про «кем стал».
        try:
            await _notify_level_up(db, user_id, sorted(unlocked_now))
        except Exception:
            logger.exception("Failed to create level_up notification")
            try:
                await db.rollback()
            except Exception:
                pass

    return sorted(unlocked_now)


async def _notify_level_up(
    db: AsyncSession,
    user_id: UUID,
    unlocked_codes: list[str],
) -> None:
    """Создаёт level_up-уведомление, если батч ачивок поднял юзера на ступень."""
    from app.models.notification import PRIORITY_PUSH
    from app.services import push_copy
    from app.services.achievements.levels import detect_level_up
    from app.services.notification_service import upsert_notification

    level_up = await detect_level_up(db, user_id, unlocked_codes=unlocked_codes)
    if level_up is None:
        return

    push_title, push_body = push_copy.level_up(
        label=level_up.level.label,
        flavor_ru=level_up.level.flavor,
    )
    await upsert_notification(
        db,
        user_id=user_id,
        type="level_up",
        dedup_key=f"level_up:{level_up.level.key}",
        entity_type="level",
        entity_id=level_up.level.key,
        data={
            "level_key": level_up.level.key,
            "level_label": level_up.level.label,
            "level_index": level_up.index,
            "previous_key": level_up.previous.key,
            "previous_label": level_up.previous.label,
            "flavor": level_up.level.flavor,
            "score": level_up.score,
        },
        push_title=push_title,
        push_body=push_body,
        priority=PRIORITY_PUSH,
    )
    await db.commit()
    logger.info(
        "level_up",
        extra={
            "user_id": str(user_id),
            "level": level_up.level.key,
            "score": level_up.score,
        },
    )


async def _persist(
    db: AsyncSession,
    user_id: UUID,
    defn: AchievementDefinition,
    existing: UserAchievement | None,
    result: EvalResult,
) -> None:
    """Записывает результат evaluator-а в БД.

    Идемпотентность:
    - Уже unlocked — не пишем (отфильтровано выше).
    - progress пишем только если новое значение больше текущего (защита от
      устаревших событий).
    """
    from app.services.achievements.levels import weight_for_code

    if existing is None:
        if not result.unlocked and result.progress is None:
            return
        ua = UserAchievement(
            user_id=user_id,
            code=defn.code,
            is_unlocked=result.unlocked,
            unlocked_at=datetime.utcnow() if result.unlocked else None,
            # Замораживаем опыт прямо здесь: дальше он не пересчитывается.
            xp_awarded=weight_for_code(defn.code) if result.unlocked else None,
            progress=result.progress or 0,
            progress_target=result.progress_target or 0,
            ach_metadata=result.metadata,
        )
        db.add(ua)
        await db.flush()
        return

    if result.unlocked:
        existing.is_unlocked = True
        existing.unlocked_at = datetime.utcnow()
        if existing.xp_awarded is None:
            existing.xp_awarded = weight_for_code(defn.code)
        if result.progress is not None:
            existing.progress = max(existing.progress, result.progress)
        if result.progress_target is not None:
            existing.progress_target = result.progress_target
        if result.metadata is not None:
            existing.ach_metadata = result.metadata
        await db.flush()
        return

    if result.progress is not None and result.progress > existing.progress:
        existing.progress = result.progress
        if result.progress_target is not None:
            existing.progress_target = result.progress_target
        await db.flush()
