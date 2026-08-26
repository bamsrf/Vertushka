"""profile_shares.shared_at — факт отправки ссылки на профиль

Ачивка A4 «Распахнул» висела на событии profile_shared_enabled, а оно
эмитилось только при переходе тумблера is_active false → true. С тех пор
как профиль создаётся публичным (server_default="true"), перехода не
случается ни у кого — ачивка перестала выдаваться вовсе.

shared_at проставляется по осознанному действию: «Поделиться» или
«Копировать ссылку» на экране профиля (POST /api/profile/share). Это же
поле — серверная правда для шага чеклиста «Поделиться профилем», который
раньше жил только в AsyncStorage и слетал при переустановке.

Бэкфилл: тем, у кого A4 уже открыта (успели щёлкнуть тумблером до того,
как профиль стал публичным по умолчанию), ставим shared_at = момент
анлока — иначе шаг чеклиста откроется у них заново.

Revision ID: 20260825_profile_shared_at
Revises: 20260820_gift_verified_at
Create Date: 2026-08-25
"""
from alembic import op
import sqlalchemy as sa

revision = "20260825_profile_shared_at"
down_revision = "20260820_gift_verified_at"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "profile_shares",
        sa.Column("shared_at", sa.DateTime(), nullable=True),
    )
    op.execute(
        """
        UPDATE profile_shares ps
        SET shared_at = COALESCE(ua.unlocked_at, ps.created_at)
        FROM user_achievements ua
        WHERE ua.user_id = ps.user_id
          AND ua.code = 'A4_public_profile'
          AND ua.is_unlocked IS TRUE
          AND ps.shared_at IS NULL
        """
    )


def downgrade() -> None:
    op.drop_column("profile_shares", "shared_at")
