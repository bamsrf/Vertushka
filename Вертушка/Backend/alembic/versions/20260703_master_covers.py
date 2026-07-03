"""Add discogs_master_covers — обложки мастеров, добытые live-путями

Revision ID: 20260703_master_covers
Revises: 20260703_unofficial
Create Date: 2026-07-03

Сетка артиста (local-first) берёт обложку из cover_image_url строк индекса,
но покрытие индекса ограничено (CAA-маппинг ~6% релизов + drip). При этом
экран мастера тянет live get_master, у которого обложка есть почти всегда —
она просто нигде не сохранялась для сетки.

Эта таблица замыкает петлю: открыл мастер → обложка персистится → сетка
артиста показывает её всем и навсегда. Отдельная таблица, а НЕ заливка всех
строк группы в индексе: обложка мастера ≠ обложка конкретного издания,
экран версий не должен получать фейковые обложки прессов.

Идемпотентна.
"""
from alembic import op
import sqlalchemy as sa

revision = "20260703_master_covers"
down_revision = "20260703_unofficial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    exists = conn.execute(sa.text(
        "SELECT EXISTS (SELECT 1 FROM information_schema.tables "
        "WHERE table_schema = 'public' AND table_name = 'discogs_master_covers')"
    )).scalar()
    if not exists:
        op.create_table(
            "discogs_master_covers",
            sa.Column("master_id", sa.BigInteger, primary_key=True),
            sa.Column("cover_image_url", sa.Text, nullable=False),
            sa.Column(
                "updated_at", sa.DateTime,
                nullable=False, server_default=sa.text("now()"),
            ),
        )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS discogs_master_covers")
