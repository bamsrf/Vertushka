"""add estimated_price_rub to collection_items

Revision ID: a1b2c3d4e5f6
Revises:
Create Date: 2026-02-25
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'collection_items',
        sa.Column('estimated_price_rub', sa.Numeric(10, 2), nullable=True)
    )


def downgrade() -> None:
    op.drop_column('collection_items', 'estimated_price_rub')
