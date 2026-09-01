# План: Wishlist Price Alerts — колокольчик, price-drop, история цен

> Дополняет [PLAN_NOTIFICATIONS_V2.md](../social/PLAN_NOTIFICATIONS_V2.md). Не дублирует транспорт/дедуп/snooze — переиспользует их. Здесь только то, чего в v2 нет: **per-item подписка (bell)**, **живой `wishlist_price_drop`**, **история цен**.

## Содержание
- [Проблема](#проблема)
- [Что уже есть](#что-уже-есть)
- [Целевая модель](#целевая-модель)
- [Волна A — Bell (per-item push opt-in)](#волна-a--bell)
- [Волна B — price_history + price_drop producer](#волна-b--price_history--price_drop-producer)
- [Волна C — порог цены + график динамики](#волна-c--порог-цены--график)
- [Acceptance Criteria](#acceptance-criteria)
- [Открытые вопросы](#открытые-вопросы)

---

## Проблема

Сейчас **вся** вишка живёт в одном режиме: 15-мин джоба пишет тихие in-app нити (`PRIORITY_QUIET`, без push), раз в неделю — один digest-push. Гигиена отличная, но:

1. Нельзя сказать «эту одну пластинку не хочу пропустить» → нет мгновенного push-опт-ина.
2. `wishlist_price_drop` объявлен во всех слоях (snooze-ladder, push-pref, stale-types, mobile-types) — но **продюсера нет**, тип мёртв.
3. `StoreListing.price_rub` хранит только текущее значение → **историю/динамику построить не из чего**.

Цель: юзер жмёт 🔔 на нужной пластинке → мгновенный push при «появилась / появилась цена / подешевела». Остальное — как сейчас, тихо + недельный digest. Плюс копим историю цен под будущий график.

## Что уже есть (переиспользуем, не трогаем)

- **Push-транспорт**: [`push.py`](../../../Backend/app/services/push.py) — Expo API, batch, retry, freq-cap 1/тип/час, quiet hours.
- **`upsert_notification`** ([`notification_service.py:80`](../../../Backend/app/services/notification_service.py)) — bump-or-create. **Ключевое:** если передать `priority=PRIORITY_PUSH (1)` + `push_title`/`push_body` → push уходит немедленно И пробивает snooze (`priority > PRIORITY_PUSH` в snooze-гейте). Механизм колокольчика уже встроен — надо лишь прокинуть per-item.
- **Крауль-триггер in_stock**: [`notification_tasks.py`](../../../Backend/app/tasks/notification_tasks.py) `emit_wishlist_in_stock` (15 мин) + `emit_weekly_wishlist_digest` (пн 10:00).
- **Точка записи листингов**: `_upsert_listing` ([`runner.py:184`](../../../Backend/app/services/scrapers/runner.py)) — INSERT…ON CONFLICT DO UPDATE. Единственное место, где меняется `price_rub`/`status`. Сюда врезаем снапшот и price-drop детект.
- **UI-настройки**: [`settings/notifications.tsx`](../../../Mobile/app/settings/notifications.tsx) — глобальный тумблер «Снова в продаже» (`notify_wishlist_in_stock`).

## Целевая модель

Два уровня, оба уже поддержаны механикой приоритетов:

| Уровень | Кто выбирает | Приоритет | Push |
|---|---|---|---|
| **Subscribed** (bell вкл) | юзер per-item | `PRIORITY_PUSH (1)` | мгновенно, пробивает snooze, свой cap |
| **Watched** (bell выкл, дефолт) | автоматом на всю вишку | `PRIORITY_QUIET (3)` | нет, только лента + недельный digest |

Глобальный тумблер `notify_wishlist_in_stock` остаётся мастер-килом: выкл → ни push, ни bell не шлют (уже работает через `PUSH_PREFERENCE_FIELD`).

---

## Волна A — Bell

**Задача:** per-item подписка → мгновенный push на in_stock. Самая дешёвая, полезная сразу, не ждёт истории цен.

### Schema

Миграция `add_wishlist_item_notify`:

```python
# wishlist_items:
op.add_column("wishlist_items", sa.Column(
    "notify_mode", sa.String(16), nullable=False, server_default="watched"))
# 'watched' (дефолт, тихо) | 'subscribed' (bell → push)
op.create_index("ix_wishlist_items_subscribed", "wishlist_items",
    ["record_id"], postgresql_where=sa.text("notify_mode = 'subscribed'"))
```

`WishlistItem.notify_mode: Mapped[str]` в [`models/wishlist.py`](../../../Backend/app/models/wishlist.py).

> Порог цены (`price_threshold_rub`) добавляем в **Волне C**, не сейчас — чтобы A ушла быстро.

### API

- `WishlistItemUpdate` (+ `notify_mode: str | None`), `WishlistItemResponse` (+ `notify_mode`) в [`schemas/wishlist.py`](../../../Backend/app/schemas/wishlist.py).
- `PUT /wishlists/records/{item_id}` уже принимает `WishlistItemUpdate` — расширяем валидацией (`watched|subscribed`). Отдельный endpoint не нужен.

### Producer (правка существующего джоба)

В `emit_wishlist_in_stock._run` ([`notification_tasks.py`](../../../Backend/app/tasks/notification_tasks.py)) при сборке нити на `WishlistItem`:

```python
subscribed = wi.notify_mode == "subscribed"
notif, is_new = await upsert_notification(
    db, user_id=owner_id, type="wishlist_in_stock",
    dedup_key=f"wishlist_in_stock:{record.id}",
    entity_type="record", entity_id=str(record.id),
    data={...},  # как сейчас
    priority=PRIORITY_PUSH if subscribed else PRIORITY_QUIET,
    push_title=(f"«{record.title}» снова в продаже" if subscribed else None),
    push_body=(f"от {int(min_price)} ₽" if subscribed and min_price else "Появилась в продаже") if subscribed else None,
    push_image=getattr(record, "cover_image_url", None),
    merge_data_fn=merge_wishlist_stores,
)
```

Watched-ветка — байт-в-байт как сейчас (тихо). Subscribed — push через уже готовый путь. Никаких новых слоёв.

### Push-гигиена для subscribed

- **Свой cap-slot**: `send_push(..., cap_key=f"wl_item:{record.id}")` — 1 push/час на *пластинку*, не на весь тип. Иначе первая подписка съест часовой cap для всех.
- Quiet hours / глобальный тумблер / freq-cap — уже применяются внутри `send_push`, ничего не добавляем.
- `wishlist_price_drop` в Волне A **не трогаем** (нет producer'а) — только in_stock.

### UI

- **Bell на карточке item** ([`app/wishlist-folder/[id].tsx`](../../../Mobile/app/wishlist-folder/) + карточка в вишке): иконка `bell`/`bell-slash` (уже есть в [`Icon.tsx`](../../../Mobile/components/ui/Icon.tsx), используется в чатах для mute). Тап → `PUT notify_mode`. Оптимистичный апдейт в Zustand.
- Микро-состояние: `bell-slash` серый (watched) → `bell` brand-цвет + лёгкий scale-in при вкл. Инвок `make-interfaces-feel-better` на этот тумблер.
- Первый тап на bell → one-time тултип «Пришлём пуш, как только появится в продаже или подешевеет».

**Волна A ≈ 1 таблица-колонка + 1 правка джоба + bell-тумблер. Ценность сразу, риск минимальный.**

---

## Волна B — price_history + price_drop producer

**Задача:** оживить `wishlist_price_drop` + начать копить историю (фундамент под график).

### Schema

Миграция `add_price_history`:

```python
op.create_table("listing_price_history",
    sa.Column("id", UUID, primary_key=True),
    sa.Column("listing_id", UUID, sa.ForeignKey("store_listings.id", ondelete="CASCADE"), nullable=False),
    sa.Column("record_id", UUID, sa.ForeignKey("records.id", ondelete="SET NULL"), nullable=True),  # денорм для запросов по record
    sa.Column("price_rub", sa.Numeric(12, 2), nullable=True),
    sa.Column("status", sa.String(32), nullable=False),  # in_stock/out_of_stock — ловим и уход в 0 листингов
    sa.Column("captured_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
)
op.create_index("ix_price_history_record_time", "listing_price_history", ["record_id", "captured_at"])
op.create_index("ix_price_history_listing_time", "listing_price_history", ["listing_id", "captured_at"])
```

> Пишем снапшот **только при изменении** (price или status), не каждый проход — иначе таблица растёт мусором. Крауль идёт ~ежедневно; при отсутствии изменений строку не добавляем.

### Snapshot + drop-детект в `_upsert_listing`

`_upsert_listing` ([`runner.py:184`](../../../Backend/app/services/scrapers/runner.py)) сейчас делает ON CONFLICT DO UPDATE «вслепую». Меняем на read-then-write, чтобы видеть старое значение:

```python
# 1. SELECT existing (price_rub, status) by (store_id, external_id)
# 2. UPSERT как сейчас
# 3. if existing is None or existing.price != new.price or existing.status != new.status:
#        INSERT listing_price_history(listing_id, record_id=matched_record_id, price, status, now)
# 4. if existing and existing.price and new.price and new.price < existing.price * (1 - MIN_DROP_PCT):
#        собрать (record_id, old_price, new_price) в список price_drops прогона
```

`MIN_DROP_PCT = 0.05` (порог значимости — не шумим на ±2%). Список `price_drops` отдаётся в отдельный producer (не в scraper — разделяем ответственность).

### price_drop producer

Новый джоб `emit_wishlist_price_drop_notifications` (interval 15 мин, симметрично in_stock), либо расширение существующего — читает listing_price_history за окно, находит падения, матчит на WishlistItem:

```python
upsert_notification(
    db, user_id=owner_id, type="wishlist_price_drop",
    dedup_key=f"wishlist_price_drop:{record.id}",
    data={"record_id", "old_price_rub", "new_price_rub", "drop_pct", "store": {...}},
    priority=PRIORITY_PUSH if wi.notify_mode == "subscribed" else PRIORITY_QUIET,
    push_title=(f"«{record.title}» подешевела" if subscribed else None),
    push_body=(f"{int(old)} → {int(new)} ₽" if subscribed else None),
)
```

Snooze-ladder для `wishlist_price_drop` уже задан (`[14 дней]` в [`notification_service.py:43`](../../../Backend/app/services/notification_service.py)) — не трогаем.

### Регистрация

`scheduler.add_job(emit_wishlist_price_drop_notifications, 'interval', minutes=15, ...)` в [`main.py`](../../../Backend/app/main.py) рядом со строкой 130.

---

## Волна C — порог цены + график

**Задача:** «хочу дешевле X» + визуальная динамика. Строится поверх B (нужна история).

### Порог

- `wishlist_items.price_threshold_rub: Numeric | null`. Bell-поповер: «Уведомить когда дешевле ___ ₽».
- В price_drop/in_stock producer: если `threshold` задан → push только при `min_price <= threshold`; иначе — на любое падение (как в B).

### График динамики

- `GET /records/{id}/price-history?days=90` → аггрегат из `listing_price_history` (min price по дням, число листингов). Кэш 6ч.
- Mobile: спарклайн на карточке record + полный график на детали. Метки: историческая нижняя цена (сильный сигнал желания), «сейчас vs медиана 90д».
- Дизайн графика — через skill `dataviz`.

---

## Acceptance Criteria

**Волна A**
- [ ] Bell на item тогглит `notify_mode`, оптимистично, переживает рестарт.
- [ ] Subscribed item → push в течение ≤15 мин после появления in_stock; пробивает активный snooze.
- [ ] Watched item → поведение не изменилось (тихая лента + недельный digest).
- [ ] Глобальный `notify_wishlist_in_stock=false` → ни push по bell, ни digest.
- [ ] Cap: две subscribed-пластинки появились одновременно → два push (cap по item, не по типу), но одна и та же — не чаще 1/час.
- [ ] Quiet hours глушат subscribed-push.

**Волна B**
- [ ] `listing_price_history` пишется только при смене price/status.
- [ ] Падение <5% push не рождает; ≥5% — рождает `wishlist_price_drop`.
- [ ] Subscribed → push «подешевела»; watched → тихая нить.

**Волна C**
- [ ] Порог: push только при цене ≤ threshold.
- [ ] `/price-history` отдаёт дневной аггрегат; график рисуется.

## Решения (locked 2026-07-13)

1. **Ретеншн `listing_price_history`** — ✅ **чистить >1 года** cleanup-джобой (по образцу `cleanup_covers`, cron ночью). Заложить в Волну B вместе с таблицей.
2. **`_upsert_listing`** — ✅ **CTE `UPDATE … RETURNING old`** (один roundtrip, без удвоения запросов). Реализовать в Волне B.
3. **`wishlist_in_stock_alt` = «аналог»** — ✅ **в скоуп** (Волна B). Критерий аналога = общий `records.discogs_master_id` (разные прессинги одного мастера), кроме самой заказанной пластинки. Producer симметричен in_stock/price_drop.
4. **Порог цены** — ✅ **колонка `price_threshold_rub` заведена уже в Волне A** (миграция `20260713_wishlist_item_notify`). Producer применяет порог для subscribed. UI-поповер порога — Волна B/C.

## Статус реализации

**Волна A — готова (2026-07-13), не задеплоена:**
- Миграция `20260713_wishlist_item_notify` (`notify_mode`, `price_threshold_rub`, partial index) — **требует `alembic upgrade head` на проде**.
- Модель/схемы/API `PUT /wishlists/records/{id}` (notify_mode + threshold).
- `upsert_notification` — новый параметр `push_cap_key` (per-item часовой cap).
- `emit_wishlist_in_stock` — subscribed → `PRIORITY_PUSH` + push с порогом + `cap_key=wl_item:{record}`; watched без изменений.
- Mobile: `WishlistItem.notify_mode/price_threshold_rub`, `api.updateWishlistItem`, `store.setWishlistNotifyMode` (оптимистично), bell-тумблер на `record/[id]` (haptics + разовый тултип).

**Волна B — готова (2026-07-13), не задеплоена:**
- Миграция `20260713_listing_price_history` (таблица + 3 индекса) — **`alembic upgrade head`**.
- Модель `ListingPriceHistory` + регистрация в `models/__init__`.
- `_upsert_listing` → prev-CTE `RETURNING old` (один roundtrip); снапшот в history при смене price||status.
- `emit_wishlist_price_drop_notifications` (LAG по history, падение ≥5%) — interval 15м.
- Alt/аналог: `_emit_alt_versions` в 15-мин in_stock job — матч по общему `discogs_master_id`, тип `wishlist_in_stock_alt`.
- `cleanup_price_history` — cron 03:30, DELETE >365 дней.
- Реестры: push-pref/stale-types/dedup-helper дополнены `wishlist_in_stock_alt` (SNOOZE_LADDER уже был).
- Mobile: deep-link `alt` → record (типы и тексты карточек уже были из V2).

**Волна C — готова (2026-07-13), не задеплоена:**
- `GET /records/{id}/price-history?days=` — дневной min in_stock + историческая нижняя.
- Порог цены: long-press колокольчика → `Alert.prompt` (iOS) → `setWishlistPriceThreshold`; бейдж-точка на колокольчике.
- `PriceSparkline` (react-native-svg) на `record/[id]` — линия динамики + «сейчас/мин», пунктир дна.

**Открытый край:** порог задаётся только на iOS (`Alert.prompt`); Android — снять/оставить. Полноценный ввод порога на Android = отдельный модал (за скоупом).
