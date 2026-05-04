"""
Модель waitlist — сбор email-ов для рассылки ссылки на сторы при запуске мобильного приложения.
"""
import uuid
from datetime import datetime
from sqlalchemy import String, DateTime, Index
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID

from app.database import Base


class WaitlistEntry(Base):
    """Запись в waitlist для рассылки ссылок на стор."""

    __tablename__ = "waitlist_entries"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    email: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        index=True,
    )

    # Откуда пришёл (например, имя профиля + tab)
    source: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    # IP/User-Agent для базовой защиты от спама (не PII, но удобно)
    user_agent: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        nullable=False,
    )

    __table_args__ = (
        Index("ix_waitlist_email_source", "email", "source"),
    )

    def __repr__(self) -> str:
        return f"<WaitlistEntry {self.email} from {self.source}>"
