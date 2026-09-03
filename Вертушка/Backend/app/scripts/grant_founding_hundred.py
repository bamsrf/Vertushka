"""Выдача пина «Первая сотня» (OG1) — догон для уже зарегистрированных.

Ничего не проставляет руками: каждому кандидату эмитится обычное
USER_REGISTERED — evaluator сам проверит зачёт, ранг и предохранитель, ядро
само создаст нотификацию и пуш. Идемпотентен: открытые ачивки повторно не
выдаются, повторный запуск безопасен.

Нужен один раз после смены правила «первая пластинка» → «регистрация»:
аккаунты, созданные ДО деплоя, события USER_REGISTERED не получали. Новым
юзерам скрипт не нужен — им пин выдаёт сама регистрация.

Кандидаты: allowlist + все, кто зарегистрировался с FOUNDERS_CUTOFF.
Порядок обхода — по created_at, чтобы ранние занимали слоты первыми.

Запуск (на проде, внутри scheduler-контейнера):
  python -m app.scripts.grant_founding_hundred
  python -m app.scripts.grant_founding_hundred --dry-run
"""
import argparse
import asyncio
import logging

from sqlalchemy import func, or_, select

from app.database import async_session_maker, engine
from app.models.user import User
from app.models.user_achievement import UserAchievement
from app.services.achievements import emit_event
from app.services.achievements.events import USER_REGISTERED
from app.services.achievements.definitions.series.origins import (
    FOUNDER_ALLOWLIST,
    FOUNDERS_CUTOFF,
    OG1_CODE,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("grant_founding_hundred")


async def grant(dry_run: bool) -> None:
    async with async_session_maker() as db:
        rows = await db.execute(
            select(User)
            .where(
                User.is_active.is_(True),
                or_(
                    func.lower(User.username).in_(sorted(FOUNDER_ALLOWLIST)),
                    User.created_at >= FOUNDERS_CUTOFF,
                ),
            )
            .order_by(User.created_at, User.id)
        )
        users = rows.scalars().all()

    found_names = {u.username.lower() for u in users}
    for name in sorted(FOUNDER_ALLOWLIST - found_names):
        logger.warning("Юзер '%s' из допуска НЕ найден среди активных", name)

    logger.info("Кандидатов: %d", len(users))
    granted = skipped = 0

    for user in users:
        if dry_run:
            logger.info("[dry-run] эмитил бы user_registered для %s (%s)",
                        user.username, user.created_at)
            continue
        # Каждый юзер — в своей сессии: ошибка одного не валит остальных.
        async with async_session_maker() as db:
            await emit_event(db, user.id, USER_REGISTERED, {})
            has_pin = await db.scalar(
                select(UserAchievement.is_unlocked).where(
                    UserAchievement.user_id == user.id,
                    UserAchievement.code == OG1_CODE,
                )
            )
        if has_pin:
            granted += 1
        else:
            skipped += 1
            logger.info("%s: пина нет (вне сотни или вне зачёта)", user.username)

    logger.info("Итог: с пином %d, без пина %d, всего кандидатов %d",
                granted, skipped, len(users))


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Догон пина «Первая сотня» для зарегистрированных")
    parser.add_argument("--dry-run", action="store_true", help="Не писать в БД")
    return parser.parse_args()


async def _amain() -> None:
    args = _parse_args()
    try:
        await grant(dry_run=args.dry_run)
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(_amain())
