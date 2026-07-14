# UGC Moderation (M2 → разблокировать App Store)

> Статус: **PLAN** · Создан 2026-06-19
> Контекст: Apple **Guideline 1.2 (User-Generated Content)** требует реактивных
> механизмов модерации для апок с UGC, видимым другим юзерам. У Вертушки UGC:
> **user-records (`source='user'`, публичные после §6), профили, сообщения**.
> §6 убрал пре-модерацию — это ОК для Apple (человек-модератор не нужен), но
> ревью требует: EULA zero-tolerance + report + block + удаление по жалобе +
> контакт. Без этого сабмит завернут (1.2). `ROADMAP.md`: фича user-records
> «Блокируется: M2 (UGC moderation policy в Store)».

## Что уже есть (переиспользуем)
- **Block юзера** — `Backend/app/api/messages.py::block_user` + модель `UserBlock`.
- **Скрытие user-record** — `moderation_status` на `records`; `profile.py`
  `_PUBLIC_VISIBLE_CLAUSE` / `_is_publicly_visible` уже прячут не-`approved`
  user-records из публичного профиля. Тейкдаун = выставить `'rejected'`.
- **Бан-флаг** — `users.is_active` (уже есть; login можно резать по нему).
- ActionSheet на карточке (`record/[id].tsx`), профиль, чат — точки для кнопки
  «Пожаловаться».

## Чего не хватает (закрыть для 1.2)

### 1. EULA / Условия с zero-tolerance (обязательно — Apple читает текст)
- Экран `Mobile/app/legal/terms.tsx` (и `privacy.tsx`) — статический текст с явной
  формулировкой: «нулевая терпимость к оскорбительному/незаконному контенту и
  abusive-пользователям; нарушители удаляются». Можно markdown/Text.
- Ссылка на условия: экран `(auth)/register.tsx` (чекбокс «принимаю условия» перед
  регистрацией) + строка в `profile.tsx` (Настройки → «Условия использования»).
- Контакт для жалоб (email) — в тексте Terms + в App Store Connect metadata.

### 2. Report — жалоба на контент/юзера (backend)
- Модель `Backend/app/models/report.py::Report`: `id, reporter_id (FK users),
  target_type ('record'|'user'|'message'), target_id (UUID/str), reason (String),
  status ('open'|'reviewed'|'actioned'|'dismissed') default 'open', created_at`.
- Миграция Alembic (новая таблица + индекс `(status, created_at)`).
- API `Backend/app/api/reports.py`:
  - `POST /reports/` — body `{target_type, target_id, reason?}` → создаёт `open`.
    Rate-limit (как gifts anti-abuse) — не больше N/час на юзера.
  - (опц.) `GET /reports/` — только `is_staff`, лента `open`.
- Подключить router в `main.py`.

### 3. Тейкдаун + бан по жалобе (backend, минимально без полноценной админки)
- `POST /reports/{id}/action` (только `is_staff`): `action ∈ {hide_record, ban_user,
  dismiss}`.
  - `hide_record` → `record.moderation_status='rejected'` (исчезает из публичных
    профилей через `_PUBLIC_VISIBLE_CLAUSE`).
  - `ban_user` → `user.is_active=False`.
  - проставить `report.status='actioned'|'dismissed'`.
- **Гейт `rejected` в `get_record`** (`api/records.py`): сейчас после §6 гейта нет —
  вернуть скрытие, но для `moderation_status='rejected'` (не `pending`): не-владельцу
  и не-staff → 404. Иначе скрытый по жалобе релиз остаётся доступен по прямой ссылке.
- **Login-гейт**: `auth.py` login — если `not user.is_active` → 403 «аккаунт
  заблокирован».
- Staff-флоу можно дёргать руками (SQL/скрипт) на старте — главное, что механизм
  удаления/бана СУЩЕСТВУЕТ (Apple проверяет наличие, не UI админки).

### 4. Report-кнопка (mobile)
- `record/[id].tsx` ActionSheet → пункт «Пожаловаться» (для чужих user-records;
  свою не репортим) → `api.reportContent({target_type:'record', target_id})`.
- Профиль чужого юзера (`user/[username]/index.tsx`) → «Пожаловаться» + «Заблокировать»
  (block уже есть в чате — переиспользовать).
- Чат (`messages/[conversationId].tsx`) — «Пожаловаться» на сообщение/собеседника.
- `lib/api.ts::reportContent(payload)` → `POST /reports/`.
- Тост «Спасибо, жалоба отправлена».

## Apple 1.2 чек-лист (что показать на ревью)
- [x] Block abusive users — есть.
- [ ] EULA с zero-tolerance + accept при регистрации.
- [ ] Report objectionable content (кнопка на каждом UGC-объекте).
- [ ] Механизм удаления контента + бана (staff-action endpoint).
- [ ] Контакт для жалоб (Terms + App Store Connect).
- [ ] Реакция ≤24ч — операционно (ты как owner смотришь `GET /reports`).

## Объём
Бэк: 1 модель + 1 миграция + `reports.py` (2-3 ручки) + 2 гейта (get_record
rejected, login is_active). Фронт: 2 статик-экрана (Terms/Privacy) + чекбокс в
register + 3 точки report-кнопки + 1 api-метод. Полноценная админка НЕ нужна.

## Verification
- `POST /reports/` создаёт `open`; rate-limit режет спам.
- staff `action hide_record` → `GET /records/{id}` чужим = 404, в профиле автора нет.
- `ban_user` → login забаненного = 403.
- Register без принятия условий → нельзя продолжить.
- Report-кнопка шлёт жалобу, тост.

## Out of scope
UI-админка (лента/кнопки в апке) — позже. Авто-фильтрация текста (профанити) —
опционально, Apple не требует при наличии report+takedown.
