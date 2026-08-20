"""Бэкфилл улик «за какую музыку» для уже открытых ачивок.

У ачивок, выданных до появления evidence, ach_metadata пуст (или несёт только
рабочее состояние evaluator-а). Восстанавливаем улику по текущей БД — честная
оговорка: это «по состоянию коллекции на сегодня», а не снапшот момента анлока
(его уже не восстановить). Подарочные восстанавливаются точно — история
GiftBooking в БД.

Идемпотентен: строки, где evidence уже есть, не трогаем.

Запуск (на проде, внутри scheduler-контейнера):
  python -m app.scripts.backfill_achievement_evidence
  python -m app.scripts.backfill_achievement_evidence --dry-run
"""
import argparse
import asyncio
import logging

from sqlalchemy import select

from app.database import async_session_maker, engine
from app.models.user_achievement import UserAchievement
from app.services.achievements.evidence import evidence_text, get_evidence_builder

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("backfill_evidence")


async def backfill(dry_run: bool) -> None:
    async with async_session_maker() as db:
        rows = await db.execute(
            select(UserAchievement).where(UserAchievement.is_unlocked.is_(True))
        )
        candidates = [
            ua
            for ua in rows.scalars().all()
            if get_evidence_builder(ua.code) is not None
            and not (isinstance(ua.ach_metadata, dict) and ua.ach_metadata.get("evidence"))
        ]

    logger.info("Кандидатов без улики: %d", len(candidates))
    filled = 0
    empty = 0

    for ua in candidates:
        builder = get_evidence_builder(ua.code)
        try:
            # Каждая строка — в своей сессии: ошибка одной не валит остальных.
            async with async_session_maker() as db:
                evidence = await builder(db, ua.user_id, {})
                if not evidence:
                    empty += 1
                    continue
                fresh = await db.scalar(
                    select(UserAchievement).where(UserAchievement.id == ua.id)
                )
                if fresh is None:
                    continue
                merged = dict(fresh.ach_metadata or {})
                merged["evidence"] = evidence
                if dry_run:
                    logger.info(
                        "[dry-run] %s / user %s → %s",
                        ua.code, ua.user_id, evidence_text(merged),
                    )
                else:
                    fresh.ach_metadata = merged
                    await db.commit()
                filled += 1
        except Exception:  # noqa: BLE001
            logger.exception("Улика не собралась: %s / user %s", ua.code, ua.user_id)

    logger.info(
        "Готово: улик %s %d, пусто (нет данных) %d, всего кандидатов %d",
        "собралось бы" if dry_run else "записано", filled, empty, len(candidates),
    )


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Backfill evidence для открытых ачивок")
    parser.add_argument("--dry-run", action="store_true", help="Показать без записи")
    return parser.parse_args()


async def _amain() -> None:
    args = _parse_args()
    try:
        await backfill(dry_run=args.dry_run)
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(_amain())
