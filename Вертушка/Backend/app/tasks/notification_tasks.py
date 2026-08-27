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

from sqlalchemy import ARRAY, all_, any_, func, literal, select
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
from app.services import push_copy
from app.services.affiliate import wrap_url
from app.services.alt_media_match import alt_media_ok
from app.services.radar_status import condition_ok, record_radar_event
from app.services.radar_threshold import baseline_prices, effective_threshold

logger = logging.getLogger(__name__)

# Окно: новые/изменённые listing'и за последние N минут (с запасом перед интервалом запуска).
# TODO: окно по updated_at — хрупкий источник событий: чекпоинта нет, поэтому
# упавший/пропущенный прогон теряет уведомления безвозвратно, а обход краулера,
# бампающий updated_at всему маркету (~54k листингов), вбирает в окно весь
# каталог разом. Правильный источник — listing_price_history с водяным знаком
# (последний обработанный captured_at); это архитектурная переделка и она
# сознательно НЕ в этом фиксе.
RECENT_WINDOW_MINUTES = 20

# Минимальное падение цены, которое считаем значимым (10%) — шум мелких колебаний
# не шлём. Раньше было 5%, подняли: 5-9% редко меняет решение о покупке.
MIN_DROP_PCT = 0.10

# Доля порога, внутри которой цену считаем «почти дошла» (порог 5000 → 5500).
NEAR_THRESHOLD_RATIO = 0.10

# Горизонт истории, в котором ищем «прошлую цену» для LAG (снапшоты редкие —
# пишутся лишь при смене, так что окно широкое, но скан ограничен).
PRICE_DROP_HISTORY_DAYS = 90

# Сколько дней назад смотрим непрочитанные wishlist_in_stock при сборке недельного digest.
WEEKLY_DIGEST_LOOKBACK_DAYS = 7

# Максимум превью-обложек в data.items недельного digest.
DIGEST_PREVIEW_LIMIT = 10


def _resurface_on_price_improvement(old_data: dict, new_data: dict) -> bool:
    """Anti-churn guard для wishlist-нитей.

    Строка всплывает наверх (bumped_at/occurrences) только если цена реально
    улучшилась относительно уже показанной. Повторное «снова в наличии» по той
    же/худшей цене — не новость: мержим stores, но не воскрешаем и не крутим
    «обновлено N×». Если старой цены не было (первое наполнение) — всплываем.
    """
    old_min = old_data.get("min_price_rub")
    new_min = new_data.get("min_price_rub")
    if new_min is None:
        return False
    if old_min is None:
        return True
    try:
        return float(new_min) < float(old_min)
    except (TypeError, ValueError):
        return True


def _threshold_gap(price: float | None, threshold: float | None) -> tuple[float | None, bool]:
    """(сколько ₽ осталось до порога, попадает ли цена в «почти дошла»).

    Радар знал только бинарное match/не-match: цена 5 200 при пороге 5 000 не
    отличалась от 11 000, и пользователь не видел, что почти дошло. Зазор едет
    в data существующей тихой нити (PRIORITY_QUIET) — отдельного пуша тут нет
    и быть не должно, иначе каждое колебание цены станет уведомлением.

    Цена ≤ порога → (None, False): это уже match, зазор бессмысленен.
    """
    if price is None or threshold is None or threshold <= 0 or price <= threshold:
        return None, False
    gap = round(price - threshold, 2)
    return gap, gap <= threshold * NEAR_THRESHOLD_RATIO


def _id_filter(col, ids, *, dialect: str, negate: bool = False):
    """Фильтр «col ∈ ids» без взрыва bind-параметров.

    `col.in_(python_list)` разворачивается в отдельный параметр на каждый
    элемент. После обхода краулера окно «recent» вбирает весь маркет, и
    запрос alt-версий собирал 48 961 бинд при лимите asyncpg 32 767 —
    задача падала после каждого обхода (02:00 и 14:00).

    На PostgreSQL шлём ОДИН array-бинд: `col = ANY(:ids)` /
    `col != ALL(:ids)` (семантика NOT IN для non-null значений). На прочих
    диалектах (SQLite в тестах) — прежние in_/not_in: там ANY/ALL по массиву
    не поддерживаются, а списки маленькие.
    """
    values = list(ids)
    if dialect == "postgresql":
        arr = literal(values, type_=ARRAY(col.type))
        return col != all_(arr) if negate else col == any_(arr)
    return col.not_in(values) if negate else col.in_(values)


def _dialect_name(db: AsyncSession) -> str:
    """Имя диалекта живой сессии — чтобы _id_filter выбрал форму запроса."""
    return db.get_bind().dialect.name


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

    dialect = _dialect_name(db)
    record_ids = list({l.matched_record_id for l in listings if l.matched_record_id})
    wishlist_items = (
        await db.execute(
            select(WishlistItem)
            .join(Wishlist)
            .where(_id_filter(WishlistItem.record_id, record_ids, dialect=dialect))
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

    # База для айтемов в режиме «дешевле обычного» — одним запросом на прогон.
    baselines = await baseline_prices(
        db, [wi.record_id for wi in wishlist_items if wi.threshold_pct is not None]
    )

    for wi in wishlist_items:
        owner_id = wi.wishlist.user_id
        record = wi.record
        if not record:
            continue

        related = listings_by_record.get(str(record.id), [])
        # Фильтр по «Состоянию релиза» (для watched conditions=None → без фильтра).
        related = [l for l in related if condition_ok(l.condition, wi.conditions)]
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
        threshold = effective_threshold(
            wi.price_threshold_rub, wi.threshold_pct, baselines.get(wi.record_id)
        )
        within_threshold = (
            threshold is None
            or (min_price is not None and min_price <= threshold)
        )
        push_now = subscribed and within_threshold
        radar_status = "match" if (subscribed and within_threshold and min_price is not None) else "available"
        gap_rub, near_threshold = _threshold_gap(min_price, threshold if subscribed else None)

        if push_now:
            push_title, push_body = push_copy.wishlist_in_stock(
                artist=getattr(record, "artist", None),
                title=record.title,
                min_price=min_price,
                store_name=getattr(cheapest.store, "name", None),
            )
        else:
            push_title = push_body = None

        try:
            # Savepoint на айтем: не-IntegrityError ошибка БД (гонки внутри
            # upsert_notification закрыты его собственным begin_nested, но
            # любая другая — нет) без savepoint переводит сессию в
            # failed-состояние, и весь прогон умирает на следующем запросе.
            async with db.begin_nested():
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
                        "on_radar": subscribed,
                        "radar_status": radar_status if subscribed else None,
                        "threshold_rub": (float(threshold) if threshold is not None else None),
                        "to_threshold_rub": gap_rub,
                        "near_threshold": near_threshold,
                    },
                    push_title=push_title,
                    push_body=push_body,
                    push_image=(getattr(record, "cover_image_url", None) if push_now else None),
                    push_cap_key=(f"wl_item:{record.id}" if push_now else None),
                    priority=PRIORITY_PUSH if push_now else PRIORITY_QUIET,
                    merge_data_fn=merge_wishlist_stores,
                    should_resurface=_resurface_on_price_improvement,
                )
                # Хронология радара (только subscribed; дедуп внутри).
                await record_radar_event(
                    db, wi, radar_status, min_price, getattr(cheapest.store, "name", None)
                )
            if notif is not None and is_new:
                emitted_per_user[owner_id].append(notif)
        except Exception:
            logger.exception(
                "Failed to upsert wishlist_in_stock for user=%s record=%s",
                owner_id,
                record.id,
            )

    # Коммитим основной цикл ДО alt-шага. Push уже ушёл внутри
    # upsert_notification (до коммита), и падение alt-шага не должно
    # откатывать строки, на которые эти push'и ссылаются, — именно так после
    # каждого обхода краулера терялись все уведомления прогона.
    await db.commit()

    # Аналоги: другой прессинг того же мастера появился в продаже.
    # Best-effort: своё исключение и свой commit — основные уведомления уже
    # в базе, исход alt-шага их не трогает.
    try:
        await _emit_alt_versions(db, listings, record_ids, emitted_per_user)
        await db.commit()
    except Exception:
        logger.exception("emit_wishlist_in_stock: alt-versions step failed")
        await db.rollback()

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

    # После обхода краулера masters/instock_record_ids — почти весь маркет;
    # array-бинды вместо in_/not_in, иначе asyncpg упирается в лимит 32 767.
    dialect = _dialect_name(db)
    alt_items = (
        await db.execute(
            select(WishlistItem)
            .join(Wishlist)
            .join(Record, WishlistItem.record_id == Record.id)
            .where(
                _id_filter(Record.discogs_master_id, masters, dialect=dialect),
                _id_filter(
                    WishlistItem.record_id,
                    instock_record_ids,
                    dialect=dialect,
                    negate=True,
                ),
            )
            .options(
                selectinload(WishlistItem.wishlist),
                selectinload(WishlistItem.record),
            )
        )
    ).scalars().all()

    # База относительного порога — по ЖЕЛАЕМОЙ записи, а не по аналогу: юзер
    # задавал «дешевле обычного» для своей версии, её история и есть ориентир.
    baselines = await baseline_prices(
        db, [wi.record_id for wi in alt_items if wi.threshold_pct is not None]
    )

    for wi in alt_items:
        wanted = wi.record
        if not wanted:
            continue
        mid = str(getattr(wanted, "discogs_master_id", "") or "")
        related = instock_by_master.get(mid, [])
        # Отклонённые аналоги («Нет» в шите радара) больше не поводы для пуша.
        rejected_alts = set(wi.rejected_alt_record_ids or [])
        related = [
            l for l in related
            if condition_ok(l.condition, wi.conditions)
            and str(getattr(l, "matched_record_id", "")) not in rejected_alts
            # Тот же носитель, что в вишлисте: под винил не шлём «File, MP3».
            and alt_media_ok(
                getattr(wanted, "format_type", None),
                getattr(wanted, "format_description", None),
                getattr(l.record, "format_type", None),
                getattr(l.record, "format_description", None),
                getattr(l, "format_raw", None),
            )
        ]
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
        threshold = effective_threshold(
            wi.price_threshold_rub, wi.threshold_pct, baselines.get(wi.record_id)
        )
        within_threshold = (
            threshold is None
            or (min_price is not None and min_price <= threshold)
        )
        push_now = subscribed and within_threshold

        if push_now:
            alt_push_title, alt_push_body = push_copy.wishlist_in_stock_alt(
                artist=getattr(wanted, "artist", None),
                title=wanted.title,
                min_price=min_price,
                store_name=getattr(cheapest.store, "name", None),
            )
        else:
            alt_push_title = alt_push_body = None

        try:
            # Savepoint — как в основном цикле: ошибка БД по одному айтему не
            # должна оставлять сессию в failed-состоянии для остальных.
            async with db.begin_nested():
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
                        "on_radar": subscribed,
                        "radar_status": "alt" if subscribed else None,
                    },
                    push_title=alt_push_title,
                    push_body=alt_push_body,
                    push_image=(getattr(alt_record, "cover_image_url", None) if push_now else None),
                    push_cap_key=(f"wl_alt:{wanted.id}" if push_now else None),
                    priority=PRIORITY_PUSH if push_now else PRIORITY_QUIET,
                    merge_data_fn=merge_wishlist_stores,
                    should_resurface=_resurface_on_price_improvement,
                )
                await record_radar_event(
                    db, wi, "alt", min_price, getattr(cheapest.store, "name", None)
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
    """Маленький payload магазина для data.stores[]. Slug — дедуп-ключ внутри.

    `url` — тот же fallback-контракт, что `OfferResponse.preview_url`: UTM-only,
    без subid. Клиент открывает его лишь если POST /offers/{id}/click не ответил
    (см. WishlistDigestSheet.openStoreUrl), поэтому UTM тут обязателен — иначе
    аварийный переход невидим и в нашей, и в магазинной аналитике.
    """
    store = listing.store
    return {
        "slug": getattr(store, "slug", None),
        "name": getattr(store, "name", None),
        "price_rub": float(listing.price_rub) if listing.price_rub is not None else None,
        "url": wrap_url(store, listing.url) if store is not None else listing.url,
        "listing_id": str(listing.id),
    }


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
    """Недельный digest-push «За неделю: N пластинок из вишлиста».

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
    from app.services.push import send_push

    now = datetime.utcnow()
    lookback = now - timedelta(days=WEEKLY_DIGEST_LOOKBACK_DAYS)

    # Тянем сами строки (а не COUNT): из data.record_artist собираем имена для
    # body — «Miles Davis, Bill Evans, John Coltrane». Ради них дайджест и открывают.
    # Аналоги идут в тот же дайджест, но своим счётчиком: в ленте они тоже
    # свёрнуты отдельной строкой (buildDigest в notifications.tsx), и push
    # должен отражать то же деление — «твоя пластинка» ≠ «другой прессинг».
    rows = await db.execute(
        select(Notification.user_id, Notification.type, Notification.data)
        .where(
            Notification.type.in_(["wishlist_in_stock", "wishlist_in_stock_alt"]),
            Notification.read_at.is_(None),
            Notification.created_at >= lookback,
        )
        .order_by(Notification.bumped_at.desc())
    )

    counts: dict[UUID, int] = defaultdict(int)
    alt_counts: dict[UUID, int] = defaultdict(int)
    artists_by_user: dict[UUID, list[str]] = defaultdict(list)
    for user_id, ntype, data in rows.all():
        if ntype == "wishlist_in_stock_alt":
            alt_counts[user_id] += 1
        else:
            counts[user_id] += 1
        d = data or {}
        # Артист, а если его не сохранили — название пластинки: пустой body хуже.
        artist = (d.get("record_artist") or d.get("record_title") or "").strip()
        # Дедуп: один артист мог появиться несколькими пластинками.
        if artist and artist not in artists_by_user[user_id]:
            artists_by_user[user_id].append(artist)

    recipients = set(counts) | set(alt_counts)
    if not recipients:
        return

    sent = 0
    for user_id in recipients:
        count = counts.get(user_id, 0)
        alt_count = alt_counts.get(user_id, 0)
        title, body = push_copy.weekly_digest(
            count=count, artists=artists_by_user[user_id], alt_count=alt_count
        )
        try:
            ok = await send_push(
                db,
                user_id,
                notification_type="digest_wishlist_in_stock",
                title=title,
                body=body,
                data={
                    "type": "digest_wishlist_in_stock",
                    "count": count,
                    "alt_count": alt_count,
                },
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
    #
    # Привязку к пластинке берём ДЖОЙНОМ через store_listings.matched_record_id,
    # а не из денормализованного listing_price_history.record_id. Денорм пишется
    # в _upsert_listing значением НА МОМЕНТ снятия снапшота, а матчинг листингов
    # — отдельная часовая задача (hourly_match_unmatched), и listing_matcher
    # историю не досыпает: в нём нет ни одного обращения к ListingPriceHistory.
    # Значит всё, что снято до привязки, лежит с record_id=NULL.
    #
    # Что это ломало здесь. Фильтр `record_id IS NOT NULL` вырезал до-матчевые
    # строки ДО вычисления окна, поэтому у первого снапшота после привязки не
    # оказывалось предшественника в партиции: prev_price=NULL → строка гибла на
    # `prev_price.is_not(None)`. Первое же падение цены на свежепривязанном
    # листинге не рождало ни одного wishlist_price_drop — а это ровно тот
    # момент, когда пластинка впервые появляется в чьём-то радаре.
    #
    # Джойн — inner, и потерять он ничего не может: listing_id NOT NULL с
    # ON DELETE CASCADE, то есть история не переживает свой листинг. Партицию
    # LAG он тоже не трогает: store_listings.id — PK, связь 1:1.
    lag_price = func.lag(ListingPriceHistory.price_rub).over(
        partition_by=ListingPriceHistory.listing_id,
        order_by=ListingPriceHistory.captured_at,
    )
    ranked = (
        select(
            ListingPriceHistory.listing_id.label("listing_id"),
            StoreListing.matched_record_id.label("record_id"),
            ListingPriceHistory.price_rub.label("price_rub"),
            ListingPriceHistory.status.label("status"),
            ListingPriceHistory.captured_at.label("captured_at"),
            lag_price.label("prev_price"),
        )
        .select_from(ListingPriceHistory)
        .join(StoreListing, StoreListing.id == ListingPriceHistory.listing_id)
        .where(
            StoreListing.matched_record_id.is_not(None),
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
    dialect = _dialect_name(db)

    # HIGH-сигнал: исторический минимум цены. Берём min(price) по истории in-stock
    # снапшотов СТРОГО ДО текущего окна: `new` уже записан в историю, и если его не
    # исключить, min всегда равен new и сравнение вырождается в тавтологию.
    # Побочная польза: previous_low — настоящее «прошлый минимум N ₽» для текста push.
    #
    # Привязка — тем же джойном, что и выше. По денорму этот минимум считался по
    # ПОЛОВИНЕ истории: до-матчевые снапшоты в него не входили, и «дешевле ещё
    # не было» уезжало в push на цене, которую уже били раньше. Здесь ошибка
    # опаснее, чем в графике: is_all_time_low пробивает push даже watched-айтемам
    # без порога.
    previous_low: dict[UUID, float] = {}
    low_rows = (
        await db.execute(
            select(
                StoreListing.matched_record_id,
                func.min(ListingPriceHistory.price_rub),
            )
            .select_from(ListingPriceHistory)
            .join(StoreListing, StoreListing.id == ListingPriceHistory.listing_id)
            .where(
                _id_filter(StoreListing.matched_record_id, record_ids, dialect=dialect),
                ListingPriceHistory.status == ListingStatus.IN_STOCK,
                ListingPriceHistory.price_rub.is_not(None),
                ListingPriceHistory.captured_at < window_start,
            )
            .group_by(StoreListing.matched_record_id)
        )
    ).all()
    for rid, min_price in low_rows:
        if min_price is not None:
            previous_low[rid] = float(min_price)

    wishlist_items = (
        await db.execute(
            select(WishlistItem)
            .join(Wishlist)
            .where(_id_filter(WishlistItem.record_id, record_ids, dialect=dialect))
            .options(
                selectinload(WishlistItem.wishlist),
                selectinload(WishlistItem.record),
            )
        )
    ).scalars().all()
    if not wishlist_items:
        return

    baselines = await baseline_prices(
        db, [wi.record_id for wi in wishlist_items if wi.threshold_pct is not None]
    )

    emitted = 0
    for wi in wishlist_items:
        record = wi.record
        if not record:
            continue
        old, new = best_drop[wi.record_id]
        drop_pct = round((old - new) / old * 100) if old else 0

        subscribed = wi.notify_mode == "subscribed"
        threshold = effective_threshold(
            wi.price_threshold_rub, wi.threshold_pct, baselines.get(wi.record_id)
        )
        within_threshold = threshold is None or new <= threshold
        # HIGH-сигнал: новый исторический минимум цены. Пробивает push даже для
        # watched-айтемов (без порога) — «дешевле, чем когда-либо» реально меняет
        # решение о покупке. Порог 1₽ гасит копеечный шум округлений.
        # Сравниваем с минимумом ДО этого прогона. Нет истории — заявлять «дешевле
        # не было» не на чем, уходим в обычный price-drop.
        prev_low = previous_low.get(wi.record_id)
        is_all_time_low = prev_low is not None and new <= prev_low
        push_now = (subscribed and within_threshold) or is_all_time_low
        radar_status = "match" if (subscribed and within_threshold) else "price_drop"
        gap_rub, near_threshold = _threshold_gap(new, threshold if subscribed else None)

        if is_all_time_low:
            push_title, push_body = push_copy.wishlist_all_time_low(
                title=record.title,
                new_price=new,
                previous_low=prev_low,
            )
        elif push_now:
            push_title, push_body = push_copy.wishlist_price_drop(
                artist=getattr(record, "artist", None),
                title=record.title,
                old_price=old,
                new_price=new,
                drop_pct=drop_pct,
            )
        else:
            push_title = None
            push_body = None

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
                    "all_time_low": is_all_time_low,
                    "on_radar": subscribed,
                    "radar_status": radar_status if subscribed else None,
                    "threshold_rub": (threshold if threshold is not None else None),
                    "to_threshold_rub": gap_rub,
                    "near_threshold": near_threshold,
                },
                push_title=push_title,
                push_body=push_body,
                push_image=(getattr(record, "cover_image_url", None) if push_now else None),
                push_cap_key=(f"wl_drop:{record.id}" if push_now else None),
                priority=PRIORITY_PUSH if push_now else PRIORITY_QUIET,
                should_resurface=_resurface_on_price_improvement,
            )
            if notif is not None and is_new:
                emitted += 1
            await record_radar_event(db, wi, radar_status, new, None)
        except Exception:
            logger.exception(
                "Failed to upsert wishlist_price_drop for user=%s record=%s",
                wi.wishlist.user_id,
                record.id,
            )

    await db.commit()
    if emitted:
        logger.info("emit_wishlist_price_drop: emitted=%d", emitted)


async def emit_wishlist_absent_notifications() -> None:
    """Идемпотентная фоновая задача — каждые 15 минут фиксирует «пропала из наличия».

    Ловит matched-листинги, недавно ушедшие в OUT_OF_STOCK/REMOVED, у которых НЕ
    осталось ни одного in-stock листинга на ту же запись → пишет radar-событие
    `absent` (для «Истории» в шторке цены — «маркетплейс продал»). Только для
    subscribed-айтемов (watched историю радара не ведёт). Push НЕ шлём — исчезновение
    само по себе не решение о покупке; это летопись, а не алерт.
    """
    try:
        async with async_session_maker() as db:
            await _run_absent(db)
    except Exception:
        logger.exception("emit_wishlist_absent_notifications failed")


async def _run_absent(db: AsyncSession) -> None:
    now = datetime.utcnow()
    window_start = now - timedelta(minutes=RECENT_WINDOW_MINUTES)

    gone = (
        await db.execute(
            select(StoreListing)
            .where(
                StoreListing.status.in_(
                    [ListingStatus.OUT_OF_STOCK, ListingStatus.REMOVED]
                ),
                StoreListing.matched_record_id.is_not(None),
                StoreListing.updated_at >= window_start,
            )
            .options(selectinload(StoreListing.store))
        )
    ).scalars().all()
    if not gone:
        return

    record_ids = list({l.matched_record_id for l in gone if l.matched_record_id})
    dialect = _dialect_name(db)

    # Записи, у которых ещё остался хоть один in-stock листинг, — не «пропали».
    still_instock = set(
        (
            await db.execute(
                select(StoreListing.matched_record_id)
                .where(
                    _id_filter(StoreListing.matched_record_id, record_ids, dialect=dialect),
                    StoreListing.status == ListingStatus.IN_STOCK,
                )
                .distinct()
            )
        ).scalars().all()
    )
    truly_gone = [rid for rid in record_ids if rid not in still_instock]
    if not truly_gone:
        return

    # По одному «последнему магазину» на запись — для store_name в событии.
    store_by_record: dict[UUID, StoreListing] = {}
    for l in gone:
        if l.matched_record_id in truly_gone:
            store_by_record.setdefault(l.matched_record_id, l)

    wishlist_items = (
        await db.execute(
            select(WishlistItem)
            .join(Wishlist)
            .where(_id_filter(WishlistItem.record_id, truly_gone, dialect=dialect))
            .options(
                selectinload(WishlistItem.wishlist),
                selectinload(WishlistItem.record),
            )
        )
    ).scalars().all()

    recorded = 0
    for wi in wishlist_items:
        if wi.notify_mode != "subscribed":
            continue  # radar-историю ведём только для подписанных айтемов
        listing = store_by_record.get(wi.record_id)
        store_name = getattr(listing.store, "name", None) if listing else None
        # record_radar_event сам дедупит (тот же статус+цена подряд → skip).
        await record_radar_event(db, wi, "absent", None, store_name)
        recorded += 1

    await db.commit()
    if recorded:
        logger.info("emit_wishlist_absent: recorded=%d absent events", recorded)


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
