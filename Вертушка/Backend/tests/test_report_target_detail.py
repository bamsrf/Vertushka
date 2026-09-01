"""Карточка объекта жалобы: обложка, автор, метаданные.

Раньше staff видел одну строку «артист — тайтл» и решал вслепую, хотя
жалуются обычно на саму картинку. Тесты держат сборку URL обложки и
устойчивость к уже удалённому объекту.
"""
import asyncio
import uuid
from datetime import datetime

from app.api.reports import _build_target_detail
from app.models.record import Record
from app.models.report import Report
from app.models.user import User


class FakeDB:
    """db.get(Model, id) → заранее подложенный объект. Живой БД тут не нужно:
    вся логика — чтение полей и сборка URL."""

    def __init__(self, objects):
        self._objects = objects

    async def get(self, model, obj_id):
        return self._objects.get(obj_id)


def _record(**over):
    fields = dict(
        id=uuid.uuid4(),
        source="user",
        artist="ruslan4ik",
        title="pizza grooves",
        year=2026,
        format_type="LP",
        moderation_status="approved",
        cover_local_path="covers/user_abc.jpg",
        cover_cached_at=datetime(2026, 8, 23, 12, 0, 0),
        created_at=datetime(2026, 8, 23),
        updated_at=datetime(2026, 8, 23),
    )
    fields.update(over)
    return Record(**fields)


def test_cover_url_points_at_uploads_with_cache_bust():
    """Тот же URL, что уходит в мобилку: /uploads/-путь плюс метка перезалива,
    иначе staff смотрел бы на старую закэшированную картинку."""
    rec = _record()
    report = Report(target_type="record", target_id=rec.id)

    detail = asyncio.run(_build_target_detail(FakeDB({rec.id: rec}), report))

    assert detail.cover_url.startswith("/uploads/covers/user_abc.jpg?v=")
    assert detail.moderation_status == "approved"
    assert ("Год", "2026") in detail.fields
    assert ("Источник", "user") in detail.fields


def test_author_is_resolved_for_user_submitted_record():
    """Бан автора — соседняя кнопка; staff должен видеть, кого банит."""
    author = User(id=uuid.uuid4(), username="ruslan4ik", email="r@example.com")
    rec = _record(created_by_user_id=author.id)
    report = Report(target_type="record", target_id=rec.id)

    detail = asyncio.run(
        _build_target_detail(FakeDB({rec.id: rec, author.id: author}), report)
    )

    assert detail.author_username == "ruslan4ik"


def test_missing_record_yields_no_card():
    """Запись удалили, жалоба осталась — карточка не должна падать."""
    report = Report(target_type="record", target_id=uuid.uuid4())

    assert asyncio.run(_build_target_detail(FakeDB({}), report)) is None


def test_record_without_cover_reports_none():
    """Шаблон рисует заглушку «без обложки», а не битую картинку."""
    rec = _record(cover_local_path=None)
    report = Report(target_type="record", target_id=rec.id)

    detail = asyncio.run(_build_target_detail(FakeDB({rec.id: rec}), report))

    assert detail.cover_url is None


def test_banned_user_is_visible_on_user_report():
    """Чтобы не банить дважды и не гадать, сработала ли прошлая кнопка."""
    user = User(id=uuid.uuid4(), username="spammer", email="s@example.com", is_active=False)
    report = Report(target_type="user", target_id=user.id)

    detail = asyncio.run(_build_target_detail(FakeDB({user.id: user}), report))

    assert ("Статус", "забанен") in detail.fields
