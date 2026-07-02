"""Default-public profiles — server_default true + backfill missing rows.

Раньше `profile_shares.is_active` дефолтился в False, а сама строка создавалась
лениво (при первом открытии настроек). Поэтому ссылка на свежий аккаунт отдавала
404 «Профиль не активирован» — выглядело как баг. Новая политика: профиль публичен
по умолчанию, деактивация — только вручную в настройках.

Здесь: ставим server_default 'true' на колонку и доливаем строку с is_active=true
для всех пользователей, у кого ProfileShare ещё не было. Существующие строки
(включая осознанно выключенные) не трогаем.

Revision ID: 20260630_default_public_profile
Revises: 20260629_artist_names
"""
from alembic import op


revision = "20260630_default_public_profile"
down_revision = "20260629_artist_names"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE profile_shares ALTER COLUMN is_active SET DEFAULT true")
    op.execute(
        """
        INSERT INTO profile_shares (id, user_id, is_active)
        SELECT gen_random_uuid(), u.id, true
        FROM users u
        LEFT JOIN profile_shares ps ON ps.user_id = u.id
        WHERE ps.id IS NULL
        """
    )


def downgrade() -> None:
    op.execute("ALTER TABLE profile_shares ALTER COLUMN is_active SET DEFAULT false")
