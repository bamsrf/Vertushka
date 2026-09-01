# План: Публичная страница профиля Вертушка

## Обзор
Единая публичная страница профиля с коллекцией и вишлистом, доступная по ссылке `vinyl-vertushka.ru/@username`. Бронирование подарков анонимное, срок 60 дней с напоминанием и автопродлением. OG-теги для красивых превью в соцсетях.

---

## 0. Критические доработки (на основе ревью)

### 0.1 Mobile: Добавить статус "Забронировано" в вишлист

**Проблема:** В Mobile типах и UI нет отображения статуса бронирования.

**Файлы для изменения:**
- `Mobile/lib/types.ts` — добавить поля в WishlistItem:
  ```typescript
  export interface WishlistItem {
    // ... существующие поля
    is_booked?: boolean;  // Забронировано ли
    gift_booking?: {
      id: string;
      status: 'pending' | 'booked' | 'completed' | 'cancelled';
      booked_at: string;
    } | null;
  }
  ```

- `Mobile/components/RecordCard.tsx` — добавить бейдж "Забронировано":
  ```tsx
  {item.is_booked && (
    <View style={styles.bookedBadge}>
      <Text>🎁 Забронировано</Text>
    </View>
  )}
  ```

- `Mobile/app/(tabs)/collection.tsx` — в режиме "Хочу" показывать бейдж

### 0.2 Логика завершения подарка

**Проблема:** Когда владелец переносит пластинку в коллекцию (`moveToCollection`), нужно автоматически:
1. Отметить `GiftBooking.status = COMPLETED`
2. Отправить email дарителю "Ваш подарок был получен!"

**КРИТИЧЕСКИЙ БАГ:** Сейчас `move_to_collection` удаляет wishlist_item, а у GiftBooking
FK `wishlist_item_id` стоит `ondelete="CASCADE"` — бронирование каскадно удалится и данные потеряются!

**Решение:** Сделать `wishlist_item_id` nullable + `ondelete="SET NULL"`.
Перед удалением wishlist_item — обновить booking:

**Файлы для изменения:**
- `Backend/app/models/gift_booking.py` — изменить FK:
  ```python
  wishlist_item_id: Mapped[uuid.UUID | None] = mapped_column(
      UUID(as_uuid=True),
      ForeignKey("wishlist_items.id", ondelete="SET NULL"),
      nullable=True,  # Было nullable=False
      unique=True,
      index=True
  )
  ```

- `Backend/app/api/wishlists.py` — в endpoint `move_to_collection`:
  ```python
  # 1. Подгрузить gift_booking (добавить selectinload)
  # 2. Перед удалением wishlist_item:
  if item.gift_booking:
      item.gift_booking.status = GiftStatus.COMPLETED
      item.gift_booking.completed_at = datetime.utcnow()
      item.gift_booking.wishlist_item_id = None  # Отвязываем до удаления
      await db.flush()  # Сохраняем booking
  # 3. Только потом удаляем wishlist_item
  ```

### 0.3 Экран просмотра чужого вишлиста (в приложении)

**Новый файл:** `Mobile/app/user/[username]/wishlist.tsx`

**Зависимость:** Нужен новый backend endpoint `GET /api/users/{username}/wishlist/`
(существующий `GET /wishlists/share/{share_token}` работает по токену, не по username).

**Права доступа (два уровня):**
- **Просмотр вишлиста:** профиль открытый ИЛИ ты фолловер
- **Бронирование подарка в приложении:** ТОЛЬКО фолловеры
- **Бронирование через веб-страницу** (`/@username`): доступно всем, авторизация не нужна, но email обязателен (подтверждение, напоминания, отмена по cancel_token)

Функционал:
- Просмотр вишлиста друга (если подписан или профиль открытый)
- Кнопка "🎁 Подарить" — только для фолловеров (иначе показываем "Подпишитесь, чтобы подарить")
- Модалка бронирования (имя, email, сообщение)
- Бронирование анонимное (владелец не видит кто)

---

## 1. Backend

### 1.1 Новая модель ProfileShare
**Файл:** `Backend/app/models/profile_share.py`

```python
class ProfileShare(Base):
    id: UUID
    user_id: UUID (FK, unique)

    # Публичность
    is_active: bool = False
    is_private_profile: bool = False  # Требует одобрения фолловеров
    show_collection: bool = True
    show_wishlist: bool = True

    # Персонализация
    custom_title: str | None
    highlight_record_ids: list[UUID] | None  # Избранные (до 4, выбирает юзер)

    # Настройки отображения карточек пластинок
    show_record_year: bool = True
    show_record_label: bool = True
    show_record_format: bool = True
    show_record_prices: bool = False       # Цены пластинок — скрыты по умолчанию

    # Настройки статистики профиля
    show_collection_value: bool = False    # Общая стоимость — скрыта по умолчанию

    # OG Meta
    og_image_url: str | None  # Сгенерированное изображение

    # Статистика
    view_count: int = 0
    created_at, updated_at
```

**Принцип:** Юзер сам решает что показывать. Цены скрыты по умолчанию —
кто хочет похвастаться, включает сам. Кто не хочет — всё скрыто из коробки.

### 1.2 Расширение GiftBooking
**Файл:** `Backend/app/models/gift_booking.py` — добавить:

```python
expires_at: datetime | None  # booked_at + 60 дней
reminder_sent_at: datetime | None  # Когда отправили напоминание
```

### 1.3 Новые API endpoints
**Файл:** `Backend/app/api/profile.py`

| Endpoint | Auth | Описание |
|----------|------|----------|
| `GET /@{username}` | - | HTML страница профиля с OG-тегами |
| `GET /@{username}/og-image.png` | - | Динамическое OG-изображение |
| `GET /api/profile/public/{username}` | - | JSON данные профиля |
| `GET /api/users/{username}/wishlist/` | Опц. | Вишлист юзера (просмотр: открытый профиль / фолловер) |
| `GET /api/profile/settings` | Да | Настройки шеринга |
| `PUT /api/profile/settings` | Да | Обновить настройки (вкл. отображение полей) |
| `PUT /api/profile/highlights` | Да | Установить 4 избранные пластинки |
| `GET /api/users/search?q=` | Да | Поиск по username |

### 1.4 Cron-задачи (APScheduler)
**Файл:** `Backend/app/tasks/booking_tasks.py`

1. **Каждый день:** Отправить напоминание дарителям за 7 дней до истечения
2. **Каждый час:** Автопродлить истёкшие брони на 30 дней (если не отменены)

### 1.5 Уведомления
**Файл:** `Backend/app/services/notifications.py`

- Push + email владельцу при новом бронировании (без имени дарителя!)
- Email дарителю за 7 дней до истечения брони

---

## 2. Web страница с OG-тегами

### 2.1 HTML шаблон
**Файл:** `Backend/app/web/templates/public_profile.html`

```html
<head>
    <!-- Open Graph для соцсетей -->
    <meta property="og:type" content="profile">
    <meta property="og:title" content="Коллекция винила @{{ username }}">
    <meta property="og:description" content="{{ collection_count }} пластинок{% if show_value %} • ~${{ total_value }}{% endif %}">
    <meta property="og:image" content="https://vinyl-vertushka.ru/@{{ username }}/og-image.png">
    <meta property="og:url" content="https://vinyl-vertushka.ru/@{{ username }}">

    <!-- Twitter Card -->
    <meta name="twitter:card" content="summary_large_image">
    <meta name="twitter:image" content="https://vinyl-vertushka.ru/@{{ username }}/og-image.png">
</head>
```

### 2.2 Структура страницы
- **Header:** Аватар, имя, bio, статистика (кол-во пластинок, стоимость если включена, в вишлисте)
- **Highlights:** Секция с 4 избранными пластинками (юзер выбирает сам)
- **Табы:** Коллекция / Вишлист
- **Коллекция:** Grid пластинок (только просмотр, поля по настройкам юзера)
- **Вишлист:** Grid с кнопками "Забронировать" (анонимно, доступно всем на вебе)
- **Footer:** CTA "Создать свой профиль" + ссылка на приложение

**Карточки пластинок показывают только то, что включил юзер в настройках:**
год, лейбл, формат, цена — каждое поле отдельно включается/выключается.

### 2.3 Динамическое OG-изображение
**Файл:** `Backend/app/services/og_image.py`

Генерация PNG 1200x630px:
- Коллаж из 4 обложек избранных пластинок (из highlight_record_ids)
- Имя пользователя
- Статистика: "127 пластинок" (+ стоимость только если show_collection_value = true)
- Логотип Вертушка

Кэшировать в файловую систему, обновлять при изменении коллекции.

---

## 3. Mobile приложение

### 3.1 Новые экраны
| Экран | Путь | Описание |
|-------|------|----------|
| Настройки шеринга | `app/settings/share-profile.tsx` | Управление публичным профилем |
| Профиль пользователя | `app/user/[username].tsx` | Просмотр профиля другого юзера |
| Поиск пользователей | `app/search/users.tsx` | Поиск по @username |

### 3.2 Функционал профиля друга
- Просмотр коллекции и вишлиста (если разрешено)
- Кнопка "Подписаться" (follow)
- Бронирование из вишлиста (анонимно)
- Запрос на подписку (если приватный профиль)

### 3.3 Store
**Файл:** `Mobile/lib/store.ts` — добавить:

```typescript
// ProfileStore - настройки публичности
// FollowStore - подписки и подписчики
// UserSearchStore - поиск пользователей
```

### 3.4 Кнопка "Поделиться"
В `app/profile.tsx` и `app/(tabs)/collection.tsx`:
- Копировать ссылку `vinyl-vertushka.ru/@username`
- Нативный Share Sheet

---

## 4. Социальные функции (внутри приложения)

### 4.1 Follow система
**Файл:** `Backend/app/models/follow.py` (уже существует)

- Открытый профиль: подписка мгновенная
- Приватный профиль: запрос → одобрение владельцем

### 4.2 Лента друзей (опционально, v2)
- Новые пластинки в коллекциях друзей
- Активность (кто что добавил)

---

## 5. Критические файлы для изменения

| Файл | Изменения |
|------|-----------|
| `Backend/app/models/user.py` | Связь с ProfileShare |
| `Backend/app/models/gift_booking.py` | + expires_at, reminder_sent_at |
| `Backend/app/api/wishlists.py` | Убрать показ имени дарителя |
| `Backend/app/main.py` | + APScheduler, + web routes |
| `Mobile/lib/api.ts` | + методы profile, users, follow |
| `Mobile/lib/store.ts` | + ProfileStore, FollowStore |
| `Mobile/lib/types.ts` | + типы ProfileShare, UserPublic |

---

## 6. Порядок реализации

### Фаза 1: Backend Core
1. Модель ProfileShare + миграция
2. Поле expires_at в GiftBooking + миграция
3. API endpoints для профиля
4. Cron-задачи для бронирований

### Фаза 2: Web страница
1. HTML шаблон public_profile.html
2. OG мета-теги
3. Web route `/@username`
4. Генерация OG-изображений

### Фаза 3: Mobile
1. Экран настроек шеринга
2. Просмотр профиля другого юзера
3. Поиск по username
4. Бронирование из приложения

### Фаза 4: Уведомления
1. Push при бронировании
2. Email при бронировании
3. Email-напоминание дарителю

---

## 7. Ключевые решения

| Вопрос | Решение |
|--------|---------|
| URL формат | `/@username` (красиво, но раскрывает username) |
| Анонимность брони | Всегда анонимно, владелец не видит кто |
| Срок бронирования | 60 дней → напоминание за 7 дней → автопродление на 30 |
| Цены / стоимость | **Скрыты по умолчанию**, юзер включает сам |
| Поля на карточках | Год, лейбл, формат, цена — каждое отдельно вкл/выкл |
| Топ-пластинки | 4 штуки, юзер выбирает сам из своей коллекции |
| Приватность профиля | На выбор пользователя |
| Бронирование (веб) | Без авторизации, но email обязателен (для уведомлений и отмены) |
| Бронирование (приложение) | Только для фолловеров, email тоже обязателен |
| Поиск друзей | По @username |

---

## 8. Дизайн публичной страницы

### 8.1 Визуальная концепция

**Стиль:** Минималистичный dark-theme, как в существующем `public_wishlist.html`

**Цветовая палитра (из theme.ts):**
- Background: `#0f0f0f` (тёмный)
- Card: `#252525`
- Accent: `#e85d04` (оранжевый)
- Text: `#ffffff` / `#a0a0a0`

### 8.2 Структура страницы

```
┌─────────────────────────────────────────┐
│  ┌────┐                                 │
│  │ 👤 │  @vladislav                     │
│  └────┘  "Собираю винил с 2015 года"    │
│                                         │
│  ┌─────────┐ ┌─────────┐ ┌─────────┐   │
│  │ 127     │ │ ~$2,400 │ │ 23      │   │
│  │пластинок│ │стоимость│ │в вишлист│   │
│  └─────────┘ └─────────┘ └─────────┘   │
│  (стоимость только если show_collection_value = true)
├─────────────────────────────────────────┤
│  ⭐ ИЗБРАННОЕ (4 пластинки, юзер выбирает)
│  ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐
│  │ 🎵      │ │ 🎵      │ │ 🎵      │ │ 🎵      │
│  └─────────┘ └─────────┘ └─────────┘ └─────────┘
├─────────────────────────────────────────┤
│  [Коллекция] [Вишлист]  ← табы          │
├─────────────────────────────────────────┤
│  ┌─────────┐ ┌─────────┐ ┌─────────┐   │
│  │ 🎵      │ │ 🎵      │ │ 🎵 🎁   │   │
│  │ Title   │ │ Title   │ │ Title   │   │
│  │ Artist  │ │ Artist  │ │ Artist  │   │
│  │ 1975    │ │ 1975    │ │ 1975    │   │  ← если show_record_year
│  │ ~$30    │ │ ~$30    │ │Заброн.  │   │  ← если show_record_prices
│  │ [Дарить]│ │ [Дарить]│ │         │   │
│  └─────────┘ └─────────┘ └─────────┘   │
├─────────────────────────────────────────┤
│  Создано в Вертушка 🎶                  │
│  [Создать свой профиль]                 │
└─────────────────────────────────────────┘
```

### 8.3 OG-изображение для соцсетей

**Размер:** 1200x630px
**Формат:** PNG

```
┌────────────────────────────────────────────────┐
│                                                │
│  ┌────┐ ┌────┐           ВЕРТУШКА              │
│  │ 🎵 │ │ 🎵 │                                 │
│  └────┘ └────┘           @vladislav            │
│  ┌────┐ ┌────┐           ───────────           │
│  │ 🎵 │ │ 🎵 │           127 пластинок         │
│  └────┘ └────┘           ~$2,400               │
│                                                │
│  коллаж из 4 обложек     vinyl-vertushka.ru    │
└────────────────────────────────────────────────┘
```

**Генерация:** Python + Pillow, кэшировать в файловую систему.

### 8.4 Бейдж "Забронировано" в Mobile

В карточке пластинки в режиме "Хочу":

```
┌─────────────────┐
│ 🎵 [Cover]      │
│                 │
│ ┌─────────────┐ │
│ │ 🎁 Заброн.  │ │  ← бейдж поверх обложки
│ └─────────────┘ │
│ Pink Floyd      │
│ The Wall        │
│ [В коллекцию]   │  ← если забронировано, меняем текст кнопки
└─────────────────┘
```

---

## 9. Верификация

1. Открыть `vinyl-vertushka.ru/@testuser` — должна загрузиться страница
2. Поделиться ссылкой в Telegram — должна появиться карточка с картинкой
3. Забронировать пластинку — владелец получает push без имени дарителя
4. В приложении в "Хочу" видеть бейдж "Забронировано"
5. Перенести забронированную пластинку в коллекцию — даритель получает email "Подарок получен!"
6. В приложении найти друга по @username и подписаться
7. Забронировать пластинку из вишлиста друга внутри приложения
