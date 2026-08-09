"""wishlist_items.rejected_alt_record_ids — отклонённые аналоги

Радар: «Нет» на альт-версии запоминает конкретный прессинг, чтобы он больше
не предлагался. Другие (новые) аналоги того же мастера предлагаться продолжат.

Revision ID: 20260809_wl_reject_alt
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "20260809_wl_reject_alt"
down_revision = "20260807_achievement_xp_awarded"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "wishlist_items",
        sa.Column("rejected_alt_record_ids", JSONB(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("wishlist_items", "rejected_alt_record_ids")
