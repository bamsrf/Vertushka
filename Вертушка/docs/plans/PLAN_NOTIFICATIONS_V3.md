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
- `buildDigest` в `notifications.tsx` (бывший `buildWishlistDigest`): ≥3 непрочитанных
  сворачиваются в одну строку. Вызывается дважды и даёт **две независимые свёртки**:
  `wishlist_in_stock` → «N пластинок снова в продаже» (`__wishlist_digest__`) и
  `wishlist_in_stock_alt` → «N других версий появились в продаже»
  (`__wishlist_alt_digest__`, синтетический тип `digest_wishlist_in_stock_alt`,
  бэкенд его не шлёт). Раздельно, потому что это разные обещания: «твоя пластинка
  в продаже» ≠ «есть другой прессинг».
- **Радар не сворачивается**: строки с `data.on_radar` остаются отдельными. Радар —
  явная подписка «следи за этой», прятать её в общую кучу значит обнулить смысл
  колокольчика. В дайджест уходит только фон (`watched`).
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
| `digest_wishlist_in_stock` | 1 push/неделю (пн 10:00); считает и `_alt`, но **своим счётчиком** — «5 пластинок из вишлиста» + body «и ещё 4 других издания» |
| `absent` пропала («продали») | ❌ без push, только radar-история |

**Социальные/транзакционные (push всегда, если тип не выключен):**
`follow_request` · `new_follower` (+ «запрос одобрен») · `gift_booked` ·
`gift_confirmed` · `message`/`message_request` (минует часовой cap) ·
`achievement_unlocked` · `milestone_unlocked`.

**Гейтинг всех push:** флаг `notify_*` (тип можно выключить) → quiet hours →
freq-cap 1/тип/час (у wishlist свой слот на каждую пластинку) → валидный expo-токен.

## Тон пушей (✅ сделано)

Весь копирайт push живёт в одном месте — `Backend/app/services/push_copy.py`.
Функции возвращают `(title, body)` и принимают примитивы, не ORM-объекты, чтобы
тексты проверялись без БД. Call-site'ы текстов больше не содержат.

**Правила:**
- Обращение на «ты» — во всех каналах, включая email (`services/notifications.py`).
- Констатация, не восклицание: точка вместо «!», без «Ура»/«Поздравляем».
- Без императивов-CTA («Открой ленту», «Поделись») — на push и так нажимают.
- Цифра конкретная, она и есть эмоция: «−34%», «3 200 ₽» (неразрывные пробелы).
- Ноль гендера: настоящее время или конструкция без глагола. Никаких «(а)».
- Эмодзи не используем.
- **Title — субъект новости** (пластинка, человек), **body — что случилось + цифра**.
  Раньше было наоборот: в title стояла рубрика («Новый подписчик»), а новость
  пряталась в body, который на Android обрезается.
- Имена подставляем только в **именительном падеже**: `display_name` произвольный,
  склонять его нечем («Коллекция Ксения теперь доступна» — брак).

**Итоговые тексты:**

| Тип | Title | Body |
|---|---|---|
| `wishlist_in_stock` | `{artist} — {title}` | `Есть в наличии · от {N} ₽ · {store}` |
| `wishlist_in_stock_alt` | `{artist} — {title}` | `В продаже другое издание · от {N} ₽ · {store}` |
| `wishlist_price_drop` | `{artist} — {title}` | `−{pct}% · {old} ₽ → {new} ₽` |
| …исторический минимум | `Минимальная цена: {title}` | `{new} ₽ · прошлый минимум {prev_low} ₽` |
| `digest_wishlist_in_stock` | `За неделю: {N} {пластинок} из вишлиста` | `{artist1}, {artist2}, {artist3}` |
| `follow_request` | `{name} хочет подписаться` | `@{username} · {N} пластинок в коллекции` |
| `new_follower` | `{name} — твой новый подписчик` | `@{username} · {N} пластинок в коллекции` |
| …заявка одобрена | `Заявка принята` | `{name} открывает тебе коллекцию` |
| `message` | `{имя отправителя}` | превью сообщения |
| `gift_booked` (аноним) | `Кто-то забронировал подарок` | `«{artist} — {title}» из твоего вишлиста` |
| `gift_booked` (раскрыт) | `{gifter} дарит тебе пластинку` | `«{artist} — {title}»` |
| `gift_confirmed` | `Подарок на месте` | `{owner} добавляет «{title}» в коллекцию` |
| `achievement_unlocked` | `Ачивка: {title_ru}` | `{flavor_ru}` |
| `milestone_unlocked` | `В коллекции {N} пластинок` | `Полка заметно тяжелее` |

`{flavor_ru}` в body ачивки — это подстановка поля `AchievementDefinition.flavor_ru`
целиком («33⅓. Это не число, это скорость.»), без всякой обёртки. Пустой flavor →
фолбэк «Открыта новая ачивка».

**Deep-link'и (`Mobile/lib/pushRouting.ts`) — проверено по всем 13 типам:**

| Тип | Куда ведёт | Ключ в payload |
|---|---|---|
| `follow_request` | `/social/follow-requests` | — |
| `new_follower` (и «заявка одобрена») | `/user/{username}` | `actor_username` |
| `message` · `message_request` | `/messages/{id}` | `conversation_id` → `entity_id` |
| `gift_booked` · `gift_confirmed` | `/gift/{id}` | `entity_id` (booking) |
| `achievement_unlocked` | `/achievements?code=` → DetailsSheet | `code` |
| `milestone_unlocked` | `/achievements` | `code` нет — вехи не ачивки |
| `wishlist_in_stock` · `wishlist_price_drop` | `/record/{id}` | `record_id` |
| `wishlist_in_stock_alt` | `/record/{alt_record_id}` | `alt_record_id`, фолбэк `record_id` |
| `digest_wishlist_in_stock` | `/notifications` (там дайджест-шторка) | — |

Починено при проверке:
- `new_follower` вёл в ленту вместо профиля: роутер читал `data.username`, а бэкенд
  такого ключа не кладёт **ни в одном** типе — только `actor_username`/`sender_username`.
  Ветка `if (type === 'new_follower' && username)` не срабатывала никогда.
- `wishlist_in_stock_alt` вёл на желаемую пластинку, у которой листингов нет, хотя
  push анонсирует другое издание → теперь на `alt_record_id`.

**Доработки данных, которые потребовались под тексты:**
- В радар-пуши прокинуты `record.artist` и `store.name` (лежали в `data`, в push не шли).
- `drop_pct` считался в price-drop джобе и **нигде не использовался** — теперь в body.
- Дайджест тянет строки уведомлений вместо `COUNT(*)` и собирает имена артистов
  из `data.record_artist` (дедуп, топ-3 в body).
- «Исторический минимум» сравнивается с `min(price)` по снапшотам **строго до
  текущего окна**. Раньше `min` считался по всей истории, включая только что
  записанный `new`, из-за чего условие `new <= min` было тавтологией и срабатывало
  на любом падении цены. Побочно это дало настоящее число для «прошлый минимум N ₽».

## Открытые вопросы
- Нужен ли `absent`-push для subscribed или только тихая строка? (сейчас план: тихо)
- Порог «исторического минимума»: ровно ниже min или ниже на X%?
- Дайджест-карточка: сворачивать всегда или только при N≥порог (напр. ≥3)?
