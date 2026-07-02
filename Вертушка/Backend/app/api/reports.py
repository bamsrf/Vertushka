"""
Reports API — жалобы на UGC (записи, пользователей, сообщения).

App Store Guideline 1.2: report objectionable content + takedown + бан.
Staff-действия минимальны (без UI-админки): hide_record / ban_user / dismiss.
См. docs/plans/UGC_MODERATION_M2.md.
"""
from datetime import datetime, timedelta
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.admin import require_staff
from app.api.auth import get_current_user
from app.database import get_db
from app.models.conversation import Message
from app.models.record import Record
from app.models.report import Report
from app.models.user import User
from app.schemas.report import ReportActionRequest, ReportCreate, ReportResponse

router = APIRouter()

# Анти-спам: не больше N жалоб в час на пользователя.
REPORTS_PER_HOUR_LIMIT = 10


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
    return ReportResponse.model_validate(report)


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
    return [ReportResponse.model_validate(r) for r in result.scalars().all()]


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
        record.moderation_status = "rejected"
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
    return ReportResponse.model_validate(report)
