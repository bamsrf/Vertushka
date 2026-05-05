"""Add blocked_contacts table

Revision ID: 20260504_blocked_contacts
Revises: 20260504_gift_antifraud
Create Date: 2026-05-04
"""
from alembic import op
import sqlalchemy as sa


revision = "20260504_blocked_contacts"
down_revision = "20260504_gift_antifraud"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Полностью идемпотентная миграция через raw SQL: CREATE ... IF NOT EXISTS на каждом шаге.
    # Это нужно потому что предыдущие неудачные деплои оставили частичное состояние
    # (тип, в части случаев — таблицу), и стандартные op.create_* не справятся.

    # 1. Тип
    op.execute(
        """
        DO $$ BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'blocked_contact_kind') THEN
                CREATE TYPE blocked_contact_kind AS ENUM ('email', 'ip');
            END IF;
        END $$;
        """
    )

    # 2. Таблица
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS blocked_contacts (
            id UUID NOT NULL,
            kind blocked_contact_kind NOT NULL,
            value VARCHAR(255) NOT NULL,
            reason TEXT,
            blocked_at TIMESTAMP WITHOUT TIME ZONE DEFAULT now() NOT NULL,
            blocked_by_admin_id UUID,
            PRIMARY KEY (id),
            FOREIGN KEY (blocked_by_admin_id) REFERENCES users (id) ON DELETE SET NULL
        )
        """
    )

    # 3. Индексы
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_blocked_contacts_kind ON blocked_contacts (kind)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_blocked_contacts_value ON blocked_contacts (value)"
    )
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS ix_blocked_contacts_kind_value "
        "ON blocked_contacts (kind, value)"
    )


def downgrade() -> None:
    op.drop_index("ix_blocked_contacts_kind_value", table_name="blocked_contacts")
    op.drop_index("ix_blocked_contacts_value", table_name="blocked_contacts")
    op.drop_index("ix_blocked_contacts_kind", table_name="blocked_contacts")
    op.drop_table("blocked_contacts")
    sa.Enum(name="blocked_contact_kind").drop(op.get_bind(), checkfirst=True)
