# План: Нотификации v2 — дедуп, snooze, дайджест, видимый бейдж

> **Проблема, которая запустила работу:** на скриншоте от 2026-05-25 в ленте «Ты» один и тот же `wishlist_in_stock` по «Mordechai» приходит **4 раза за 6 дней** (20ч, 2д, 3д, 6д). Аналогично «Mountain» 2 раза, «A Moon Shaped Pool» 1 раз. Юзер задолбан. Бейдж на аватаре есть, но визуально незаметен.
>
> **Корневая причина:** `DEDUP_HOURS=24` в [`Backend/app/tasks/notification_tasks.py`](../../../Backend/app/tasks/notification_tasks.py) защищает от повтора только в пределах суток. Каждый sold→in_stock цикл магазина (или касание `StoreListing.updated_at`) после 25+ часов снова порождает новую запись `Notification`.

## Содержание

1. [Что уже есть](#что-уже-есть-инвентарь)
2. [Архитектура v2 — принципы](#архитектура-v2--принципы)
3. [Schema-изменения](#schema-изменения)
4. [Лестница типов событий](#лестница-типов-событий)
5. [`upsert_notification` — bump-or-create](#upsert_notification--bump-or-create)
6. [Дайджест >5/день](#дайджест-5день)
7. [Frequency cap → по dedup_key](#frequency-cap--по-dedup_key)
8. [UI: bump-aware карточка, snooze, видимый бейдж](#ui-bump-aware-карточка-snooze-видимый-бейдж)
9. [iOS push v2 (Волна C)](#ios-push-v2-волна-c)
10. [Порядок волн](#порядок-волн)

---

## Что уже есть (инвентарь)

**Backend:**
- [`Backend/app/models/notification.py`](../../../Backend/app/models/notification.py) — модель `Notification(user_id, actor_id, type, entity_type, entity_id, data JSONB, created_at, read_at)`. Индексы `(user_id, created_at)`, `(user_id, read_at)`.
- 7 типов: `follow_request`, `new_follower`, `gift_booked`, `gift_confirmed`, `wishlist_in_stock`, `wishlist_price_drop` (не эмиттится), `achievement_unlocked` (+ `milestone_unlocked`).
- [`Backend/app/services/notification_service.py:create_notification`](../../../Backend/app/services/notification_service.py) — единая точка входа.
- [`Backend/app/services/push.py:send_push`](../../../Backend/app/services/push.py) — Expo, **frequency cap = 1 push/час/(user,type)** через Redis, **Quiet Hours**, маппинг `notification_type → User.notify_*`, авточистка протухших токенов.
- [`Backend/app/tasks/notification_tasks.py:emit_wishlist_in_stock_notifications`](../../../Backend/app/tasks/notification_tasks.py) — APScheduler каждые 15 мин, **DEDUP_HOURS=24** по `(user, record)`.
- `User`: `push_token`, `notify_*` (9 флагов), `quiet_hours_*`.

**Mobile:**
- [`Mobile/app/notifications.tsx`](../../../Mobile/app/notifications.tsx) — экран `SectionList` с date-buckets, 2 таба (Ты/Подписки), swipe markRead/delete, long-press menu «отключить тип».
- [`Mobile/lib/notificationsStore.ts`](../../../Mobile/lib/notificationsStore.ts) — Zustand, оптимистичный markRead, `pendingNew` (push'и пока экран открыт).
- [`Mobile/app/_layout.tsx`](../../../Mobile/app/_layout.tsx) — Expo push-listener, foreground → `inAppToast` (OS-баннер подавлен), tap → deep-link.
- [`Mobile/components/Header.tsx:77`](../../../Mobile/components/Header.tsx) — **красная точка 10×10 на аватаре уже есть** (`hasUnread = unreadCount > 0 || pendingNew > 0`), но визуально незаметна.
- [`Mobile/app/settings/notifications.tsx`](../../../Mobile/app/settings/notifications.tsx) — toggle'ы по группам + Quiet Hours.

---

## Архитектура v2 — принципы

1. **Один record — одна «живая» нить** per user. Если у юзера в ленте есть unread алерт по «Mordechai», новый алерт не создаёт вторую запись — он **обновляет** существующую (`occurrences++`, `bumped_at=now`, в `data.stores[]` аппендится новый магазин с ценой).
2. **Тихая экспоненциальная пауза (snooze ladder).** После прочтения юзером — следующий алерт по этому же record возможен не раньше: **7д → 30д → 90д**. Сбрасывается, если событие явно значимое (цена упала на ≥15%, появилась первая версия другого пресса master'а).
3. **Дайджест порога.** Если за окно (24ч) у юзера ≥5 новых `wishlist_in_stock` — схлопывать в 1 запись «5 пластинок из вишлиста снова в продаже».
4. **Значимость > частота.** Push отправляется только при `priority<=2`. Re-stock тривиальный (`priority=3`) — только в фид, без push.
5. **Видимый бейдж.** Красный pill с числом непрочитанных (1, 2, 9, 9+) на аватаре, со scale-анимацией при росте.

---

## Schema-изменения

### Миграция `add_notification_dedup_v2`

```python
revision = "20260525_notif_v2"
down_revision = "20260525_merge"

def upgrade():
    op.add_column("notifications", sa.Column("dedup_key", sa.Text(), nullable=True))
    op.add_column("notifications", sa.Column("bumped_at", sa.DateTime(), nullable=True))
    op.add_column("notifications", sa.Column("occurrences", sa.Integer(), nullable=False, server_default="1"))
    op.add_column("notifications", sa.Column("snoozed_until", sa.DateTime(), nullable=True))
    op.add_column("notifications", sa.Column("priority", sa.SmallInteger(), nullable=False, server_default="2"))

    # Backfill: dedup_key по type + entity_id/data
    op.execute("""
        UPDATE notifications SET dedup_key = type || ':' || COALESCE(entity_id, '');
        UPDATE notifications SET bumped_at = created_at WHERE bumped_at IS NULL;
    """)
    op.alter_column("notifications", "dedup_key", nullable=False)
    op.alter_column("notifications", "bumped_at", nullable=False)

    # Partial unique: одновременно один активный (unread) алерт на (user, dedup_key)
    op.create_index(
        "ix_notifications_user_dedup_unread",
        "notifications",
        ["user_id", "dedup_key"],
        unique=True,
        postgresql_where=sa.text("read_at IS NULL"),
    )
    op.create_index(
        "ix_notifications_snooze",
        "notifications",
        ["user_id", "dedup_key", "snoozed_until"],
    )

def downgrade():
    op.drop_index("ix_notifications_snooze", "notifications")
    op.drop_index("ix_notifications_user_dedup_unread", "notifications")
    op.drop_column("notifications", "priority")
    op.drop_column("notifications", "snoozed_until")
    op.drop_column("notifications", "occurrences")
    op.drop_column("notifications", "bumped_at")
    op.drop_column("notifications", "dedup_key")
```

### Семантика полей

| Поле | Зачем |
|---|---|
| `dedup_key TEXT NOT NULL` | Канонический ключ свёртки. `wishlist_in_stock:<record_id>`, `new_follower:<actor_id>`, `digest:wl:<YYYY-MM-DD>` |
| `bumped_at TIMESTAMP NOT NULL` | Когда событие повторилось последний раз — для сортировки и UI «обновлено 2ч назад» |
| `occurrences INT NOT NULL DEFAULT 1` | Сколько раз свёрнуто. Показываем «в N магазинах» |
| `snoozed_until TIMESTAMP NULL` | Если юзер прочитал и snooze активен — до этой даты новые с тем же dedup_key не создаём |
| `priority SMALLINT NOT NULL DEFAULT 2` | 1=push+badge, 2=feed+badge, 3=feed only (без push) |
| `ix_notifications_user_dedup_unread` partial unique | Защита от гонок: два бэкенд-воркера одновременно не вставят дубликат |

---

## Лестница типов событий

| Тип | priority | dedup_key | snooze после read | merge_data | push? |
|---|---|---|---|---|---|
| `follow_request` | 1 | `follow_request:<request_id>` | удаляется при ответе | — | да |
| `new_follower` | 1 | `new_follower:<actor_id>` | 365д | — | да |
| `gift_booked` | 1 | `gift_booked:<booking_id>` | — | — | да |
| `gift_confirmed` | 1 | `gift_confirmed:<booking_id>` | — | — | да |
| `wishlist_in_stock` (первый матч) | 1 | `wishlist_in_stock:<record_id>` | 7д→30д→90д | `stores[] += {store, price}`, `min_price = min(...)` | да |
| `wishlist_in_stock` (повторный re-stock) | 3 | то же | то же | bump | **нет push**, только в фид |
| `wishlist_in_stock_alt` (другая версия master) | 1 | `wishlist_alt:<master_id>` | 30д | `versions[] += {…}` | да |
| `wishlist_price_drop` (≥15%) | 1 | `wishlist_price_drop:<record_id>` | 14д | `low_price=min(old,new)` | да |
| `digest:wishlist_in_stock` | 2 | `digest:wl:<YYYY-MM-DD>` | — | `items[]` | 1 push/день максимум |
| `achievement_unlocked` | 2 | `ach:<code>` | — | — | да (cap 1/час) |
| `milestone_unlocked` | 2 | `milestone:<code>` | — | — | да |

### Первый vs повторный wishlist_in_stock

Считается по таблице самой `notifications`:
- Если у юзера **никогда не было** `wishlist_in_stock:<record_id>` → `priority=1` (push).
- Если была за последние 90 дней → `priority=3` (bump в ленту, без push).
- Если последняя была >90 дней назад → снова `priority=1`.

---

## `upsert_notification` — bump-or-create

```python
# Backend/app/services/notification_service.py

from typing import Callable
from datetime import datetime, timedelta
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

SNOOZE_LADDER = {
    "wishlist_in_stock": [timedelta(days=7), timedelta(days=30), timedelta(days=90)],
    "wishlist_in_stock_alt": [timedelta(days=30)],
    "wishlist_price_drop": [timedelta(days=14)],
    "new_follower": [timedelta(days=365)],
}


async def upsert_notification(
    db: AsyncSession,
    *,
    user_id: UUID,
    type: str,
    dedup_key: str,
    actor_id: UUID | None = None,
    entity_type: str | None = None,
    entity_id: str | None = None,
    data: dict | None = None,
    push_title: str | None = None,
    push_body: str | None = None,
    priority: int = 2,
    merge_data_fn: Callable[[dict, dict], dict] | None = None,
) -> tuple[Notification | None, bool]:
    """
    Upsert-логика:
      1) Найти самую свежую запись (user_id, dedup_key).
      2) Если unread → BUMP: occurrences++, bumped_at=now, merge data. Push НЕ слать.
      3) Если read + snoozed_until > now → SKIP, не создаём.
      4) Иначе → INSERT. Push шлём, если priority<=2.
    Возвращает (notification | None, is_new_inserted).
    """
    if actor_id is not None and actor_id == user_id:
        return None, False  # не уведомляем себя

    latest = await db.scalar(
        select(Notification)
        .where(Notification.user_id == user_id, Notification.dedup_key == dedup_key)
        .order_by(Notification.created_at.desc())
        .limit(1)
    )
    now = datetime.utcnow()

    # 2) BUMP
    if latest is not None and latest.read_at is None:
        latest.occurrences = (latest.occurrences or 1) + 1
        latest.bumped_at = now
        if merge_data_fn is not None:
            latest.data = merge_data_fn(latest.data or {}, data or {})
        if priority < (latest.priority or 2):
            latest.priority = priority
        return latest, False

    # 3) SNOOZE active
    if latest is not None and latest.snoozed_until and latest.snoozed_until > now:
        return None, False

    # 4) INSERT
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
    db.add(notif)
    await db.flush()

    if push_title and push_body and priority <= 2:
        try:
            await send_push(
                db, user_id,
                notification_type=type,
                title=push_title,
                body=push_body,
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


def apply_snooze_on_read(notif: Notification, snooze_level_data_key: str = "snooze_level"):
    """Вызывается из mark_read. Выставляет snoozed_until по lestnice."""
    ladder = SNOOZE_LADDER.get(notif.type)
    if not ladder:
        return
    level = int((notif.data or {}).get(snooze_level_data_key, 0))
    interval = ladder[min(level, len(ladder) - 1)]
    notif.snoozed_until = (notif.read_at or datetime.utcnow()) + interval
    new_data = dict(notif.data or {})
    new_data[snooze_level_data_key] = level + 1
    notif.data = new_data
```

### `merge_data_fn` для wishlist_in_stock

```python
def merge_wishlist_stores(old: dict, new: dict) -> dict:
    """Сливает stores[] и пересчитывает min_price."""
    merged = dict(old)
    stores = list(merged.get("stores") or [])
    new_store = new.get("store")
    if new_store:
        # Дедуп по store_slug — обновляем цену
        idx = next((i for i, s in enumerate(stores) if s.get("slug") == new_store.get("slug")), None)
        if idx is not None:
            stores[idx] = new_store
        else:
            stores.append(new_store)
    merged["stores"] = stores
    prices = [s.get("price_rub") for s in stores if s.get("price_rub") is not None]
    merged["min_price_rub"] = min(prices) if prices else None
    merged["store_count"] = len(stores)
    return merged
```

---

## Дайджест >5/день

В конце `emit_wishlist_in_stock_notifications`, перед коммитом:

```python
DIGEST_THRESHOLD = 5

# Группируем созданные нотификации по user_id
per_user = defaultdict(list)
for notif in emitted_list:
    per_user[notif.user_id].append(notif)

for user_id, notifs in per_user.items():
    if len(notifs) < DIGEST_THRESHOLD:
        continue
    # 1. Удалить (или пометить hidden) индивидуальные
    for n in notifs:
        await db.delete(n)
    # 2. INSERT digest
    today = datetime.utcnow().date().isoformat()
    digest, _ = await upsert_notification(
        db,
        user_id=user_id,
        type="digest_wishlist_in_stock",
        dedup_key=f"digest:wl:{today}",
        priority=2,
        data={
            "count": len(notifs),
            "items": [
                {
                    "record_id": n.entity_id,
                    "record_title": (n.data or {}).get("record_title"),
                    "cover_url": (n.data or {}).get("cover_url"),
                    "min_price_rub": (n.data or {}).get("min_price_rub"),
                }
                for n in notifs[:10]  # превью 10
            ],
        },
        push_title=f"{len(notifs)} пластинок из вишлиста снова в продаже",
        push_body="Открой, чтобы посмотреть",
    )
```

UI digest-карточки в [`NotificationItem.tsx`](../../../Mobile/components/notifications/NotificationItem.tsx) — раскрывающийся аккордеон с превью первых 3 обложек.

---

## Frequency cap → по dedup_key

В [`Backend/app/services/push.py:189`](../../../Backend/app/services/push.py):

```python
# Было:
acquired = await cache.set_nx("push_cap", f"{user_id}:{notification_type}", "1", ttl=3600)

# Станет:
acquired = await cache.set_nx("push_cap", f"{user_id}:{dedup_key}", "1", ttl=3600)
```

Сейчас «Mountain» и «Mordechai» делят один cap по типу `wishlist_in_stock`, и юзер получит **только один** из двух пушей в час. С dedup_key — оба придут (но всё равно не более 1 пуша на каждую пластинку в час).

Плюс глобальный мягкий cap «не больше 5 push/час/юзер любых типов» — защита от каскадов после долгого офлайна юзера.

---

## UI: bump-aware карточка, snooze, видимый бейдж

### Бейдж на аватаре — pill с числом

В [`Mobile/components/Header.tsx:77`](../../../Mobile/components/Header.tsx) сейчас круглая точка 10×10. Заменяем на pill:

```tsx
{unreadCount > 0 && (
  <Animated.View style={[styles.badge, animatedScale]}>
    <Text style={styles.badgeText}>{unreadCount > 9 ? '9+' : unreadCount}</Text>
  </Animated.View>
)}

// styles:
badge: {
  position: 'absolute', top: -4, right: -4,
  minWidth: 18, height: 18, borderRadius: 9,
  paddingHorizontal: 4,
  backgroundColor: Colors.error,
  borderWidth: 2, borderColor: Colors.background,
  alignItems: 'center', justifyContent: 'center',
},
badgeText: {
  color: Colors.background,
  fontSize: 10,
  fontFamily: 'Inter_700Bold',
  lineHeight: 12,
},
```

Анимация при росте `unreadCount`: `scale 1.0 → 1.25 → 1.0` пружинка + `Haptics.selectionAsync()`.

`pendingNew` НЕ показывать на аватаре (он сбрасывается при открытии ленты и добавляет шум) — оставить только для in-screen pill «Показать N новых».

### NotificationItem — bump-ware текст

В [`Mobile/components/notifications/NotificationItem.tsx:buildText`](../../../Mobile/components/notifications/NotificationItem.tsx) для `wishlist_in_stock` с `occurrences > 1`:

```tsx
case 'wishlist_in_stock': {
  const title = (data.record_title as string) ?? 'пластинка';
  const stores = data.store_count as number | undefined;
  const minPrice = data.min_price_rub as number | undefined;
  if (item.occurrences && item.occurrences > 1 && stores) {
    return `«${title}» в ${stores} ${pluralStores(stores)}${minPrice ? ` · от ${minPrice}₽` : ''}`;
  }
  return `«${title}» снова в продаже${minPrice ? ` · ${minPrice}₽` : ''}`;
}
```

Под текстом добавить чип `обновлено 2ч назад` (на базе `bumped_at`), если `bumped_at !== created_at`.

### Long-press → snooze per-entity

В текущем меню `notifications.tsx:handleLongPress` добавить:
```
- Не напоминать про «Mordechai» 30 дней
```
вызов: `api.snoozeNotification(item.id, days=30)` → backend `POST /api/notifications/{id}/snooze {days}` → `apply_snooze_on_read(notif, level=manual_30d)`.

### Скрыть устаревшие из ленты

В [`Backend/app/api/notifications.py:list_personal`](../../../Backend/app/api/notifications.py) и `unread_count`:
```python
# wishlist_in_stock/price_drop старше 30 дней — скрываем (висели бы вечно)
STALE_TYPES = ("wishlist_in_stock", "wishlist_price_drop", "digest_wishlist_in_stock")
STALE_AFTER = timedelta(days=30)

# .where(or_(Notification.type.notin_(STALE_TYPES),
#            Notification.created_at >= datetime.utcnow() - STALE_AFTER))
```

---

## iOS push v2 (Волна C)

**Что есть**: Expo push токен регистрируется, backend шлёт через Expo HTTP API. Работает на EAS-билде.

**Что нужно для prod-релиза:**

1. **APNs `.p8` key в Expo Push** (в [expo.dev → credentials](https://expo.dev/)). Без этого Expo не доставит push в TestFlight/AppStore билд.
2. **Entitlement `aps-environment=production`** — EAS добавляет автоматически в `production` профиль. Проверить `Mobile/app.json`.
3. **Notification Categories с actions** (iOS-native UX):
   - `WISHLIST_IN_STOCK` → «Купить» (deep-link на offer) + «Не напоминать»
   - `GIFT_BOOKED` → «Открыть»
   - Регистрируется через `Notifications.setNotificationCategoryAsync` в `_layout.tsx`.
4. **Rich push с обложкой** — `attachments` через mutable-content + Notification Service Extension (Expo plugin), либо проще: thumb только в собственном in-app toast.
5. **Badge на иконке** — `shouldSetBadge: true` в [`_layout.tsx:55`](../../../Mobile/app/_layout.tsx) + бэкенд передаёт `badge: unread_count` в Expo message.
6. **Thread-id для group** — payload `_thread-id: "wishlist" | "gifts" | "social"`. iOS складывает стеком.
7. **Permission priming** — pre-prompt по [PLAN_PROFILE_IMPROVEMENTS](PLAN_PROFILE_IMPROVEMENTS.md) до OS-modal.
8. **Time-Sensitive** для `wishlist_in_stock`: `interruptionLevel: "timeSensitive"` (iOS 15+), в Expo через `_priority: "high"`.
9. **Delivery analytics** — логировать tickets от Expo в Sentry/Amplitude: `MessageRateExceeded`, `MismatchSenderId`.
10. **WebSocket-канал** для unread (расширить `messages-realtime`), polling 30с → fallback 5 мин.

---

## Порядок волн

### Волна A — anti-spam now (1-2 дня)

- `DEDUP_HOURS = 24 → 168` в [`notification_tasks.py:27`](../../../Backend/app/tasks/notification_tasks.py)
- Скрытие из ленты `wishlist_in_stock` старше 30 дней в `list_personal` + `unread_count`
- Атомарный PR, тестим в проде

### Волна B — schema + bump-or-create (1 неделя)

- Миграция `add_notification_dedup_v2` + backfill
- `upsert_notification` сервис + `apply_snooze_on_read`
- Переписать call-sites (notification_tasks, gifts, users, collections)
- Дайджест >5/день
- Mobile types + bump-aware NotificationItem + Header pill с числом + snooze long-press
- Endpoint `POST /api/notifications/{id}/snooze`

### Волна C — iOS push prod-ready (1 неделя)

- APNs `.p8` в Expo, Notification Categories, time-sensitive, thread-id, app icon badge
- Notification Service Extension для rich attachments
- WebSocket-канал unread
- Permission priming

---

## Acceptance Criteria

1. ✅ Один и тот же `wishlist_in_stock` по «Mordechai» приходит **только 1 раз** в течение 7 дней (Волна A).
2. ✅ После прочтения юзером — следующий алерт по тому же record возможен не раньше чем через 7д (Волна B).
3. ✅ Если за день у юзера ≥5 in_stock алертов — приходит 1 digest, не 5 (Волна B).
4. ✅ В ленте: «Mordechai» в 3 магазинах · от 4 490 ₽ — одна карточка вместо трёх (Волна B, bump-aware UI).
5. ✅ На аватаре виден pill `3` / `9+`, а не точка (Волна B).
6. ✅ Long-press → «Не напоминать про X 30 дней» работает (Волна B).
7. ✅ Push доходит в prod TestFlight/AppStore билд (Волна C).
8. ✅ iOS group push'и стеком по thread-id (Волна C).
