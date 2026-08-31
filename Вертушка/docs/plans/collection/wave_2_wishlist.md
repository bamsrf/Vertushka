# Волна 2 — Wishlists/Gifts

Дата: 2026-05-04
Контекст: продолжение фикса флоу подарков после волны 1. Цель — владелец видит свои подарки в приложении и одной кнопкой может «получил → пластинка в коллекции», ключевые события флоу не происходят молча.

Активная копия: `/Users/vladislavrumancev/Desktop/Cursor/Вертушка/`.
Предыдущий контекст: [wishlist_gifting_gaps.md](wishlist_gifting_gaps.md) (инвентарь пробелов, 12 пунктов).

Что закрыто волной 1:
- Самобронь (auth + email match) → 403 c единым текстом.
- `cancel_booking` обнуляет `wishlist_item_id` сразу.
- `/me/given` фильтрует orphaned (SQL + safety).
- `/my-bookings/by-email` удалён.

---

## Группа 1 — Mobile «Мне забронировано»

**Файлы:**
- [Mobile/lib/api.ts](../../../Desktop/Cursor/Вертушка/Mobile/lib/api.ts) — `getReceivedGifts()`, `completeBooking(bookingId)`.
- [Mobile/lib/types.ts](../../../Desktop/Cursor/Вертушка/Mobile/lib/types.ts) — `GiftReceivedItem` (id, status, booked_at, completed_at, record). Без `gifter_*` — анонимно.
- [Mobile/app/profile.tsx](../../../Desktop/Cursor/Вертушка/Mobile/app/profile.tsx) — секция «Мне забронировано» рядом с «Я дарю». Горизонтальный скролл, пустое состояние — компактный баннер.
- Карточка → лист действий: «Подарок получен» (главное), «Открыть пластинку».

**Анонимность:** на карточке только обложка/название/исполнитель + статус. Имя дарителя — нет (соответствует серверному ответу).

**Состояния пустоты:** баннер «Тебя ещё не забронировали — поделись профилем» с CTA на share.

**Риск:** инвалидация кеша коллекции после complete (см. Группу 2).

---

## Группа 2 — Единый путь «получено»

**Сейчас:** два эндпоинта делают разное:
- `PUT /api/gifts/me/received/{booking_id}/complete` ([gifts.py](../../../Desktop/Cursor/Вертушка/Backend/app/api/gifts.py)) — только `status=COMPLETED` + `is_purchased=True`.
- `PUT /api/wishlists/items/{id}/move-to-collection` ([wishlists.py](../../../Desktop/Cursor/Вертушка/Backend/app/api/wishlists.py)) — создаёт `CollectionItem`, обнуляет связь, email дарителю.

**Что делаем:**
- Новый файл `Backend/app/services/gifts.py` с функцией `complete_gift_booking(booking, db, *, send_email=True)`:
  1. Меняет статус → `COMPLETED`, выставляет `completed_at`.
  2. Помечает `wishlist_item.is_purchased = True`, `purchased_at`.
  3. Создаёт `CollectionItem` с тем же `record_id` (если уже есть — добавляет второй экземпляр, без unique-конфликта).
  4. Обнуляет `booking.wishlist_item_id`.
  5. Если есть email дарителя — `send_gift_received_to_gifter`.
- `complete_booking` и `move-to-collection` оба зовут эту функцию.
- Bonus: при `move-to-collection` без активной брони — просто шаг 3 (создать `CollectionItem`), как сейчас.

**Риск:** на mobile нужно инвалидировать стор коллекции после complete. В `useCollectionStore` уже есть метод обновления — подёргаем его.

---

## Группа 3 — Нотификации на «тихие» переходы

**Файл:** [Backend/app/services/notifications.py](../../../Desktop/Cursor/Вертушка/Backend/app/services/notifications.py) + интеграция в `gifts.py`, `booking_tasks.py`, `wishlists.py`.

**Новые функции:**
- `send_booking_cancelled_to_owner(owner_email, record_title)` — владельцу при ручной отмене по cancel-ссылке. Тон: «пункт снова свободен, дарителя мы не раскрыли».
- `send_booking_auto_released_to_gifter(gifter_email, gifter_name, record_title, owner_name)` — дарителю при auto-release. Тон: «бронь истекла, забронируй снова если ещё хочешь».
- `send_wishlist_item_removed_to_gifter(gifter_email, gifter_name, record_title, owner_name)` — дарителю при удалении пункта владельцем (см. Группу 4).
- (`send_gift_received_to_gifter` уже есть — просто подвязать к новому единому пути в Группе 2.)

**Куда подключить:**
- `cancel_booking` ([gifts.py](../../../Desktop/Cursor/Вертушка/Backend/app/api/gifts.py)) → `send_booking_cancelled_to_owner`.
- `auto_release_expired_bookings` ([booking_tasks.py](../../../Desktop/Cursor/Вертушка/Backend/app/tasks/booking_tasks.py)) → `send_booking_auto_released_to_gifter`. Не путать с reminder за 7 дней — это другое событие.
- `complete_gift_booking` (Группа 2) → `send_gift_received_to_gifter` (уже работает в move-to-collection, теперь и в complete).

**Push-эквиваленты:** не делаем в этой волне (для дарителей нужна отдельная привязка девайса по `booked_by_user_id` + проверка push-токена). Уходит в волну 3.

**Риск:** не дублировать письма. Reminder за 7 дней + письмо при release = 2 письма. Это нормально, но в копи нужно учесть («ты получал напоминание неделю назад, теперь бронь истекла»).

---

## Группа 4 — Удаление пункта с активной бронью

**Файл:** [Backend/app/api/wishlists.py](../../../Desktop/Cursor/Вертушка/Backend/app/api/wishlists.py), эндпоинт DELETE `/wishlists/records/{item_id}`.

**Что делаем (вариант A — мягкий, выбран):**
- Перед удалением проверяем `item.gift_booking and status == BOOKED`.
- Если есть активная бронь:
  1. Авто-cancel: `status = CANCELLED`, `cancelled_at = now`, `cancellation_reason = "item_removed_by_owner"`, `wishlist_item_id = None`.
  2. `send_wishlist_item_removed_to_gifter` (Группа 3).
  3. Только потом удаляем `WishlistItem`.
- На mobile при удалении пункта с активной бронью — модалка-предупреждение: «Этот пункт кто-то уже бронирует. Если удалить — дарителю отправим уведомление об отмене. Удалить?». Кнопки «Удалить» / «Отмена».

**Вариант B (отвергнут):** soft-delete пункта (флаг `archived_at`). Сложнее, нужны миграция, фильтры везде. Откладываем.

**Риск:** письмо может уйти в момент, когда даритель уже сделал отмену сам и получил «ваша бронь отменена». В этом случае `status` уже CANCELLED → пропускаем шаги 1-2, просто удаляем.

---

## Группа 5 — Косметика

- На вебе ([public_profile.html](../../../Desktop/Cursor/Вертушка/Backend/app/web/templates/public_profile.html), [public_wishlist.html](../../../Desktop/Cursor/Вертушка/Backend/app/web/templates/public_wishlist.html)) — для status === 403 показывать `alert(detail)` без префикса «Ошибка:», чтобы дружелюбный текст самоброни не звучал как тех. сбой.
- В чужом профиле на карточке «Забронировано» добавить серый поясняющий текст «Подарите другую» (если соседние карточки доступны для бронирования). Уточнить на месте при работе с UI.

---

## Что **НЕ** входит (волна 3)

- Email-верификация дарителя через `PENDING` (24-48ч на подтверждение, 60 дней на покупку).
- Rate-limit на `POST /book` + `gifter_ip`/`gifter_user_agent_hash` в модели.
- Лимит активных броней на email.
- Ротация share-token через UI.
- Разделение `show_gifter_names` на «видно публике» / «видно владельцу».
- Блок-лист email/IP.
- Push для дарителей.

---

## Порядок реализации

1. Группа 2 (бэк, рефактор complete) — фундамент.
2. Группа 3 (новые письма) — параллельно с 2, общие интеграции.
3. Группа 4 (удаление пункта) — после 3 (нужна `send_wishlist_item_removed_to_gifter`).
4. Группа 1 (mobile UI) — после 2-3, нужны рабочие эндпоинты и поведение.
5. Группа 5 (косметика).

Без миграций БД. Без смены контракта работающих эндпоинтов.
