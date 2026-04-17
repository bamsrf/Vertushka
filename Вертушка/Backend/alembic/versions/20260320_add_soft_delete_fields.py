"""Add soft delete fields to users table

Revision ID: 20260320_soft_delete
Revises: 20260227_reset
Create Date: 2026-03-20
"""
from alembic import op
import sqlalchemy as sa


revision = "20260320_soft_delete"
down_revision = "20260227_reset"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("deleted_at", sa.DateTime, nullable=True))
    op.add_column("users", sa.Column("scheduled_purge_at", sa.DateTime, nullable=True))


def downgrade() -> None:
    op.drop_column("users", "scheduled_purge_at")
    op.drop_column("users", "deleted_at")
