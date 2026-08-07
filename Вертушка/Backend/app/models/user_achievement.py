"""
Модель ачивок пользователя
"""
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import String, DateTime, ForeignKey, Integer, Boolean, UniqueConstraint, Index
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class UserAchievement(Base):
    """Прогресс и анлок ачивок пользователя.

    Одна строка = одна (user, code) пара. Для динамических ачивок (например,
    H2_artist_studio_full с разным артистом) код включает slug:
    'H2:king-crimson'.
    """

    __tablename__ = "user_achievements"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    code: Mapped[str] = mapped_column(String(64), nullable=False)
    is_unlocked: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    unlocked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    progress: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    progress_target: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    # Опыт, начисленный В МОМЕНТ анлока. Заморожен намеренно: вес тира со
    # временем меняется, но прошлое начисление переписывать нельзя — иначе
    # суммарный XP юзера может уменьшиться и уровень «отберётся».
    # NULL = ачивка ещё не открыта.
    xp_awarded: Mapped[int | None] = mapped_column(Integer, nullable=True)
    ach_metadata: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )

    __table_args__ = (
        UniqueConstraint("user_id", "code", name="uq_user_achievement"),
        Index("ix_user_achievements_user_unlocked", "user_id", "is_unlocked"),
        Index("ix_user_achievements_code", "code"),
    )

    user = relationship("User", back_populates="achievements")

    def __repr__(self) -> str:
        state = "unlocked" if self.is_unlocked else f"{self.progress}/{self.progress_target}"
        return f"<UserAchievement user={self.user_id} code={self.code} {state}>"
