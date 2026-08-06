"""discogs_release_formats — полные описания формата из дампа

`discogs_releases_index.format_type` несёт только ПЕРВОЕ описание первого
формата (`ingest_discogs_dump._derive_format`): у релиза с
`['Sampler','Promo','Compilation']` в базе оказывается `CD, Sampler`, а у
`['12"','33 ⅓ RPM','EP']` — `Vinyl, 12"`, из-за чего EP числится синглом.
Классификатор `services/release_type.py` работает по этой строке, и на 1.06M
строк без типового маркера ему остаётся гадать — отсюда мешанина в фильтре
«Альбомы» на экране артиста.

Почему отдельная таблица, а не колонка в `discogs_releases_index`: UPDATE 13.1M
строк переписал бы весь heap (2.95 ГБ) и до VACUUM удвоил бы его, а на проде
свободно 4.3 ГБ. COPY в новую таблицу растёт линейно и обрывается без вреда для
существующих данных.

Хранятся только релизы с ≥2 описаниями (~60% дампа): при 0–1 описании
`format_type` уже полон, дубль не нужен.

Revision ID: 20260806_release_formats
Revises: 20260804_records_blurhash
"""
import sqlalchemy as sa
from alembic import op

revision = "20260806_release_formats"
down_revision = "20260804_records_blurhash"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "CREATE TABLE IF NOT EXISTS discogs_release_formats ("
        "  discogs_id  BIGINT PRIMARY KEY, "
        "  format_full TEXT NOT NULL, "
        "  dump_version DATE NOT NULL"
        ")"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS discogs_release_formats")
