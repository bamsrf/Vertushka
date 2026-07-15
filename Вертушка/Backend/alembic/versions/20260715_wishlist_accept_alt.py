"""wishlist_items.accept_alt — юзер принял альт-прессинг как подходящий

Радар: тап «Да, следить» на альтернативной версии помечает accept_alt=true.
Тогда наличие другого прессинга того же мастера считается как «в продаже».

Revision ID: 20260715_wl_accept_alt
Revises: 20260714_wl_conditions
"""
import sqlalchemy as sa
from alembic import op

revision = "20260715_wl_accept_alt"
down_revision = "20260714_wl_conditions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "wishlist_items",
        sa.Column("accept_alt", sa.Boolean(), nullable=False, server_default="false"),
    )


def downgrade() -> None:
    op.drop_column("wishlist_items", "accept_alt")
