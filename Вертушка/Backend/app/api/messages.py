"""
API личных сообщений (DM).

Privacy-модель: любой авторизованный пользователь может написать кому угодно;
если получатель не подписан на отправителя — тред помечается request_status='pending'
у получателя и попадёт в папку «Запросы» (UX-разделение появляется на M3).
"""
import logging
from datetime import datetime
from uuid import UUID

from fastapi import (
    APIRouter,
    Depends,
    File,
    HTTPException,
    Query,
    Request,
    UploadFile,
    WebSocket,
    WebSocketDisconnect,
    status,
)
from slowapi import Limiter
from app.utils.request_ip import get_client_ip
from sqlalchemy import select, and_, or_, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.models.conversation import (
    Conversation,
    ConversationParticipant,
    Message,
)
from app.models.user import User
from app.models.user_block import UserBlock
from app.api.auth import get_current_user
from app.schemas.message import (
    AttachedRecord,
    ConversationCreate,
    ConversationDetail,
    ConversationPartner,
    ConversationRead,
    MessageCreate,
    MessageEdit,
    MessageFolder,
    MessageRead,
    MuteRequest,
    PinnedMessagePreview,
    PresenceResponse,
    ReactionRead,
    ReactionToggle,
    ReadMarker,
    ReplyPreview,
    UnreadCount,
)
from app.services.messaging import (
    check_can_send,
    compute_total_unread,
    count_unread_in_conversation,
    get_or_create_conversation,
    is_user_blocked,
    mark_read as svc_mark_read,
    partner_id_of,
    post_message,
    require_participant,
)
from app.services import messages_ws_hub
from app.config import get_settings
from app.utils.security import verify_token_type

logger = logging.getLogger(__name__)

router = APIRouter()
limiter = Limiter(key_func=get_client_ip)


PAGE_LIMIT_DEFAULT = 50
PAGE_LIMIT_MAX = 100


async def _hydrate_message_previews(
    db: AsyncSession, messages: list[Message]
) -> list[MessageRead]:
    """Догружает ReplyPreview, AttachedRecord и реакции для batch-отдачи."""
    from app.models.record import Record
    from app.models.message_reaction import MessageReaction
    from app.services.artist_name import clean_artist_name

    reply_ids = {m.reply_to_message_id for m in messages if m.reply_to_message_id}
    targets: dict = {}
    if reply_ids:
        q = await db.execute(select(Message).where(Message.id.in_(reply_ids)))
        targets = {t.id: t for t in q.scalars().all()}

    record_ids = {m.attached_record_id for m in messages if m.attached_record_id}
    records: dict = {}
    if record_ids:
        rq = await db.execute(select(Record).where(Record.id.in_(record_ids)))
        records = {r.id: r for r in rq.scalars().all()}

    msg_ids = [m.id for m in messages]
    reactions_by_msg: dict = {}
    if msg_ids:
        rq = await db.execute(
            select(MessageReaction).where(MessageReaction.message_id.in_(msg_ids))
        )
        for r in rq.scalars().all():
            reactions_by_msg.setdefault(r.message_id, []).append(r)

    result: list[MessageRead] = []
    for m in messages:
        mr = MessageRead.model_validate(m)
        if m.reply_to_message_id and m.reply_to_message_id in targets:
            t = targets[m.reply_to_message_id]
            mr.reply_to = ReplyPreview(
                id=t.id,
                sender_id=t.sender_id,
                body=t.body,
                deleted_at=t.deleted_at,
            )
        if m.attached_record_id and m.attached_record_id in records:
            r = records[m.attached_record_id]
            mr.attached_record = AttachedRecord(
                id=r.id,
                title=r.title,
                artist=clean_artist_name(r.artist) or r.artist,
                year=r.year,
                cover_image_url=r.cover_image_url,
                cover_url=getattr(r, "cover_url", None),
            )
        if m.id in reactions_by_msg:
            mr.reactions = [
                ReactionRead(user_id=r.user_id, emoji=r.emoji)
                for r in reactions_by_msg[m.id]
            ]
        result.append(mr)
    return result


def _effective_muted(me_part: ConversationParticipant) -> tuple[bool, datetime | None]:
    """Возвращает (is_muted_now, muted_until). Учитывает истекший timed mute."""
    from datetime import datetime as _dt

    if not me_part.muted:
        return False, None
    if me_part.muted_until is None:
        return True, None  # forever
    if me_part.muted_until > _dt.utcnow():
        return True, me_part.muted_until
    return False, None  # expired


def _conv_to_read(
    conv: Conversation,
    partner: User,
    me_part: ConversationParticipant,
    partner_part: ConversationParticipant | None,
    unread: int,
    is_blocked: bool,
    pinned_message: Message | None = None,
) -> ConversationRead:
    is_muted, muted_until = _effective_muted(me_part)
    return ConversationRead(
        id=conv.id,
        partner=ConversationPartner(
            id=partner.id,
            username=partner.username,
            display_name=partner.display_name,
            avatar_url=partner.avatar_url,
        ),
        last_message_preview=conv.last_message_preview,
        last_message_at=conv.last_message_at,
        last_message_sender_id=conv.last_message_sender_id,
        unread_count=unread,
        muted=is_muted,
        muted_until=muted_until,
        request_status=me_part.request_status,  # type: ignore[arg-type]
        is_blocked=is_blocked,
        partner_last_read_at=partner_part.last_read_at if partner_part else None,
        pinned=me_part.pinned_at is not None,
        pinned_message=PinnedMessagePreview(
            id=pinned_message.id,
            sender_id=pinned_message.sender_id,
            body=pinned_message.body,
            deleted_at=pinned_message.deleted_at,
        )
        if pinned_message
        else None,
    )


@router.get("/conversations/", response_model=list[ConversationRead])
async def list_conversations(
    folder: MessageFolder = Query("primary"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Список диалогов пользователя.

    folder=primary — request_status='accepted' и не архивированные
    folder=requests — request_status='pending' и не архивированные
    """
    parts_q = await db.execute(
        select(ConversationParticipant)
        .where(
            ConversationParticipant.user_id == current_user.id,
            ConversationParticipant.archived_at.is_(None),
            ConversationParticipant.request_status
            == ("pending" if folder == "requests" else "accepted"),
        )
    )
    parts = parts_q.scalars().all()
    if not parts:
        return []

    conv_ids = [p.conversation_id for p in parts]
    convs_q = await db.execute(
        select(Conversation).where(Conversation.id.in_(conv_ids))
    )
    convs = {c.id: c for c in convs_q.scalars().all()}

    partner_ids = [partner_id_of(convs[p.conversation_id], current_user.id) for p in parts]
    partners_q = await db.execute(select(User).where(User.id.in_(partner_ids)))
    partners = {u.id: u for u in partners_q.scalars().all()}

    # Batch-загрузка participant-строк собеседников для read-receipts
    partner_parts_q = await db.execute(
        select(ConversationParticipant).where(
            ConversationParticipant.conversation_id.in_(conv_ids),
            ConversationParticipant.user_id != current_user.id,
        )
    )
    partner_parts_by_conv = {pp.conversation_id: pp for pp in partner_parts_q.scalars().all()}

    items: list[ConversationRead] = []
    for p in parts:
        conv = convs.get(p.conversation_id)
        if not conv:
            continue
        partner = partners.get(partner_id_of(conv, current_user.id))
        if not partner:
            continue
        unread = await count_unread_in_conversation(
            db, conv.id, current_user.id, p.last_read_at
        )
        blocked = await is_user_blocked(db, current_user.id, partner.id)
        items.append(
            _conv_to_read(conv, partner, p, partner_parts_by_conv.get(conv.id), unread, blocked)
        )

    # Сначала закреплённые (Telegram-style), внутри секции — по last_message_at desc
    from datetime import datetime as _dt
    fallback = _dt.min

    def sort_key(r: ConversationRead) -> tuple:
        return (
            0 if r.pinned else 1,
            -(r.last_message_at.timestamp() if r.last_message_at else fallback.timestamp()),
        )

    items.sort(key=sort_key)
    return items


@router.post("/conversations/", response_model=ConversationRead, status_code=status.HTTP_200_OK)
async def create_or_get_conversation(
    data: ConversationCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Получить или создать диалог с пользователем (idempotent на паре)."""
    recipient, goes_to_requests = await check_can_send(db, current_user, data.recipient_user_id)
    conv = await get_or_create_conversation(
        db, current_user.id, recipient.id, goes_to_requests
    )
    me_part = await require_participant(db, conv.id, current_user.id)
    await db.commit()
    await db.refresh(conv)
    await db.refresh(me_part)

    unread = await count_unread_in_conversation(
        db, conv.id, current_user.id, me_part.last_read_at
    )
    blocked = await is_user_blocked(db, current_user.id, recipient.id)
    partner_part_q = await db.execute(
        select(ConversationParticipant).where(
            ConversationParticipant.conversation_id == conv.id,
            ConversationParticipant.user_id == recipient.id,
        )
    )
    partner_part = partner_part_q.scalar_one_or_none()
    return _conv_to_read(conv, recipient, me_part, partner_part, unread, blocked)


@router.get("/conversations/{conversation_id}/", response_model=ConversationDetail)
async def get_conversation_detail(
    conversation_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Диалог + первая страница сообщений (PAGE_LIMIT_DEFAULT штук, новые в конце)."""
    me_part = await require_participant(db, conversation_id, current_user.id)
    conv = await db.get(Conversation, conversation_id)
    if not conv:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Диалог не найден")

    partner_id = partner_id_of(conv, current_user.id)
    partner = await db.get(User, partner_id)
    if not partner:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Собеседник не найден")

    from app.models.message_hidden import MessageHiddenFor

    hidden_sub = select(MessageHiddenFor.message_id).where(
        MessageHiddenFor.user_id == current_user.id
    )
    msgs_stmt = (
        select(Message)
        .where(
            Message.conversation_id == conv.id,
            ~Message.id.in_(hidden_sub),
        )
        .order_by(Message.created_at.desc())
        .limit(PAGE_LIMIT_DEFAULT)
    )
    if me_part.cleared_at is not None:
        msgs_stmt = msgs_stmt.where(Message.created_at > me_part.cleared_at)
    msgs_q = await db.execute(msgs_stmt)
    messages = list(reversed(msgs_q.scalars().all()))

    unread = await count_unread_in_conversation(
        db, conv.id, current_user.id, me_part.last_read_at
    )
    blocked = await is_user_blocked(db, current_user.id, partner.id)
    partner_part_q = await db.execute(
        select(ConversationParticipant).where(
            ConversationParticipant.conversation_id == conv.id,
            ConversationParticipant.user_id == partner.id,
        )
    )
    partner_part = partner_part_q.scalar_one_or_none()

    pinned_message: Message | None = None
    if conv.pinned_message_id:
        pinned_message = await db.get(Message, conv.pinned_message_id)
        if pinned_message and pinned_message.deleted_at:
            pinned_message = None
    return ConversationDetail(
        conversation=_conv_to_read(
            conv, partner, me_part, partner_part, unread, blocked, pinned_message,
        ),
        messages=await _hydrate_message_previews(db, messages),
    )


@router.get(
    "/conversations/{conversation_id}/messages/",
    response_model=list[MessageRead],
)
async def list_messages(
    conversation_id: UUID,
    before: UUID | None = Query(None),
    limit: int = Query(PAGE_LIMIT_DEFAULT, ge=1, le=PAGE_LIMIT_MAX),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Пагинация сообщений: страницами по `limit`, до сообщения с id=before."""
    from app.models.message_hidden import MessageHiddenFor

    me_part = await require_participant(db, conversation_id, current_user.id)

    stmt = select(Message).where(Message.conversation_id == conversation_id)
    if me_part.cleared_at is not None:
        stmt = stmt.where(Message.created_at > me_part.cleared_at)
    # Скрытые «для себя» сообщения
    hidden_sub = select(MessageHiddenFor.message_id).where(
        MessageHiddenFor.user_id == current_user.id
    )
    stmt = stmt.where(~Message.id.in_(hidden_sub))
    if before is not None:
        before_msg = await db.get(Message, before)
        if not before_msg or before_msg.conversation_id != conversation_id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Опорное сообщение не найдено"
            )
        stmt = stmt.where(Message.created_at < before_msg.created_at)

    stmt = stmt.order_by(Message.created_at.desc()).limit(limit)
    rows = await db.execute(stmt)
    messages = list(reversed(rows.scalars().all()))
    return await _hydrate_message_previews(db, messages)


@router.post("/upload-media/")
@limiter.limit("30/minute")
async def upload_media(
    request: Request,
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
):
    """Загрузка фото-вложения для DM. Возвращает {media_url, media_type}.

    Контент-тайпы: image/jpeg | image/png | image/webp. Размер: ≤8 МБ.
    Файл сжимается через Pillow (long-edge 1600px, JPEG q=85). Хранится в
    `uploads/messages/<user_id>/<uuid>.jpg` и отдаётся через статик-mount
    `/uploads/...` (см. `app/main.py`).
    """
    import io
    import uuid as _uuid
    from pathlib import Path
    from PIL import Image as PILImage

    allowed = {"image/jpeg", "image/png", "image/webp"}
    if file.content_type not in allowed:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Только JPEG/PNG/WebP",
        )

    contents = await file.read()
    if len(contents) > 8 * 1024 * 1024:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Максимальный размер — 8 МБ",
        )

    MAGIC = {
        "image/jpeg": (b"\xff\xd8\xff",),
        "image/png":  (b"\x89PNG",),
        "image/webp": (b"RIFF",),
    }
    if not any(contents[: len(m)] == m for m in MAGIC[file.content_type]):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Файл не является допустимым изображением",
        )

    try:
        img = PILImage.open(io.BytesIO(contents))
        img = img.convert("RGB")
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Не удалось прочитать изображение",
        )

    max_edge = 1600
    w, h = img.size
    if max(w, h) > max_edge:
        ratio = max_edge / max(w, h)
        img = img.resize((int(w * ratio), int(h * ratio)), PILImage.LANCZOS)

    user_dir = Path("uploads/messages") / str(current_user.id)
    user_dir.mkdir(parents=True, exist_ok=True)

    filename = f"{_uuid.uuid4().hex}.jpg"
    filepath = user_dir / filename
    img.save(filepath, "JPEG", quality=85, optimize=True)

    media_url = f"/uploads/messages/{current_user.id}/{filename}"
    return {"media_url": media_url, "media_type": "image"}


@router.post(
    "/conversations/{conversation_id}/messages/",
    response_model=MessageRead,
    status_code=status.HTTP_201_CREATED,
)
@limiter.limit("60/minute")
async def send_message(
    request: Request,
    conversation_id: UUID,
    data: MessageCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Отправить сообщение в существующий диалог."""
    me_part = await require_participant(db, conversation_id, current_user.id)
    conv = await db.get(Conversation, conversation_id)
    if not conv:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Диалог не найден")

    partner_id = partner_id_of(conv, current_user.id)
    # Проверяем права (блок / приватный профиль) на каждом сообщении — состояние мог измениться
    await check_can_send(db, current_user, partner_id)

    message = await post_message(
        db,
        conversation=conv,
        sender_id=current_user.id,
        body=data.body,
        client_nonce=data.client_nonce,
        reply_to_message_id=data.reply_to_message_id,
        attached_record_id=data.attached_record_id,
        media_url=data.media_url,
        media_type=data.media_type,
    )

    # Если у меня тред был в pending (необычно — я инициатор), сбросить на accepted
    if me_part.request_status == "pending":
        me_part.request_status = "accepted"

    await db.commit()
    await db.refresh(message)
    hydrated = await _hydrate_message_previews(db, [message])
    payload = hydrated[0].model_dump(mode="json")

    # WS-эхо обоим участникам (один из которых может быть текущим — отправитель)
    partner_id_str = str(partner_id)
    event = {"type": "message.new", "conversation_id": str(conv.id), "message": payload}
    await messages_ws_hub.push_event(current_user.id, event)
    await messages_ws_hub.push_event(partner_id, event)

    # Эмиссия события ачивок (K11–K13). Счётчик берётся из БД, событие — триггер.
    from app.services.achievements import emit_event
    from app.services.achievements.events import MESSAGE_SENT
    await emit_event(db, current_user.id, MESSAGE_SENT, {"message_id": message.id})

    return hydrated[0]


@router.post(
    "/conversations/{conversation_id}/read/",
    status_code=status.HTTP_200_OK,
)
async def mark_conversation_read(
    conversation_id: UUID,
    data: ReadMarker,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Пометить диалог прочитанным до указанного сообщения включительно."""
    me_part = await require_participant(db, conversation_id, current_user.id)
    await svc_mark_read(db, me_part, data.up_to_message_id)
    await db.commit()

    # Уведомляем собеседника об обновлении read receipts
    conv = await db.get(Conversation, conversation_id)
    if conv:
        partner_id = partner_id_of(conv, current_user.id)
        await messages_ws_hub.push_event(
            partner_id,
            {
                "type": "message.read",
                "conversation_id": str(conversation_id),
                "reader_id": str(current_user.id),
                "up_to_message_id": str(data.up_to_message_id),
                "last_read_at": me_part.last_read_at.isoformat() if me_part.last_read_at else None,
            },
        )
    return {"status": "ok"}


EDIT_WINDOW_SECONDS = 15 * 60


@router.patch(
    "/messages/{message_id}/",
    response_model=MessageRead,
)
async def edit_message(
    message_id: UUID,
    payload: MessageEdit,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Редактировать текст своего сообщения в 15-минутном окне."""
    from datetime import datetime as _dt, timedelta as _td

    message = await db.get(Message, message_id)
    if not message:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Сообщение не найдено")
    if message.sender_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Можно редактировать только свои сообщения"
        )
    if message.deleted_at is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Сообщение удалено"
        )
    if message.created_at < _dt.utcnow() - _td(seconds=EDIT_WINDOW_SECONDS):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Окно редактирования (15 минут) истекло",
        )

    message.body = payload.body
    message.edited_at = _dt.utcnow()
    await db.commit()
    await db.refresh(message)

    # Обновим last_message_preview если это последнее сообщение треда
    conv = await db.get(Conversation, message.conversation_id)
    if conv and conv.last_message_at and message.created_at >= conv.last_message_at - _td(seconds=1):
        conv.last_message_preview = (payload.body or "")[:160]
        await db.commit()

    hydrated = await _hydrate_message_previews(db, [message])
    result = hydrated[0]

    if conv:
        partner_id = partner_id_of(conv, current_user.id)
        event = {
            "type": "message.edited",
            "conversation_id": str(message.conversation_id),
            "message_id": str(message_id),
            "body": payload.body,
            "edited_at": message.edited_at.isoformat() if message.edited_at else None,
        }
        await messages_ws_hub.push_event(current_user.id, event)
        await messages_ws_hub.push_event(partner_id, event)

    return result


@router.delete(
    "/messages/{message_id}/",
    status_code=status.HTTP_200_OK,
)
async def delete_message(
    message_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Удалить своё сообщение «у всех» (tombstone: body=NULL, deleted_at=now)."""
    from datetime import datetime as _dt

    message = await db.get(Message, message_id)
    if not message:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Сообщение не найдено")
    if message.sender_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Нельзя удалить чужое сообщение"
        )

    message.body = None
    message.deleted_at = _dt.utcnow()
    conv_id = message.conversation_id
    await db.commit()

    conv = await db.get(Conversation, conv_id)
    if conv:
        partner_id = partner_id_of(conv, current_user.id)
        event = {
            "type": "message.deleted",
            "conversation_id": str(conv_id),
            "message_id": str(message_id),
        }
        await messages_ws_hub.push_event(current_user.id, event)
        await messages_ws_hub.push_event(partner_id, event)
    return {"status": "ok"}


@router.get("/unread-count/", response_model=UnreadCount)
async def unread_count(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Счётчики непрочитанного для бейджа в табе сообщений."""
    primary, requests_n = await compute_total_unread(db, current_user.id)
    return UnreadCount(primary=primary, requests=requests_n)


# ==================== Реакции ====================


@router.post(
    "/messages/{message_id}/reactions/",
    status_code=status.HTTP_200_OK,
)
async def toggle_reaction(
    message_id: UUID,
    payload: ReactionToggle,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Поставить/снять реакцию на сообщение. Идемпотентно — если такая
    эмоджи-реакция уже стоит от этого юзера, она снимается; иначе ставится.

    Возвращает финальный список реакций сообщения + флаг added.
    Шлёт WS-событие `message.reaction` обоим участникам.
    """
    from app.models.message_reaction import MessageReaction

    message = await db.get(Message, message_id)
    if not message:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Сообщение не найдено")

    # Проверим, что юзер — участник этого диалога (нельзя реагировать на чужой чат)
    await require_participant(db, message.conversation_id, current_user.id)

    existing_q = await db.execute(
        select(MessageReaction).where(
            MessageReaction.message_id == message_id,
            MessageReaction.user_id == current_user.id,
            MessageReaction.emoji == payload.emoji,
        )
    )
    existing = existing_q.scalar_one_or_none()
    added = False
    if existing:
        await db.delete(existing)
    else:
        db.add(
            MessageReaction(
                message_id=message_id,
                user_id=current_user.id,
                emoji=payload.emoji,
            )
        )
        added = True
    await db.commit()

    # Перечитываем все реакции сообщения для ответа
    all_q = await db.execute(
        select(MessageReaction).where(MessageReaction.message_id == message_id)
    )
    reactions = [
        ReactionRead(user_id=r.user_id, emoji=r.emoji) for r in all_q.scalars().all()
    ]

    conv = await db.get(Conversation, message.conversation_id)
    if conv:
        partner_id = partner_id_of(conv, current_user.id)
        event = {
            "type": "message.reaction",
            "conversation_id": str(message.conversation_id),
            "message_id": str(message_id),
            "user_id": str(current_user.id),
            "emoji": payload.emoji,
            "added": added,
            "reactions": [
                {"user_id": str(r.user_id), "emoji": r.emoji} for r in reactions
            ],
        }
        await messages_ws_hub.push_event(current_user.id, event)
        await messages_ws_hub.push_event(partner_id, event)

    return {"added": added, "reactions": [r.model_dump(mode="json") for r in reactions]}


# ==================== Действия над диалогом ====================


@router.post(
    "/conversations/{conversation_id}/accept/",
    status_code=status.HTTP_200_OK,
)
async def accept_conversation(
    conversation_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Принять request — переносит тред из «Запросов» в «Личные» у получателя."""
    me_part = await require_participant(db, conversation_id, current_user.id)
    if me_part.request_status != "pending":
        return {"status": "already_accepted"}
    me_part.request_status = "accepted"
    await db.commit()
    return {"status": "ok"}


@router.post(
    "/conversations/{conversation_id}/reject/",
    status_code=status.HTTP_200_OK,
)
async def reject_conversation(
    conversation_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Отклонить request — у получателя ставим cleared_at + archived_at.

    Тред больше не показывается у текущего пользователя.
    Отправитель продолжает видеть диалог в своём primary, но новые сообщения
    инициируются через check_can_send и проверяются на блок (если был).
    """
    from datetime import datetime as _dt

    me_part = await require_participant(db, conversation_id, current_user.id)
    now = _dt.utcnow()
    me_part.cleared_at = now
    me_part.archived_at = now
    await db.commit()
    return {"status": "ok"}


@router.post(
    "/conversations/{conversation_id}/mute/",
    status_code=status.HTTP_200_OK,
)
async def toggle_mute(
    conversation_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Переключить mute диалога у текущего пользователя (legacy on/off).
    Для длительности используется /mute-duration/."""
    me_part = await require_participant(db, conversation_id, current_user.id)
    me_part.muted = not me_part.muted
    me_part.muted_until = None
    await db.commit()
    return {"status": "ok", "muted": me_part.muted, "muted_until": None}


@router.post(
    "/conversations/{conversation_id}/mute-duration/",
    status_code=status.HTTP_200_OK,
)
async def set_mute_duration(
    conversation_id: UUID,
    payload: MuteRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Включить mute на заданный промежуток или снять. duration:
    off | hour | 8hours | day | forever."""
    from datetime import datetime as _dt, timedelta as _td

    me_part = await require_participant(db, conversation_id, current_user.id)
    if payload.duration == "off":
        me_part.muted = False
        me_part.muted_until = None
    elif payload.duration == "forever":
        me_part.muted = True
        me_part.muted_until = None
    else:
        seconds = {"hour": 3600, "8hours": 28_800, "day": 86_400}[payload.duration]
        me_part.muted = True
        me_part.muted_until = _dt.utcnow() + _td(seconds=seconds)

    await db.commit()
    return {
        "status": "ok",
        "muted": me_part.muted,
        "muted_until": me_part.muted_until.isoformat() if me_part.muted_until else None,
    }


@router.post(
    "/messages/{message_id}/hide/",
    status_code=status.HTTP_200_OK,
)
async def hide_message_for_me(
    message_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Скрыть сообщение только у себя (delete-for-me). Собеседник видит."""
    from app.models.message_hidden import MessageHiddenFor

    message = await db.get(Message, message_id)
    if not message:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Сообщение не найдено")
    await require_participant(db, message.conversation_id, current_user.id)

    existing_q = await db.execute(
        select(MessageHiddenFor).where(
            MessageHiddenFor.message_id == message_id,
            MessageHiddenFor.user_id == current_user.id,
        )
    )
    if existing_q.scalar_one_or_none() is None:
        db.add(MessageHiddenFor(message_id=message_id, user_id=current_user.id))
        await db.commit()
    return {"status": "ok"}


@router.post(
    "/conversations/{conversation_id}/clear/",
    status_code=status.HTTP_200_OK,
)
async def clear_history(
    conversation_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Очистить историю у себя — старые сообщения скрываются из выдачи."""
    from datetime import datetime as _dt

    me_part = await require_participant(db, conversation_id, current_user.id)
    me_part.cleared_at = _dt.utcnow()
    await db.commit()
    return {"status": "ok"}


@router.delete(
    "/conversations/{conversation_id}/",
    status_code=status.HTTP_200_OK,
)
async def archive_conversation(
    conversation_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Удалить диалог у себя (архив). У собеседника тред остаётся."""
    from datetime import datetime as _dt

    me_part = await require_participant(db, conversation_id, current_user.id)
    me_part.archived_at = _dt.utcnow()
    await db.commit()
    return {"status": "ok"}


# Лимит закреплённых диалогов на пользователя (Telegram: 5)
PINNED_LIMIT = 5


@router.post(
    "/conversations/{conversation_id}/pin/",
    status_code=status.HTTP_200_OK,
)
async def toggle_pin(
    conversation_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Закрепить или открепить диалог. Лимит 5 закреплённых на пользователя."""
    from datetime import datetime as _dt

    me_part = await require_participant(db, conversation_id, current_user.id)

    if me_part.pinned_at is None:
        # пытаемся закрепить — проверяем лимит
        count_q = await db.execute(
            select(func.count(ConversationParticipant.id)).where(
                ConversationParticipant.user_id == current_user.id,
                ConversationParticipant.pinned_at.is_not(None),
            )
        )
        count = int(count_q.scalar() or 0)
        if count >= PINNED_LIMIT:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Можно закрепить максимум {PINNED_LIMIT} диалогов",
            )
        me_part.pinned_at = _dt.utcnow()
        pinned = True
    else:
        me_part.pinned_at = None
        pinned = False

    await db.commit()
    return {"status": "ok", "pinned": pinned}


@router.post(
    "/conversations/{conversation_id}/pin-message/{message_id}/",
    status_code=status.HTTP_200_OK,
)
async def pin_message(
    conversation_id: UUID,
    message_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Закрепить сообщение в треде (TG-style). Видно обоим участникам."""
    await require_participant(db, conversation_id, current_user.id)
    conv = await db.get(Conversation, conversation_id)
    if not conv:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Диалог не найден")

    message = await db.get(Message, message_id)
    if not message or message.conversation_id != conversation_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Сообщение не найдено в этом диалоге",
        )
    if message.deleted_at:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Сообщение удалено"
        )

    conv.pinned_message_id = message_id
    await db.commit()

    pinned_preview = PinnedMessagePreview(
        id=message.id,
        sender_id=message.sender_id,
        body=message.body,
        deleted_at=message.deleted_at,
    )
    partner_id = partner_id_of(conv, current_user.id)
    event = {
        "type": "conversation.pinned",
        "conversation_id": str(conversation_id),
        "pinned_message": pinned_preview.model_dump(mode="json"),
    }
    await messages_ws_hub.push_event(current_user.id, event)
    await messages_ws_hub.push_event(partner_id, event)

    return {"status": "ok", "pinned_message": pinned_preview.model_dump(mode="json")}


@router.delete(
    "/conversations/{conversation_id}/pin-message/",
    status_code=status.HTTP_200_OK,
)
async def unpin_message(
    conversation_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Открепить сообщение треда. Идемпотентно."""
    await require_participant(db, conversation_id, current_user.id)
    conv = await db.get(Conversation, conversation_id)
    if not conv:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Диалог не найден")

    conv.pinned_message_id = None
    await db.commit()

    partner_id = partner_id_of(conv, current_user.id)
    event = {
        "type": "conversation.pinned",
        "conversation_id": str(conversation_id),
        "pinned_message": None,
    }
    await messages_ws_hub.push_event(current_user.id, event)
    await messages_ws_hub.push_event(partner_id, event)
    return {"status": "ok"}


# ==================== Блокировки ====================


@router.post("/block/{user_id}/", status_code=status.HTTP_200_OK)
async def block_user(
    user_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Заблокировать пользователя в DM. Идемпотентно.

    Если есть совместный тред — у текущего пользователя он архивируется и
    история очищается, чтобы UI скрыл его сразу после блока.
    """
    from datetime import datetime as _dt

    if user_id == current_user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Нельзя заблокировать самого себя",
        )

    target = await db.get(User, user_id)
    if not target:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Пользователь не найден"
        )

    existing = await db.execute(
        select(UserBlock).where(
            UserBlock.blocker_id == current_user.id,
            UserBlock.blocked_id == user_id,
        )
    )
    if existing.scalar_one_or_none() is None:
        db.add(UserBlock(blocker_id=current_user.id, blocked_id=user_id))

    # Архивируем существующий тред у блокирующего
    a, b = (
        (current_user.id, user_id) if str(current_user.id) < str(user_id) else (user_id, current_user.id)
    )
    conv_q = await db.execute(
        select(Conversation).where(
            Conversation.user_a_id == a,
            Conversation.user_b_id == b,
        )
    )
    conv = conv_q.scalar_one_or_none()
    if conv:
        my_part_q = await db.execute(
            select(ConversationParticipant).where(
                ConversationParticipant.conversation_id == conv.id,
                ConversationParticipant.user_id == current_user.id,
            )
        )
        my_part = my_part_q.scalar_one_or_none()
        if my_part:
            now = _dt.utcnow()
            my_part.archived_at = now
            my_part.cleared_at = now

    await db.commit()
    return {"status": "ok"}


@router.delete("/block/{user_id}/", status_code=status.HTTP_200_OK)
async def unblock_user(
    user_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Снять блокировку. Идемпотентно."""
    result = await db.execute(
        select(UserBlock).where(
            UserBlock.blocker_id == current_user.id,
            UserBlock.blocked_id == user_id,
        )
    )
    block = result.scalar_one_or_none()
    if block:
        await db.delete(block)
        await db.commit()
    return {"status": "ok"}


@router.get("/blocks/", response_model=list[UUID])
async def list_blocks(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Список UUID заблокированных пользователей."""
    result = await db.execute(
        select(UserBlock.blocked_id).where(UserBlock.blocker_id == current_user.id)
    )
    return list(result.scalars().all())


# ==================== Presence ====================

ONLINE_THRESHOLD_SECONDS = 60


# ==================== WebSocket realtime ====================


@router.websocket("/ws")
async def messages_ws(websocket: WebSocket, token: str = Query(...)):
    """Realtime канал. Авторизация по JWT в query-параметре (RN-клиенты не
    могут передавать заголовки в WS-handshake удобно).

    Серверные события: message.new / message.read / message.deleted.
    Клиентские команды: {"type": "typing", "conversation_id": ...}

    На connect/disconnect обновляем last_seen_at — это даёт честный
    «онлайн»-индикатор без необходимости REST-полла.
    """
    import asyncio as _asyncio
    from app.api.auth import _touch_last_seen
    from app.database import async_session_maker
    from uuid import UUID as _UUID

    payload = verify_token_type(token, "access")
    if not payload:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    user_id = payload["sub"]

    # Ревокация: токен с устаревшим tv (после смены пароля) или неактивный аккаунт
    # не должны открывать realtime-канал.
    async with async_session_maker() as _db:
        _user = await _db.get(User, _UUID(user_id))
    if not _user or not _user.is_active or payload.get("tv", 0) != _user.token_version:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    await websocket.accept()
    await messages_ws_hub.register(user_id, websocket)
    try:
        _asyncio.create_task(_touch_last_seen(_UUID(user_id)))
    except Exception:
        pass
    try:
        while True:
            data = await websocket.receive_json()
            t = data.get("type")
            if t == "typing":
                conv_id = data.get("conversation_id")
                if not conv_id:
                    continue
                # Ретранслируем собеседнику (вычислим его id через БД)
                async with async_session_maker() as db:
                    conv = await db.get(Conversation, _UUID(conv_id))
                    if not conv:
                        continue
                    partner_id = partner_id_of(conv, _UUID(user_id))
                    await messages_ws_hub.push_event(
                        partner_id,
                        {
                            "type": "typing",
                            "conversation_id": conv_id,
                            "user_id": user_id,
                        },
                    )
            # ignore unknown types
    except WebSocketDisconnect:
        pass
    finally:
        await messages_ws_hub.unregister(user_id, websocket)
        try:
            _asyncio.create_task(_touch_last_seen(_UUID(user_id)))
        except Exception:
            pass


@router.get("/presence/{user_id}/", response_model=PresenceResponse)
async def get_presence(
    user_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Статус пользователя: онлайн (WS активен или last_seen_at < 60с) +
    последний визит. WS-флаг — авторитетный источник истины: реальный
    «он-лайн» индикатор не зависит от REST-троттлинга last_seen_at."""
    from datetime import datetime as _dt, timedelta as _td

    target = await db.get(User, user_id)
    if not target:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Пользователь не найден")

    last_seen = target.last_seen_at
    ws_active = messages_ws_hub.has_active(str(user_id))
    online = ws_active or bool(
        last_seen and last_seen >= _dt.utcnow() - _td(seconds=ONLINE_THRESHOLD_SECONDS)
    )
    if ws_active:
        last_seen = _dt.utcnow()
    return PresenceResponse(online=online, last_seen_at=last_seen)
