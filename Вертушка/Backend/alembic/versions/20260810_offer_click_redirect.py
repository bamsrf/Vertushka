"""offer_clicks.redirected_at + is_bot — подтверждение перехода и отсечка ботов

Редиректор `/go/...` (см. docs/plans/CLICK_REDIRECTOR_AND_METRIKA.md):

* `redirected_at` — когда мы реально отдали 302. Разница с `created_at` даёт
  метрику потерь: клик записан, редирект не отдан = юзер отвалился между тапом
  и открытием браузера. Сейчас такие случаи невидимы.
* `is_bot` — краулер/превью мессенджера. Отдельной колонкой, а не «просто не
  писать redirected_at»: иначе бот неотличим от отвалившегося юзера и метрика
  потерь врёт.

Индекс на `redirected_at` не ставим: колонка нужна в агрегатах по периоду
(`WHERE created_at BETWEEN ... AND redirected_at IS NOT NULL`), где ведущим
всегда идёт уже проиндексированный `created_at`.

Revision ID: 20260810_click_redirect
"""
import sqlalchemy as sa
from alembic import op

revision = "20260810_click_redirect"
down_revision = "20260809_wl_reject_alt"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "offer_clicks",
        sa.Column("redirected_at", sa.DateTime(), nullable=True),
    )
    # server_default обязателен: таблица уже с данными, а колонка NOT NULL.
    # Старые клики (до редиректора) остаются false — они и не проходили /go/.
    op.add_column(
        "offer_clicks",
        sa.Column(
            "is_bot",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )


def downgrade() -> None:
    op.drop_column("offer_clicks", "is_bot")
    op.drop_column("offer_clicks", "redirected_at")
