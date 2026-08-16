"""discogs_price_jobs — очередь дозагрузки цен после импорта коллекции

Импорт из Discogs кладёт записи без цен: в списке коллекции API отдаёт только
`basic_information`, а marketplace-статистика доступна лишь поштучно, по
запросу на релиз. Локальный дамп тут не помогает — в `discogs_releases_index`
ценовых колонок нет и быть не может, месячный XML-дамп Discogs содержит только
каталожные метаданные.

До сих пор цены после импорта добирал единственный ночной `update_prices_batch`
пачкой в 50 записей на всю базу — коллекция в 400 пластинок заполнялась бы
неделями. Задача в БД позволяет гнать дозагрузку под OAuth-токеном самого
юзера: у него персональный бакет rate-limiter'а (60 req/min), то есть те же 400
пластинок закрываются минут за семь и не отъедают общий лимит приложения.

Строка в таблице, а не BackgroundTasks: API-контейнер перезапускается на каждом
деплое и незавершённая корутина умерла бы молча, без следов и без шанса
доехать. Плюс мобилке нужен прогресс для поллинга.

Revision ID: 20260816_price_jobs
Revises: 20260816_radar_pct
Create Date: 2026-08-16
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "20260816_price_jobs"
down_revision = "20260816_radar_pct"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "discogs_price_jobs",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        # unique: одна задача на юзера. Повторный импорт переиспользует строку,
        # сбрасывая счётчики — история прогонов не нужна, а без ограничения
        # нетерпеливый юзер настрогал бы десяток параллельных задач на один
        # и тот же rate-limit бакет.
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column("status", sa.String(16), nullable=False, server_default="pending"),
        sa.Column("total", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("processed", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("updated", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
        sa.Column("heartbeat_at", sa.DateTime(), nullable=True),
    )
    # Воркер отбирает работу по (status, created_at): pending в порядке очереди
    # плюс running с протухшим heartbeat.
    op.create_index(
        "ix_price_job_status", "discogs_price_jobs", ["status", "created_at"]
    )


def downgrade() -> None:
    op.drop_index("ix_price_job_status", table_name="discogs_price_jobs")
    op.drop_table("discogs_price_jobs")
