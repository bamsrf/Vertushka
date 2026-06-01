"""Merge 5 divergent alembic heads into one

Revision ID: 20260601_merge_heads
Revises: 20260516_wishlist_folders, 20260516_offer_clicks, 20260528_msg_media, 20260517_attached_record, 20260601_discogs_oauth
Create Date: 2026-06-01

Граф миграций разветвился на 5 веток (фичи мая + discogs_oauth). `alembic
upgrade head` падал с "multiple heads". Эта миграция — пустой merge-узел:
схему не меняет, только сводит ветки в единый head, чтобы деплой
(deploy.sh → alembic upgrade head) снова работал.
"""

revision = "20260601_merge_heads"
down_revision = (
    "20260516_wishlist_folders",
    "20260516_offer_clicks",
    "20260528_msg_media",
    "20260517_attached_record",
    "20260601_discogs_oauth",
)
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
