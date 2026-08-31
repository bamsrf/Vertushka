# План: Доработки профиля

## Обзор
Шесть улучшений экрана профиля: проверка уникальности юзернейма, удаление аккаунта с soft delete, настройка нотификаций, блок подписок/подписчиков, кнопка «Планы Вертушки», смена аватарки.

---

## 1. Проверка уникальности юзернейма

**Проблема:** Username уникален в БД (unique constraint), но нет отдельного эндпоинта для проверки доступности. В edit-profile.tsx нет поля для изменения username.

### Backend

**Файл:** `Backend/app/api/users.py`
- Новый эндпоинт `GET /users/check-username/{username}`
- Без авторизации, с rate limit (10/мин)
- Проверяет: длина 3–50, допустимые символы (a-z, 0-9, _), не занят другим юзером
- Возвращает `{ "available": true/false, "reason?": "taken" | "invalid" | "too_short" }`

**Файл:** `Backend/app/schemas/user.py`
- Схема `UsernameCheckResponse`

### Mobile

**Файл:** `Mobile/lib/api.ts`
- Метод `checkUsername(username: string): Promise<{ available: boolean; reason?: string }>`

**Файл:** `Mobile/app/settings/edit-profile.tsx`
- Добавить поле "Юзернейм" (`@username`) с debounced проверкой (300ms)
- Визуальная индикация: зелёная галочка (свободен) / красный текст (занят/невалидный)
- Валидация на клиенте: regex `^[a-z0-9_]{3,50}$`
- При сохранении — `updateMe({ username })` (endpoint уже поддерживает)

---

## 2. Удаление аккаунта (Danger Zone)

### Backend

**Файл:** `Backend/app/models/user.py`
- Новые поля: `deleted_at: DateTime | None`, `scheduled_purge_at: DateTime | None`

**Миграция Alembic:**
- `alembic revision --autogenerate -m "add soft delete fields to user"`

**Файл:** `Backend/app/api/users.py`
- `DELETE /users/me` — soft delete:
  - Ставит `is_active=False`, `deleted_at=now()`, `scheduled_purge_at=now()+30d`
  - Инвалидирует все токены
  - Возвращает 200 с сообщением о 30-дневном окне восстановления

**Файл:** `Backend/app/api/auth.py`
- При логине: если `deleted_at is not None` и `scheduled_purge_at > now()`:
  - Возвращать специальный ответ `{ "status": "deleted", "message": "Аккаунт удалён. Восстановить?", "restore_token": "..." }`
- `POST /auth/restore` — восстановление: очищает `deleted_at`, `scheduled_purge_at`, ставит `is_active=True`

**Cron / Background task:**
- Скрипт `Backend/app/scripts/purge_deleted_users.py`
- Удаляет юзеров где `scheduled_purge_at < now()` с каскадным удалением данных
- Запуск через cron на сервере раз в сутки

### Mobile

**Файл:** `Mobile/lib/api.ts`
- Метод `deleteMyAccount(): Promise<void>`

**Файл:** `Mobile/app/profile.tsx`
- В самом низу, под кнопкой "Выйти" → секция "Опасная зона"
- Красная кнопка "Удалить аккаунт"
- Дисклеймер: серый текст "Аккаунт и все данные будут безвозвратно удалены через 30 дней"

**Модалка подтверждения:**
- Текст: "Вы уверены? Ваш аккаунт, коллекция, вишлист и все данные будут удалены. В течение 30 дней можно восстановить аккаунт, войдя снова."
- Поле ввода: "Введите УДАЛИТЬ для подтверждения"
- Кнопка активна только при вводе "УДАЛИТЬ"
- После подтверждения → вызов API → logout → redirect на auth

---

## 3. Настройка нотификаций

### Запрос разрешения после онбординга

**Файл:** `Mobile/app/onboarding.tsx` (или новый `Mobile/app/notifications-prompt.tsx`)
- Экран после последнего шага онбординга, перед переходом в (tabs)
- UI: иконка колокольчика, текст "Будьте в курсе новых подписчиков и подарков"
- Кнопки: "Разрешить уведомления" (primary) / "Позже" (text)
- При "Разрешить" → `expo-notifications` → `requestPermissionsAsync()` → сохранить push token
- При "Позже" → переход в приложение, можно включить потом в настройках

### Backend

**Файл:** `Backend/app/models/user.py` или новая модель
- Поля: `push_token`, `notify_new_follower`, `notify_gift_booked`, `notify_app_updates`

**Файл:** `Backend/app/api/users.py`
- `PUT /users/me/push-token` — сохранение Expo push token
- `GET /users/me/notification-settings` — текущие настройки
- `PUT /users/me/notification-settings` — обновление тоглов

### Mobile

**Новый файл:** `Mobile/app/settings/notifications.tsx`
- Тоглы (VinylToggle, как в share-profile):
  - "Новый подписчик" (`notify_new_follower`)
  - "Подарок забронирован" (`notify_gift_booked`)
  - "Обновления приложения" (`notify_app_updates`)
- Если уведомления отключены на уровне ОС → баннер "Уведомления отключены" + кнопка "Открыть настройки" (`Linking.openSettings()`)

**Файл:** `Mobile/lib/api.ts`
- `savePushToken(token: string)`
- `getNotificationSettings()`
- `updateNotificationSettings(data)`

**Файл:** `Mobile/lib/store.ts`
- Добавить в `useAuthStore` или новый `useNotificationStore`: `pushToken`, `notificationSettings`

**Зависимость:** `expo-notifications` (установить)

---

## 4. Квадраты "Подписки / Подписчики"

**Текущее состояние:** В профиле 2 карточки: "В коллекции", "В вишлисте". API `GET /users/me/following` и `GET /users/me/followers` уже существуют. `useFollowStore` с `followers/following` уже есть.

### Mobile

**Файл:** `Mobile/app/profile.tsx`
- Секция статистики → grid 2×2 вместо текущих 2 карточек в ряд:
  - "В коллекции" (число) — навигация на вкладку коллекции
  - "В вишлисте" (число) — навигация на вкладку вишлиста
  - "Подписки" (число) — навигация на `social/list?tab=following`
  - "Подписчики" (число) — навигация на `social/list?tab=followers`
- Загрузка counts: из `useFollowStore` (fetchFollowers/fetchFollowing)

**Новый файл:** `Mobile/app/social/list.tsx`
- Параметр `tab`: `followers` | `following`
- SegmentedControl сверху для переключения
- FlatList юзеров: аватарка (круглая, с градиентом) + `@username` + `display_name`
- По нажатию → `router.push(\`/user/${username}\`)`
- Пагинация (infinite scroll)
- Пустое состояние: "Пока нет подписчиков" / "Вы ни на кого не подписаны"

**Новый компонент:** `Mobile/components/UserListItem.tsx`
- Аватарка (40×40, круглая) + username (bold) + display_name (grey)
- Переиспользуемый (для поиска юзеров тоже)

**Файл:** `Mobile/app/_layout.tsx`
- Зарегистрировать маршрут `social/list`

---

## 5. Кнопка «Планы Вертушки»

### Mobile

**Файл:** `Mobile/app/profile.tsx`
- В секцию меню (рядом с "Помощь и обратная связь") добавить пункт:
  - Иконка: `clipboard-list` или `map` (Ionicons)
  - Текст: "Планы Вертушки"
  - Подтекст: "Прозрачность перед пользователями"
  - onPress: `Linking.openURL('https://timestripe.com/boards/sX8B5Keg/')`

---

## 6. Смена аватарки

### Backend

**Файл:** `Backend/app/api/users.py`
- `POST /users/me/avatar` — принимает `multipart/form-data` (файл изображения)
- Валидация: JPEG/PNG, макс 5MB
- Сохранение: локально в `Backend/static/avatars/{user_id}.jpg` (или S3 если настроен)
- Resize до 400×400, сжатие JPEG quality=85
- Обновляет `user.avatar_url` → возвращает URL
- Зависимость: `Pillow` (для resize)

**Файл:** `Backend/app/main.py`
- Раздача статики: `app.mount("/static", StaticFiles(directory="static"))`

### Mobile

**Файл:** `Mobile/app/profile.tsx`
- На аватарке → overlay иконка карандашика (маленький кружок 28×28 в правом нижнем углу)
- Фон кружка: `theme.colors.royalBlue`, иконка: белый pencil
- onPress → ActionSheet: "Выбрать из галереи" / "Сделать фото" / "Удалить аватарку" / "Отмена"

**Файл:** `Mobile/lib/api.ts`
- `uploadAvatar(file: FormData): Promise<{ avatar_url: string }>`
- `deleteAvatar(): Promise<void>`

**Обработка:**
- `expo-image-picker` → `launchImageLibraryAsync` / `launchCameraAsync`
- Настройки: `allowsEditing: true`, `aspect: [1, 1]`, `quality: 0.8`
- После выбора → FormData upload → обновить `useAuthStore.user.avatar_url`
- Синий градиентный контур (`LinearGradient`) остаётся поверх — не зависит от аватарки

**Зависимость:** `expo-image-picker` (проверить, установлен ли)

---

## Порядок реализации

| Приоритет | Пункт | Сложность | Оценка |
|-----------|-------|-----------|--------|
| 1 | **5 — Планы Вертушки** | Низкая | ~15 мин |
| 2 | **4 — Подписки/Подписчики** | Средняя | API готов, нужен UI |
| 3 | **1 — Проверка username** | Средняя | endpoint + UI |
| 4 | **6 — Смена аватарки** | Средняя–высокая | файловый upload |
| 5 | **2 — Удаление аккаунта** | Высокая | миграция, soft delete, UI |
| 6 | **3 — Нотификации** | Высокая | push infra, expo-notifications |

---

## Зависимости для установки

- `expo-notifications` (пункт 3)
- `expo-image-picker` (пункт 6, проверить наличие)
- `Pillow` (Backend, пункт 6, для resize изображений)
