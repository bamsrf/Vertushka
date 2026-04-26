"""Add collection_value_snapshots table and gift_bookings.cancellation_reason

Revision ID: 20260427_value_snap
Revises: 20260417_user_photos
Create Date: 2026-04-27
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID


revision = "20260427_value_snap"
down_revision = "20260417_user_photos"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "collection_value_snapshots",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("snapshot_date", sa.Date, nullable=False),
        sa.Column("total_value_rub", sa.Numeric(14, 2), nullable=False, server_default="0"),
        sa.Column("items_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("user_id", "snapshot_date", name="uq_value_snapshot_user_date"),
    )
    op.create_index(
        "ix_value_snapshot_user_date",
        "collection_value_snapshots",
        ["user_id", "snapshot_date"],
    )
    op.create_index(
        "ix_collection_value_snapshots_user_id",
        "collection_value_snapshots",
        ["user_id"],
    )

    op.add_column(
        "gift_bookings",
        sa.Column("cancellation_reason", sa.String(50), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("gift_bookings", "cancellation_reason")
    op.drop_index("ix_collection_value_snapshots_user_id", table_name="collection_value_snapshots")
    op.drop_index("ix_value_snapshot_user_date", table_name="collection_value_snapshots")
    op.drop_table("collection_value_snapshots")
