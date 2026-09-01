# План: Direct Messages (личные сообщения)

## Обзор

Прямые сообщения между пользователями Вертушки. Доступ через кнопку «Написать» в чужом профиле (`Mobile/app/user/[username]/index.tsx:436`) и через новый таб «Сообщения». Privacy-модель — Instagram-style:

- Любой авторизованный пользователь может написать кому угодно.
- Если получатель **не подписан** на отправителя → сообщение попадает в папку **Запросы**, без push-уведомления, без бейджа в основном инбоксе.
- Получатель видит превью, может нажать «Принять» (тред переезжает в primary, дальнейшие сообщения идут как обычно), «Удалить» или «Заблокировать».
- Для **приватных** профилей (`is_private_profile=true`) сообщения принимаются только от взаимных подписчиков; иначе 403.

Realtime через WebSocket в том же FastAPI, оффлайн — Expo push. Стор — PostgreSQL основного бекенда (не Supabase).

---

## Архитектурные решения

| Решение | Выбор | Причина |
|---|---|---|
| Где хранится | Postgres основного backend | Транзакционность с follows/users, общая JWT-авторизация, Alembic |
| Realtime транспорт | WebSocket в FastAPI | Уже uvicorn, не нужен внешний сервис; in-memory hub в MVP |
| Privacy | Instagram-style requests | Нулевой барьер для первого контакта, спам в отдельной папке |
| Read receipts | Включены всегда | В MVP без выключателя |
| Удаление сообщения «у всех» | Без time-limit, tombstone | Простая логика, понятно пользователю |
| Группы | Нет в MVP | Только 1-к-1 |
| Saved messages | Нет | Не приоритет |

---

## Фазинг

| Фаза | Содержание | Готово когда |
|---|---|---|
| **M1** | Модели, миграция, REST CRUD, базовый mobile UI на polling | Можно открыть чужой профиль → «Написать» → переписаться (с задержкой до 8с) |
| **M2** | WebSocket realtime + статусы доставки/чтения | Сообщения мгновенно, индикатор прочтения работает |
| **M3** | Папка «Запросы» + Expo push + блокировки | Полный Instagram-flow, push на оффлайн получателя |
| **M4** | Rich content (share record), edit, typing | Inline-карточки пластинок, редактирование, индикатор печати |

В этом плане детально расписаны **M1–M3**. M4 — список идей, без детализации.

---

## M1 — Каркас: модели, REST, базовый UI (polling)

### 1.1 Backend: модели

#### Новый файл `Backend/app/models/conversation.py`
```python
import uuid
from datetime import datetime
from sqlalchemy import DateTime, String, ForeignKey, UniqueConstraint, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID

from app.database import Base


class Conversation(Base):
    """Диалог 1-к-1 между двумя пользователями."""
    __tablename__ = "conversations"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Каноничная пара (min(user_id), max(user_id)) для уникальности диалога на пару
    user_a_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    user_b_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    last_message_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    last_message_preview: Mapped[str | None] = mapped_column(String(160), nullable=True)
    last_message_sender_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    __table_args__ = (
        UniqueConstraint("user_a_id", "user_b_id", name="uq_conversation_pair"),
        Index("ix_conversation_last_message_at", "last_message_at"),
    )

    participants = relationship("ConversationParticipant", back_populates="conversation", cascade="all, delete-orphan")
    messages = relationship("Message", back_populates="conversation", cascade="all, delete-orphan")


class ConversationParticipant(Base):
    """Per-user состояние участника диалога: прочтение, мьют, архив, очистка."""
    __tablename__ = "conversation_participants"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    conversation_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)

    joined_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    last_read_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    muted: Mapped[bool] = mapped_column(default=False, nullable=False, server_default="false")
    archived_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    cleared_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    # M3: статус запроса для этого участника как получателя
    request_status: Mapped[str] = mapped_column(String(16), default="accepted", nullable=False, server_default="accepted")
    # 'accepted' | 'pending' | 'rejected' — see M3.1

    __table_args__ = (UniqueConstraint("conversation_id", "user_id", name="uq_participant"),)

    conversation = relationship("Conversation", back_populates="participants")


class Message(Base):
    """Одно сообщение в диалоге."""
    __tablename__ = "messages"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    conversation_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False, index=True)
    sender_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)

    body: Mapped[str | None] = mapped_column(String(4000), nullable=True)  # null если deleted_at
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    edited_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    client_nonce: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)

    __table_args__ = (
        Index("ix_messages_conv_created", "conversation_id", "created_at"),
        UniqueConstraint("sender_id", "client_nonce", name="uq_message_idempotency"),
    )

    conversation = relationship("Conversation", back_populates="messages")
```

#### Новый файл `Backend/app/models/user_block.py`
```python
import uuid
from datetime import datetime
from sqlalchemy import DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID

from app.database import Base


class UserBlock(Base):
    """Блокировка одного пользователя другим. Симметрична по эффекту в чате."""
    __tablename__ = "user_blocks"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    blocker_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    blocked_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (UniqueConstraint("blocker_id", "blocked_id", name="uq_user_block"),)
```

#### Регистрация в `Backend/app/models/__init__.py`
Добавить импорты `Conversation`, `ConversationParticipant`, `Message`, `UserBlock`.

#### Изменения в `Backend/app/models/user.py`
Добавить настройку нотификаций для сообщений:
```python
notify_messages: Mapped[bool] = mapped_column(
    Boolean, default=True, nullable=False, server_default="true"
)
```

### 1.2 Alembic миграция

Файл `Backend/alembic/versions/<NEXT>_add_direct_messages.py`:
- `create_table("conversations", ...)`
- `create_table("conversation_participants", ...)`
- `create_table("messages", ...)`
- `create_table("user_blocks", ...)`
- `add_column("users", "notify_messages", server_default="true")`
- Все индексы из моделей.

После генерации проверить: `cd Backend && alembic upgrade head` локально.

### 1.3 Pydantic-схемы

#### Новый файл `Backend/app/schemas/message.py`
```python
from datetime import datetime
from uuid import UUID
from pydantic import BaseModel, Field


class MessageCreate(BaseModel):
    body: str = Field(..., min_length=1, max_length=4000)
    client_nonce: str | None = Field(None, max_length=64)


class MessageRead(BaseModel):
    id: UUID
    conversation_id: UUID
    sender_id: UUID
    body: str | None
    created_at: datetime
    edited_at: datetime | None
    deleted_at: datetime | None
    client_nonce: str | None
    class Config: from_attributes = True


class ConversationPartner(BaseModel):
    id: UUID
    username: str
    display_name: str | None
    avatar_url: str | None


class ConversationRead(BaseModel):
    id: UUID
    partner: ConversationPartner
    last_message_preview: str | None
    last_message_at: datetime | None
    last_message_sender_id: UUID | None
    unread_count: int
    muted: bool
    request_status: str  # 'accepted' | 'pending'
    is_blocked: bool
    class Config: from_attributes = True


class ConversationCreate(BaseModel):
    recipient_user_id: UUID


class ReadMarker(BaseModel):
    up_to_message_id: UUID


class UnreadCount(BaseModel):
    primary: int
    requests: int
```

### 1.4 Сервисный слой `Backend/app/services/messaging.py`

Центральный модуль. Содержит pure-функции:

```python
async def get_or_create_conversation(db, user_a_id, user_b_id) -> Conversation:
    """Возвращает существующий диалог пары или создаёт новый.
    user_a_id, user_b_id канонизируются по min/max для уникальности."""
    ...

async def can_send_message(db, sender, recipient) -> tuple[bool, str | None, bool]:
    """Возвращает (allowed, reason_if_denied, goes_to_requests).
    - блок в любую сторону → (False, 'blocked', _)
    - получатель приватный и нет mutual follow → (False, 'private_profile', _)
    - получатель не подписан на отправителя → (True, None, True)  # request
    - иначе → (True, None, False)"""
    ...

async def post_message(db, conversation, sender_id, body, client_nonce, goes_to_requests) -> Message:
    """Создаёт Message, обновляет conversations.last_message_*,
    выставляет request_status='pending' получателю если goes_to_requests=True."""
    ...

async def mark_read(db, conversation_id, user_id, up_to_message_id) -> int:
    """Обновляет ConversationParticipant.last_read_at; возвращает новое непрочитанное."""
    ...

async def compute_unread(db, user_id) -> tuple[int, int]:
    """Возвращает (primary_unread, requests_unread)."""
    ...
```

### 1.5 API роутер `Backend/app/api/messages.py`

```
GET    /api/messages/conversations/            ?folder=primary|requests
GET    /api/messages/conversations/{id}/        # тред + first page messages
GET    /api/messages/conversations/{id}/messages/  ?before=<msg_id>&limit=50
POST   /api/messages/conversations/             # body: {recipient_user_id}
POST   /api/messages/conversations/{id}/messages/  # body: MessageCreate
POST   /api/messages/conversations/{id}/read/   # body: ReadMarker
DELETE /api/messages/messages/{id}/             # tombstone
GET    /api/messages/unread-count/
```

Endpoints из M3 (accept/mute/archive/clear/block) добавятся в M3.

Регистрация в `Backend/app/main.py`:
```python
from app.api import auth, records, collections, wishlists, users, gifts, profile, export, covers, user_photos, waitlist, achievements, offers, messages
app.include_router(messages.router, prefix="/api/messages", tags=["Сообщения"])
```

Rate limits на отправку:
- `60/minute` для `POST .../messages/` (slowapi)
- `10/hour` для `POST /conversations/` (создание новых тредов)

### 1.6 Mobile: типы и API-клиент

#### `Mobile/lib/types.ts` — добавить
```typescript
export interface ConversationPartner {
  id: string;
  username: string;
  display_name: string | null;
  avatar_url: string | null;
}

export interface Conversation {
  id: string;
  partner: ConversationPartner;
  last_message_preview: string | null;
  last_message_at: string | null;
  last_message_sender_id: string | null;
  unread_count: number;
  muted: boolean;
  request_status: 'accepted' | 'pending';
  is_blocked: boolean;
}

export interface Message {
  id: string;
  conversation_id: string;
  sender_id: string;
  body: string | null;
  created_at: string;
  edited_at: string | null;
  deleted_at: string | null;
  client_nonce: string | null;
  // клиентский статус, не приходит с сервера
  _local_status?: 'sending' | 'sent' | 'failed';
}

export type MessageFolder = 'primary' | 'requests';

export interface UnreadCount { primary: number; requests: number }
```

#### `Mobile/lib/api.ts` — добавить методы
```typescript
listConversations(folder: MessageFolder): Promise<Conversation[]>
getConversation(id: string): Promise<{ conversation: Conversation; messages: Message[] }>
listMessages(id: string, before?: string, limit?: number): Promise<Message[]>
createConversation(recipient_user_id: string): Promise<Conversation>
sendMessage(conv_id: string, body: string, client_nonce: string): Promise<Message>
markRead(conv_id: string, up_to_message_id: string): Promise<void>
deleteMessage(id: string): Promise<void>
getUnreadCount(): Promise<UnreadCount>
```

### 1.7 Mobile: Zustand store

#### `Mobile/lib/store.ts` — добавить `useMessagesStore`
```typescript
interface MessagesState {
  conversationsPrimary: Conversation[];
  conversationsRequests: Conversation[];
  // messages by conversation id
  threads: Record<string, Message[]>;
  unread: UnreadCount;
  isLoadingList: boolean;
  isLoadingThread: Record<string, boolean>;

  loadConversations(folder: MessageFolder): Promise<void>;
  loadThread(id: string): Promise<void>;
  loadMore(id: string): Promise<void>;
  send(id: string, body: string): Promise<void>;
  markRead(id: string): Promise<void>;
  refreshUnread(): Promise<void>;
  openOrCreate(partnerUserId: string): Promise<string>; // вернёт conversation id
}
```

Внутри `send`: оптимистично push в `threads[id]` со статусом `'sending'` и временным id `local-<nonce>`. По ответу сервера — заменить запись на серверную, не дублируя.

### 1.8 Mobile: экраны

#### Новый файл `Mobile/app/(tabs)/messages.tsx`
Инбокс. Сегментед-контрол `Primary / Запросы` если есть запросы (иначе только primary). FlatList диалогов: аватар, ник, превью, время, бейдж непрочитанных. Pull-to-refresh.

При тапе → `router.push('/messages/' + conv.id)`.

#### Новый файл `Mobile/app/messages/[conversationId].tsx`
Экран треда. Header с аватаром собеседника и его @username (тап → его профиль). FlatList сообщений (inverted), TextInput внизу, кнопка отправки. Polling `loadThread` каждые 8с пока экран открыт (в M2 заменим на WS).

Пузыри: свои справа (cobalt), чужие слева (whiteSoft). Тайм-маркеры группировкой по часу. Tombstone deleted_at — серый «Сообщение удалено».

#### Новый файл `Mobile/app/messages/new.tsx`
Поиск пользователя для нового сообщения. Использует существующую ручку поиска юзеров. На выбор → `openOrCreate` → push на тред.

#### Изменить `Mobile/app/(tabs)/_layout.tsx`
Добавить таб «Сообщения» с иконкой `chatbubble-outline`. Бейдж непрочитанных из `useMessagesStore.unread.primary`.

#### Изменить `Mobile/app/user/[username]/index.tsx:436`
```typescript
const handleMessage = useCallback(async () => {
  if (!profileUserId) return;
  try {
    const convId = await useMessagesStore.getState().openOrCreate(profileUserId);
    router.push(`/messages/${convId}`);
  } catch (error: any) {
    toast.error('Ошибка', error?.response?.data?.detail || 'Не удалось открыть чат');
  }
}, [profileUserId, router]);
```

### 1.9 Polling unread в фоне

В `Mobile/app/_layout.tsx` или корневом провайдере — `setInterval` каждые 20с дёргать `refreshUnread()` пока user авторизован и app foreground. Через `AppState` слушать `change`. В M2 заменится на WS-события.

### 1.10 Acceptance criteria M1

- [ ] Миграция применяется на dev и prod
- [ ] `POST /api/messages/conversations/` с recipient_user_id возвращает существующий или создаёт новый
- [ ] `POST /api/messages/conversations/{id}/messages/` создаёт сообщение, обновляет `last_message_*`
- [ ] Идемпотентность: повтор с тем же `client_nonce` от того же sender возвращает существующий message
- [ ] Кнопка «Написать» на чужом профиле открывает тред
- [ ] Список диалогов в табе отсортирован по `last_message_at desc`
- [ ] Polling работает: получатель видит новое сообщение в течение 8с
- [ ] Rate limits срабатывают: 61-е сообщение в минуту получает 429

---

## M2 — Realtime: WebSocket + статусы

### 2.1 Backend: WS endpoint

#### Новый файл `Backend/app/api/messages_ws.py`
```python
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query, Depends, status
from app.api.deps import authenticate_ws_token

router = APIRouter()

# In-memory hub: user_id (UUID str) → list[WebSocket]
hub: dict[str, list[WebSocket]] = {}

@router.websocket("/ws")
async def messages_ws(websocket: WebSocket, token: str = Query(...)):
    user = await authenticate_ws_token(token)
    if not user:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return
    await websocket.accept()
    hub.setdefault(str(user.id), []).append(websocket)
    try:
        while True:
            # читаем чтобы детектить disconnect; команды клиента не используем в M2
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        hub[str(user.id)].remove(websocket)
        if not hub[str(user.id)]:
            del hub[str(user.id)]


async def push_event(user_id, event: dict):
    """Отправить событие пользователю по всем его WS-сессиям."""
    for ws in list(hub.get(str(user_id), [])):
        try:
            await ws.send_json(event)
        except Exception:
            pass
```

`authenticate_ws_token` — обёртка над существующим JWT-декодером, принимает токен из query (т.к. WS не передают заголовки удобно с RN).

### 2.2 Интеграция в `post_message`

В `Backend/app/services/messaging.py` после успешного создания сообщения:
```python
from app.api.messages_ws import push_event

event = {
  "type": "message.new",
  "conversation_id": str(message.conversation_id),
  "message": MessageRead.model_validate(message).model_dump(mode="json"),
  "goes_to_requests": goes_to_requests,
}
await push_event(recipient_id, event)
# отправитель тоже получает echo — для синхронизации между устройствами
await push_event(sender_id, event)
```

Аналогично для `mark_read` → `message.read`, для `delete_message` → `message.deleted`.

### 2.3 Mobile: WS-клиент

#### Новый файл `Mobile/lib/ws.ts`
```typescript
type WsEvent =
  | { type: 'message.new'; conversation_id: string; message: Message; goes_to_requests: boolean }
  | { type: 'message.read'; conversation_id: string; user_id: string; up_to_message_id: string }
  | { type: 'message.deleted'; conversation_id: string; message_id: string };

class MessagesSocket {
  private ws: WebSocket | null = null;
  private listeners = new Set<(e: WsEvent) => void>();
  private reconnectTimer: any;
  private backoffMs = 1000;

  connect(token: string) {
    const url = `${API_WS_URL}/api/messages/ws?token=${token}`;
    this.ws = new WebSocket(url);
    this.ws.onopen = () => { this.backoffMs = 1000; };
    this.ws.onmessage = (e) => {
      const event = JSON.parse(e.data) as WsEvent;
      this.listeners.forEach((l) => l(event));
    };
    this.ws.onclose = () => this.scheduleReconnect(token);
    this.ws.onerror = () => this.ws?.close();
  }

  private scheduleReconnect(token: string) {
    clearTimeout(this.reconnectTimer);
    this.reconnectTimer = setTimeout(() => this.connect(token), this.backoffMs);
    this.backoffMs = Math.min(this.backoffMs * 2, 30_000);
  }

  subscribe(fn: (e: WsEvent) => void) {
    this.listeners.add(fn);
    return () => this.listeners.delete(fn);
  }

  disconnect() {
    clearTimeout(this.reconnectTimer);
    this.ws?.close();
    this.ws = null;
  }
}

export const messagesSocket = new MessagesSocket();
```

### 2.4 Подписка в store

`useMessagesStore` подписывается на события и:
- `message.new` → push в `threads[conv_id]` (если sender !== me → инкремент unread; иначе — сверить с optimistic через `client_nonce` и заменить)
- `message.read` → обновить статусы своих сообщений в треде
- `message.deleted` → найти сообщение и установить `deleted_at`

Подключение WS — в `Mobile/app/_layout.tsx` при наличии auth-токена; отключение — на logout и при app background.

### 2.5 Статусы доставки и прочтения

Локальное поле `_local_status` на сообщении:
- `'sending'` — после оптимистичного push
- `'sent'` — после REST-ответа
- `'failed'` — при ошибке отправки, показывать ⚠️ + tap to retry

Под последним моим сообщением — лейбл «Прочитано» если `last_read_at собеседника >= message.created_at`.

### 2.6 Polling fallback

Если WS не подключён (нет интернета / не дошёл `onopen` за 10с) → store включает polling каждые 8с. Когда WS открывается → polling выключается.

### 2.7 Acceptance criteria M2

- [ ] WS соединение устанавливается с валидным JWT, отклоняется без
- [ ] Сообщение, отправленное юзером A, появляется у юзера B в течение 1с (оба онлайн)
- [ ] Reconnect с экспоненциальным backoff после потери соединения
- [ ] Optimistic UI: своё сообщение мгновенно в треде, дедуплицируется при echo
- [ ] Read receipt у собеседника обновляется при открытии треда
- [ ] При потере WS включается polling и наоборот

---

## M3 — Папка «Запросы» + Expo push + блокировки

### 3.1 Логика request_status

В M1 поле `ConversationParticipant.request_status` уже есть. В M3 активируем:

При `post_message` определяется `goes_to_requests`:
```python
recipient_participant = ...
if recipient_participant.request_status == 'accepted':
    pass  # уже принято, ничего не делать
else:
    # Это первое сообщение или ещё не принят запрос
    is_recipient_following_sender = await check_follow(db, recipient.id, sender.id)
    if is_recipient_following_sender:
        recipient_participant.request_status = 'accepted'
    else:
        recipient_participant.request_status = 'pending'  # уйдёт в Запросы
```

Сторона отправителя всегда `request_status='accepted'` — он видит тред в своём primary.

При listing `GET /api/messages/conversations/?folder=primary|requests`:
- primary → `ConversationParticipant.request_status='accepted'`
- requests → `ConversationParticipant.request_status='pending'`

### 3.2 Endpoints M3

```
POST   /api/messages/conversations/{id}/accept/   # request_status: pending → accepted
POST   /api/messages/conversations/{id}/reject/   # удалить тред у получателя (cleared_at = now)
POST   /api/messages/conversations/{id}/mute/     # toggle muted
DELETE /api/messages/conversations/{id}/          # archived_at = now (своё удаление)
POST   /api/messages/conversations/{id}/clear/    # cleared_at = now (очистить историю у себя)
POST   /api/messages/block/{user_id}/             # создать UserBlock
DELETE /api/messages/block/{user_id}/             # снять блок
GET    /api/messages/blocks/                      # список заблокированных
```

### 3.3 Приватные профили

`User.is_private_profile` (поле уже есть, проверить — иначе использовать ProfileShare).
В `can_send_message`:
```python
if recipient.is_private_profile:
    mutual = await is_mutual_follow(db, sender.id, recipient.id)
    if not mutual:
        return False, 'private_profile', False
```

Сообщения отправителю в этом случае возвращают 403 с понятным detail.

### 3.4 Backend: Expo push

#### Расширить `Backend/app/services/notifications.py`
```python
EXPO_PUSH_URL = "https://exp.host/--/api/v2/push/send"

async def send_push(user_id, title: str, body: str, data: dict | None = None):
    """Отправляет Expo push, если у user есть push_token и notify_messages=True."""
    async with async_session_maker() as db:
        user = await db.get(User, user_id)
        if not user or not user.push_token or not user.notify_messages:
            return
        payload = {
            "to": user.push_token,
            "title": title,
            "body": body,
            "data": data or {},
            "sound": "default",
            "priority": "high",
        }
        try:
            async with httpx.AsyncClient(timeout=8.0) as client:
                r = await client.post(EXPO_PUSH_URL, json=payload)
            if r.status_code >= 400:
                logger.error("Expo push failed: %s %s", r.status_code, r.text)
        except Exception as e:
            logger.error("Expo push exception: %s", e)
```

### 3.5 Условие отправки push

В `post_message` после рассылки WS-событий:
```python
recipient_has_active_ws = bool(hub.get(str(recipient_id)))
should_push = (
    not recipient_has_active_ws
    and not goes_to_requests        # запросы — без push, чтобы не спамили
    and not recipient_participant.muted
)
if should_push:
    await send_push(
        recipient_id,
        title=f"@{sender.username}",
        body=message.body[:120],
        data={"type": "message", "conversation_id": str(message.conversation_id)},
    )
```

### 3.6 Mobile: глубокая ссылка из push

При тапе на push → `expo-notifications` listener читает `data.conversation_id` → `router.push('/messages/' + id)`. Реализовать в `Mobile/app/_layout.tsx`.

### 3.7 Mobile: папка «Запросы»

#### Новый файл `Mobile/app/messages/requests.tsx`
Список тредов с `request_status='pending'`. Для каждого:
- Превью первого сообщения, аватар, ник отправителя
- Кнопки: «Принять» / «Удалить» / «Заблокировать»

«Принять» → `POST /accept/` → тред переезжает в primary (локально перенести в `conversationsPrimary`).
«Удалить» → `POST /reject/` → удалить из списка.
«Заблокировать» → `POST /block/{user_id}/` + reject.

В `messages.tsx` (инбокс) — сверху строка-вход «Запросы (N)» если есть pending. Тап → `router.push('/messages/requests')`.

### 3.8 Mobile: настройки уведомлений

В `Mobile/app/settings/` (если экрана нет — создать) — toggle «Уведомления о сообщениях», дёргает `PATCH /api/users/me/` с `notify_messages: bool`.

### 3.9 Mobile: блок-меню в треде

Header диалога — кнопка `ellipsis-horizontal` → ActionSheet/Alert с пунктами:
- «Очистить историю» → confirm → `POST /clear/`
- «Заблокировать @username» → confirm → `POST /block/{user_id}/`
- «Заглушить уведомления» → `POST /mute/`

После блока — баннер в треде «Вы заблокировали этого пользователя. Сообщения недоступны.» и input заблокирован.

### 3.10 Acceptance criteria M3

- [ ] Незнакомый пользователь пишет → попадает в Запросы получателя
- [ ] Push НЕ приходит на запросы
- [ ] «Принять» переносит тред в primary, дальше всё как обычно
- [ ] «Заблокировать» из запросов / из треда — обе стороны не могут писать
- [ ] Push приходит когда получатель offline и тред уже accepted
- [ ] При муте — нет push, но сообщение приходит и инкрементит unread
- [ ] Приватный профиль: незнакомец получает 403, не создаётся даже request
- [ ] Тап на push → открывается нужный тред

---

## M4 — Rich content (идеи, без детализации)

- **Inline-карточка пластинки**: в input есть «📀» — выбор из своей коллекции/вишлиста, посылается специальный message с `payload_type='record'` и `record_id`; в треде рендерится мини-карточка с deep-link на `/record/{id}`
- **Share Profile/Collection**: аналогично, payload карточки профиля или папки
- **Typing indicator**: WS-событие `typing.start` / `typing.stop`, дебаунс на клиенте, отрисовка под header'ом
- **Edit message**: `PATCH /api/messages/messages/{id}/`, в течение 24ч, рисуется «(изменено)»
- **Reactions**: эмодзи-реакции на конкретное сообщение (отдельная таблица `message_reactions`)
- **Поиск по сообщениям**: Postgres FTS по `body` в пределах своих тредов

---

## Тесты (минимальный набор)

### Backend (`Backend/tests/test_messages.py`)
- `test_create_conversation_idempotent` — повтор POST возвращает тот же id
- `test_send_message_to_non_follower_goes_to_requests` — request_status='pending'
- `test_send_to_private_profile_without_mutual_follows_returns_403`
- `test_blocked_user_cannot_send`
- `test_idempotency_via_client_nonce`
- `test_unread_count_correct` — после mark_read обнуляется
- `test_accept_request_moves_to_primary`
- `test_rate_limit_send_message`

### Mobile (smoke-test вручную по acceptance criteria каждой фазы)

---

## Анти-абуз и edge cases

- **Spam-волна**: rate limits 60 msg/min + 10 new conversations/hour. При превышении — 429.
- **Удалённый аккаунт**: при `User.deleted_at` все его треды доступны на чтение в архиве, но новые сообщения от/к нему запрещены 410.
- **Длинные сообщения**: Pydantic min/max 1..4000, на клиенте — TextInput maxLength={4000}.
- **Самосообщения**: `recipient_user_id == sender.id` → 400.
- **Дубликаты WS**: до 5 параллельных соединений на пользователя; шестое — закрыть самое старое.
- **Reordering**: на клиенте сортировка по `created_at`, не по моменту получения.

---

## Чек-лист релиза M1

- [ ] Модели `Conversation`, `ConversationParticipant`, `Message`, `UserBlock`
- [ ] Поле `notify_messages` на `User`
- [ ] Alembic миграция применена локально и на prod
- [ ] Pydantic-схемы
- [ ] Сервис `messaging.py` с pure-функциями + тесты unit
- [ ] Роутер `messages.py` зарегистрирован в `main.py`
- [ ] Rate limits настроены
- [ ] Mobile: types, api-методы, store
- [ ] Mobile: экран инбокса, экран треда, кнопка «Новое сообщение»
- [ ] Mobile: интеграция кнопки «Написать» в профиле
- [ ] Polling unread в _layout
- [ ] Smoke-test всех acceptance M1
- [ ] Commit message: `feat(messages): M1 — base direct messages (REST + polling)`
- [ ] Запись в ROADMAP.md (sync через workflow)

## Чек-лист релиза M2

- [ ] WS endpoint в FastAPI + auth по JWT в query
- [ ] In-memory hub, push_event helper
- [ ] Интеграция push_event в post_message/mark_read/delete_message
- [ ] Mobile: ws.ts с reconnect
- [ ] Mobile: подписка в store, дедупликация по client_nonce
- [ ] Mobile: read receipts UI
- [ ] Mobile: optimistic UI со статусами sending/sent/failed
- [ ] Fallback на polling при отсутствии WS
- [ ] Smoke-test acceptance M2
- [ ] Commit: `feat(messages): M2 — realtime via WebSocket`

## Чек-лист релиза M3

- [ ] Логика request_status в post_message
- [ ] Endpoints accept/reject/mute/archive/clear/block
- [ ] Expo push в notifications.py
- [ ] Условие should_push в post_message
- [ ] Mobile: экран Запросов, секция в инбоксе
- [ ] Mobile: меню действий в треде
- [ ] Mobile: настройка notify_messages
- [ ] Mobile: deep-link из push в тред
- [ ] Smoke-test acceptance M3
- [ ] Commit: `feat(messages): M3 — requests folder + push + blocks`
