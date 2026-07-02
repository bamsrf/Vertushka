"""Reports — жалобы на UGC (App Store Guideline 1.2).

Таблица reports: жалоба юзера на record / user / message.
Индекс (status, created_at) — лента открытых жалоб для staff.
См. docs/plans/UGC_MODERATION_M2.md.

Revision ID: 20260702_reports
Revises: 20260630_default_public_profile
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "20260702_reports"
down_revision = "20260630_default_public_profile"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "reports",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "reporter_id",
            UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("target_type", sa.String(16), nullable=False),
        sa.Column("target_id", UUID(as_uuid=True), nullable=False),
        sa.Column("reason", sa.String(500), nullable=True),
        sa.Column("status", sa.String(16), nullable=False, server_default="open"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_reports_reporter_id", "reports", ["reporter_id"])
    op.create_index("ix_reports_status_created_at", "reports", ["status", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_reports_status_created_at", table_name="reports")
    op.drop_index("ix_reports_reporter_id", table_name="reports")
    op.drop_table("reports")
