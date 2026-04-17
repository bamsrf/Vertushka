"""Add notification fields to users table

Revision ID: 20260320_notif
Revises: 20260320_soft_delete
Create Date: 2026-03-20
"""
from alembic import op
import sqlalchemy as sa


revision = "20260320_notif"
down_revision = "20260320_soft_delete"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("push_token", sa.String(255), nullable=True))
    op.add_column("users", sa.Column("notify_new_follower", sa.Boolean, nullable=False, server_default="true"))
    op.add_column("users", sa.Column("notify_gift_booked", sa.Boolean, nullable=False, server_default="true"))
    op.add_column("users", sa.Column("notify_app_updates", sa.Boolean, nullable=False, server_default="true"))


def downgrade() -> None:
    op.drop_column("users", "notify_app_updates")
    op.drop_column("users", "notify_gift_booked")
    op.drop_column("users", "notify_new_follower")
    op.drop_column("users", "push_token")
