"""offer_clicks.source — откуда внутри UI пришёл переход

`surface` отвечает на «с какой платформы» (mobile / web), и смешивать с ним
«из какого места интерфейса» нельзя: через полгода отчёт «сколько переходов
из Маркета» стал бы неоднозначным. Поэтому отдельная колонка.

Значения (валидируются на уровне API, а не CHECK-констрейнтом — список будет
расти вместе с UI, и ловить это миграцией на каждый новый экран накладно):
    record          — блок офферов на карточке пластинки
    market          — витрина Маркета
    market_store    — страница конкретного магазина
    wishlist_swipe  — свайп-ценник в коллекции/вишлисте
    wishlist_digest — поп-ап «Где купить» из дайджеста
    web_profile     — публичная веб-страница профиля
    unknown         — старые сборки, которые source ещё не присылают

`unknown` как server_default обязателен: таблица уже с данными, а колонка
NOT NULL. Старые клики честно остаются `unknown` — задним числом место в UI
у них не восстановить.

Revision ID: 20260810_click_source
"""
import sqlalchemy as sa
from alembic import op

revision = "20260810_click_source"
down_revision = "20260810_click_redirect"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "offer_clicks",
        sa.Column(
            "source",
            sa.String(length=24),
            nullable=False,
            server_default="unknown",
        ),
    )
    # Отчёты для магазина всегда режутся по периоду И по источнику
    # («сколько переходов из Маркета за месяц»), поэтому композитный индекс
    # с created_at ведущим — он же покрывает сортировку по времени.
    op.create_index(
        "ix_offer_clicks_created_source",
        "offer_clicks",
        ["created_at", "source"],
    )


def downgrade() -> None:
    op.drop_index("ix_offer_clicks_created_source", table_name="offer_clicks")
    op.drop_column("offer_clicks", "source")
