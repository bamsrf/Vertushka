# Волна 3 — Wishlists/Gifts

Дата: 2026-05-04
Контекст: продолжение после волн 1-2. Цель — анти-фрод и приватность, без слома существующего флоу. Ключевой принцип: всё новое — под флагами или с дефолтами, повторяющими текущее поведение.

Активная копия: `/Users/vladislavrumancev/Desktop/Cursor/Вертушка/`.
Предыдущий контекст: [wave_2_wishlist.md](wave_2_wishlist.md), [wishlist_gifting_gaps.md](wishlist_gifting_gaps.md).

Что закрыто волнами 1-2:
- Самобронь блокирована (auth + email).
- Cancel освобождает пункт сразу.
- `/me/given` фильтрует orphaned.
- `/by-email` удалён.
- Единый путь complete: бронь → коллекция + email дарителю.
- Письма на cancel/auto-release/item-removed.
- Mobile секция «Мне забронировано» + кнопка «Получено».
- Предупреждение при удалении пункта с бронью.
- Косметика alert/toast для 403.

---

## Группа 6 — Анти-фрод на `POST /book` (невидимое, безопасное)

**Файлы:** [Backend/app/models/gift_booking.py](../../../Desktop/Cursor/Вертушка/Backend/app/models/gift_booking.py), [Backend/app/api/gifts.py](../../../Desktop/Cursor/Вертушка/Backend/app/api/gifts.py), [Backend/app/config.py](../../../Desktop/Cursor/Вертушка/Backend/app/config.py), новая alembic-миграция.

**Что:**
- Поля в `GiftBooking` (nullable, чтобы не ломать историю): `gifter_ip` (String 45), `gifter_user_agent_hash` (String 64).
- В `book_gift` — `Request` параметр FastAPI, извлечение IP с учётом `X-Forwarded-For`, sha256 от UA.
- **Rate-limit per IP**: ≤ 5 броней / 1 час окно (в `config.py`: `gift_booking_per_ip_limit`, `gift_booking_per_ip_window_minutes`).
- **Limit per email (active)**: ≤ 3 одновременных `BOOKED` броней с одного email (`gift_booking_per_email_active_limit`).
- При превышении — 429 + дружелюбный текст.

**Риск:** низкий, всё параметризовано. Конфиг в одном месте — легко откатить.

---

## Группа 7 — Ротация share-token через UI (чистый аддитив)

**Файлы:** [Backend/app/api/wishlists.py](../../../Desktop/Cursor/Вертушка/Backend/app/api/wishlists.py), [Mobile/lib/api.ts](../../../Desktop/Cursor/Вертушка/Mobile/lib/api.ts), [Mobile/app/profile.tsx](../../../Desktop/Cursor/Вертушка/Mobile/app/profile.tsx) (или экран настроек шеринга).

**Что:**
- `POST /api/wishlists/regenerate-share-token` — выдаёт новый токен, старый недействителен.
- Mobile: кнопка «Сменить ссылку» рядом с «Скопировать» с Alert-подтверждением «Старая ссылка перестанет работать у всех, кому ты её отправлял».

**Риск:** минимальный. Метод `regenerate_share_token()` в модели уже есть.

---

## Группа 8 — Разделение `show_gifter_names`

**Файлы:** [Backend/app/models/wishlist.py](../../../Desktop/Cursor/Вертушка/Backend/app/models/wishlist.py), [Backend/app/api/gifts.py](../../../Desktop/Cursor/Вертушка/Backend/app/api/gifts.py) (`/me/received`), [Backend/app/services/notifications.py](../../../Desktop/Cursor/Вертушка/Backend/app/services/notifications.py) (письма владельцу), Mobile settings, alembic-миграция.

**Что:**
- Новое поле `Wishlist.reveal_gifter_to_owner: bool = False`.
- Старое `show_gifter_names` — **как было**, управляет публикой.
- `/me/received` отдаёт `gifter_name` если `reveal_gifter_to_owner=True`, иначе пустую строку (текущее поведение).
- `send_booking_notification_to_owner` — упоминает имя при включённом флаге.
- Mobile: два toggle в настройках вишлиста с подписями «Видно публике на странице» / «Хочу знать имя сразу при бронировании».

**Риск:** низкий, дефолт `False` сохраняет анонимность.

---

## Группа 9 — Email-верификация дарителя (под фичефлагом)

**Файлы:** [Backend/app/config.py](../../../Desktop/Cursor/Вертушка/Backend/app/config.py), [Backend/app/api/gifts.py](../../../Desktop/Cursor/Вертушка/Backend/app/api/gifts.py), новый шаблон `confirm_booking.html`, [Backend/app/web/routes.py](../../../Desktop/Cursor/Вертушка/Backend/app/web/routes.py), [Backend/app/services/notifications.py](../../../Desktop/Cursor/Вертушка/Backend/app/services/notifications.py), [Backend/app/tasks/booking_tasks.py](../../../Desktop/Cursor/Вертушка/Backend/app/tasks/booking_tasks.py).

**Что:**
- Флаг `gift_booking_require_email_verification: bool = False` в `config.py`.
- При **False** — поведение строго как сейчас, бронь сразу `BOOKED`.
- При **True**:
  - `book_gift` создаёт `status=PENDING`, `expires_at = now + 24h` (только окно верификации).
  - Письмо «подтвердить бронь» с ссылкой `/confirm/{id}?token=<verify_token>`.
  - HTML-страница confirm (по образцу `cancel_booking.html`).
  - При подтверждении: `status=BOOKED`, `expires_at = confirmed_at + 60 days` (полный срок брони начинается отсюда).
  - Новая таска `auto_cancel_unverified_bookings` (каждые 5 мин): `PENDING` + `expires_at <= now` → CANCELLED + `cancellation_reason="not_verified"` + `wishlist_item_id=None`.
- Cancel-токен для отмены и verify-токен для подтверждения — раздельные строки на брони (`verify_token` — новое nullable поле).

**Риск:** под флагом — нулевой. С флагом без рабочего SMTP — все брони повиснут в PENDING и через 24ч отменятся. **Поэтому включаем только после подключения почты.**

---

## Группа 10 — Блок-лист email/IP (минимально, без UI)

**Файлы:** новая модель `Backend/app/models/blocked_contact.py`, [Backend/app/api/gifts.py](../../../Desktop/Cursor/Вертушка/Backend/app/api/gifts.py), alembic-миграция.

**Что:**
- Таблица `blocked_contacts` (`id`, `kind` enum email/ip, `value` indexed, `reason`, `blocked_at`, `blocked_by_admin_id` FK→users nullable).
- В `book_gift` перед всеми проверками — lookup по email и IP → 403 «Бронирование недоступно».
- **Без API-ручек** на чтение/запись (поверхность атаки) — заносить SQL'ом или через будущий внутренний инструмент.

**Риск:** минимальный. Пустая таблица никого не блокирует.

---

## Что **не** делаем

- Push для дарителей (нужна привязка push-токена к user + dispatch-сервис → отдельная инфра-задача, в волну 4 при необходимости).
- Админ-UI для блок-листа (управляем SQL'ом до появления админки).
- Алертинг подозрительной активности (всплески, паттерны).

---

## Открытые вопросы

1. **Алембик** — настроен ли `alembic revision --autogenerate` или миграции пишем руками? Проверить перед стартом.
2. **Дефолты лимитов** — 5/час IP, 3 одновременно на email. Корректировать на основании трафика.
3. **Email-верификация** — стартует выключенной (`require_email_verification=False`). Включаем после SMTP.

---

## Порядок реализации

1. Группа 7 (ротация токена) — самое аддитивное.
2. Группа 8 (разделение `show_gifter_names`) — миграция + флаг.
3. Группа 6 (анти-фрод) — миграция + лимиты.
4. Группа 10 (блок-лист) — миграция + lookup.
5. Группа 9 (email-верификация под флагом) — самая большая, но изолирована.

Все миграции — отдельные файлы alembic для индивидуального применения/отката.
