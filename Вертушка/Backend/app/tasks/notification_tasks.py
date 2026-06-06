"""
Фоновые задачи уведомлений.

emit_wishlist_in_stock_notifications:
    Раз в N минут: находит StoreListing, которые недавно стали in_stock,
    проверяет — нет ли совпадений с чьими-то WishlistItem, и эмитит
    `wishlist_in_stock` уведомления.

Логика «один record — одна живая нить» теперь работает через `upsert_notification`
и partial unique index `ix_notifications_user_dedup_unread`:
- если у юзера уже есть unread по этому record → bump (occurrences++ и stores[] += новый магазин);
- если последняя прочитана и snooze ещё активен (7д/30д/90д) → skip;
- если за окно сработало ≥DIGEST_THRESHOLD алертов одному юзеру → склеиваем в digest.

См. docs/plans/PLAN_NOTIFICATIONS_V2.md.
"""
from __future__ import annotations

import logging
from collections import defaultdict
from datetime import datetime, timedelta
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import async_session_maker
from app.models.notification import (
    Notification,
    PRIORITY_QUIET,
)
from app.models.store_listing import StoreListing, ListingStatus
from app.models.wishlist import Wishlist, WishlistItem
from app.services.notification_service import (
    merge_wishlist_stores,
    upsert_notification,
)

logger = logging.getLogger(__name__)

# Окно: новые/изменённые listing'и за последние N минут (с запасом перед интервалом запуска).
RECENT_WINDOW_MINUTES = 20

# Сколько дней назад смотрим непрочитанные wishlist_in_stock при сборке недельного digest.
WEEKLY_DIGEST_LOOKBACK_DAYS = 7

# Максимум превью-обложек в data.items недельного digest.
DIGEST_PREVIEW_LIMIT = 10


async def emit_wishlist_in_stock_notifications() -> None:
    """Идемпотентная фоновая задача — вызывается из APScheduler каждые 15 минут."""
    try:
        async with async_session_maker() as db:
            await _run(db)
    except Exception:
        logger.exception("emit_wishlist_in_stock_notifications failed")


async def _run(db: AsyncSession) -> None:
    now = datetime.utcnow()
    window_start = now - timedelta(minutes=RECENT_WINDOW_MINUTES)

    listings = (
        await db.execute(
            select(StoreListing)
            .where(
                StoreListing.status == ListingStatus.IN_STOCK,
                StoreListing.matched_record_id.is_not(None),
                StoreListing.updated_at >= window_start,
            )
            .options(
                selectinload(StoreListing.record),
                selectinload(StoreListing.store),
            )
        )
    ).scalars().all()
    if not listings:
        return

    record_ids = list({l.matched_record_id for l in listings if l.matched_record_id})
    wishlist_items = (
        await db.execute(
            select(WishlistItem)
            .join(Wishlist)
            .where(WishlistItem.record_id.in_(record_ids))
            .options(
                selectinload(WishlistItem.wishlist),
                selectinload(WishlistItem.record),
            )
        )
    ).scalars().all()
    if not wishlist_items:
        return

    # Группируем listings по record для аккуратного передачи в data.stores[].
    listings_by_record: dict[str, list[StoreListing]] = defaultdict(list)
    for l in listings:
        if l.matched_record_id:
            listings_by_record[str(l.matched_record_id)].append(l)

    # Что эмитили в этот прогон — для последующей конвертации в digest.
    emitted_per_user: dict[UUID, list[Notification]] = defaultdict(list)

    for wi in wishlist_items:
        owner_id = wi.wishlist.user_id
        record = wi.record
        if not record:
            continue

        related = listings_by_record.get(str(record.id), [])
        if not related:
            continue

        prices = [l.price_rub for l in related if l.price_rub is not None]
        min_price = float(min(prices)) if prices else None
        # Берём самый дешёвый магазин как «инициатор» — у него и сюжет «появилась» интереснее.
        cheapest = min(
            (l for l in related if l.price_rub is not None),
            key=lambda x: x.price_rub,
            default=related[0],
        )
        store_payload = _build_store_payload(cheapest)

        dedup_key = f"wishlist_in_stock:{record.id}"

        # In-app only: индивидуальные wishlist_in_stock больше НЕ шлют push.
        # Кадэнс push отдан недельному digest (emit_weekly_wishlist_digest),
        # чтобы юзер не получал одну и ту же обложку раз в пару дней.
        try:
            notif, is_new = await upsert_notification(
                db,
                user_id=owner_id,
                type="wishlist_in_stock",
                dedup_key=dedup_key,
                entity_type="record",
                entity_id=str(record.id),
                data={
                    "record_id": str(record.id),
                    "record_title": record.title,
                    "record_artist": getattr(record, "artist", None),
                    "cover_url": getattr(record, "cover_image_url", None),
                    "price_rub": min_price,
                    "min_price_rub": min_price,
                    "store_count": 1,
                    "stores": [store_payload],
                    "store": store_payload,  # для merge_data_fn в bump-path
                },
                priority=PRIORITY_QUIET,
                merge_data_fn=merge_wishlist_stores,
            )
            if notif is not None and is_new:
                emitted_per_user[owner_id].append(notif)
        except Exception:
            logger.exception(
                "Failed to upsert wishlist_in_stock for user=%s record=%s",
                owner_id,
                record.id,
            )

    await db.commit()
    total = sum(len(v) for v in emitted_per_user.values())
    if total:
        logger.info("emit_wishlist_in_stock: emitted=%d (in-app, no push)", total)


def _build_store_payload(listing: StoreListing) -> dict:
    """Маленький payload магазина для data.stores[]. Slug — дедуп-ключ внутри."""
    store = listing.store
    return {
        "slug": getattr(store, "slug", None),
        "name": getattr(store, "name", None),
        "price_rub": float(listing.price_rub) if listing.price_rub is not None else None,
        "url": listing.url,
        "listing_id": str(listing.id),
    }


def _plural_records(n: int) -> str:
    mod10, mod100 = n % 10, n % 100
    if 11 <= mod100 <= 14:
        return "пластинок"
    if mod10 == 1:
        return "пластинка"
    if 2 <= mod10 <= 4:
        return "пластинки"
    return "пластинок"


async def check_push_receipts() -> None:
    """Отложенная проверка доставки push (Expo receipts).

    Expo возвращает синхронный ticket=ok ещё до реальной доставки в APNs/FCM.
    Настоящие ошибки (`DeviceNotRegistered` и пр.) приходят позже в receipts.
    Этот джоб изымает накопленные receipt-id, спрашивает Expo и зачищает
    протухшие push_token. Идемпотентен, best-effort (без Redis — no-op)."""
    try:
        from app.services.push import process_pending_receipts
        async with async_session_maker() as db:
            stats = await process_pending_receipts(db)
        if stats.get("checked"):
            logger.info(
                "check_push_receipts: checked=%d errors=%d cleared=%d",
                stats["checked"], stats["errors"], stats["cleared"],
            )
    except Exception:
        logger.exception("check_push_receipts failed")


async def emit_weekly_wishlist_digest() -> None:
    """Недельный digest-push «N пластинок из вишлиста снова в продаже».

    Push-only: in-app лента уже наполнена индивидуальными `wishlist_in_stock`
    (тихими, без push) из 15-минутного джоба. Здесь мы лишь раз в неделю
    шлём ОДИН push на юзера, чтобы напомнить заглянуть в ленту — без спама
    одной и той же обложкой раз в пару дней.
    """
    try:
        async with async_session_maker() as db:
            await _run_weekly_digest(db)
    except Exception:
        logger.exception("emit_weekly_wishlist_digest failed")


async def _run_weekly_digest(db: AsyncSession) -> None:
    from sqlalchemy import func

    from app.services.push import send_push

    now = datetime.utcnow()
    lookback = now - timedelta(days=WEEKLY_DIGEST_LOOKBACK_DAYS)

    # Сколько непрочитанных wishlist_in_stock накопилось у каждого юзера за неделю.
    rows = await db.execute(
        select(Notification.user_id, func.count(Notification.id))
        .where(
            Notification.type == "wishlist_in_stock",
            Notification.read_at.is_(None),
            Notification.created_at >= lookback,
        )
        .group_by(Notification.user_id)
    )
    counts = rows.all()
    if not counts:
        return

    sent = 0
    for user_id, count in counts:
        if not count:
            continue
        try:
            ok = await send_push(
                db,
                user_id,
                notification_type="digest_wishlist_in_stock",
                title=f"{count} {_plural_records(count)} из вишлиста снова в продаже",
                body="Открой ленту, чтобы посмотреть",
                data={"type": "digest_wishlist_in_stock", "count": count},
            )
            if ok:
                sent += 1
        except Exception:
            logger.exception("weekly digest push failed for user=%s", user_id)

    logger.info("emit_weekly_wishlist_digest: pushed=%d users", sent)
