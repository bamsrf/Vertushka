"""Очередь дозагрузки цен после импорта коллекции из Discogs.

Импорт кладёт в базу «тонкие» записи: Discogs отдаёт в списке коллекции только
`basic_information`, без цен. Цены есть исключительно в marketplace-API
(`/marketplace/stats/{id}`) — по одному запросу на релиз, то есть для коллекции
в 400 пластинок это ~7 минут. Держать столько открытым HTTP-запрос нельзя,
а общий ночной `update_prices_batch` разгребает всю базу пачками и до конкретного
юзера дойдёт за недели.

Поэтому — задача в БД, а не BackgroundTasks: API-контейнер перезапускается на
каждом деплое, и незавершённая корутина умерла бы молча. Строка в таблице
переживает рестарт, даёт мобилке прогресс для поллинга и гарантирует, что
задача доедет.

Одна строка на юзера (unique): повторный импорт переиспользует её, сбрасывая
счётчики. История прогонов не нужна.
"""
import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base

STATUS_PENDING = "pending"
STATUS_RUNNING = "running"
STATUS_DONE = "done"
STATUS_FAILED = "failed"

# Терминальные — воркер их не подхватывает.
TERMINAL_STATUSES = (STATUS_DONE, STATUS_FAILED)


class DiscogsPriceJob(Base):
    """Состояние дозагрузки цен для коллекции одного пользователя."""

    __tablename__ = "discogs_price_jobs"
    __table_args__ = (
        Index("ix_price_job_status", "status", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default=STATUS_PENDING
    )
    # Сколько записей без цены было на момент постановки задачи.
    total: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # Сколько обработано (включая те, по которым Discogs цену не дал).
    processed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # Сколько реально получили цену — это число и показываем юзеру.
    updated: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    # Сдвигается на каждом батче. Воркер по нему отбирает «зависшие» running-строки
    # (контейнер упал посреди прогона) и возвращает их в работу.
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    def __repr__(self) -> str:
        return (
            f"<DiscogsPriceJob user={self.user_id} status={self.status} "
            f"{self.processed}/{self.total}>"
        )
