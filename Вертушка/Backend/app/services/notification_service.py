"""
Сервис создания/обновления in-app уведомлений + отправка push.

См. docs/plans/social/PLAN_NOTIFICATIONS_V2.md.

API:
- `upsert_notification(...)` — основной путь: bump-or-create с явным dedup_key и priority.
- `create_notification(...)` — LEGACY-фасад: автогенерит dedup_key по типу/entity_id,
  чтобы старые call-site'ы (gifts/users/collections) работали без правок.
- `apply_snooze_on_read(notif)` — вызывается из mark_read, выставляет snoozed_until
  по лестнице 7д → 30д → 90д для wishlist-семейства типов.
- `merge_wishlist_stores(old, new)` — merge_data_fn для wishlist_in_stock,
  сворачивает stores[] и пересчитывает min_price_rub.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any, Callable
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.notification import (
    Notification,
    PRIORITY_FEED,
    PRIORITY_PUSH,
    PRIORITY_QUIET,
)
from app.services.blocking import is_user_blocked
from app.services.push import send_push

logger = logging.getLogger(__name__)


# Длина snooze после каждого следующего прочтения (snooze_level в data).
# Чем больше раз юзер прочитал alert по одной и той же сущности, тем дольше
# мы не возвращаемся к ней. Не применяется для high-signal событий (gift_booked).
SNOOZE_LADDER: dict[str, list[timedelta]] = {
    "wishlist_in_stock": [timedelta(days=7), timedelta(days=30), timedelta(days=90)],
    "wishlist_in_stock_alt": [timedelta(days=30)],
    "wishlist_price_drop": [timedelta(days=14)],
    "new_follower": [timedelta(days=365)],
}


def _default_dedup_key(
    type: str,
    entity_id: str | None,
    actor_id: UUID | None,
    data: dict[str, Any] | None,
) -> str:
    """Совместимость со старым API: вывести dedup_key из имеющихся полей.

    Каноны должны совпадать с явными ключами в notification_tasks/digest и тестах.
    """
    d = data or {}
    if type in ("wishlist_in_stock", "wishlist_in_stock_alt", "wishlist_price_drop"):
        rid = d.get("record_id") or entity_id
        return f"{type}:{rid or 'unknown'}"
    if type == "wishlist_in_stock_alt":
        mid = d.get("master_id") or entity_id
        return f"wishlist_in_stock_alt:{mid or 'unknown'}"
    if type == "new_follower":
        return f"new_follower:{actor_id or entity_id or 'unknown'}"
    if type == "achievement_unlocked":
        code = d.get("code") or entity_id
        return f"ach:{code or 'unknown'}"
    if type == "milestone_unlocked":
        return f"milestone:{entity_id or d.get('milestone') or 'unknown'}"
    if type in ("gift_booked", "gift_confirmed", "follow_request"):
        return f"{type}:{entity_id or 'unknown'}"
    if type == "message_request":
        # одна нить на диалог — повторные сообщения-запросы бампают, а не спамят
        return f"message_request:{entity_id or 'unknown'}"
    return f"{type}:{entity_id or 'na'}"


async def upsert_notification(
    db: AsyncSession,
    *,
    user_id: UUID,
    type: str,
    dedup_key: str,
    actor_id: UUID | None = None,
    entity_type: str | None = None,
    entity_id: str | None = None,
    data: dict[str, Any] | None = None,
    push_title: str | None = None,
    push_body: str | None = None,
    push_image: str | None = None,
    push_cap_key: str | None = None,
    priority: int = PRIORITY_FEED,
    merge_data_fn: Callable[[dict, dict], dict] | None = None,
    should_resurface: Callable[[dict, dict], bool] | None = None,
) -> tuple[Notification | None, bool]:
    """Bump-or-create.

    1) Если у юзера уже есть unread запись с этим dedup_key → bump:
       occurrences++, bumped_at=now, data = merge_data_fn(old, new) (если задана).
       Push НЕ слать — юзер ещё не прочитал предыдущий.
       Anti-churn: если задан `should_resurface(old_data, new_data)` и он вернул
       False — данные всё равно мержим (stores не теряем), но bumped_at и
       occurrences НЕ трогаем: строка не всплывает наверх и не крутит «обновлено
       N×» на ре-флипах наличия по той же/худшей цене.
    2) Если последняя запись прочитана, но snoozed_until > now → skip.
    3) Иначе → INSERT. Push идёт, если push_title/body заданы и priority<=2.

    Возвращает (notification|None, is_new_inserted).
    Гонки между воркерами защищены savepoint + retry-bump
    через partial unique index `ix_notifications_user_dedup_unread`.
    """
    if actor_id is not None and actor_id == user_id:
        return None, False  # не уведомляем самого себя

    # Блокировка — здесь, а не в каждом call-site: это единственная воронка
    # всех уведомлений, значит одна проверка закрывает follow, подарки, реакции
    # и всё, что появится позже. Двусторонняя: заблокировавший не хочет видеть
    # активность визави, заблокированный не должен пробиваться пушами.
    # actor_id=None — системное уведомление (вишлист, ачивки), проверять нечего.
    if actor_id is not None and await is_user_blocked(db, user_id, actor_id):
        return None, False

    now = datetime.utcnow()

    bumped = await _find_and_bump_unread(
        db,
        user_id=user_id,
        dedup_key=dedup_key,
        now=now,
        new_data=data,
        priority=priority,
        merge_data_fn=merge_data_fn,
        should_resurface=should_resurface,
    )
    if bumped is not None:
        return bumped, False

    latest_read = await db.scalar(
        select(Notification)
        .where(Notification.user_id == user_id, Notification.dedup_key == dedup_key)
        .order_by(Notification.created_at.desc())
        .limit(1)
    )
    if (
        latest_read is not None
        and latest_read.snoozed_until is not None
        and latest_read.snoozed_until > now
        and priority > PRIORITY_PUSH
    ):
        # snooze активен для тихих/нормальных событий. high-signal (priority=1)
        # прорывается всегда — это «реально важно сейчас».
        return None, False

    notif = Notification(
        user_id=user_id,
        actor_id=actor_id,
        type=type,
        dedup_key=dedup_key,
        entity_type=entity_type,
        entity_id=entity_id,
        data=data or {},
        bumped_at=now,
        priority=priority,
    )
    try:
        async with db.begin_nested():
            db.add(notif)
            await db.flush()
    except IntegrityError:
        # Гонка: между нашим SELECT и INSERT другой воркер вставил unread с
        # тем же dedup_key. Перечитываем и делаем bump.
        logger.debug("upsert_notification race on dedup_key=%s, retrying as bump", dedup_key)
        bumped = await _find_and_bump_unread(
            db,
            user_id=user_id,
            dedup_key=dedup_key,
            now=now,
            new_data=data,
            priority=priority,
            merge_data_fn=merge_data_fn,
            should_resurface=should_resurface,
        )
        return bumped, False

    if push_title and push_body and priority <= PRIORITY_FEED:
        try:
            await send_push(
                db,
                user_id,
                notification_type=type,
                title=push_title,
                body=push_body,
                image=push_image,
                cap_key=push_cap_key,
                data={
                    "notification_id": str(notif.id),
                    "type": type,
                    "dedup_key": dedup_key,
                    "entity_type": entity_type or "",
                    "entity_id": entity_id or "",
                    **(data or {}),
                },
            )
        except Exception:
            logger.exception("Push send failed (notification_id=%s)", notif.id)

    return notif, True


async def _find_and_bump_unread(
    db: AsyncSession,
    *,
    user_id: UUID,
    dedup_key: str,
    now: datetime,
    new_data: dict[str, Any] | None,
    priority: int,
    merge_data_fn: Callable[[dict, dict], dict] | None,
    should_resurface: Callable[[dict, dict], bool] | None = None,
) -> Notification | None:
    existing = await db.scalar(
        select(Notification)
        .where(
            Notification.user_id == user_id,
            Notification.dedup_key == dedup_key,
            Notification.read_at.is_(None),
        )
        .limit(1)
    )
    if existing is None:
        return None

    # Anti-churn: решаем ДО мержа, всплывать ли строка. По умолчанию — да
    # (историческое поведение). Guard сравнивает старые/новые data (напр. цену).
    old_data = dict(existing.data or {})
    resurface = True
    if should_resurface is not None:
        try:
            resurface = should_resurface(old_data, new_data or {})
        except Exception:
            resurface = True  # на ошибке guard'а не роняем нить — ведём себя как раньше

    if merge_data_fn is not None:
        existing.data = merge_data_fn(old_data, new_data or {})
    elif new_data:
        merged = dict(old_data)
        merged.update(new_data)
        existing.data = merged

    if resurface:
        existing.occurrences = (existing.occurrences or 1) + 1
        existing.bumped_at = now
        if priority < (existing.priority or PRIORITY_FEED):
            existing.priority = priority
    await db.flush()
    return existing


async def create_notification(
    db: AsyncSession,
    *,
    user_id: UUID,
    type: str,
    actor_id: UUID | None = None,
    entity_type: str | None = None,
    entity_id: str | None = None,
    data: dict[str, Any] | None = None,
    push_title: str | None = None,
    push_body: str | None = None,
    push_image: str | None = None,
    push_cap_key: str | None = None,
    flush: bool = True,  # сохраняем kwarg для совместимости
) -> Notification:
    """LEGACY-фасад. Сохраняет контракт старых call-site'ов в gifts/users/collections.

    Внутри использует `upsert_notification` с автоматически выведенным dedup_key.
    Возвращает Notification (или «фейковый» при self-actor — для совместимости с
    прежним кодом, который не ожидал None).
    """
    dedup_key = _default_dedup_key(type, entity_id, actor_id, data)
    notif, _ = await upsert_notification(
        db,
        user_id=user_id,
        type=type,
        dedup_key=dedup_key,
        actor_id=actor_id,
        entity_type=entity_type,
        entity_id=entity_id,
        data=data,
        push_title=push_title,
        push_body=push_body,
        push_image=push_image,
        push_cap_key=push_cap_key,
        priority=PRIORITY_FEED,
    )
    if notif is None:
        # Self-actor / snooze — старый API возвращал «фейковый» объект.
        return Notification(
            user_id=user_id,
            type=type,
            dedup_key=dedup_key,
            data=data or {},
            bumped_at=datetime.utcnow(),
            priority=PRIORITY_FEED,
        )
    return notif


def apply_snooze_on_read(notif: Notification) -> None:
    """Выставить `snoozed_until` по лестнице. Идемпотентно, безопасно повторять.

    Уровень snooze хранится в `data.snooze_level` и инкрементируется при каждом
    прочтении. После последнего шага лестницы интервал держится максимальным.
    Вызывается из API mark_read/mark_all_read.
    """
    ladder = SNOOZE_LADDER.get(notif.type)
    if not ladder:
        return
    level = int((notif.data or {}).get("snooze_level", 0))
    interval = ladder[min(level, len(ladder) - 1)]
    base = notif.read_at or datetime.utcnow()
    notif.snoozed_until = base + interval
    new_data = dict(notif.data or {})
    new_data["snooze_level"] = level + 1
    notif.data = new_data


def merge_wishlist_stores(old: dict, new: dict) -> dict:
    """merge_data_fn для wishlist_in_stock.

    Сливает stores[] (дедуп по store_slug), пересчитывает min_price_rub и
    store_count. Сохраняет неосновные поля из `old` (cover_url, record_title).
    """
    merged: dict[str, Any] = dict(old or {})
    # Базовые поля «инициатора» не теряем: запоминаем первый встреченный record_title/cover.
    for k in ("record_title", "record_artist", "cover_url", "record_id"):
        if not merged.get(k) and new.get(k):
            merged[k] = new[k]

    stores: list[dict[str, Any]] = list(merged.get("stores") or [])
    new_store = new.get("store")
    if isinstance(new_store, dict):
        slug = new_store.get("slug")
        idx = next(
            (i for i, s in enumerate(stores) if slug and s.get("slug") == slug),
            None,
        )
        if idx is not None:
            stores[idx] = {**stores[idx], **new_store}
        else:
            stores.append(new_store)

    merged["stores"] = stores
    prices = [s.get("price_rub") for s in stores if s.get("price_rub") is not None]
    merged["min_price_rub"] = min(prices) if prices else merged.get("min_price_rub")
    merged["store_count"] = len(stores)
    return merged
