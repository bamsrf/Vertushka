"""Add records.blurhash

Revision ID: 20260804_records_blurhash
Revises: 20260723_collectible_idx
Create Date: 2026-08-04

Компактный (~30 символов) blurhash обложки для мгновенного blur-плейсхолдера на
клиенте, пока грузится full-res. Считается при зеркалировании
(cover_storage._encode_and_place), заполняется вперёд + разовым бэкфиллом по
локальным файлам (app/scripts/backfill_blurhash.py).

DEFAULT-less nullable колонка — metadata-only, мгновенно. Идемпотентна.
"""
from alembic import op
import sqlalchemy as sa

revision = "20260804_records_blurhash"
down_revision = "20260723_collectible_idx"
branch_labels = None
depends_on = None


def _has_column(conn, column: str) -> bool:
    return bool(conn.execute(sa.text(
        "SELECT EXISTS (SELECT 1 FROM information_schema.columns "
        "WHERE table_schema = 'public' AND table_name = 'records' "
        "AND column_name = :col)"
    ), {"col": column}).scalar())


def upgrade() -> None:
    conn = op.get_bind()
    if not _has_column(conn, "blurhash"):
        op.add_column(
            "records",
            sa.Column("blurhash", sa.String(64), nullable=True),
        )


def downgrade() -> None:
    op.execute("ALTER TABLE records DROP COLUMN IF EXISTS blurhash")
