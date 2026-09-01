# Вишлисты и брони подарков — инвентарь пробелов

Дата: 2026-05-04
Срез по активной копии: `/Users/vladislavrumancev/Desktop/Cursor/Вертушка/`

Документ описывает фактическое состояние флоу «вишлист → бронь → дарение», находит пробелы, потенциальные баги и точки конфликта между состояниями. Без императивов «сделать X» — для каждого пробела перечислены варианты направлений, выбор откладывается.

---

## 0. Карта компонентов

**Backend**
- Модели: [Backend/app/models/wishlist.py](Backend/app/models/wishlist.py), [Backend/app/models/gift_booking.py](Backend/app/models/gift_booking.py), [Backend/app/models/follow.py](Backend/app/models/follow.py), [Backend/app/models/profile_share.py](Backend/app/models/profile_share.py)
- API: [Backend/app/api/wishlists.py](Backend/app/api/wishlists.py), [Backend/app/api/gifts.py](Backend/app/api/gifts.py), [Backend/app/api/users.py](Backend/app/api/users.py) (ручка `/by-username/{u}/wishlist/`), [Backend/app/api/profile.py](Backend/app/api/profile.py)
- Web (HTML): [Backend/app/web/routes.py](Backend/app/web/routes.py), шаблоны `public_profile.html`, `public_wishlist.html`, `cancel_booking.html`
- Notifications: [Backend/app/services/notifications.py](Backend/app/services/notifications.py)
- Фон: [Backend/app/tasks/booking_tasks.py](Backend/app/tasks/booking_tasks.py) (reminder + auto-release)

**Mobile**
- Типы/API/стор: [Mobile/lib/types.ts](Mobile/lib/types.ts), [Mobile/lib/api.ts](Mobile/lib/api.ts), [Mobile/lib/store.ts](Mobile/lib/store.ts)
- Свой профиль: [Mobile/app/profile.tsx](Mobile/app/profile.tsx)
- Чужой профиль: [Mobile/app/user/\[username\]/index.tsx](Mobile/app/user/[username]/index.tsx)
- Настройки уведомлений: [Mobile/app/settings/notifications.tsx](Mobile/app/settings/notifications.tsx)

**Каналы получения чужого вишлиста (3 ручки, разный gate доступа)**
1. Public share-token: `GET /api/wishlists/share/{share_token}` — без auth, обходит `is_public=False`. Работает, пока токен не ротирован.
2. By-username: `GET /api/users/by-username/{username}/wishlist/` — `is_public OR is_follower OR is_owner` ([users.py:198+](Backend/app/api/users.py)). Это путь, по которому ходит mobile.
3. Web HTML `/@{username}` — отдельный рендер ([web/routes.py:50-218](Backend/app/web/routes.py)).

---

## 1. Самобронь (booking себе)

### Текущее поведение
- В `POST /api/gifts/book` ([Backend/app/api/gifts.py:33-153](Backend/app/api/gifts.py)) **нет проверки** `wishlist.user_id != current_user.id`. Только: вишлист публичный, не забронирован уже, не куплен.
- В мобильном чужом профиле фронт-guard есть: `if (isWishlist && item && !reserved && !isOwn) setBookingItem(item);` ([Mobile/app/user/\[username\]/index.tsx:673,694](Mobile/app/user/[username]/index.tsx)). Но guard только UI — прямой `POST /gifts/book` с собственного `wishlist_item_id` пройдёт.
- Анонимный сценарий: владелец без авторизации, на любую почту, на свой публичный share-token — забронит сам себе.

### Где видно последствия
- `gifter_email == current_user.email` попадает в `/me/given` ([gifts.py:285](Backend/app/api/gifts.py)) → собственная бронь засветится в «Я дарю» (если email совпал) или останется висеть до auto-release.
- Анонимизация в `/me/received` ([gifts.py:347-350](Backend/app/api/gifts.py)) сделает её неотличимой от внешней.

### Варианты направлений
- Серверная проверка `current_user and current_user.id == wishlist.user_id` → 403.
- Дополнительно: для гостя — сравнение `gifter_email` с `wishlist.user.email` (но email юзера может быть скрыт; даёт ложноположительные при общем email на семью).
- Альтернатива: разрешить, но скрывать в UI и логах под флагом `self_booking=True` — на случай «я сам себе планирую».

---

## 2. Отмена брони не освобождает пункт

### Текущее поведение
- `GiftBooking.wishlist_item_id` имеет `unique=True` ([Backend/app/models/gift_booking.py:34-40](Backend/app/models/gift_booking.py)). На один пункт — одна запись брони, в любом статусе.
- `book_gift` блокирует повторное бронирование тривиальным truthy: `if item.gift_booking:` ([gifts.py:69](Backend/app/api/gifts.py)) — сюда попадают и `CANCELLED`-записи.
- `cancel_booking` ([gifts.py:192-235](Backend/app/api/gifts.py)) выставляет `status=CANCELLED` + `cancelled_at`, но **не обнуляет `wishlist_item_id`**.
- Освобождение пункта делает только фоновый `auto_release_expired_bookings` (по истечении `expires_at`, по умолчанию 60 дней) — там `booking.wishlist_item_id = None` ([booking_tasks.py:83](Backend/app/tasks/booking_tasks.py)).

### Эффект
- Даритель отменил → у владельца пункт продолжает выглядеть «забронировано» в любых ручках, проверяющих `is_booked = item.gift_booking is not None` ([users.py при сборке public_items], [/api/wishlists/share/{token}], `/me/received` через JOIN). Никто другой не сможет забронировать тот же пункт следующие до 60 дней.
- Сценарий: даритель ошибся, отменил по cancel-ссылке — пункт «зависает» без сигнала.

### Варианты направлений
- В `cancel_booking` обнулять `wishlist_item_id` (как делает auto-release).
- Альтернатива: оставлять связь, но в `book_gift` фильтровать `if item.gift_booking and item.gift_booking.status == BOOKED`. И поправить все места `is_booked = item.gift_booking is not None` на проверку статуса. Минус — придётся пройти по всем ручкам и шаблонам.
- Третий путь: уникальный индекс — частичный (`WHERE status = 'booked'`) + nullify wishlist_item_id при отмене. Делает аудиторский след по отменам читаемым по этому полю.

---

## 3. На мобильном нет секции «Я получаю / мне забронировано»

### Текущее поведение
- В свой профиль mobile грузится только `getGivenGifts()` — секция «Я дарю» ([profile.tsx:404-498](Mobile/app/profile.tsx), [api.ts:731](Mobile/lib/api.ts)).
- API-методы `getReceivedGifts()` / `completeGiftBooking()` — **в [Mobile/lib/api.ts](Mobile/lib/api.ts) отсутствуют** (есть только `bookGift`, `getGivenGifts`, `cancelGiftBooking`).
- Серверный `GET /api/gifts/me/received` ([gifts.py:315-356](Backend/app/api/gifts.py)) и `PUT /api/gifts/me/received/{id}/complete` ([gifts.py:359-395](Backend/app/api/gifts.py)) — есть, но клиент их не вызывает.
- Перенос в коллекцию через `moveToCollection` ([wishlists.py:467-562](Backend/app/api/wishlists.py)) идёт от элемента вишлиста, не от брони. Это альтернативный путь «отметил полученным» через UI коллекции, но он не показывает «вам забронировано N подарков».

### Эффект
- Из жалобы «всё намешано и не открывается»: владелец не видит ни счётчика «вам забронировали», ни элемента, на который кликнуть для отметки «получено». Подтверждение получения возможно только через перенос в коллекцию.
- На веб-публичной странице (`/@{username}`) гость видит «Забронировано», но владельцу в приложении эта информация не выводится явным списком.

### Варианты направлений
- Добавить в [Mobile/lib/api.ts](Mobile/lib/api.ts) `getReceivedGifts/completeBooking`, в `profile.tsx` — секцию «Мне забронировано» (анонимно: только обложка + статус).
- Альтернатива: оставить только сигнал-уведомление через push (`notify_gift_booked`, см. [notifications.tsx:283-289](Mobile/app/settings/notifications.tsx)), а отметку получения объединить с move-to-collection.
- Гибрид: badge с числом активных броней на табе профиля + раскрытие в отдельный экран «Подарки», где параллельно списки `received` и `given`.

---

## 4. Удаление пункта владельцем при активной брони

### Текущее поведение
- `DELETE /api/wishlists/records/{item_id}` ([wishlists.py:248-276](Backend/app/api/wishlists.py)) удаляет `WishlistItem`. На уровне БД `gift_booking.wishlist_item_id` имеет `ondelete="SET NULL"` ([gift_booking.py:34-40](Backend/app/models/gift_booking.py)) — бронь становится orphaned (без пункта).
- Даритель уведомления не получает; сам даритель в `/me/given` увидит запись со статусом BOOKED, но `b.wishlist_item.record` теперь NULL → потенциальный 500 при `selectinload(WishlistItem.record)` и сборке `RecordBrief.model_validate(b.wishlist_item.record)` ([gifts.py:306](Backend/app/api/gifts.py)).
- Владелец, удалив пункт, не получает диалога-предупреждения «есть активная бронь».

### Эффект
- Тихий разрыв: даритель готов купить → пункт исчез → купит «не туда» / задаст вопрос в поддержку.
- Возможный краш `/me/given` для дарителя, если в выборке окажется orphaned-бронь.

### Варианты направлений
- Перед DELETE: запретить или показать предупреждение, если есть `gift_booking.status == BOOKED`. Совместить с авто-cancel брони + email дарителю «пункт удалён».
- Альтернатива: «soft-delete» пункта (флаг `archived_at`), бронь остаётся валидной, в публичном вишлисте пункт скрыт.
- Минимально: фильтр в `/me/given` по `b.wishlist_item is not None` (как в `/me/received`).

---

## 5. Анонимность и видимость дарителя

### Текущее поведение
| Кто смотрит | Что видит | Где |
| --- | --- | --- |
| Владелец вишлиста | `is_booked=True`, имя дарителя пусто | `/me/received` ([gifts.py:347-350](Backend/app/api/gifts.py)) |
| Гость по share-token | `is_booked=True`, имя если `wishlist.show_gifter_names` | `/api/wishlists/share/{token}` ([wishlists.py](Backend/app/api/wishlists.py), `WishlistPublicItemResponse`) |
| Фолловер по username | то же поведение, что у share-token | [users.py:280-289](Backend/app/api/users.py) |
| Даритель | свои данные + `cancel_token` | `/me/given` ([gifts.py:300-312](Backend/app/api/gifts.py)) |

### Заметные точки
- `wishlist.show_gifter_names` управляет показом и для гостя по share-token, и для фолловера в mobile-флоу. Получается, владелец **не видит** имя, но другие посетители его публичного вишлиста — **видят** (если флаг включён). Это контр-интуитивно для слова «анонимность» в письме владельцу («Кто-то хочет подарить»).
- В мобильном UI на чужом профиле — нет индикации, что владелец узнает или не узнает имя дарителя. В письме `send_booking_notification_to_owner` явно «анонимно».

### Варианты направлений
- Развести два флага: `show_gifter_names_to_public` (видимо гостям) и `reveal_gifter_to_owner` (видимо владельцу). Сейчас один флаг означает оба смысла, но реально работает только для публичного.
- Альтернатива: убрать `show_gifter_names` из публичного вообще, оставить только в момент `complete` (после получения подарка владелец узнаёт имя).
- Третий путь: в момент бронирования спрашивать дарителя «открыть имя владельцу: да/нет» и хранить per-booking.

---

## 6. Анти-фрод

### Текущее поведение
- Rate-limit на `/api/gifts/book` — нет (общий [services/rate_limiter.py](Backend/app/services/rate_limiter.py) есть, но к этой ручке не применён — проверить usage отдельно при принятии решения).
- Лимит N броней на email — нет.
- Email дарителя не верифицируется (любой ввод сохраняется как контакт). Cancel-токен уходит на этот email; если email чужой — невинный получатель получит письмо.
- `GET /api/gifts/my-bookings/by-email?email=X` ([gifts.py:238-271](Backend/app/api/gifts.py)) — без auth, без OTP. Перебором можно получить чужие брони + имя получателя по любому известному email.
- IP/fingerprint в `GiftBooking` не хранятся.
- Блок-листа email/IP нет.
- Нет ограничения «один email — N активных броней суммарно».

### Эффект
- Массовое бронирование вишлиста «впрок» без намерения купить — заблокирует пункты на 60 дней (auto-release), за это время вишлист выглядит для других гостей пустым.
- Утечка по `by-email` — низкорисковая (имя получателя + название пластинки), но публичная.
- Атака «чужим email»: ввести email пользователя X → ему придёт письмо «Вы забронировали…» → жалоба на спам.

### Варианты направлений
- На `/book`: rate-limit IP (например, 5/час), capture IP в модель (новые поля `gifter_ip`, `gifter_user_agent_hash`).
- Лимит активных броней с одного email (например, ≤ 3 одновременно в статусе BOOKED).
- Email-верификация: либо OTP перед фиксацией, либо «soft-pending» (`PENDING` статус → бронь активируется кликом по ссылке в письме). Заодно нагрузит неиспользуемый сейчас `GiftStatus.PENDING`.
- `/my-bookings/by-email` — закрыть за magic-link (письмо со ссылкой `?email=X&token=Y`) или удалить ручку, дав вместо этого просто «зарегистрируйтесь, чтобы видеть свои брони».
- Блок-лист: таблица `blocked_email`/`blocked_ip` + проверка на входе в `/book`.

---

## 7. Состояния и status-машина

### Текущее поведение
- Перечисление `GiftStatus`: `PENDING | BOOKED | COMPLETED | CANCELLED` ([gift_booking.py:14-19](Backend/app/models/gift_booking.py)). `PENDING` нигде не присваивается, бронь сразу `BOOKED`.
- `WishlistItem.is_purchased` (bool) — отдельный флаг, синхронизируется с `COMPLETED` в двух местах:
  - `move-to-collection` ([wishlists.py:467-562](Backend/app/api/wishlists.py)): создаёт CollectionItem, выставляет COMPLETED, обнуляет `wishlist_item_id`.
  - `complete_booking` ([gifts.py:359-395](Backend/app/api/gifts.py)): только `is_purchased=True`, без CollectionItem, без обнуления `wishlist_item_id`.
- В результате есть два «получено», ведущих к разным побочным эффектам:
  - Через перенос в коллекцию — пластинка добавлена в коллекцию + бронь освобождена + email дарителю.
  - Через complete — пластинка НЕ в коллекции + бронь связана с пунктом + email дарителю не отправляется (нет вызова `send_gift_received_to_gifter`).

### Эффект
- В зависимости от того, каким путём владелец отметит «получено», даритель либо получит письмо «подарок вручён», либо нет. Состояния пункта и брони расходятся.

### Варианты направлений
- Свести в одну операцию: `complete_booking` тоже создаёт CollectionItem + шлёт письмо + обнуляет `wishlist_item_id`. Тогда `move-to-collection` остаётся как путь «вручную, без брони».
- Альтернатива: разрешить «complete без переноса в коллекцию», но в обоих случаях слать письмо дарителю и обнулять `wishlist_item_id`.
- Использовать `PENDING` как промежуточный для email-верификации (см. п.6).

---

## 8. `is_public` vs share-token vs followers

### Текущее поведение
- `Wishlist.is_public` (default True) — определяет доступ через `/by-username/{u}/wishlist/` для не-фолловера ([users.py:255-258](Backend/app/api/users.py)).
- `share_token` всегда работает (нет проверки `is_public`) — ручка `/api/wishlists/share/{share_token}` отдаёт вишлист в любом случае.
- `Wishlist.regenerate_share_token()` есть в модели ([wishlist.py:86-89](Backend/app/models/wishlist.py)), но публичной API-ручки для ротации в коде не нашлось (есть `/wishlists/generate-link` — судя по [api.ts:592](Mobile/lib/api.ts), генерит/возвращает текущий, не уверен в семантике — нужна перепроверка).
- `ProfileShare.is_private_profile` ([profile_share.py:38](Backend/app/models/profile_share.py)) — отдельный флаг приватности профиля, не блокирует share-token-ручку напрямую.

### Эффект
- Юзер «закрылся» (`is_public=False`) → фолловеры всё видят, share-token продолжает работать. Если ссылка утекла — отозвать её невозможно через mobile UI.

### Варианты направлений
- Добавить ручку `POST /wishlists/regenerate-share-token` + кнопку в mobile (settings/share).
- Привязать share-token к `is_public`: если выключен — share-ручка возвращает 403.
- Множественные токены с метками («для друга X», «для группового подарка») и индивидуальная отзываемость — расширение, может быть out-of-scope сейчас.

---

## 9. Привязка email дарителя к юзеру

### Текущее поведение
- `booked_by_user_id` заполняется только если даритель залогинен на момент `POST /book` ([gifts.py:87](Backend/app/api/gifts.py)).
- В `/me/given` подтягиваются ещё и записи по `gifter_email == current_user.email` ([gifts.py:285](Backend/app/api/gifts.py)).
- Email юзера не верифицируется при регистрации (нужно проверить отдельно — не входит в этот обзор), а email дарителя при бронировании не валидируется.

### Эффект
- Юзер сменил email в профиле → старые брони, забронированные «гостем» с прежнего email, отвалятся из «Я дарю».
- Если в каком-то месте email юзера меняется без подтверждения → атакующий, поставивший себе чужой email, увидит чужие брони в `/me/given`.

### Варианты направлений
- При регистрации/смене email — фиксировать в `GiftBooking.booked_by_user_id` все брони с совпавшим `gifter_email` (миграция + фоновая привязка).
- В `/me/given` использовать только `booked_by_user_id` — но тогда брони, сделанные до регистрации, теряются.
- Гибрид: привязка по email только если email верифицирован.

---

## 10. Уведомления и каналы

### Текущее поведение
- `send_booking_notification_to_owner` — анонимный email владельцу при создании брони.
- `send_booking_confirmation_to_gifter` — email дарителю с cancel-ссылкой.
- `send_gift_received_to_gifter` — email дарителю при `move-to-collection`. **Не вызывается** при `complete_booking` (см. п.7).
- `send_booking_reminder_email` — за 7 дней до `expires_at`, отметка `reminder_sent_at`.
- Push в mobile: только `notify_gift_booked` toggle ([notifications.tsx:283](Mobile/app/settings/notifications.tsx)). На дарителя пушей нет (ему только email).
- Уведомлений «бронь отменена» — ни владельцу, ни дарителю не отсылается.
- Уведомлений «пункт удалён владельцем, ваша бронь сброшена» — нет.

### Эффект
- Тихие отмены: ни владелец не узнаёт, что пункт снова свободен (если кто-то отменил), ни даритель — что пункт пропал из вишлиста.

### Варианты направлений
- Добавить три события: `booking_cancelled_to_owner`, `booking_auto_released_to_gifter`, `wishlist_item_removed_to_gifter`.
- Push для дарителей с привязанным `booked_by_user_id`.
- Соблюдение `notify_gift_booked` toggle в `send_booking_notification_to_owner` (проверить, что условие toggle учитывается — отдельная задача).

---

## 11. Состояния пункта vs состояния брони — точки конфликта

| # | Сценарий | Текущее поведение |
| --- | --- | --- |
| 1 | Даритель отменил руками | Пункт остаётся «забронирован» до 60-дневного auto-release (см. п.2) |
| 2 | Бронь auto-released | Пункт свободен, даритель уведомлён email-reminder за 7 дней до, но не самим фактом релиза |
| 3 | Владелец удалил пункт | Бронь orphaned (`wishlist_item_id=NULL`), статус не меняется, дарителю не сообщают (см. п.4) |
| 4 | Владелец отметил `move-to-collection` | Бронь `COMPLETED`, `wishlist_item_id=NULL`, email дарителю |
| 5 | Владелец отметил `complete_booking` | Бронь `COMPLETED`, `wishlist_item_id` сохраняется, email дарителю **не отправляется** |
| 6 | Владелец сделал `is_purchased=True` напрямую | Не нашёл такой ручки; через UI скрытие пункта только через delete или move-to-collection |
| 7 | Двойная бронь (race) | Уникальный индекс `wishlist_item_id` защищает на уровне БД; ошибка пользователю — 400 «уже забронирован» (см. п.2 — но также блокирует после CANCELLED) |

### Варианты направлений
- Свести 4 и 5 в один путь.
- В сценариях 1, 3 — добавить нотификации (см. п.10).

---

## 12. Безопасность ручек на чтение

| Ручка | Auth | Что может утечь |
| --- | --- | --- |
| `GET /api/wishlists/share/{token}` | нет | весь вишлист по токену; ротации токена нет в публичном API |
| `GET /api/users/by-username/{u}/wishlist/` | optional | то же, что выше; gate `is_public OR follower OR owner` |
| `GET /api/gifts/my-bookings/by-email?email=X` | **нет** | список броней любого email + кому подарок |
| `GET /api/gifts/{booking_id}` | нет | статус брони + имя дарителя по ID; cancel_token не отдаётся (line 186) |
| `GET /@{username}` (web) | нет | публичный профиль + вишлист |

### Варианты направлений
- `/by-email` — закрыть за magic-link.
- `/api/gifts/{booking_id}` — оставить, но скрыть `gifter_name/email` от не-владельца брони.
- Логирование всех вызовов `/share/{token}` для аудита подозрительной активности.

---

## 13. Сводная таблица (приоритет — экспертная оценка для будущего обсуждения, не финальная)

| # | Пробел | Тип | Влияние |
| --- | --- | --- | --- |
| 1 | Самобронь не блокируется на сервере | bug + security | Любой может забронировать свой вишлист, флоу запутывается |
| 2 | Cancel руками не освобождает пункт | **bug** | Пункт «зависает» до 60 дней; основная причина «всё намешано» |
| 3 | Mobile не показывает `received` | UX gap | Владелец не видит свои подарки в приложении |
| 4 | Удаление пункта без уведомления | UX gap + потенциальный 500 | Тихий разрыв с дарителем |
| 5 | `show_gifter_names` для гостя ≠ для владельца | UX/смысловой | Анонимность для владельца, имя — для гостей |
| 6 | Нет анти-фрода | security | Спам-брони, утечка через `by-email`, чужой email |
| 7 | Два пути «complete» расходятся | inconsistency | `complete_booking` без email дарителю и без обнуления связи |
| 8 | Share-token нельзя ротировать через UI | security | Утёкший токен не отозвать |
| 9 | Привязка по email хрупкая | data drift | Смена email теряет «Я дарю» |
| 10 | Нет уведомлений на отмену/release/удаление | UX gap | Тишина в ключевых переходах |
| 11 | `PENDING` не используется | dead state | Резерв под email-верификацию |
| 12 | Авторизация чтений (`/by-email`, `/{id}`) | security | Утечки данных |

---

## 14. Что НЕ исследовано в этом срезе (для отдельных проходов)

- Реальные тексты email-шаблонов и push-копий — только сигнатуры функций.
- Frontend веб-страниц `/@{username}` и `/cancel/{id}` — полный JS/UX поведения.
- Поведение `getReceivedGifts` через swagger/postman (только код API).
- Покрытие `services/rate_limiter.py` другими ручками (для оценки готовности применить к `/book`).
- Семантика `/wishlists/generate-link` — генерит ли новый токен или возвращает существующий.
- Мониторинг/алертинг текущих ошибок 500 на orphaned выборках.
