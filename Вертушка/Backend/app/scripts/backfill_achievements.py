"""Бэкфилл ачивок для существующих пользователей.

Идёт по всем активным юзерам и эмитирует релевантные события один раз каждое:
- collection_item_added — если есть хоть один CollectionItem;
- wishlist_item_added — если есть хоть один WishlistItem;
- avatar_set — если стоит avatar_url;
- profile_shared_enabled — если ProfileShare.shared_at заполнен;
- gift_booked — если есть GiftBooking с booked_by_user_id=user.id;
- daily_tick — для всех, чтобы покрыть B-серию (≥24h записи) и R_thirty_three.

Идемпотентен: повторный запуск ничего не сломает (evaluator skip-ает уже
открытые ачивки).

Запуск:
  cd ~/vertushka/Backend && python -m app.scripts.backfill_achievements
  cd ~/vertushka/Backend && python -m app.scripts.backfill_achievements --dry-run
  cd ~/vertushka/Backend && python -m app.scripts.backfill_achievements --user-id=<uuid>
"""
import argparse
import asyncio
import logging
from uuid import UUID

from sqlalchemy import select, exists
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import async_session_maker, engine
from app.models.collection import Collection, CollectionItem
from app.models.gift_booking import GiftBooking, GiftStatus
from app.models.profile_share import ProfileShare
from app.models.user import User
from app.models.user_achievement import UserAchievement
from app.models.wishlist import Wishlist, WishlistItem
from app.services.achievements import emit_event
from app.services.achievements.events import (
    AVATAR_SET,
    COLLECTION_ITEM_ADDED,
    DAILY_TICK,
    FOLLOW_CREATED,
    FOLLOW_RECEIVED,
    GIFT_BOOKED,
    GIFT_COMPLETED,
    PROFILE_SHARED_ENABLED,
    PROFILE_VIEW,
    WISHLIST_ITEM_ADDED,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("backfill")


async def _user_events(db: AsyncSession, user: User) -> list[tuple[str, dict]]:
    """Какие события эмитировать для этого юзера на основе его текущего состояния."""
    events: list[tuple[str, dict]] = []

    has_collection_item = await db.scalar(
        select(
            exists().where(
                CollectionItem.collection_id == Collection.id,
                Collection.user_id == user.id,
            )
        )
    )
    if has_collection_item:
        events.append((COLLECTION_ITEM_ADDED, {}))

    has_wishlist_item = await db.scalar(
        select(
            exists().where(
                WishlistItem.wishlist_id == Wishlist.id,
                Wishlist.user_id == user.id,
            )
        )
    )
    if has_wishlist_item:
        events.append((WISHLIST_ITEM_ADDED, {}))

    if user.avatar_url:
        events.append((AVATAR_SET, {}))

    share = await db.scalar(
        select(ProfileShare).where(ProfileShare.user_id == user.id)
    )
    if share:
        # Не is_active: публичность включена у всех по умолчанию, и по ней
        # A4 досталась бы каждому даром. Считается только факт отправки
        # ссылки — shared_at.
        if share.shared_at:
            events.append((PROFILE_SHARED_ENABLED, {}))
        # K5/K6 (просмотры) — обновляем прогресс через PROFILE_VIEW
        if share.view_count > 0:
            events.append((PROFILE_VIEW, {"backfill_view_count": share.view_count}))

    has_gift = await db.scalar(
        select(
            exists().where(
                GiftBooking.booked_by_user_id == user.id,
                GiftBooking.status.in_(
                    [GiftStatus.PENDING, GiftStatus.BOOKED, GiftStatus.COMPLETED]
                ),
            )
        )
    )
    if has_gift:
        events.append((GIFT_BOOKED, {}))

    # Завершённые подарки (как даритель) → J2 + сезонные (по completed_at).
    # J3/J4/J7 и GIFT_RECEIVED НЕ догоняем: историч. COMPLETED имеют
    # recipient_user_id IS NULL (миграция бэкфилит только активные брони),
    # поэтому distinct-получатели = 0. Anti-farm стартует с нуля — by design.
    has_completed_gift = await db.scalar(
        select(
            exists().where(
                GiftBooking.booked_by_user_id == user.id,
                GiftBooking.status == GiftStatus.COMPLETED,
            )
        )
    )
    if has_completed_gift:
        events.append((GIFT_COMPLETED, {}))

    # Follow-события — следим только за фактом, остальное соберёт evaluator
    from app.models.follow import Follow
    has_following = await db.scalar(
        select(exists().where(Follow.follower_id == user.id))
    )
    if has_following:
        events.append((FOLLOW_CREATED, {}))
    has_followers = await db.scalar(
        select(exists().where(Follow.following_id == user.id))
    )
    if has_followers:
        events.append((FOLLOW_RECEIVED, {}))

    # daily_tick — всегда, на нём считаются B-серии и R_thirty_three
    events.append((DAILY_TICK, {}))

    return events


async def backfill_user(user: User, *, dry_run: bool) -> dict[str, list[str]]:
    """Бэкфилл одного юзера. Возвращает карту event → коды свежеоткрытых."""
    summary: dict[str, list[str]] = {}
    async with async_session_maker() as db:
        events = await _user_events(db, user)
        if dry_run:
            summary["__dry_run_events__"] = [ev for ev, _ in events]
            return summary
        for event, payload in events:
            unlocked = await emit_event(db, user.id, event, payload)
            if unlocked:
                summary[event] = unlocked
    return summary


async def backfill_all(*, dry_run: bool, only_user_id: UUID | None = None) -> None:
    async with async_session_maker() as db:
        q = select(User).where(User.is_active.is_(True))
        if only_user_id is not None:
            q = q.where(User.id == only_user_id)
        result = await db.execute(q)
        users = result.scalars().all()

    logger.info("Backfill start: %d users, dry_run=%s", len(users), dry_run)

    total_unlocked = 0
    for idx, user in enumerate(users, 1):
        try:
            summary = await backfill_user(user, dry_run=dry_run)
        except Exception:  # noqa: BLE001
            logger.exception("backfill_user_failed: user_id=%s", user.id)
            continue

        unlocked_count = sum(
            len(codes) for key, codes in summary.items() if not key.startswith("__")
        )
        total_unlocked += unlocked_count
        if summary:
            logger.info(
                "[%d/%d] user=%s (%s): %s",
                idx, len(users), user.username, user.id,
                summary,
            )
        if idx % 50 == 0:
            logger.info("Progress: %d/%d users", idx, len(users))

    logger.info(
        "Backfill done: %d users, %d total achievements unlocked, dry_run=%s",
        len(users), total_unlocked, dry_run,
    )


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Backfill achievements for existing users")
    parser.add_argument("--dry-run", action="store_true", help="Не писать в БД")
    parser.add_argument("--user-id", type=str, default=None, help="Бэкфилл одного юзера")
    return parser.parse_args()


async def _amain() -> None:
    args = _parse_args()
    user_uuid = UUID(args.user_id) if args.user_id else None
    try:
        await backfill_all(dry_run=args.dry_run, only_user_id=user_uuid)
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(_amain())
