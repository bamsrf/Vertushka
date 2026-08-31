# План: DM v2 — UX-улучшения (Instagram + Telegram стиль)

## Обзор

В M1 уже работает базовая инфраструктура — модели, REST, экраны, optimistic UI. Но визуально и поведенчески UI «бедный», есть конкретные баги и недостающие паттерны, которые есть у эталонов (Instagram DM, Telegram). Этот план фиксит баги и доводит UX до уровня production.

**Эталоны:**
- **Instagram DM** — папки primary/requests, превью с аватарами, action sheet «принять/удалить/блок», pull-to-archive
- **Telegram** — поведение клавиатуры/инпута, состояние «онлайн/был N мин назад», быстрая отправка, индикаторы прочтения, ровные хедеры, плавные переходы

---

## БАГИ — фиксим в первую очередь

### B1. Иконка «назад» рендерится как плюс/мусор

**Где:** [Mobile/app/messages/[conversationId].tsx:217](Mobile/app/messages/%5BconversationId%5D.tsx:217), [Mobile/app/messages/new.tsx:120](Mobile/app/messages/new.tsx:120)

**Корень:** используется `Icon name="chevron-left"`, но в маппинге [Mobile/components/ui/Icon.tsx](Mobile/components/ui/Icon.tsx) такого имени нет. Возвращается дефолт-фоллбэк (видимо плюс).

**Фикс:** заменить на `arrow-left` (точно есть, см. Icon.tsx:182) во всех трёх экранах сообщений (включая `messages/index.tsx` если там тоже back-кнопка).

### B2. Клавиатура наезжает на инпут и кнопку «Отправить»

**Где:** [Mobile/app/messages/[conversationId].tsx:209-213](Mobile/app/messages/%5BconversationId%5D.tsx:209)

**Корень:** `KeyboardAvoidingView` с `keyboardVerticalOffset={0}`. Header высотой ~50px + `insets.top` не компенсируются — клавиатура поднимается на правильную высоту, но контейнер «сжат» на `paddingTop: insets.top`, и инпут с send-кнопкой уезжают вниз за пределы видимой области.

**Фикс:** 
- Убрать `paddingTop: insets.top` с корневого `KeyboardAvoidingView`
- Передавать `paddingTop` отдельно во внутренний `View` хедера через safe-area
- `keyboardVerticalOffset` = высота хедера (~50) + `insets.top` для iOS, `0` для Android
- Альтернатива (надёжнее): использовать `react-native-keyboard-controller` `KeyboardAvoidingView` — рекомендуемый паттерн в RN 0.74+

### B3. «Запросы сообщений • N новых» — без контекста, неясно от кого

**Где:** [Mobile/app/messages/index.tsx:148-167](Mobile/app/messages/index.tsx:148)

**Корень:** баннер только показывает count, без визуального превью отправителей. В Instagram там стек 3-х аватарок и инициалы первого отправителя.

**Фикс:** см. F2 ниже (это и баг, и фича одновременно).

### B4. Серый кружок вверху чата

**Где:** [Mobile/app/messages/[conversationId].tsx:226-238](Mobile/app/messages/%5BconversationId%5D.tsx:226)

**Корень:** хедер чата показывает `partner.avatar_url` или инициалы. Когда диалог открыт впервые через `openOrCreate`, `partner` ещё не загрузился (приходит из `getConversation`), и UI рисует пустой `partnerAvatar` контейнер с `backgroundColor: Colors.surface` — это серый кружок без инициалов и без аватарки.

**Фикс:** 
- Скелетон (`SkeletonPlaceholder` или плавный pulse) пока `partner === null`
- Когда есть `username`, но нет `avatar_url` — рендерить gradient-кружок с инициалами через `LinearGradient`, как в инбоксе и в `user/[username]/index.tsx` (тот же визуальный язык)

### B5. Запрос пустого тела отправляется, кнопка не блокируется визуально

**Где:** [Mobile/app/messages/[conversationId].tsx](Mobile/app/messages/%5BconversationId%5D.tsx) styles.sendBtnDisabled

**Корень:** `opacity: 0.6` слабо считывается, юзер пытается тапать.

**Фикс:** усилить визуал disabled-состояния (серый фон, белый чек или иконка не видна). Плюс: при пустом `draft` кнопка должна быть скрыта или заменена на иконку микрофона (как в Telegram — будущая фича).

---

## ФИЧИ — UX-апгрейд

### F1. Инбокс — компоненты по образцу Telegram/Instagram

**Где:** [Mobile/app/messages/index.tsx](Mobile/app/messages/index.tsx)

**Изменения:**

1. **Сегмент-контрол Primary / Requests** (как в Instagram) если есть pending. Сейчас requests — отдельный экран; правильнее — табы внутри инбокса. Анимированный pill-переключатель (как в `user/[username]/index.tsx` segmented).

2. **Row** диалога — увеличенный аватар (56×56), 2 строки текста:
   - 1-я: имя + время справа
   - 2-я: превью + bullet + бейдж непрочитанного
   - Жирный шрифт превью если непрочитанное
   - Иконка «🔇» рядом с временем если `muted`
   - Иконка «✓✓» если `last_message_sender_id == me && partner.last_read_at >= last_message.created_at`

3. **Swipe actions** (как в Telegram через `react-native-gesture-handler` + `Swipeable`):
   - Свайп влево → кнопки «Закрепить», «Mute», «Архивировать»
   - Свайп вправо → «Прочитано»
   - Долгий тап → ActionSheet с теми же опциями + «Заблокировать», «Очистить историю»

4. **Поиск по диалогам** — search bar над списком (как в Telegram при scroll-up).

5. **Pinned conversations** — закреплённые наверху списка, отдельная секция (требует поле `pinned_at` в `ConversationParticipant` — отдельная миграция M3.2).

### F2. Папка Requests — превью отправителей

**Где:** [Mobile/app/messages/index.tsx](Mobile/app/messages/index.tsx) requestsBanner

**Дизайн (Instagram-style):**
```
┌─────────────────────────────────────────────────┐
│  [👤][👤][👤]   Запросы сообщений           › │
│                 От @alex, @maria и ещё 3        │
└─────────────────────────────────────────────────┘
```

**Реализация:**
- Из `useMessagesStore.conversationsRequests` взять первые 3 — стек аватарок со смещением `marginLeft: -12`, border `#fff`
- Текст: «От @first, @second и ещё N» (если > 3) или «От @first» (если 1)
- Тап → переход на `/messages/requests` (отдельный экран, см. F3)

### F3. Экран «Запросы»

**Новый файл:** `Mobile/app/messages/requests.tsx`

**Дизайн:** список как primary, но каждая карточка раскрыта (превью первого сообщения целиком, до 2 строк) и снизу — 3 кнопки: **Принять** / **Удалить** / **Заблокировать**.

**Бекенд (M3):**
- `POST /api/messages/conversations/{id}/accept/` — меняет `request_status` с pending на accepted
- `POST /api/messages/conversations/{id}/reject/` — ставит `cleared_at` себе (фактически архивирует у получателя)
- `POST /api/messages/block/{user_id}/` — создаёт `UserBlock` + reject

(Эндпоинты M3 уже описаны в [PLAN_DIRECT_MESSAGES.md](PLAN_DIRECT_MESSAGES.md), задача — реализовать)

### F4. Экран треда — paste Telegram

**Где:** [Mobile/app/messages/[conversationId].tsx](Mobile/app/messages/%5BconversationId%5D.tsx)

**Изменения:**

1. **Хедер:**
   - Слева: `arrow-left` (фикс B1)
   - По центру: tappable блок `[avatar 36×36] [username + статус]`. Статус: `онлайн` (зелёная точка) или `был в сети N мин назад` (требует поле `last_seen_at` у User — уже есть, нужен endpoint `/users/{id}/presence/`)
   - Справа: `ellipsis-vertical` → ActionSheet с действиями: «Поиск», «Заглушить», «Очистить историю», «Заблокировать»

2. **Список сообщений** — `FlatList inverted` (как в Telegram), новые сверху в массиве рендерятся внизу экрана. Автоскролл при новом сообщении только если юзер на дне; иначе показать «↓ N новых» pill.

3. **Группировка**:
   - Сообщения от одного отправителя в подряд — единый bubble с одной аватаркой и одним временем
   - Дата-разделитель между блоками («Сегодня», «Вчера», «12 мая»)

4. **Bubble:**
   - Свои справа (cobalt), чужие слева (поверхность)
   - Скруглённый угол со стороны хвоста (как в Telegram)
   - Время и read-receipt внутри пузыря в правом нижнем углу
   - Tap на свой bubble → ActionSheet «Скопировать», «Ответить», «Удалить»

5. **Reply (Telegram-style)** — F5 ниже

6. **Pill «N новых»** при скролле вверх — кнопка прыжка к последнему непрочитанному

### F5. Reply на сообщение (M4 в roadmap, но базовая версия нужна)

- Swipe-right на bubble → активирует reply
- Над input появляется блок «Отвечаем @username: …» с крестиком отмены
- Отправка добавляет к сообщению `reply_to_message_id` (новое поле в `messages`)
- Rendered: тап на reply-preview прокручивает к оригиналу

### F6. Composer (input bar) — нативно как в Telegram

**Где:** [Mobile/app/messages/[conversationId].tsx](Mobile/app/messages/%5BconversationId%5D.tsx) styles.inputBar

**Изменения:**
- Левая иконка `paperclip` (скрепка) — заглушка под «прикрепить пластинку из своей коллекции» (F8)
- TextInput растёт до 5 строк, дальше скролл внутри
- Правая зона: если `draft` пустой → иконка `microphone` (заглушка); если есть текст → круглая кнопка «Отправить» с `arrow-up`
- Анимация плавного перехода (300ms `withTiming`)
- Под TextInput тонкая `divider` сверху, тень — наверх (а не вниз — то что снизу клавиатура, не должна отбрасывать тень)

### F7. Empty state — Telegram-style

**Где:** [Mobile/app/messages/[conversationId].tsx](Mobile/app/messages/%5BconversationId%5D.tsx) emptyConv

**Сейчас:** «Напишите первое сообщение»
**Лучше:** карточка по центру:
```
┌─────────────────────────────┐
│        [avatar 64×64]       │
│         @username           │
│      коллекционер винила    │
│                             │
│   Это начало вашей беседы   │
└─────────────────────────────┘
```
Tap на карточку → `/user/{username}`.

### F8. Share record в чат (M4)

Кнопка «📀» в composer → bottom-sheet с коллекцией пользователя → выбрать пластинку → отправляется специальное сообщение `payload_type='record'` + `record_id`. В чате рендерится мини-карточка обложки + название (как share Instagram-поста).

**Бекенд:** новые поля в `messages`:
- `payload_type` enum: `text | record | profile`
- `payload_data` jsonb

### F9. Typing indicator (M2 — после WS)

Когда собеседник печатает — под последним сообщением «@username печатает…» с тремя точками bouncing. WS-события `typing.start` / `typing.stop` с дебаунсом 1500ms.

### F10. Read receipts visual (Telegram)

Под последним своим сообщением:
- одна тёмная галочка → отправлено серверу
- двойная галочка серая → доставлено (WS-эхо получателю)
- двойная галочка синяя → прочитано (`partner.last_read_at >= message.created_at`)

Сейчас есть `_local_status`, но нет visual diff между 'sent' и 'read'. Добавить компонент `<MessageStatus message conversation me />`.

### F11. Долгий тап → выделение и multi-action

Долгий тап на свой bubble → entering selection mode:
- Top bar превращается в action bar: «Удалить (N)», «Скопировать», иконка `close` для выхода
- Можно тапать другие свои сообщения чтобы добавить в выделение
- «Удалить N» → confirm → batch DELETE

### F12. Pull-to-refresh в треде

Сейчас polling каждые 8с. При жесте pull-down — мгновенный refresh + анимация. На моменте M2 (WS) это станет менее важно, но всё равно полезно.

### F13. Анимация появления нового сообщения

При получении нового сообщения от собеседника — `LayoutAnimation.configureNext(LayoutAnimation.Presets.spring)` или Reanimated `entering={SlideInDown}` для bubble. Своё сообщение появляется с такой же анимацией но из right.

### F14. Прокрутка к unread

При открытии диалога с unread > 0 — автоматически прокрутить к разделителю «Непрочитанные» (Telegram-style линия с надписью). Если unread == 0 — к самому последнему сообщению.

### F15. Composer haptics

`Haptics.selectionAsync()` на:
- успешной отправке
- удалении сообщения
- mute toggle

Уже используется в TabBar (`Haptics.impactAsync`) — переиспользовать.

---

## Технические задачи

### T1. Заменить `chevron-left` → `arrow-left` глобально
```bash
rg "chevron-left" Mobile/app/messages Mobile/app/user
```
Все вхождения → `arrow-left`. **5 минут.**

### T2. Headless-keyboard pattern для composer

```tsx
// messages/[conversationId].tsx
<View style={[styles.container, { paddingTop: insets.top }]}>
  <Header />  {/* фиксированный */}
  <KeyboardAvoidingView
    behavior={Platform.OS === 'ios' ? 'padding' : 'height'}
    keyboardVerticalOffset={Platform.OS === 'ios' ? insets.top + 56 : 0}
    style={{ flex: 1 }}
  >
    <FlatList inverted ... />
    <InputBar />
  </KeyboardAvoidingView>
</View>
```

Альтернатива: `react-native-keyboard-controller` — рекомендуется добавить в зависимости проекта, он уже стандартизирован для подобных кейсов в RN-сообществе.

### T3. Скелетон-плейсхолдер для partner

Пакет `react-content-loader` или ручная анимация opacity через `useSharedValue + withRepeat`. Уже используется reanimated в проекте, проще ручной вариант.

### T4. Группировка сообщений (одинаковый sender + ≤5 мин)

```typescript
function groupMessages(messages: Message[]): Group[] {
  // массив групп: { sender_id, messages, last_at }
  // правило: тот же sender + diff(created_at) <= 5 минут → одна группа
}
```

### T5. Swipeable rows (react-native-gesture-handler)

Уже в зависимостях (`GestureHandlerRootView` в `_layout.tsx`). Использовать `Swipeable` из `react-native-gesture-handler`.

### T6. Папка Requests endpoints

См. M3 в [PLAN_DIRECT_MESSAGES.md](PLAN_DIRECT_MESSAGES.md). Реализовать accept/reject/block + создать экран `messages/requests.tsx`.

### T7. Pinned (M3.2 — новое)

Миграция: `ConversationParticipant.pinned_at: datetime nullable`. Эндпоинт `POST /conversations/{id}/pin/` (toggle). Сортировка в инбоксе: pinned первыми, потом по `last_message_at`. Лимит 5 закреплённых на пользователя.

### T8. Presence (last_seen)

`User.last_seen_at` уже есть в БД. Эндпоинт `GET /api/users/{id}/presence/` возвращает `{online: bool, last_seen_at: datetime}`. `online = last_seen_at > now() - 60s`. Дёргать раз в 30с пока тред открыт.

---

## Фазинг

| Фаза | Содержание | Срок |
|---|---|---|
| **V2.1 — Hotfix** | B1, B2, B4, B5, T1 | 1 коммит, ~30 мин |
| **V2.2 — Inbox polish** | F1 (row + segments), F2 (requests preview), F7 (empty state) | 1 коммит, 2-3 часа |
| **V2.3 — Thread polish** | F4 (header+inverted+grouping), F6 (composer), F13 (animations), T4 | 1 коммит, 3-4 часа |
| **V2.4 — Requests folder** | F3 + T6 (backend endpoints M3) | 1-2 коммита |
| **V2.5 — Actions** | F11 (multi-select), F10 (read receipts visual) | 1 коммит |
| **V2.6 — Swipes & pins** | F1 swipe actions, T5, T7 (pinned) | 1 коммит + миграция |
| **V2.7 — Presence** | T8, индикатор онлайн в хедере | 1 коммит |
| **V2.8 — Reply** | F5 + миграция для `reply_to_message_id` | 1 коммит |
| **V2.9 — Share record** | F8 + payload в messages | 1 коммит + миграция |
| **V2.10 — Realtime (WS)** | M2 из основного плана + F9 (typing) | отдельный план |

---

## Acceptance criteria для V2.1 (hotfix первый)

- [ ] Иконка назад в treade и в /new — нормальная стрелка, не плюс
- [ ] При фокусе TextInput клавиатура не наезжает на кнопку отправки на iOS и Android
- [ ] Серого кружка нет — либо аватар, либо инициалы в gradient-кружке
- [ ] disabled-кнопка отправки очевидно неактивна
- [ ] Smoke-test на iOS Simulator и физическом девайсе

## Acceptance criteria для V2.2 (inbox)

- [ ] Сегмент primary/requests внутри инбокса (без отдельного экрана)
- [ ] Список диалогов: жирное превью при непрочитанном, время справа, бейдж справа от превью
- [ ] Если есть requests — стек 3-х аватаров и текст «От @first, @second и ещё N»
- [ ] Empty state карточкой по центру для нового диалога

## Acceptance criteria для V2.3 (thread)

- [ ] `inverted` FlatList — новые сообщения снизу, скролл естественный
- [ ] Группировка сообщений того же отправителя в один блок если интервал ≤5 мин
- [ ] Дата-разделители («Сегодня», «Вчера», конкретная дата) между группами
- [ ] Composer с paperclip/mic/send-кнопкой, анимация перехода mic ↔ send
- [ ] Анимация появления нового сообщения

---

## Открытые вопросы

1. **Закреплённые диалоги** — 5 шт лимит ок? Или нужен другой?
2. **Reply** — какая визуальная иерархия: маленький блок поверх bubble, или внутри как у iMessage?
3. **Share record** — отправлять только из своей коллекции или из любого результата поиска?
4. **Голосовые сообщения** — в roadmap или нет? (Telegram-классика, но требует expo-av + storage на бекенде)
5. **Typing indicator** — за чей счёт нагрузка: WS отдельным каналом или event'ом основного? (Решение в M2 — единый WS-канал с типизированными событиями)

---

## Эталоны в коде проекта

- **Сегментед-контрол** — использовать `SegmentedControl` из `Mobile/components/ui` (есть в `social/list.tsx`)
- **Avatar gradient placeholder** — паттерн из `Mobile/app/profile.tsx:332-345` (LinearGradient + Icon disc) или `user/[username]/index.tsx:705-720`
- **ActionSheet** — `ActionSheetIOS.showActionSheetWithOptions` на iOS + `Alert.alert` на Android, паттерн в `user/[username]/index.tsx:407-430`
- **Haptics** — `import * as Haptics from 'expo-haptics'`; вызов `Haptics.selectionAsync()` / `impactAsync(Light)`
