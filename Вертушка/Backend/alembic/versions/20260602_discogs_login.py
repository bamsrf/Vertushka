"""Make users.email nullable for Discogs-only accounts

Revision ID: 20260602_discogs_login
Revises: 20260601_merge_heads
Create Date: 2026-06-02

Логин через Discogs создаёт аккаунт без email (Discogs identity отдаёт только
username). Снимаем NOT NULL с users.email. Уникальность сохраняется — в Postgres
несколько NULL в UNIQUE-индексе разрешены, так что discogs-юзеры с email=NULL
не конфликтуют.

Идемпотентна.
"""
from alembic import op
import sqlalchemy as sa


revision = "20260602_discogs_login"
down_revision = "20260601_merge_heads"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column("users", "email", existing_type=sa.String(255), nullable=True)


def downgrade() -> None:
    # Откат опасен если есть аккаунты с email=NULL — он упадёт. Это намеренно:
    # downgrade требует ручной чистки таких юзеров.
    op.alter_column("users", "email", existing_type=sa.String(255), nullable=False)
