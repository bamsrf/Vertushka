"""Auto-approve existing user-records (§6: moderation cancelled).

Модерация user-submitted records отменена — все source='user' теперь approved
по умолчанию (см. docs/plans/collection/USER_SUBMITTED_RECORDS.md §6 revised). Старые
записи, висевшие в 'pending', делаем видимыми.

Revision ID: 20260617_approve_user_records
Revises: 20260613_user_records
"""
from alembic import op

revision = "20260617_approve_user_records"
down_revision = "20260613_user_records"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "UPDATE records SET moderation_status = 'approved' "
        "WHERE source = 'user' AND moderation_status = 'pending'"
    )


def downgrade() -> None:
    # Необратимо по смыслу (не знаем, какие были pending). No-op.
    pass
