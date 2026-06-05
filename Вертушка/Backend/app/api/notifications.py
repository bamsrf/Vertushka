"""
API персональных уведомлений и социальной ленты.
"""
import logging
from datetime import datetime, timedelta
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select, func, update, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.auth import get_current_user
from app.database import get_db
from app.models.notification import Notification
from app.models.user import User
from app.schemas.notification import (
    MarkReadBatchRequest,
    MarkReadResponse,
    NotificationActor,
    NotificationListResponse,
    NotificationResponse,
    SnoozeRequest,
    SnoozeResponse,
    SocialFeedItem,
    SocialFeedResponse,
    UnreadCountResponse,
)
from app.services.feed import get_social_feed
from app.services.notification_service import apply_snooze_on_read

logger = logging.getLogger(__name__)

router = APIRouter()

# Типы, у которых протухший unread болтается в ленте без смысла (магазинные алерты —
# через месяц уже неактуальны). Волна A: скрываем их из выдачи и unread-счётчика.
# Волна B заменит это полноценным snooze ladder через `snoozed_until`.
_STALE_TYPES = ("wishlist_in_stock", "wishlist_price_drop")
_STALE_AFTER = timedelta(days=30)


def _hide_stale_clause():
    """Скрыть из ленты `_STALE_TYPES` старше `_STALE_AFTER`."""
    cutoff = datetime.utcnow() - _STALE_AFTER
    return or_(
        Notification.type.notin_(_STALE_TYPES),
        Notification.created_at >= cutoff,
    )


def _serialize(n: Notification) -> NotificationResponse:
    actor: NotificationActor | None = None
    if n.actor is not None:
        actor = NotificationActor(
            id=n.actor.id,
            username=n.actor.username,
            display_name=n.actor.display_name,
            avatar_url=n.actor.avatar_url,
        )
    return NotificationResponse(
        id=n.id,
        type=n.type,
        dedup_key=n.dedup_key,
        entity_type=n.entity_type,
        entity_id=n.entity_id,
        data=n.data or {},
        created_at=n.created_at,
        bumped_at=n.bumped_at or n.created_at,
        occurrences=n.occurrences or 1,
        snoozed_until=n.snoozed_until,
        read_at=n.read_at,
        actor=actor,
    )


@router.get("/", response_model=NotificationListResponse)
async def list_personal(
    cursor: str | None = Query(None, description="ISO timestamp последнего полученного item"),
    limit: int = Query(20, ge=1, le=50),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Личная лента уведомлений (вкладка «Ты»).

    Сортируется по `bumped_at` (а не created_at), чтобы свежие повторы
    (occurrences>1) поднимались наверх. Cursor — тоже по bumped_at.
    """
    q = (
        select(Notification)
        .where(Notification.user_id == current_user.id)
        .where(_hide_stale_clause())
        .options(selectinload(Notification.actor))
        .order_by(Notification.bumped_at.desc())
        .limit(limit)
    )
    if cursor:
        try:
            cutoff = datetime.fromisoformat(cursor)
            q = q.where(Notification.bumped_at < cutoff)
        except ValueError:
            pass

    rows = (await db.execute(q)).scalars().all()
    unread = await db.scalar(
        select(func.count(Notification.id)).where(
            Notification.user_id == current_user.id,
            Notification.read_at.is_(None),
            _hide_stale_clause(),
        )
    )

    next_cursor = rows[-1].bumped_at.isoformat() if len(rows) == limit else None

    return NotificationListResponse(
        items=[_serialize(n) for n in rows],
        unread_count=int(unread or 0),
        next_cursor=next_cursor,
    )


@router.get("/unread-count", response_model=UnreadCountResponse)
async def unread_count(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Сколько непрочитанных personal-уведомлений."""
    cnt = await db.scalar(
        select(func.count(Notification.id)).where(
            Notification.user_id == current_user.id,
            Notification.read_at.is_(None),
            _hide_stale_clause(),
        )
    )
    return UnreadCountResponse(unread_count=int(cnt or 0))


@router.post("/read-all", response_model=MarkReadResponse)
async def mark_all_read(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Отметить все personal-уведомления прочитанными."""
    await db.execute(
        update(Notification)
        .where(
            Notification.user_id == current_user.id,
            Notification.read_at.is_(None),
            _hide_stale_clause(),
        )
        .values(read_at=datetime.utcnow())
    )
    await db.commit()
    return MarkReadResponse(unread_count=0)


@router.post("/read", response_model=MarkReadResponse)
async def mark_read_batch(
    body: MarkReadBatchRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Батч «seen = read»: отметить прочитанными список видимых уведомлений.

    Клиент шлёт id'шники строк, попавших в видимую область экрана (viewability).
    Для wishlist-семейства применяем snooze ladder, как в одиночном пути.
    """
    rows = (
        await db.execute(
            select(Notification).where(
                Notification.id.in_(body.ids),
                Notification.user_id == current_user.id,
                Notification.read_at.is_(None),
            )
        )
    ).scalars().all()
    now = datetime.utcnow()
    for n in rows:
        n.read_at = now
        apply_snooze_on_read(n)
    if rows:
        await db.commit()
    cnt = await db.scalar(
        select(func.count(Notification.id)).where(
            Notification.user_id == current_user.id,
            Notification.read_at.is_(None),
            _hide_stale_clause(),
        )
    )
    return MarkReadResponse(unread_count=int(cnt or 0))


@router.post("/{notification_id}/read", response_model=MarkReadResponse)
async def mark_read(
    notification_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Отметить одно уведомление прочитанным.

    Для wishlist-семейства типов запускает snooze ladder
    (7д → 30д → 90д) — следующий алерт по тому же dedup_key до этой даты не создаётся.
    """
    n = await db.scalar(
        select(Notification).where(
            Notification.id == notification_id,
            Notification.user_id == current_user.id,
        )
    )
    if not n:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Notification not found")
    if n.read_at is None:
        n.read_at = datetime.utcnow()
        apply_snooze_on_read(n)
        await db.commit()
    cnt = await db.scalar(
        select(func.count(Notification.id)).where(
            Notification.user_id == current_user.id,
            Notification.read_at.is_(None),
            _hide_stale_clause(),
        )
    )
    return MarkReadResponse(unread_count=int(cnt or 0))


@router.post("/{notification_id}/snooze", response_model=SnoozeResponse)
async def snooze_notification(
    notification_id: UUID,
    body: SnoozeRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Отложить повторы по dedup_key этой записи на N дней.

    Используется long-press menu «Не напоминать про эту пластинку 30 дней».
    Помечает запись прочитанной (если ещё не) и выставляет snoozed_until.
    """
    n = await db.scalar(
        select(Notification).where(
            Notification.id == notification_id,
            Notification.user_id == current_user.id,
        )
    )
    if not n:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Notification not found")
    now = datetime.utcnow()
    if n.read_at is None:
        n.read_at = now
    n.snoozed_until = now + timedelta(days=body.days)
    await db.commit()
    return SnoozeResponse(snoozed_until=n.snoozed_until)


@router.delete("/{notification_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_notification(
    notification_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Удалить одно уведомление."""
    n = await db.scalar(
        select(Notification).where(
            Notification.id == notification_id,
            Notification.user_id == current_user.id,
        )
    )
    if not n:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Notification not found")
    await db.delete(n)
    await db.commit()


@router.get("/social", response_model=SocialFeedResponse)
async def social_feed(
    cursor: str | None = Query(None, description="ISO timestamp последнего полученного item"),
    limit: int = Query(20, ge=1, le=50),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Лента подписок (вкладка «Подписки»). Генерируется on-the-fly, без записи в БД."""
    raw_items, next_cursor = await get_social_feed(
        db,
        user_id=current_user.id,
        limit=limit,
        cursor_iso=cursor,
    )
    return SocialFeedResponse(
        items=[SocialFeedItem(**it) for it in raw_items],
        next_cursor=next_cursor,
    )
