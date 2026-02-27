"""Add password reset fields to users table

Revision ID: 20260227_reset
Revises: 20260225_add_estimated_price_rub
Create Date: 2026-02-27
"""
from alembic import op
import sqlalchemy as sa


revision = "20260227_reset"
down_revision = None  # Will be auto-detected
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("reset_code_hash", sa.String(255), nullable=True))
    op.add_column("users", sa.Column("reset_code_expires_at", sa.DateTime, nullable=True))
    op.add_column("users", sa.Column("reset_code_attempts", sa.Integer, nullable=False, server_default="0"))


def downgrade() -> None:
    op.drop_column("users", "reset_code_attempts")
    op.drop_column("users", "reset_code_expires_at")
    op.drop_column("users", "reset_code_hash")
