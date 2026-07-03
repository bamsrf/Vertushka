"""Add discogs_releases_index.is_unofficial (бутлеги)

Revision ID: 20260703_unofficial
Revises: 20260703_artist_map
Create Date: 2026-07-03

Локальная дискография артиста без этого флага тонет в бутлегах (у Pink Floyd
топ-2025 — сплошные unofficial live-записи): live-путь исключал их через
role=Main у Discogs API, дамп же несёт officiality только в format
descriptions ("Unofficial Release"). Флаг пишет load_artist_map.py из CSV
extract_discogs_artist_map.py; get_artist_masters_local фильтрует.

DEFAULT false на 13M строк — metadata-only (PG11+), мгновенно. Идемпотентна.
"""
from alembic import op
import sqlalchemy as sa

revision = "20260703_unofficial"
down_revision = "20260703_artist_map"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    exists = conn.execute(sa.text(
        "SELECT EXISTS (SELECT 1 FROM information_schema.columns "
        "WHERE table_schema = 'public' AND table_name = 'discogs_releases_index' "
        "AND column_name = 'is_unofficial')"
    )).scalar()
    if not exists:
        op.add_column(
            "discogs_releases_index",
            sa.Column("is_unofficial", sa.Boolean, nullable=False, server_default=sa.text("false")),
        )


def downgrade() -> None:
    op.execute("ALTER TABLE discogs_releases_index DROP COLUMN IF EXISTS is_unofficial")
