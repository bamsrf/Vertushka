"""users.reset_token_jti — одноразовый токен сброса пароля

`POST /auth/verify-reset-code/` выдаёт JWT с `type: "reset"` и TTL 10 минут,
`POST /auth/reset-password/` его принимает. Токен не помечался использованным,
поэтому оставался рабочим весь свой срок и после того, как пароль уже сменили:
утёкший экземпляр (скриншот, лог прокси, история шаринга) позволял поменять
пароль ещё раз в пределах окна. Смена пароля инкрементирует `token_version`, но
это убивает access/refresh, а на сам reset-токен не влияет — в нём нет `tv`.

Теперь в токен кладётся `jti`, его копия пишется сюда, и `reset-password`
принимает только совпадающий. После успешного сброса поле зануляется, второй
раз тот же токен не проходит. Запрос нового кода через `forgot-password` тоже
зануляет поле — то есть свежий код обесценивает ранее выданный токен.

Колонка nullable без бэкфилла: NULL = «действующего reset-токена нет», ровно
то, что верно для всех существующих строк. Индекс не нужен — поле читается
только по уже найденному по id юзеру, а не ищется по значению.

Revision ID: 20260814_reset_jti
"""
import sqlalchemy as sa
from alembic import op

revision = "20260814_reset_jti"
down_revision = "20260813_cover_tier"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("reset_token_jti", sa.String(length=64), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("users", "reset_token_jti")
