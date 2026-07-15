"""radar_status_events — хронология смен статуса пластинки на радаре

Revision ID: 20260715_radar_events
Revises: 20260715_wl_accept_alt
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "20260715_radar_events"
down_revision = "20260715_wl_accept_alt"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "radar_status_events",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "wishlist_item_id",
            UUID(as_uuid=True),
            sa.ForeignKey("wishlist_items.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "record_id",
            UUID(as_uuid=True),
            sa.ForeignKey("records.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("price_rub", sa.Numeric(12, 2), nullable=True),
        sa.Column("store_name", sa.String(120), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_radar_status_events_wishlist_item_id", "radar_status_events", ["wishlist_item_id"])
    op.create_index("ix_radar_events_item_ts", "radar_status_events", ["wishlist_item_id", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_radar_events_item_ts", table_name="radar_status_events")
    op.drop_index("ix_radar_status_events_wishlist_item_id", table_name="radar_status_events")
    op.drop_table("radar_status_events")
