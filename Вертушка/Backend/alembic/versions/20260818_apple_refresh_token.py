"""users.apple_refresh_token — хранение токена ради отзыва при удалении аккаунта

Apple требует: приложение с Sign in with Apple при удалении аккаунта обязано
отозвать выданные токены через /auth/revoke (Guideline 5.1.1(v), обязательно
с 30.06.2022). Отзывать можно только refresh_token, а получить его — только в
обмен на authorization_code, который клиент присылает один раз, в момент входа.
Значит токен нужно сохранить сразу, иначе к моменту удаления отзывать нечего.

Колонка nullable без бэкфилла: NULL = «токена нет» — верно и для всех, кто
вошёл паролем/Discogs, и для тех, кто вошёл через Apple до этой миграции.
Для последних отзыв произойдёт при следующем входе через Apple, когда прилетит
свежий authorization_code.

Значение шифруется Fernet на уровне приложения (app/services/secret_crypto.py),
поэтому Text, а не String фиксированной длины.

Revision ID: 20260818_apple_revoke
Revises: 20260818_always_value
Create Date: 2026-08-18
"""
from alembic import op
import sqlalchemy as sa

revision = "20260818_apple_revoke"
down_revision = "20260818_always_value"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("apple_refresh_token", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("users", "apple_refresh_token")
