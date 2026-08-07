"""user_achievements.xp_awarded — опыт замораживается в момент анлока

Опыт за ачивку считался на лету из её тира. Пока тир — ручной ярлык, это
работало; как только он начнёт считаться от фактической редкости, любой
пересчёт задним числом переписывал бы историю: ачивка «подешевела» — и юзер
утром обнаруживает себя разжалованным.

Поэтому XP фиксируется в строке анлока и больше не меняется. Суммарный опыт
становится суммой замороженных чисел: он монотонен по построению, отдельная
защёлка «не понижать уровень» не нужна.

Бэкфилл: существующим открытым ачивкам проставляем текущий вес их тира —
на момент миграции он и есть тот, по которому им начисляли. NULL остаётся
только у незакрытых строк (там начислять нечего).

Revision ID: 20260807_achievement_xp_awarded
Revises: 20260806_release_formats
"""
import sqlalchemy as sa
from alembic import op

revision = "20260807_achievement_xp_awarded"
down_revision = "20260806_release_formats"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "user_achievements",
        sa.Column("xp_awarded", sa.Integer(), nullable=True),
    )

    # Бэкфилл по текущим весам тиров. Реестр — единственное место, где живёт
    # соответствие code → tier, поэтому импортируем его, а не хардкодим список.
    from app.services.achievements.levels import weight_for_code
    from app.services.achievements.registry import all_definitions

    conn = op.get_bind()
    by_weight: dict[int, list[str]] = {}
    for defn in all_definitions():
        by_weight.setdefault(weight_for_code(defn.code), []).append(defn.code)

    for weight, codes in by_weight.items():
        if not weight:
            continue
        conn.execute(
            sa.text(
                "UPDATE user_achievements SET xp_awarded = :w "
                "WHERE is_unlocked IS TRUE AND xp_awarded IS NULL AND code = ANY(:codes)"
            ),
            {"w": weight, "codes": codes},
        )

    # Динамические коды вида 'H2:king-crimson' в реестре отсутствуют — их
    # префикс до двоеточия совпадает с кодом определения.
    for weight, codes in by_weight.items():
        if not weight:
            continue
        conn.execute(
            sa.text(
                "UPDATE user_achievements SET xp_awarded = :w "
                "WHERE is_unlocked IS TRUE AND xp_awarded IS NULL "
                "AND split_part(code, ':', 1) = ANY(:codes)"
            ),
            {"w": weight, "codes": codes},
        )


def downgrade() -> None:
    op.drop_column("user_achievements", "xp_awarded")
