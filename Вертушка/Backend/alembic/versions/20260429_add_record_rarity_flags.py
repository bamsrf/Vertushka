"""Add rarity flags to records (is_first_press, is_limited, is_hot)

Revision ID: 20260429_rarity_flags
Revises: 20260427_value_snap
Create Date: 2026-04-29
"""
from alembic import op
import sqlalchemy as sa


revision = "20260429_rarity_flags"
down_revision = "20260427_value_snap"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "records",
        sa.Column(
            "is_first_press",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    op.add_column(
        "records",
        sa.Column(
            "is_limited",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    op.add_column(
        "records",
        sa.Column(
            "is_hot",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )


def downgrade() -> None:
    op.drop_column("records", "is_hot")
    op.drop_column("records", "is_limited")
    op.drop_column("records", "is_first_press")
