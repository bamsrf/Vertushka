"""
Модель in-app уведомлений (лента "Ты")
"""
import uuid
from datetime import datetime
from sqlalchemy import String, DateTime, ForeignKey, Index, Integer, SmallInteger, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID, JSONB

from app.database import Base


# Типы уведомлений (синхронизированы с Mobile/lib/types.ts)
NOTIFICATION_TYPES = {
    "follow_request",       # кто-то запросил подписку на приватный профиль
    "message_request",      # кто-то написал тебе в личку (тред в «Запросах»)
    "new_follower",         # кто-то подписался (или approve запроса)
    "gift_booked",          # кто-то забронировал твой подарок
    "gift_confirmed",       # даритель подтвердил выдачу
    "wishlist_in_stock",    # listing из твоего вишлиста снова в продаже
    "wishlist_in_stock_alt",  # другая версия мастера появилась в продаже
    "wishlist_price_drop",  # цена listing упала
    "achievement_unlocked", # ты получил ачивку
    "milestone_unlocked",   # веха коллекции (100/500/1000)
    "digest_wishlist_in_stock",  # дайджест ≥5 «снова в продаже» за день
}


# Приоритеты (см. docs/plans/PLAN_NOTIFICATIONS_V2.md)
PRIORITY_PUSH = 1     # push + badge + feed (high-signal)
PRIORITY_FEED = 2     # badge + feed, push если не cap (default)
PRIORITY_QUIET = 3    # только feed, без push (повторный bump)


class Notification(Base):
    """In-app уведомление в персональной ленте пользователя."""

    __tablename__ = "notifications"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    actor_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    type: Mapped[str] = mapped_column(String(50), nullable=False)

    entity_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    entity_id: Mapped[str | None] = mapped_column(String(64), nullable=True)

    data: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    # Канонический ключ свёртки (см. PLAN_NOTIFICATIONS_V2). Пример:
    #   "wishlist_in_stock:<record_id>", "new_follower:<actor_id>",
    #   "digest:wl:<YYYY-MM-DD>". Активна в выборках через partial unique index
    #   `ix_notifications_user_dedup_unread` (только WHERE read_at IS NULL).
    dedup_key: Mapped[str] = mapped_column(Text, nullable=False)

    # Когда событие повторилось последний раз. Для сортировки ленты и UI
    # «обновлено N часов назад». На insert == created_at.
    bumped_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )

    # Сколько раз событие было свёрнуто в эту запись. 1 = одиночное.
    occurrences: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")

    # Если юзер прочитал запись — следующая по тому же dedup_key не создаётся
    # до этой даты (snooze ladder в notification_service.apply_snooze_on_read).
    snoozed_until: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    # 1=push (high-signal), 2=feed+push (default), 3=только feed (без push).
    priority: Mapped[int] = mapped_column(
        SmallInteger, nullable=False, default=2, server_default="2"
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )
    read_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    actor = relationship("User", foreign_keys=[actor_id])

    __table_args__ = (
        Index("ix_notifications_user_created", "user_id", "created_at"),
        Index("ix_notifications_user_unread", "user_id", "read_at"),
        Index("ix_notifications_user_bumped", "user_id", "bumped_at"),
        Index(
            "ix_notifications_user_dedup_unread",
            "user_id", "dedup_key",
            unique=True,
            postgresql_where="read_at IS NULL",
        ),
        Index("ix_notifications_snooze", "user_id", "dedup_key", "snoozed_until"),
    )

    def __repr__(self) -> str:
        return f"<Notification {self.type} {self.dedup_key} -> {self.user_id}>"
