"""discogs_dump_state — честный водяной знак дельта-догона дампа

`refresh_discogs_dump.sh` брал точку отсчёта для следующей дельты как
`SELECT max(discogs_id) FROM discogs_releases_index`. Но в тот же индекс пишет
живой путь (`upsert_release_into_index`): открытый в приложении свежий релиз
попадает туда сразу. То есть отметка означала не «докуда дошёл прошлый дамп», а
«самый новый релиз, который кто-то полистал», и одного любопытного юзера хватало,
чтобы следующая дельта отрезала всё до его находки.

Замер на проде 2026-08-14: майский дамп закончился на id 37 220 946, отметка на
1 августа стояла на 37 942 461 (живая строка от 31 июля), и в дыре между ними —
721 515 id — индекс содержал 298 строк вместо сотен тысяч. Boards of Canada
«Inferno» (37 472 124) лежит ровно там.

Таблица отвязывает отметку от содержимого индекса: её пишет только загрузчик
дампа, по максимальному id в самой CSV. Одна строка на прогон — история заодно
показывает, какой дамп что принёс.

Бэкфилл ставит майскую отметку (37 220 946): следующий прогон должен пройти по
дыре заново. Строки, что уже есть, отсеет `ON CONFLICT` — повторный проход
дешевле пропущенных релизов.

Revision ID: 20260814_dump_state
"""
import sqlalchemy as sa
from alembic import op

revision = "20260814_dump_state"
down_revision = "20260814_reset_jti"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "discogs_dump_state",
        sa.Column("dump_date", sa.Date(), primary_key=True),
        sa.Column("max_release_id", sa.BigInteger(), nullable=False),
        sa.Column("rows_inserted", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
    )
    # Отметка последнего ЧЕСТНОГО дампа. Не max() по индексу — он отравлен
    # живыми вставками, ровно от этого таблица и заводится.
    op.execute(
        "INSERT INTO discogs_dump_state (dump_date, max_release_id, rows_inserted) "
        "VALUES (DATE '2026-05-01', 37220946, 0) "
        "ON CONFLICT (dump_date) DO NOTHING"
    )


def downgrade() -> None:
    op.drop_table("discogs_dump_state")
