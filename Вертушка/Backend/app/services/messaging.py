"""
Бизнес-логика личных сообщений: создание диалога, отправка, чтение, права.
Сюда вынесены pure-функции, чтобы роутер оставался тонким.
"""
import logging
from datetime import datetime
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import select, and_, or_, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.conversation import (
    Conversation,
    ConversationParticipant,
    Message,
)
from app.models.follow import Follow
from app.models.user import User
from app.services.blocking import is_user_blocked as _is_user_blocked

logger = logging.getLogger(__name__)


def _pair(u1: UUID, u2: UUID) -> tuple[UUID, UUID]:
    """Каноничный порядок пары — гарантия одного диалога на двоих."""
    return (u1, u2) if str(u1) < str(u2) else (u2, u1)


# Переехала в services/blocking.py: блокировку проверяют не только личные
# сообщения, но и подписки с уведомлениями. Реэкспорт — чтобы не трогать
# существующие импорты из api/messages.py.
is_user_blocked = _is_user_blocked


async def is_following(db: AsyncSession, follower_id: UUID, following_id: UUID) -> bool:
    """True если follower_id подписан на following_id."""
    row = await db.execute(
        select(Follow.id).where(
            Follow.follower_id == follower_id,
            Follow.following_id == following_id,
        ).limit(1)
    )
    return row.scalar_one_or_none() is not None


async def check_can_send(
    db: AsyncSession,
    sender: User,
    recipient_id: UUID,
) -> tuple[User, bool]:
    """Проверка прав отправки. Возвращает (recipient, goes_to_requests).

    Бросает HTTPException при недопустимых случаях.
    goes_to_requests=True означает, что у получателя тред окажется в папке «Запросы»
    (актуально на M3; в M1 значение вычисляется, но не влияет на UX).
    """
    if recipient_id == sender.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Нельзя написать самому себе",
        )

    recipient = await db.get(User, recipient_id)
    if not recipient or not recipient.is_active or recipient.deleted_at is not None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Пользователь не найден",
        )

    if await is_user_blocked(db, sender.id, recipient.id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Сообщения недоступны",
        )

    recipient_follows_sender = await is_following(db, recipient.id, sender.id)

    # Приватность профиля больше НЕ блокирует личку. Раньше входящие тонули:
    # отправитель получал 403, а получатель не видел ни сообщения, ни запроса,
    # пока сам не подпишется на отправителя. Теперь написать можно кому угодно;
    # если получатель не подписан на отправителя — тред падает в «Запросы».
    goes_to_requests = not recipient_follows_sender
    return recipient, goes_to_requests


async def get_or_create_conversation(
    db: AsyncSession,
    sender_id: UUID,
    recipient_id: UUID,
    goes_to_requests: bool,
) -> Conversation:
    """Возвращает существующий диалог пары или создаёт новый с participants.

    request_status получателя:
    - 'accepted' если получатель подписан на отправителя ИЛИ диалог уже существует
    - 'pending' иначе (попадёт в папку «Запросы» — учитывается на M3)
    """
    user_a_id, user_b_id = _pair(sender_id, recipient_id)

    existing = await db.execute(
        select(Conversation)
        .where(
            Conversation.user_a_id == user_a_id,
            Conversation.user_b_id == user_b_id,
        )
        .options(selectinload(Conversation.participants))
    )
    conv = existing.scalar_one_or_none()
    if conv:
        return conv

    conv = Conversation(user_a_id=user_a_id, user_b_id=user_b_id)
    db.add(conv)
    await db.flush()

    sender_part = ConversationParticipant(
        conversation_id=conv.id,
        user_id=sender_id,
        request_status="accepted",
    )
    recipient_part = ConversationParticipant(
        conversation_id=conv.id,
        user_id=recipient_id,
        request_status="pending" if goes_to_requests else "accepted",
    )
    db.add_all([sender_part, recipient_part])
    await db.flush()
    return conv


async def get_participant(
    db: AsyncSession, conversation_id: UUID, user_id: UUID
) -> ConversationParticipant | None:
    row = await db.execute(
        select(ConversationParticipant).where(
            ConversationParticipant.conversation_id == conversation_id,
            ConversationParticipant.user_id == user_id,
        )
    )
    return row.scalar_one_or_none()


async def require_participant(
    db: AsyncSession, conversation_id: UUID, user_id: UUID
) -> ConversationParticipant:
    part = await get_participant(db, conversation_id, user_id)
    if not part:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Диалог не найден"
        )
    return part


async def find_existing_message_by_nonce(
    db: AsyncSession, sender_id: UUID, client_nonce: str
) -> Message | None:
    row = await db.execute(
        select(Message).where(
            Message.sender_id == sender_id,
            Message.client_nonce == client_nonce,
        )
    )
    return row.scalar_one_or_none()


async def post_message(
    db: AsyncSession,
    conversation: Conversation,
    sender_id: UUID,
    body: str,
    client_nonce: str | None,
    reply_to_message_id: UUID | None = None,
    attached_record_id: UUID | None = None,
    media_url: str | None = None,
    media_type: str | None = None,
) -> Message:
    """Сохраняет сообщение и обновляет агрегаты на conversation."""
    if client_nonce:
        existing = await find_existing_message_by_nonce(db, sender_id, client_nonce)
        if existing and existing.conversation_id == conversation.id:
            return existing

    # Тело может быть пустым, если есть вложение (пластинка или медиа).
    body = (body or "").strip()
    if not body and not attached_record_id and not media_url:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Пустое сообщение",
        )

    # Валидация reply: цель должна быть в этом же диалоге, иначе ignore (None)
    valid_reply: UUID | None = None
    if reply_to_message_id is not None:
        target = await db.get(Message, reply_to_message_id)
        if target and target.conversation_id == conversation.id:
            valid_reply = reply_to_message_id

    # Валидация прикреплённой пластинки — должна существовать
    valid_record: UUID | None = None
    if attached_record_id is not None:
        from app.models.record import Record
        rec = await db.get(Record, attached_record_id)
        if rec is not None:
            valid_record = attached_record_id

    # Валидация media_url — только наш /uploads/messages/ префикс, ничего стороннего.
    valid_media_url: str | None = None
    valid_media_type: str | None = None
    if media_url:
        if media_url.startswith("/uploads/messages/"):
            valid_media_url = media_url
            valid_media_type = (media_type or "image").lower()

    now = datetime.utcnow()
    message = Message(
        conversation_id=conversation.id,
        sender_id=sender_id,
        body=body or None,
        client_nonce=client_nonce,
        created_at=now,
        reply_to_message_id=valid_reply,
        attached_record_id=valid_record,
        media_url=valid_media_url,
        media_type=valid_media_type,
    )
    db.add(message)

    if valid_media_url and not body:
        preview = "🖼 фото"
    elif valid_record and not body:
        preview = "📀 пластинка"
    elif valid_record:
        preview = f"📀 {body}"
    elif valid_media_url:
        preview = f"🖼 {body}"
    else:
        preview = body
    conversation.last_message_at = now
    conversation.last_message_preview = preview[:160]
    conversation.last_message_sender_id = sender_id
    await db.flush()
    return message


async def mark_read(
    db: AsyncSession,
    participant: ConversationParticipant,
    up_to_message_id: UUID,
) -> None:
    """Обновляет last_read_at участника по created_at указанного сообщения."""
    message = await db.get(Message, up_to_message_id)
    if not message or message.conversation_id != participant.conversation_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Сообщение не найдено"
        )

    if participant.last_read_at is None or message.created_at > participant.last_read_at:
        participant.last_read_at = message.created_at
        await db.flush()


async def count_unread_in_conversation(
    db: AsyncSession,
    conversation_id: UUID,
    user_id: UUID,
    last_read_at: datetime | None,
) -> int:
    """Сколько непрочитанных входящих сообщений в диалоге."""
    stmt = select(func.count(Message.id)).where(
        Message.conversation_id == conversation_id,
        Message.sender_id != user_id,
        Message.deleted_at.is_(None),
    )
    if last_read_at is not None:
        stmt = stmt.where(Message.created_at > last_read_at)
    return int(await db.scalar(stmt) or 0)


async def compute_total_unread(
    db: AsyncSession, user_id: UUID
) -> tuple[int, int]:
    """Возвращает (primary_unread, requests_unread) — для бейджа в табе."""
    parts_q = await db.execute(
        select(ConversationParticipant).where(
            ConversationParticipant.user_id == user_id,
            ConversationParticipant.archived_at.is_(None),
        )
    )
    parts = parts_q.scalars().all()

    primary = 0
    requests = 0
    for p in parts:
        n = await count_unread_in_conversation(
            db, p.conversation_id, user_id, p.last_read_at
        )
        if n <= 0:
            continue
        if p.request_status == "pending":
            requests += n
        else:
            primary += n
    return primary, requests


def partner_id_of(conv: Conversation, my_user_id: UUID) -> UUID:
    return conv.user_b_id if conv.user_a_id == my_user_id else conv.user_a_id
