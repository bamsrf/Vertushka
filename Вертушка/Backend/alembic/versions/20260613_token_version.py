"""Add users.token_version for session revocation

Revision ID: 20260613_token_version
Revises: 20260602_discogs_login
Create Date: 2026-06-13

token_version кладётся в JWT (claim "tv") и сверяется в get_current_user/refresh.
Инкремент (смена пароля, logout-all) мгновенно инвалидирует все ранее выданные
access/refresh токены. Идемпотентна.
"""
from alembic import op
import sqlalchemy as sa


revision = "20260613_token_version"
down_revision = "20260602_discogs_login"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    cols = {c["name"] for c in insp.get_columns("users")}
    if "token_version" not in cols:
        op.add_column(
            "users",
            sa.Column(
                "token_version",
                sa.Integer(),
                nullable=False,
                server_default="0",
            ),
        )


def downgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    cols = {c["name"] for c in insp.get_columns("users")}
    if "token_version" in cols:
        op.drop_column("users", "token_version")
