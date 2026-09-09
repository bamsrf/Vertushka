"""
Социальная лента подписок: события друзей, на которых я подписан.

Возвращает SocialFeedItem с типами:
- collection_add        — друг добавил пластинку в коллекцию
- wishlist_add          — друг добавил пластинку в вишлист
- gift_completed        — друг получил подарок (gift_booking → completed)
- friend_achievement    — друг разблокировал ачивку
- friend_new_following  — друг подписался на нового пользователя
"""
from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.collection import Collection, CollectionItem
from app.models.follow import Follow
from app.models.gift_booking import GiftBooking, GiftStatus
from app.models.user import User
from app.models.user_achievement import UserAchievement
from app.models.wishlist import Wishlist, WishlistItem


def _actor_payload(user: User) -> dict[str, Any]:
    return {
        "id": str(user.id),
        "username": user.username,
        "display_name": user.display_name,
        "avatar_url": user.avatar_url,
    }


def _record_payload(record) -> dict[str, Any] | None:
    if record is None:
        return None
    return {
        "id": str(record.id),
        "title": record.title,
        "artist": getattr(record, "artist", None),
        "cover_url": getattr(record, "cover_image_url", None),
    }


async def get_social_feed(
    db: AsyncSession,
    *,
    user_id: UUID,
    limit: int = 20,
    cursor_iso: str | None = None,
) -> tuple[list[dict[str, Any]], str | None]:
    """Собрать ленту подписок. Cursor — ISO-метка `created_at` последнего item'а."""
    following_ids_rows = await db.execute(
        select(Follow.following_id).where(Follow.follower_id == user_id)
    )
    following_ids = [r[0] for r in following_ids_rows.all()]
    if not following_ids:
        return [], None

    cutoff: datetime | None = None
    if cursor_iso:
        try:
            cutoff = datetime.fromisoformat(cursor_iso)
        except ValueError:
            cutoff = None

    items: list[tuple[datetime, dict[str, Any]]] = []
    per_source_limit = max(limit, 20)

    # --- collection_add ---
    q = (
        select(CollectionItem)
        .join(Collection)
        .where(Collection.user_id.in_(following_ids))
        .options(
            selectinload(CollectionItem.record),
            selectinload(CollectionItem.collection).selectinload(Collection.user),
        )
        .order_by(CollectionItem.added_at.desc())
        .limit(per_source_limit)
    )
    if cutoff is not None:
        q = q.where(CollectionItem.added_at < cutoff)
    for ci in (await db.execute(q)).scalars().all():
        items.append((ci.added_at, {
            "type": "collection_add",
            "actor": _actor_payload(ci.collection.user),
            "created_at": ci.added_at.isoformat(),
            "record": _record_payload(ci.record),
            "target_user": None,
            "payload": {"collection_id": str(ci.collection.id), "collection_name": ci.collection.name},
        }))

    # --- wishlist_add ---
    q = (
        select(WishlistItem)
        .join(Wishlist)
        .where(Wishlist.user_id.in_(following_ids))
        .options(
            selectinload(WishlistItem.record),
            selectinload(WishlistItem.wishlist).selectinload(Wishlist.user),
        )
        .order_by(WishlistItem.added_at.desc())
        .limit(per_source_limit)
    )
    if cutoff is not None:
        q = q.where(WishlistItem.added_at < cutoff)
    for wi in (await db.execute(q)).scalars().all():
        items.append((wi.added_at, {
            "type": "wishlist_add",
            "actor": _actor_payload(wi.wishlist.user),
            "created_at": wi.added_at.isoformat(),
            "record": _record_payload(wi.record),
            "target_user": None,
            "payload": {},
        }))

    # --- gift_completed: друг подарил пластинку другому ---
    # Время события — completed_at. Колонки updated_at у GiftBooking нет и
    # никогда не было: обращение к ней роняло весь эндпоинт на AttributeError
    # при сборке запроса, то есть у КАЖДОГО, у кого есть хоть одна подписка
    # (без подписок функция выходит раньше — потому четыре месяца и не
    # замечали). completed_at nullable, поэтому отбираем только заполненные:
    # иначе NULL уехал бы и в сортировку, и в .isoformat().
    q = (
        select(GiftBooking)
        .where(
            GiftBooking.status == GiftStatus.COMPLETED,
            GiftBooking.completed_at.isnot(None),
            GiftBooking.booked_by_user_id.in_(following_ids),
        )
        .options(
            selectinload(GiftBooking.wishlist_item).selectinload(WishlistItem.record),
            selectinload(GiftBooking.wishlist_item).selectinload(WishlistItem.wishlist).selectinload(Wishlist.user),
        )
        .order_by(GiftBooking.completed_at.desc())
        .limit(per_source_limit)
    )
    if cutoff is not None:
        q = q.where(GiftBooking.completed_at < cutoff)
    for gb in (await db.execute(q)).scalars().all():
        actor_user = await db.scalar(select(User).where(User.id == gb.booked_by_user_id))
        if not actor_user:
            continue
        wi = gb.wishlist_item
        target = wi.wishlist.user if (wi and wi.wishlist) else None
        record = wi.record if wi else None
        items.append((gb.completed_at, {
            "type": "gift_completed",
            "actor": _actor_payload(actor_user),
            "created_at": gb.completed_at.isoformat(),
            "record": _record_payload(record),
            "target_user": _actor_payload(target) if target else None,
            "payload": {},
        }))

    # --- friend_achievement ---
    q = (
        select(UserAchievement)
        .where(
            UserAchievement.user_id.in_(following_ids),
            UserAchievement.is_unlocked == True,
        )
        .order_by(UserAchievement.unlocked_at.desc().nullslast())
        .limit(per_source_limit)
    )
    if cutoff is not None:
        q = q.where(UserAchievement.unlocked_at < cutoff)
    rows = (await db.execute(q)).scalars().all()
    if rows:
        actor_ids = {r.user_id for r in rows}
        actors = {
            u.id: u
            for u in (await db.execute(select(User).where(User.id.in_(actor_ids)))).scalars().all()
        }
        for ua in rows:
            actor = actors.get(ua.user_id)
            if not actor or not ua.unlocked_at:
                continue
            items.append((ua.unlocked_at, {
                "type": "friend_achievement",
                "actor": _actor_payload(actor),
                "created_at": ua.unlocked_at.isoformat(),
                "record": None,
                "target_user": None,
                "payload": {"code": ua.code},
            }))

    # --- friend_new_following: друг подписался на нового пользователя ---
    q = (
        select(Follow)
        .where(Follow.follower_id.in_(following_ids))
        .order_by(Follow.created_at.desc())
        .limit(per_source_limit)
    )
    if cutoff is not None:
        q = q.where(Follow.created_at < cutoff)
    rows = (await db.execute(q)).scalars().all()
    if rows:
        user_ids = {r.follower_id for r in rows} | {r.following_id for r in rows}
        users_map = {
            u.id: u
            for u in (await db.execute(select(User).where(User.id.in_(user_ids)))).scalars().all()
        }
        for f in rows:
            actor = users_map.get(f.follower_id)
            target = users_map.get(f.following_id)
            if not actor or not target or target.id == user_id:
                continue
            items.append((f.created_at, {
                "type": "friend_new_following",
                "actor": _actor_payload(actor),
                "created_at": f.created_at.isoformat(),
                "record": None,
                "target_user": _actor_payload(target),
                "payload": {},
            }))

    items.sort(key=lambda x: x[0], reverse=True)
    aggregated = _aggregate_similar(items)
    sliced = aggregated[:limit]
    next_cursor = sliced[-1][0].isoformat() if len(sliced) == limit else None
    return [it[1] for it in sliced], next_cursor


# Какие типы можно схлопывать в «X добавил N пластинок» / «X получил N ачивок» и т.д.
AGGREGATABLE_TYPES = {"collection_add", "wishlist_add", "friend_achievement"}
AGGREGATE_THRESHOLD = 3  # ≥3 однотипных события одного юзера за день → группируем


def _aggregate_similar(
    items: list[tuple[datetime, dict[str, Any]]],
) -> list[tuple[datetime, dict[str, Any]]]:
    """Схлопывает ≥3 однотипных события одного юзера за один день в один aggregated item."""
    groups: dict[tuple[str, str, str], list[tuple[datetime, dict[str, Any]]]] = {}
    standalone: list[tuple[datetime, dict[str, Any]]] = []

    for ts, item in items:
        t = item["type"]
        if t not in AGGREGATABLE_TYPES:
            standalone.append((ts, item))
            continue
        actor_id = item["actor"]["id"]
        day_key = ts.date().isoformat()
        groups.setdefault((t, actor_id, day_key), []).append((ts, item))

    result: list[tuple[datetime, dict[str, Any]]] = list(standalone)
    for key, members in groups.items():
        if len(members) < AGGREGATE_THRESHOLD:
            result.extend(members)
            continue
        # Самый свежий — задаёт ts; собираем первые 3 обложки.
        members.sort(key=lambda m: m[0], reverse=True)
        latest_ts, latest_item = members[0]
        records_preview = [m[1]["record"] for m in members[:3] if m[1].get("record")]
        aggregated_item = {
            "type": latest_item["type"],
            "actor": latest_item["actor"],
            "created_at": latest_ts.isoformat(),
            "record": records_preview[0] if records_preview else None,
            "target_user": None,
            "payload": {
                "aggregated": True,
                "count": len(members),
                "records": records_preview,
            },
        }
        result.append((latest_ts, aggregated_item))

    result.sort(key=lambda x: x[0], reverse=True)
    return result
