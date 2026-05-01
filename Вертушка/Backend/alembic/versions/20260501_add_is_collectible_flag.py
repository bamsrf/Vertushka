"""Add is_collectible flag (combo: high price + scarce on market + low have)

Revision ID: 20260501_collectible
Revises: 20260429_canon_flag
Create Date: 2026-05-01
"""
from alembic import op
import sqlalchemy as sa


revision = "20260501_collectible"
down_revision = "20260429_canon_flag"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "records",
        sa.Column(
            "is_collectible",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )


def downgrade() -> None:
    op.drop_column("records", "is_collectible")
