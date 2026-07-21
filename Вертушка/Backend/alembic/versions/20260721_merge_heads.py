"""merge heads: yandex_native + store_native_country

Две ветки миграций разошлись от общего предка и не были смёржены (разные фичи,
залитые параллельно): 20260719_yandex_native и 20260721_store_native_country.
Из-за этого `alembic upgrade head` падал с «Multiple head revisions are present»
и блокировал деплой. Эта ревизия — пустой merge: только сводит граф в одну
голову, схему не трогает. upgrade/downgrade намеренно no-op.

Revision ID: 20260721_merge_heads
Revises: 20260719_yandex_native, 20260721_store_native_country
"""
from alembic import op  # noqa: F401

revision = "20260721_merge_heads"
down_revision = ("20260719_yandex_native", "20260721_store_native_country")
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
