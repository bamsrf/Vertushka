"""CLI: одноразовый бэкфилл данных в исторических achievement_unlocked нотификациях.

Зачем:
  До enrich'а (см. evaluator.py) нотификация ачивки хранила только {"code": ...}.
  Mobile теперь рисует мини-пин по data.icon_slug и реальный тайтл по data.title.
  Старые строки этих полей не имеют → fallback на трофей + сырой код.

  Скрипт проходит по type='achievement_unlocked', берёт code из data.code или
  entity_id, тянет AchievementDefinition из registry и доливает icon_slug + title.
  Идемпотентно: строки, где icon_slug уже есть, пропускаются.

Использование:
  python -m app.scripts.backfill_achievement_notifications            # dry-run, печатает план
  python -m app.scripts.backfill_achievement_notifications --apply    # реально пишет
  python -m app.scripts.backfill_achievement_notifications --apply --limit=500
"""
from __future__ import annotations

import argparse
import asyncio
import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import async_session_maker, close_db
from app.models.notification import Notification
from app.services.achievements.registry import get_definition

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger("backfill_ach_notifs")


async def _run(db: AsyncSession, *, apply: bool, limit: int) -> None:
    rows = (
        await db.execute(
            select(Notification)
            .where(Notification.type == "achievement_unlocked")
            .order_by(Notification.created_at.desc())
            .limit(limit)
        )
    ).scalars().all()

    scanned = len(rows)
    updated = 0
    skipped_has_slug = 0
    skipped_no_def = 0

    for n in rows:
        data = dict(n.data or {})
        if data.get("icon_slug"):
            skipped_has_slug += 1
            continue

        code = data.get("code") or n.entity_id
        defn = get_definition(code) if code else None
        if defn is None:
            skipped_no_def += 1
            logger.info("  skip (no defn): id=%s code=%s", n.id, code)
            continue

        data["icon_slug"] = defn.icon_slug or ""
        if not data.get("title"):
            data["title"] = defn.title_ru
        n.data = data  # реассайн — иначе SQLAlchemy не заметит мутацию JSON
        updated += 1
        logger.info("  set id=%s code=%s slug=%s title=%s", n.id, code, defn.icon_slug, defn.title_ru)

    logger.info(
        "scanned=%d updated=%d skipped_has_slug=%d skipped_no_def=%d apply=%s",
        scanned, updated, skipped_has_slug, skipped_no_def, apply,
    )

    if apply and updated:
        await db.commit()
        logger.info("committed %d updates", updated)
    elif updated:
        logger.info("dry-run — ничего не записано. Повтори с --apply")


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="реально записать (без флага — dry-run)")
    parser.add_argument("--limit", type=int, default=1000, help="максимум строк за прогон")
    args = parser.parse_args()

    try:
        async with async_session_maker() as db:
            await _run(db, apply=args.apply, limit=args.limit)
    finally:
        await close_db()


if __name__ == "__main__":
    asyncio.run(main())
