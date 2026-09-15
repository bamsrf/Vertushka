"""discogs_master_covers: очередь зеркалирования (mirrored_at + mirror_attempts)

Мастер-обложка закрывает в среднем 3.1 релиза (877 548 мастеров адресуют
2.7 млн позиций), а её источники на 98% бесплатные — CAA и Deezer. При этом
на 15.09.2026 в бакете лежало 28 970 мастеров из 877 548 известных, то есть
3.3%: адреса мы собрали, а за файлами не сходили.

Колонки — состояние очереди фонового зеркалирования:
  mirrored_at     — попытка ЗАВЕРШЕНА (успех либо исчерпанные попытки);
  mirror_attempts — сколько раз пробовали и не вышло.

Две, а не одна: ровно потому, что дрип обложек 14.09 встал на сутки из-за
одной строки, которую он не мог ни скачать, ни пометить. Счётчик попыток в
самой таблице (а не в Redis) переживает рестарты и делает очередь
самоочищающейся: predicate `mirrored_at IS NULL AND mirror_attempts < N`
не может залипнуть.

Индекс частичный — по нему ходит только выборка кандидатов, а это сотые доли
процента таблицы к концу прогона.

Revision ID: 20260915_master_mirror
Revises: 20260907_push_platform
Create Date: 2026-09-15
"""
from alembic import op
import sqlalchemy as sa

revision = "20260915_master_mirror"
down_revision = "20260907_push_platform"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "discogs_master_covers",
        sa.Column("mirrored_at", sa.DateTime(), nullable=True),
    )
    op.add_column(
        "discogs_master_covers",
        sa.Column(
            "mirror_attempts",
            sa.SmallInteger(),
            nullable=False,
            server_default="0",
        ),
    )
    # Кандидаты: есть URL, ещё не завершены. Партиал держит индекс маленьким
    # (полный по 877 тыс. строк не нужен: обслуженные из него выпадают).
    op.create_index(
        "ix_master_covers_mirror_queue",
        "discogs_master_covers",
        ["master_id"],
        unique=False,
        postgresql_where=sa.text(
            "cover_image_url IS NOT NULL AND mirrored_at IS NULL"
        ),
    )


def downgrade() -> None:
    op.drop_index("ix_master_covers_mirror_queue", table_name="discogs_master_covers")
    op.drop_column("discogs_master_covers", "mirror_attempts")
    op.drop_column("discogs_master_covers", "mirrored_at")
