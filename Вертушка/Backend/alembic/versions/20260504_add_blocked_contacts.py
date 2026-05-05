"""Add blocked_contacts table

Revision ID: 20260504_blocked_contacts
Revises: 20260504_gift_antifraud
Create Date: 2026-05-04
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID


revision = "20260504_blocked_contacts"
down_revision = "20260504_gift_antifraud"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # create_type=False — enum-тип создаём руками ниже с checkfirst,
    # иначе create_table повторно вызовет CREATE TYPE без checkfirst и упадёт
    # при повторном применении миграции на БД, где тип уже остался от предыдущего запуска.
    blocked_kind = sa.Enum("email", "ip", name="blocked_contact_kind", create_type=False)
    sa.Enum("email", "ip", name="blocked_contact_kind").create(op.get_bind(), checkfirst=True)

    op.create_table(
        "blocked_contacts",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("kind", blocked_kind, nullable=False),
        sa.Column("value", sa.String(length=255), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column(
            "blocked_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "blocked_by_admin_id",
            UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_index("ix_blocked_contacts_kind", "blocked_contacts", ["kind"])
    op.create_index("ix_blocked_contacts_value", "blocked_contacts", ["value"])
    op.create_index(
        "ix_blocked_contacts_kind_value",
        "blocked_contacts",
        ["kind", "value"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("ix_blocked_contacts_kind_value", table_name="blocked_contacts")
    op.drop_index("ix_blocked_contacts_value", table_name="blocked_contacts")
    op.drop_index("ix_blocked_contacts_kind", table_name="blocked_contacts")
    op.drop_table("blocked_contacts")
    sa.Enum(name="blocked_contact_kind").drop(op.get_bind(), checkfirst=True)
