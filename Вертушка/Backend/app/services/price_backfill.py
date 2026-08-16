"""Дозагрузка цен для коллекции конкретного пользователя.

Постановка задачи (`enqueue_price_job`) вызывается из импорта Discogs, сам
прогон — из шедулера (`app/tasks/discogs_tasks.py::run_price_backfill_jobs`).
Разделение нужно потому, что API-контейнер шедулер не запускает: он только
кладёт строку в `discogs_price_jobs`, а разгребает её отдельный процесс.

Почему не из общего `update_prices_batch`: тот идёт по всей базе под app-токеном
пачками фиксированного размера и до конкретного юзера доезжает за недели. Здесь
запросы идут под OAuth-парой самого юзера, то есть в его личный бакет
rate-limiter'а — 60 req/min, которые всё равно никем не используются, пока он
не в приложении.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.collection import Collection, CollectionItem
from app.models.discogs_price_job import (
    STATUS_PENDING,
    DiscogsPriceJob,
)
from app.models.record import Record

logger = logging.getLogger(__name__)

# Строку в статусе running с heartbeat старше этого считаем осиротевшей:
# контейнер упал или его выкатили посреди прогона. Воркер её подхватит заново.
STALE_RUNNING_AFTER = timedelta(minutes=15)


def records_without_price_query(user_id: UUID):
    """Записи в коллекциях юзера, у которых нет цены.

    DISTINCT: одна и та же пластинка лежит и в основной коллекции, и в папке —
    платить за неё двумя запросами к Discogs незачем.
    """
    return (
        select(Record)
        .join(CollectionItem, CollectionItem.record_id == Record.id)
        .join(Collection, CollectionItem.collection_id == Collection.id)
        .where(
            Collection.user_id == user_id,
            Record.discogs_id.isnot(None),
            Record.estimated_price_min.is_(None),
            Record.merged_into_id.is_(None),
        )
        .distinct()
    )


async def count_records_without_price(db: AsyncSession, user_id: UUID) -> int:
    subq = records_without_price_query(user_id).subquery()
    return int(await db.scalar(select(func.count()).select_from(subq)) or 0)


async def enqueue_price_job(db: AsyncSession, user_id: UUID) -> DiscogsPriceJob | None:
    """Ставит (или переиспользует) задачу дозагрузки цен.

    Возвращает None, если добирать нечего — тогда мобилке нечего показывать и
    прогресс-индикатор не появится.

    Не коммитит: вызывающий решает, в какую транзакцию это уходит.
    """
    total = await count_records_without_price(db, user_id)
    if total == 0:
        return None

    job = await db.scalar(
        select(DiscogsPriceJob).where(DiscogsPriceJob.user_id == user_id)
    )
    if job is None:
        job = DiscogsPriceJob(user_id=user_id)
        db.add(job)

    # Полный сброс, в том числе для уже завершённой задачи: повторный импорт —
    # это новая порция записей без цен, а не продолжение старой.
    job.status = STATUS_PENDING
    job.total = total
    job.processed = 0
    job.updated = 0
    job.error = None
    job.created_at = datetime.utcnow()
    job.started_at = None
    job.finished_at = None
    job.heartbeat_at = None

    try:
        await db.flush()
    except IntegrityError:
        # Гонка двух импортов одного юзера: unique(user_id) отработал, задача
        # уже есть и всё равно пройдёт по тем же записям. Молча уступаем.
        await db.rollback()
        logger.info("price job already enqueued for user %s", user_id)
        return None
    return job


async def get_price_job(db: AsyncSession, user_id: UUID) -> DiscogsPriceJob | None:
    return await db.scalar(
        select(DiscogsPriceJob).where(DiscogsPriceJob.user_id == user_id)
    )
