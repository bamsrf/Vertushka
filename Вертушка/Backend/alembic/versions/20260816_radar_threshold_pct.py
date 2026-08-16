"""wishlist_items.threshold_pct — режим порога «дешевле обычного»

Абсолютный порог протухает. Пользователь ставит «дешевле 5 000 ₽», рынок за год
уезжает вверх, и радар молчит навсегда: число осталось, а реальность ушла.
Пересмотреть порог вручную никто не приходит — пластинка просто тихо выпадает
из работы, занимая один из пяти слотов.

Относительный режим считает порог от скользящей базы (медиана дневных минимумов
за 90 дней — та же величина, что рисует график в шторке цены) на каждой
проверке. threshold_pct = 20 читается как «на 20% дешевле обычного».

Колонка nullable без бэкфилла: NULL = «порог абсолютный, смотри
price_threshold_rub», ровно то, что верно для всех существующих строк. Старое
поле не трогаем и не удаляем — режимы сосуществуют, переключение туда-обратно
не должно терять ранее введённую сумму.

Revision ID: 20260816_radar_pct
Revises: 20260814_dump_state
Create Date: 2026-08-16
"""
from alembic import op
import sqlalchemy as sa

revision = "20260816_radar_pct"
down_revision = "20260814_dump_state"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "wishlist_items",
        sa.Column("threshold_pct", sa.Integer(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("wishlist_items", "threshold_pct")
