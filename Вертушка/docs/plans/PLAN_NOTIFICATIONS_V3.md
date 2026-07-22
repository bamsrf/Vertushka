# PLAN_NOTIFICATIONS_V3 — снижение инфошума + ценная лента

> Продолжение [PLAN_NOTIFICATIONS_V2.md](PLAN_NOTIFICATIONS_V2.md). V2 дал механику
> (dedup_key, watched/subscribed, priority, snooze-лесенка, недельный дайджест,
> radar_status_events). V3 — про **определение «событие»**: показывать только то,
> что меняет решение о покупке; фоновый churn наличия — глушить.

## Принцип

> Уведомление оправдано, только если меняет решение о покупке. Остальное — в
> дайджест или в тишину.

Трёхуровневая модель сигнала:

| Уровень | Что | Канал |
|---|---|---|
| 🔴 HIGH | цена впервые ниже порога · новый исторический минимум · первое появление на радаре вообще | push |
| 🟡 MEDIUM | обычное «снова в наличии» · аналог/другое издание | тихо в ленту, без push |
| ⚫ SUPPRESS | состояние идентично показанному · ре-флип наличия по той же/худшей цене · падение цены < 10% | не показывать |

**«Остался последний экземпляр» — выкинуто:** скраперы не видят количество
(листинг бинарный `in_stock`/`out_of_stock`, поля `quantity` нет). Замена из того
же класса scarcity — `absent` («пропала из наличия» = «маркетплейс продал»).

## Фазы

### Фаза 1 — Anti-churn (✅ сделано)
- `notification_service._find_and_bump_unread`: параметр `should_resurface(old,new)`.
  Строка всплывает наверх (`bumped_at`/`occurrences++`) **только при улучшении
  цены**; ре-флип по той же/худшей цене — тихо мержим stores, но не воскрешаем.
  Это лечит «обновлено 16×» и всплытие складского шума наверх ленты.
- `notification_tasks._resurface_on_price_improvement` подключён к трём upsert:
  wishlist_in_stock, _alt, price_drop.
- `MIN_DROP_PCT` 5% → 10%.

### Фаза 2 — Absent («маркетплейс продал»)  (✅ сделано)
`emit_wishlist_absent_notifications` (джоб, interval 15 мин): matched-листинги,
недавно ушедшие в OUT_OF_STOCK/REMOVED, у которых **не осталось** других in-stock
листингов на ту же запись → `radar_status_event('absent')` (для «Истории» в
шторке цены; уже рендерится в radar-API). Только для `subscribed`. Push НЕ шлём —
исчезновение это летопись, а не алерт. Feed-строку «пропала» отложили: требует
нового типа `wishlist_gone` + рендер на мобилке (см. Открытые вопросы).

### Фаза 3 — Signal tiers  (✅ частично)
- **Исторический минимум** (✅): в price-drop джобе `min(price)` по
  `listing_price_history` (in_stock) → если `new ≤ min` → HIGH, `PRIORITY_PUSH`
  даже для watched, push-текст «новый минимум». Флаг `all_time_low` в data.
- **Первое появление на радаре вообще** (⏳ не сделано): нет ни одного прошлого
  in-stock снапшота по записи → HIGH. Отложено — фаззи-определение, риск без тестов.
- Обычные in_stock/alt остаются QUIET.

### Фаза 4 — Mobile: карточка-дайджест + поп-ап  (✅ сделано)
- `buildWishlistDigest` в `notifications.tsx`: ≥3 непрочитанных `wishlist_in_stock`
  сворачиваются в одну строку «N пластинок снова в продаже» (тип
  `digest_wishlist_in_stock`, синтетический id `__wishlist_digest__`).
- `WishlistDigestSheet.tsx` — bottom-sheet «полка корешков»:
  - тянешь корешок вправо → магазин (`api.trackOfferClick` + `Linking`, affiliate);
  - тап по обложке → `/record/[id]` со всеми листингами.
- Открытие поп-апа гасит unread свёрнутых (`markManyRead`).

### Фаза 5 — Пустая лента «Подписки»  (⚠️ код-часть сделана, нужен data-чек)
Провод исправен: Mobile дёргает `/notifications/social`, `feed.py` отдаёт 5
сценариев + агрегацию. Клиент **молча глотал ошибку** → «Лента пуста» была
неотличима от сбоя. Исправлено: `socialError` в сторе + отдельный empty-state
«Не удалось загрузить · Обновить».

Само «пусто» — это **данные**. Нужен прод-чек (подставить свой user_id):
```sql
-- 1. Принятые подписки (Follow-строки)
SELECT COUNT(*) FROM follows WHERE follower_id = '<MY_ID>';
-- 2. Активность тех, на кого подписан
WITH f AS (SELECT following_id FROM follows WHERE follower_id = '<MY_ID>')
SELECT
 (SELECT count(*) FROM collection_items ci JOIN collections c ON c.id=ci.collection_id
    WHERE c.user_id IN (SELECT following_id FROM f)) AS coll_adds,
 (SELECT count(*) FROM wishlist_items wi JOIN wishlists w ON w.id=wi.wishlist_id
    WHERE w.user_id IN (SELECT following_id FROM f)) AS wl_adds,
 (SELECT count(*) FROM user_achievements ua
    WHERE ua.user_id IN (SELECT following_id FROM f) AND ua.is_unlocked) AS achievements;
-- 3. Не висят ли подписки как pending-заявки
SELECT count(*) FROM follow_requests WHERE requester_id = '<MY_ID>' AND status = 'pending';
```
Диагноз: `follows`=0 при `pending`>0 → подписки на приватные аккаунты не одобрены
(продуктовый вопрос). `follows`>0, но активность=0 → фид корректно пуст, нужен
онбординг «подпишись на активных». `follows`>0 и активность>0, но UI пуст →
реальный баг фида, копать `feed.py`.

## Фаза 6 — Push deep-link (✅ сделано)
`routeForPush(data)` вынесен в `lib/pushRouting.ts` — единый для трёх точек:
OS-пуш warm-tap, cold-start (`getLastNotificationResponseAsync`), foreground toast.
`_layout.tsx`: тап кладёт цель в `pendingRoute`, flush-эффект навигирует только
когда готовы шрифты/онбординг/авторизация — auth-redirect больше не перебивает,
холодный старт доводит до раздела. Добавлен пропущенный `wishlist_in_stock_alt`.

## Матрица пушей (итоговое состояние)

**Радар/вишлист (шумочувствительные):**
| Событие | Push? |
|---|---|
| `wishlist_in_stock` снова в продаже | только Радар (subscribed) + цена ≤ порога; watched — тихо |
| `wishlist_in_stock_alt` другое издание | только subscribed + порог |
| `wishlist_price_drop` подешевела | subscribed+порог **ИЛИ новый исторический минимум** (даже watched) |
| `digest_wishlist_in_stock` | 1 push/неделю (пн 10:00) |
| `absent` пропала («продали») | ❌ без push, только radar-история |

**Социальные/транзакционные (push всегда, если тип не выключен):**
`follow_request` · `new_follower` (+ «запрос одобрен») · `gift_booked` ·
`gift_confirmed` · `message`/`message_request` (минует часовой cap) ·
`achievement_unlocked` · `milestone_unlocked`.

**Гейтинг всех push:** флаг `notify_*` (тип можно выключить) → quiet hours →
freq-cap 1/тип/час (у wishlist свой слот на каждую пластинку) → валидный expo-токен.

## Открытые вопросы
- Нужен ли `absent`-push для subscribed или только тихая строка? (сейчас план: тихо)
- Порог «исторического минимума»: ровно ниже min или ниже на X%?
- Дайджест-карточка: сворачивать всегда или только при N≥порог (напр. ≥3)?
