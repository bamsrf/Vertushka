"""
Скрипт для окончательного удаления аккаунтов, помеченных на удаление.
Запуск через cron раз в сутки:
  cd ~/vertushka && python -m app.scripts.purge_deleted_users
"""
import asyncio
import logging
from datetime import datetime

from sqlalchemy import select, delete

from app.database import async_session_maker, engine
from app.models.user import User

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


async def purge():
    async with async_session_maker() as session:
        result = await session.execute(
            select(User).where(
                User.deleted_at.isnot(None),
                User.scheduled_purge_at <= datetime.utcnow(),
            )
        )
        users = result.scalars().all()

        if not users:
            logger.info("No accounts to purge.")
            return

        for user in users:
            logger.info(
                "Purging user %s (%s), deleted_at=%s",
                user.username, user.id, user.deleted_at,
            )
            await session.delete(user)  # cascade delete-orphan удалит связанные данные

        await session.commit()
        logger.info("Purged %d account(s).", len(users))


async def main():
    try:
        await purge()
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
