"""
OfferClick — лог кликов по кнопке «Купить» в магазин.

Зачем:
- Базовая аналитика CTR (клики ÷ просмотры карточки магазина в /offers)
- Подготовка фундамента под affiliate-конверсии: каждый клик имеет stable
  ID, который мы передаём магазину как `subid` → потом матчим с отчётами
  партнёрской сети (Admitad/EPN) по этому ID.
- Anti-fraud: видим если 1 ip_hash кликает по одному листингу 1000 раз
  → можно банить.

Хранение PII:
- IP не храним в plaintext — только sha256(ip + SECRET_KEY). Этого хватает
  для аналитики «один пользователь vs много», но восстановить IP нельзя.
- user_id опционален: анонимы тоже могут клика́ть (если /offers станет
  публичным).
- user_agent храним как есть (это не PII per se, помогает дебагить
  броузер-специфичные баги).
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, ForeignKey, String, false
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.store_listing import StoreListing
    from app.models.user import User


class OfferClick(Base):
    __tablename__ = "offer_clicks"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    listing_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("store_listings.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    ip_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(500), nullable=True)
    # Источник клика внутри приложения: 'mobile' (тап в OffersBlock), 'web' (когда появится)
    surface: Mapped[str] = mapped_column(String(16), nullable=False, default="mobile")
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False, index=True
    )
    # Когда редиректор `/go/...` реально отдал 302. NULL = переход не состоялся:
    # клик записали, но до браузера дело не дошло. Разница created_at →
    # redirected_at — единственный способ увидеть эти потери; выставляется один
    # раз, повторное открытие ссылки (кнопка «назад») её не двигает.
    redirected_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    # Краулер / превью мессенджера дёрнул /go/l/{listing_id} со публичной
    # страницы. Редирект таким отдаём (ломать превью незачем), но из отчётов и
    # из хитов Метрики исключаем.
    is_bot: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=false()
    )

    listing: Mapped["StoreListing"] = relationship("StoreListing")
    user: Mapped["User | None"] = relationship("User")
