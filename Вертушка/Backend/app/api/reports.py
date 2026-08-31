"""
Reports API — жалобы на UGC (записи, пользователей, сообщения).

App Store Guideline 1.2: report objectionable content + takedown + бан.
Staff-действия минимальны (без UI-админки): hide_record / ban_user / dismiss.
См. docs/plans/appstore/UGC_MODERATION_M2.md.
"""
import logging
from datetime import datetime, timedelta
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.admin import require_staff
from app.api.auth import get_current_user
from app.database import get_db
from app.services import alerts, messages_ws_hub
from app.models.conversation import Conversation, Message
from app.models.record import Record
from app.models.report import Report
from app.models.user import User
from app.schemas.report import ReportActionRequest, ReportCreate, ReportResponse

logger = logging.getLogger(__name__)

router = APIRouter()

# Анти-спам: не больше N жалоб в час на пользователя.
REPORTS_PER_HOUR_LIMIT = 10

# Сколько символов объекта показывать staff'у. Достаточно, чтобы понять суть
# жалобы, и мало, чтобы не тащить простыню в Telegram.
_PREVIEW_MAX_CHARS = 200


async def _build_target_preview(db: AsyncSession, report: Report) -> str | None:
    """Человекочитаемое «на что жалуются» — для ленты staff и аларма."""
    if report.target_type == "record":
        record = await db.get(Record, report.target_id)
        if record is None:
            return None
        return f"{record.artist} — {record.title}"[:_PREVIEW_MAX_CHARS]

    if report.target_type == "user":
        user = await db.get(User, report.target_id)
        return f"@{user.username}"[:_PREVIEW_MAX_CHARS] if user else None

    if report.target_type == "message":
        message = await db.get(Message, report.target_id)
        if message is None:
            return None
        if message.deleted_at is not None:
            return "[сообщение уже удалено]"
        return (message.body or "[без текста]")[:_PREVIEW_MAX_CHARS]

    return None


async def _notify_message_removed(db: AsyncSession, message: Message) -> None:
    """Разослать обоим участникам событие удаления — как при обычном удалении.

    Без этого снятое модератором сообщение исчезнет только после перезахода
    в чат, и жалующийся продолжит видеть то, на что пожаловался.
    Ошибка доставки не должна валить тейкдаун: контент уже скрыт в БД.
    """
    try:
        conversation = await db.get(Conversation, message.conversation_id)
        if conversation is None:
            return

        event = {
            "type": "message.deleted",
            "conversation_id": str(message.conversation_id),
            "message_id": str(message.id),
        }
        for participant_id in (conversation.user_a_id, conversation.user_b_id):
            await messages_ws_hub.push_event(participant_id, event)
    except Exception:
        logger.warning("Не удалось разослать message.deleted после тейкдауна", exc_info=True)


async def _to_response(db: AsyncSession, report: Report) -> ReportResponse:
    response = ReportResponse.model_validate(report)
    return response.model_copy(
        update={"target_preview": await _build_target_preview(db, report)}
    )


async def _target_exists(db: AsyncSession, target_type: str, target_id: UUID) -> bool:
    model = {"record": Record, "user": User, "message": Message}[target_type]
    result = await db.execute(select(model.id).where(model.id == target_id).limit(1))
    return result.scalar_one_or_none() is not None


async def _resolve_target_user_id(
    db: AsyncSession, report: Report
) -> UUID | None:
    """Автор контента, на который жалуются (для ban_user)."""
    if report.target_type == "user":
        return report.target_id
    if report.target_type == "record":
        rec = await db.get(Record, report.target_id)
        return rec.created_by_user_id if rec else None
    if report.target_type == "message":
        msg = await db.get(Message, report.target_id)
        return msg.sender_id if msg else None
    return None


@router.post("/", response_model=ReportResponse, status_code=status.HTTP_201_CREATED)
async def create_report(
    data: ReportCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Создать жалобу. Rate-limit: ≤10 в час на пользователя."""
    window_start = datetime.utcnow() - timedelta(hours=1)
    recent_count = await db.scalar(
        select(func.count(Report.id)).where(
            Report.reporter_id == current_user.id,
            Report.created_at >= window_start,
        )
    ) or 0
    if recent_count >= REPORTS_PER_HOUR_LIMIT:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Слишком много жалоб за короткое время. Попробуй позже.",
        )

    if not await _target_exists(db, data.target_type, data.target_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Объект жалобы не найден",
        )

    report = Report(
        reporter_id=current_user.id,
        target_type=data.target_type,
        target_id=data.target_id,
        reason=data.reason,
    )
    db.add(report)
    await db.commit()
    await db.refresh(report)

    # Аларм в Telegram. В Условиях и на ревью в App Store мы обещаем реакцию
    # ≤24ч; полагаться на то, что владелец сам вспомнит открыть GET /reports,
    # — это обещание не выполнить. Ключ троттлинга общий для всех жалоб:
    # шторм репортов схлопнется в одно сообщение со счётчиком.
    preview = await _build_target_preview(db, report)
    alerts.fire_and_forget(
        key="ugc_report",
        title=f"Новая жалоба: {report.target_type}",
        body="\n".join(
            filter(
                None,
                [
                    f"id: {report.id}",
                    f"причина: {report.reason}" if report.reason else None,
                    f"объект: {preview}" if preview else None,
                    "Разобрать: GET /api/reports/?status=open",
                ],
            )
        ),
    )

    return await _to_response(db, report)


@router.get("/", response_model=list[ReportResponse])
async def list_reports(
    report_status: str = Query("open", alias="status"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    _staff: User = Depends(require_staff),
    db: AsyncSession = Depends(get_db),
):
    """Лента жалоб для staff (по умолчанию открытые, старые первыми)."""
    result = await db.execute(
        select(Report)
        .where(Report.status == report_status)
        .order_by(Report.created_at.asc())
        .limit(limit)
        .offset(offset)
    )
    return [await _to_response(db, r) for r in result.scalars().all()]


@router.post("/{report_id}/action", response_model=ReportResponse)
async def action_report(
    report_id: UUID,
    data: ReportActionRequest,
    _staff: User = Depends(require_staff),
    db: AsyncSession = Depends(get_db),
):
    """
    Staff-действие по жалобе:
    - hide_record — record.moderation_status='rejected' (исчезает из публичных мест);
    - ban_user — user.is_active=False (login и все запросы режутся гейтами auth);
    - dismiss — жалоба отклонена.
    """
    report = await db.get(Report, report_id)
    if not report:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Жалоба не найдена"
        )

    if data.action == "dismiss":
        report.status = "dismissed"

    elif data.action == "hide_record":
        if report.target_type != "record":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="hide_record применим только к жалобам на записи",
            )
        record = await db.get(Record, report.target_id)
        if not record:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Запись не найдена"
            )
        # Гейт скрытия в records.py срабатывает только для source='user'.
        # Для каталожной записи (Discogs/магазин) статус проставился бы, но
        # запись осталась видимой — staff считал бы жалобу закрытой, а контент
        # висел бы дальше. Лучше явный отказ, чем тихий no-op.
        if record.source != "user":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    "Скрыть можно только запись, добавленную пользователем. "
                    "Это каталожная запись — если проблема в ней, правь данные "
                    "или бань автора жалобной активности."
                ),
            )
        record.moderation_status = "rejected"
        report.status = "actioned"

    elif data.action == "hide_message":
        # Без этого действия оскорбительное сообщение оставалось видимым в
        # чате: забанить автора можно, а убрать сам текст — нечем.
        if report.target_type != "message":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="hide_message применим только к жалобам на сообщения",
            )
        message = await db.get(Message, report.target_id)
        if not message:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Сообщение не найдено"
            )
        # Тот же tombstone, что и при удалении «у всех» (messages.py): body в
        # NULL, deleted_at проставлен. Клиенты уже умеют его отображать.
        if message.deleted_at is None:
            message.body = None
            message.deleted_at = datetime.utcnow()
            await _notify_message_removed(db, message)
        report.status = "actioned"

    elif data.action == "ban_user":
        target_user_id = await _resolve_target_user_id(db, report)
        if target_user_id is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Не удалось определить пользователя по жалобе",
            )
        target_user = await db.get(User, target_user_id)
        if not target_user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Пользователь не найден"
            )
        target_user.is_active = False
        report.status = "actioned"

    await db.commit()
    await db.refresh(report)
    return await _to_response(db, report)
