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

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import async_session_maker
from app.models.listing_price_history import ListingPriceHistory
from app.models.notification import (
    Notification,
    PRIORITY_PUSH,
    PRIORITY_QUIET,
)
from app.models.record import Record
from app.models.store_listing import StoreListing, ListingStatus
from app.models.wishlist import Wishlist, WishlistItem
from app.services.notification_service import (
    merge_wishlist_stores,
    upsert_notification,
)

logger = logging.getLogger(__name__)

# Окно: новые/изменённые listing'и за последние N минут (с запасом перед интервалом запуска).
RECENT_WINDOW_MINUTES = 20

# Минимальное падение цены, которое считаем значимым (5%) — шум ±пары % не шлём.
MIN_DROP_PCT = 0.05

# Горизонт истории, в котором ищем «прошлую цену» для LAG (снапшоты редкие —
# пишутся лишь при смене, так что окно широкое, но скан ограничен).
PRICE_DROP_HISTORY_DAYS = 90

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

        # Колокольчик: watched (дефолт) — тихая нить, push отдан недельному
        # digest. subscribed — мгновенный push при появлении, если проходит
        # порог цены. PRIORITY_PUSH пробивает snooze; cap_key=wl_item:<record>
        # даёт независимый часовой слот на каждую пластинку (иначе первый push
        # съест общий часовой cap типа для остальных subscribed-пластинок).
        subscribed = wi.notify_mode == "subscribed"
        threshold = (
            float(wi.price_threshold_rub)
            if wi.price_threshold_rub is not None
            else None
        )
        within_threshold = (
            threshold is None
            or (min_price is not None and min_price <= threshold)
        )
        push_now = subscribed and within_threshold

        if push_now and min_price is not None:
            push_body = f"от {int(min_price)} ₽"
        elif push_now:
            push_body = "Появилась в продаже"
        else:
            push_body = None

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
                push_title=(f"«{record.title}» снова в продаже" if push_now else None),
                push_body=push_body,
                push_image=(getattr(record, "cover_image_url", None) if push_now else None),
                push_cap_key=(f"wl_item:{record.id}" if push_now else None),
                priority=PRIORITY_PUSH if push_now else PRIORITY_QUIET,
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

    # Аналоги: другой прессинг того же мастера появился в продаже.
    await _emit_alt_versions(db, listings, record_ids, emitted_per_user)

    await db.commit()
    total = sum(len(v) for v in emitted_per_user.values())
    if total:
        logger.info(
            "emit_wishlist_in_stock: emitted=%d (watched=in-app, subscribed=push)",
            total,
        )


async def _emit_alt_versions(
    db: AsyncSession,
    listings: list[StoreListing],
    exact_record_ids: list[UUID],
    emitted_per_user: dict[UUID, list[Notification]],
) -> None:
    """`wishlist_in_stock_alt` — аналог (другой прессинг того же мастера) в продаже.

    Аналог = запись с тем же `discogs_master_id`, что и желаемая, но НЕ сама
    желаемая. Желаемую покрывает обычный wishlist_in_stock — тут только «другая
    версия».
    """
    instock_by_master: dict[str, list[StoreListing]] = defaultdict(list)
    instock_record_ids: set[UUID] = set()
    for l in listings:
        rec = l.record
        if not rec:
            continue
        instock_record_ids.add(rec.id)
        mid = getattr(rec, "discogs_master_id", None)
        if mid:
            instock_by_master[str(mid)].append(l)

    masters = list(instock_by_master.keys())
    if not masters:
        return

    alt_items = (
        await db.execute(
            select(WishlistItem)
            .join(Wishlist)
            .join(Record, WishlistItem.record_id == Record.id)
            .where(
                Record.discogs_master_id.in_(masters),
                WishlistItem.record_id.not_in(instock_record_ids),
            )
            .options(
                selectinload(WishlistItem.wishlist),
                selectinload(WishlistItem.record),
            )
        )
    ).scalars().all()

    for wi in alt_items:
        wanted = wi.record
        if not wanted:
            continue
        mid = str(getattr(wanted, "discogs_master_id", "") or "")
        related = instock_by_master.get(mid, [])
        if not related:
            continue

        prices = [float(l.price_rub) for l in related if l.price_rub is not None]
        min_price = min(prices) if prices else None
        cheapest = min(
            (l for l in related if l.price_rub is not None),
            key=lambda x: x.price_rub,
            default=related[0],
        )
        alt_record = cheapest.record
        store_payload = _build_store_payload(cheapest)

        subscribed = wi.notify_mode == "subscribed"
        threshold = (
            float(wi.price_threshold_rub)
            if wi.price_threshold_rub is not None
            else None
        )
        within_threshold = (
            threshold is None
            or (min_price is not None and min_price <= threshold)
        )
        push_now = subscribed and within_threshold

        try:
            notif, is_new = await upsert_notification(
                db,
                user_id=wi.wishlist.user_id,
                type="wishlist_in_stock_alt",
                dedup_key=f"wishlist_in_stock_alt:{wanted.id}",
                entity_type="record",
                entity_id=str(wanted.id),
                data={
                    "record_id": str(wanted.id),
                    "record_title": wanted.title,
                    "record_artist": getattr(wanted, "artist", None),
                    "cover_url": getattr(wanted, "cover_image_url", None),
                    "alt_record_id": str(alt_record.id) if alt_record else None,
                    "alt_record_title": getattr(alt_record, "title", None),
                    "alt_cover_url": getattr(alt_record, "cover_image_url", None),
                    "price_rub": min_price,
                    "min_price_rub": min_price,
                    "store_count": 1,
                    "stores": [store_payload],
                    "store": store_payload,
                },
                push_title=(f"Другое издание «{wanted.title}» в продаже" if push_now else None),
                push_body=(f"от {int(min_price)} ₽" if push_now and min_price is not None else None),
                push_image=(getattr(alt_record, "cover_image_url", None) if push_now else None),
                push_cap_key=(f"wl_alt:{wanted.id}" if push_now else None),
                priority=PRIORITY_PUSH if push_now else PRIORITY_QUIET,
                merge_data_fn=merge_wishlist_stores,
            )
            if notif is not None and is_new:
                emitted_per_user[wi.wishlist.user_id].append(notif)
        except Exception:
            logger.exception(
                "Failed to upsert wishlist_in_stock_alt for user=%s record=%s",
                wi.wishlist.user_id,
                wanted.id,
            )


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


async def emit_wishlist_price_drop_notifications() -> None:
    """Идемпотентная фоновая задача — каждые 15 минут ищет падения цены.

    Источник — listing_price_history (снапшот пишется только при смене цены,
    так что соседние строки одного листинга = точки изменения). LAG(price) по
    captured_at даёт прошлую цену; падение ≥MIN_DROP_PCT на in_stock-листинге,
    привязанном к желаемой пластинке, рождает wishlist_price_drop.
    """
    try:
        async with async_session_maker() as db:
            await _run_price_drop(db)
    except Exception:
        logger.exception("emit_wishlist_price_drop_notifications failed")


async def _run_price_drop(db: AsyncSession) -> None:
    now = datetime.utcnow()
    window_start = now - timedelta(minutes=RECENT_WINDOW_MINUTES)
    history_floor = now - timedelta(days=PRICE_DROP_HISTORY_DAYS)

    # Ранжируем историю по листингу; prev_price = цена в прошлом снапшоте.
    lag_price = func.lag(ListingPriceHistory.price_rub).over(
        partition_by=ListingPriceHistory.listing_id,
        order_by=ListingPriceHistory.captured_at,
    )
    ranked = (
        select(
            ListingPriceHistory.listing_id.label("listing_id"),
            ListingPriceHistory.record_id.label("record_id"),
            ListingPriceHistory.price_rub.label("price_rub"),
            ListingPriceHistory.status.label("status"),
            ListingPriceHistory.captured_at.label("captured_at"),
            lag_price.label("prev_price"),
        )
        .where(
            ListingPriceHistory.record_id.is_not(None),
            ListingPriceHistory.captured_at >= history_floor,
        )
        .subquery()
    )

    # Падение: новый снапшот в окне прогона, статус in_stock, цена упала
    # относительно прошлой не меньше чем на MIN_DROP_PCT.
    drop_rows = (
        await db.execute(
            select(
                ranked.c.record_id,
                ranked.c.prev_price,
                ranked.c.price_rub,
            ).where(
                ranked.c.captured_at >= window_start,
                ranked.c.status == ListingStatus.IN_STOCK,
                ranked.c.price_rub.is_not(None),
                ranked.c.prev_price.is_not(None),
                ranked.c.price_rub < ranked.c.prev_price * (1 - MIN_DROP_PCT),
            )
        )
    ).all()
    if not drop_rows:
        return

    # На запись берём максимальное падение (самый низкий new, самый высокий old).
    best_drop: dict[UUID, tuple[float, float]] = {}
    for record_id, prev_price, price_rub in drop_rows:
        old = float(prev_price)
        new = float(price_rub)
        cur = best_drop.get(record_id)
        if cur is None or new < cur[1]:
            best_drop[record_id] = (old, new)

    record_ids = list(best_drop.keys())
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

    emitted = 0
    for wi in wishlist_items:
        record = wi.record
        if not record:
            continue
        old, new = best_drop[wi.record_id]
        drop_pct = round((old - new) / old * 100) if old else 0

        subscribed = wi.notify_mode == "subscribed"
        threshold = (
            float(wi.price_threshold_rub)
            if wi.price_threshold_rub is not None
            else None
        )
        within_threshold = threshold is None or new <= threshold
        push_now = subscribed and within_threshold

        try:
            notif, is_new = await upsert_notification(
                db,
                user_id=wi.wishlist.user_id,
                type="wishlist_price_drop",
                dedup_key=f"wishlist_price_drop:{record.id}",
                entity_type="record",
                entity_id=str(record.id),
                data={
                    "record_id": str(record.id),
                    "record_title": record.title,
                    "record_artist": getattr(record, "artist", None),
                    "cover_url": getattr(record, "cover_image_url", None),
                    "old_price_rub": old,
                    "new_price_rub": new,
                    "min_price_rub": new,
                    "drop_pct": drop_pct,
                },
                push_title=(f"«{record.title}» подешевела" if push_now else None),
                push_body=(f"{int(old)} → {int(new)} ₽" if push_now else None),
                push_image=(getattr(record, "cover_image_url", None) if push_now else None),
                push_cap_key=(f"wl_drop:{record.id}" if push_now else None),
                priority=PRIORITY_PUSH if push_now else PRIORITY_QUIET,
            )
            if notif is not None and is_new:
                emitted += 1
        except Exception:
            logger.exception(
                "Failed to upsert wishlist_price_drop for user=%s record=%s",
                wi.wishlist.user_id,
                record.id,
            )

    await db.commit()
    if emitted:
        logger.info("emit_wishlist_price_drop: emitted=%d", emitted)


async def cleanup_price_history() -> None:
    """Ночная чистка listing_price_history старше 1 года (ретеншн-политика)."""
    from sqlalchemy import delete

    try:
        async with async_session_maker() as db:
            cutoff = datetime.utcnow() - timedelta(days=365)
            result = await db.execute(
                delete(ListingPriceHistory).where(
                    ListingPriceHistory.captured_at < cutoff
                )
            )
            await db.commit()
            if result.rowcount:
                logger.info("cleanup_price_history: deleted=%d rows", result.rowcount)
    except Exception:
        logger.exception("cleanup_price_history failed")
