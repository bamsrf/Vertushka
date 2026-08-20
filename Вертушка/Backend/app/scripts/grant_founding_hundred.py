"""Выдача пина «Первая сотня» (OG1) бета-аккаунтам из допуска.

Ничего не проставляет руками: для каждого юзера из FOUNDER_ALLOWLIST эмитится
обычное COLLECTION_ITEM_ADDED — evaluator сам проверит зачёт и ранг, ядро само
создаст нотификацию и пуш. Идемпотентен: открытые ачивки повторно не выдаются,
повторный запуск безопасен.

Новым юзерам после отсечки FOUNDERS_CUTOFF скрипт не нужен — им пин выдаст
живое событие добавления первой пластинки (или ближайший daily_tick).

Запуск (на проде, внутри backend-контейнера):
  python -m app.scripts.grant_founding_hundred
  python -m app.scripts.grant_founding_hundred --dry-run
"""
import argparse
import asyncio
import logging

from sqlalchemy import func, select

from app.database import async_session_maker, engine
from app.models.user import User
from app.models.user_achievement import UserAchievement
from app.services.achievements import emit_event
from app.services.achievements.events import COLLECTION_ITEM_ADDED
from app.services.achievements.definitions.series.origins import (
    FOUNDER_ALLOWLIST,
    OG1_CODE,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("grant_founding_hundred")


async def grant(dry_run: bool) -> None:
    async with async_session_maker() as db:
        rows = await db.execute(
            select(User).where(func.lower(User.username).in_(sorted(FOUNDER_ALLOWLIST)))
        )
        users = rows.scalars().all()

    found_names = {u.username.lower() for u in users}
    for name in sorted(FOUNDER_ALLOWLIST - found_names):
        logger.warning("Юзер '%s' из допуска НЕ найден в БД — проверь написание", name)

    for user in users:
        if dry_run:
            logger.info("[dry-run] эмитил бы collection_item_added для %s (%s)",
                        user.username, user.id)
            continue
        async with async_session_maker() as db:
            unlocked = await emit_event(db, user.id, COLLECTION_ITEM_ADDED, {})
            has_pin = await db.scalar(
                select(UserAchievement.is_unlocked).where(
                    UserAchievement.user_id == user.id,
                    UserAchievement.code == OG1_CODE,
                )
            )
        status = "✅ пин есть" if has_pin else "❌ пина НЕТ (нет пластинок или вне зачёта)"
        logger.info("%s: %s; открыто этим прогоном: %s",
                    user.username, status, unlocked or "—")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Выдать пин «Первая сотня» бета-аккаунтам")
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
