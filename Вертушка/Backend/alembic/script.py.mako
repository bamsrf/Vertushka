"""${message}

Revision ID: ${up_revision}
Revises: ${down_revision | comma,n}
Create Date: ${create_date}

БЕЗОПАСНАЯ МИГРАЦИЯ (миграции идут, пока старый контейнер держит трафик):

1. Индекс на большой таблице — только CONCURRENTLY, иначе запись в неё встанет
   на всё время построения:
       op.execute("COMMIT")  # CONCURRENTLY нельзя внутри транзакции
       op.execute("CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_... ON ...")
2. ADD COLUMN — только nullable или с константным DEFAULT (PG11+ не переписывает
   таблицу). Volatile-дефолт (now(), gen_random_uuid()) перепишет её целиком.
3. DROP / RENAME колонки и таблицы — НЕ в одном релизе с кодом: старый
   контейнер работает со старой схемой до переключения цвета и упадёт. Сначала
   выкатываем код, который не трогает поле, следующим релизом — удаляем.
4. Бэкфилл данных — не здесь, а отдельным скриптом в app/scripts/: миграция с
   UPDATE на миллионах строк держит блокировку и валит деплой по lock_timeout.
5. Проверь размер таблицы перед ALTER: discogs_releases_index ~13M строк / 6 ГБ,
   discogs_release_formats ~8.6M, mb_mbid_rg ~5.7M.

Ожидание блокировки ограничено lock_timeout = 5s (alembic/env.py). Миграция
упадёт, а не подвесит прод; для планового окна: ALEMBIC_LOCK_TIMEOUT=30s.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
${imports if imports else ""}

# revision identifiers, used by Alembic.
revision: str = ${repr(up_revision)}
down_revision: Union[str, None] = ${repr(down_revision)}
branch_labels: Union[str, Sequence[str], None] = ${repr(branch_labels)}
depends_on: Union[str, Sequence[str], None] = ${repr(depends_on)}


def upgrade() -> None:
    ${upgrades if upgrades else "pass"}


def downgrade() -> None:
    ${downgrades if downgrades else "pass"}

