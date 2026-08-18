"""profile_shares.show_collection_value — всегда true, тумблер убран из UI

Настройка была лишним шагом: чтобы профиль стал полезным, юзеру приходилось
включать его, а потом отдельно вспоминать про стоимость коллекции. По умолчанию
она стояла false, поэтому у большинства опубликованных профилей hero-карточка
была пустой — ради приватности, которую никто не просил (сам профиль и так
включается осознанно).

Теперь стоимость показывается всегда, а решение «публиковать профиль или нет»
остаётся единственным. Колонку не удаляем: она в трёх схемах и её читают старые
сборки мобилки — сносить синхронно с релизом нельзя. Вместо этого бэкфиллим в
true и меняем server_default, чтобы новые профили рождались с тем же значением.

Revision ID: 20260818_always_value
Revises: 20260818_apple_revoke
Create Date: 2026-08-18
"""
from alembic import op
import sqlalchemy as sa

revision = "20260818_always_value"
down_revision = "20260818_apple_revoke"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "UPDATE profile_shares SET show_collection_value = true "
        "WHERE show_collection_value = false"
    )
    op.alter_column(
        "profile_shares",
        "show_collection_value",
        server_default=sa.text("true"),
        existing_type=sa.Boolean(),
        existing_nullable=False,
    )


def downgrade() -> None:
    # Обратно в false не откатываем: кто был true до миграции, тот и остаётся —
    # различить их уже нечем. Возвращаем только дефолт для новых строк.
    op.alter_column(
        "profile_shares",
        "show_collection_value",
        server_default=sa.text("false"),
        existing_type=sa.Boolean(),
        existing_nullable=False,
    )
