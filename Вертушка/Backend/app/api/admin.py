"""
Admin API — модерация user-submitted records (source='user').

Доступ только для users.is_staff. Лента pending-записей + approve/reject.
См. docs/plans/USER_SUBMITTED_RECORDS.md §6.
"""
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_current_user
from app.database import get_db
from app.models.record import Record
from app.models.user import User
from app.schemas.record import RecordResponse

router = APIRouter()


async def require_staff(current_user: User = Depends(get_current_user)) -> User:
    """Dependency: пускает только staff. Иначе 403."""
    if not current_user.is_staff:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Доступ только для модераторов",
        )
    return current_user


@router.get("/records/pending/", response_model=list[RecordResponse])
async def list_pending_records(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    _staff: User = Depends(require_staff),
    db: AsyncSession = Depends(get_db),
):
    """Лента user-записей на модерацию (moderation_status='pending')."""
    res = await db.execute(
        select(Record)
        .where(Record.source == "user", Record.moderation_status == "pending")
        .order_by(Record.created_at.asc())
        .limit(limit)
        .offset(offset)
    )
    records = res.scalars().all()
    return [RecordResponse.model_validate(r) for r in records]


async def _get_pending_user_record(record_id: UUID, db: AsyncSession) -> Record:
    res = await db.execute(select(Record).where(Record.id == record_id))
    rec = res.scalar_one_or_none()
    if rec is None or rec.source != "user":
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User-запись не найдена",
        )
    return rec


@router.post("/records/{record_id}/approve", response_model=RecordResponse)
async def approve_record(
    record_id: UUID,
    _staff: User = Depends(require_staff),
    db: AsyncSession = Depends(get_db),
):
    """Аппрув: запись становится общей (попадает в Маркет/ленту)."""
    rec = await _get_pending_user_record(record_id, db)
    rec.moderation_status = "approved"
    await db.commit()
    await db.refresh(rec)
    return RecordResponse.model_validate(rec)


@router.post("/records/{record_id}/reject", response_model=RecordResponse)
async def reject_record(
    record_id: UUID,
    _staff: User = Depends(require_staff),
    db: AsyncSession = Depends(get_db),
):
    """Отклонение: запись остаётся приватной у создателя, в общий пул не идёт."""
    rec = await _get_pending_user_record(record_id, db)
    rec.moderation_status = "rejected"
    await db.commit()
    await db.refresh(rec)
    return RecordResponse.model_validate(rec)
