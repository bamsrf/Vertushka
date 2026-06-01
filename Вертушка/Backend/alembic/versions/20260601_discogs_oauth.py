"""Add Discogs OAuth per-user token fields to users

Revision ID: 20260601_discogs_oauth
Revises: 20260528_store_stats_mv
Create Date: 2026-06-01
"""
import sqlalchemy as sa
from alembic import op


revision = "20260601_discogs_oauth"
down_revision = "20260528_store_stats_mv"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("discogs_username", sa.String(length=100), nullable=True))
    op.add_column("users", sa.Column("discogs_oauth_token", sa.String(length=255), nullable=True))
    op.add_column("users", sa.Column("discogs_oauth_token_secret", sa.Text(), nullable=True))
    op.add_column(
        "users",
        sa.Column("discogs_connected_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("users", "discogs_connected_at")
    op.drop_column("users", "discogs_oauth_token_secret")
    op.drop_column("users", "discogs_oauth_token")
    op.drop_column("users", "discogs_username")
