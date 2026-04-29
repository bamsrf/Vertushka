"""Add is_canon flag (Discogs editor-picked main_release) to records

Revision ID: 20260429_canon_flag
Revises: 20260429_rarity_flags
Create Date: 2026-04-29
"""
from alembic import op
import sqlalchemy as sa


revision = "20260429_canon_flag"
down_revision = "20260429_rarity_flags"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "records",
        sa.Column(
            "is_canon",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    # Bootstrap: every record currently flagged as is_first_press is by definition
    # also is_canon (old strict-less first_press semantics == new canon semantics).
    op.execute("UPDATE records SET is_canon = TRUE WHERE is_first_press = TRUE")


def downgrade() -> None:
    op.drop_column("records", "is_canon")
