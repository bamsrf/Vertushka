"""
API endpoints для обложек виниловых пластинок.

GET /covers/{discogs_id}  — вызывается ТОЛЬКО через nginx @covers_fallback
                            когда файл на диске не найден.
POST /covers/{discogs_id}/refresh — принудительное обновление обложки.
                                    Требует X-Internal-Token.
"""
import asyncio
import logging
from pathlib import Path

from fastapi import APIRouter, Depends, Header, HTTPException
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database import get_db
from app.models.record import Record
from app.services.cover_storage import (
    CoverStorageService,
    _download_cover_background,
    schedule_store_native_cover_cache,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Обложки"])


@router.get("/store/{record_id}")
async def get_store_cover(
    record_id: str,
    db: AsyncSession = Depends(get_db),
) -> RedirectResponse:
    """
    nginx @covers_fallback для store-native обложек (covers/store/{uuid}.jpg).

    Файл зеркала отсутствует на диске (эвикция / ещё не скачан) — пускаем
    фоновое скачивание из cover_image_url и 302-редиректим на store CDN.
    """
    rid = record_id.removesuffix(".jpg")
    result = await db.execute(
        select(Record.id, Record.cover_image_url, Record.cover_local_path)
        .where(Record.id == rid)
    )
    record = result.first()

    if record is None:
        raise HTTPException(status_code=404, detail="Record not found")

    if not record.cover_local_path and record.cover_image_url:
        schedule_store_native_cover_cache(record.id, record.cover_image_url)

    if not record.cover_image_url:
        raise HTTPException(status_code=404, detail="Cover image not available")

    return RedirectResponse(url=record.cover_image_url, status_code=302)


@router.get("/{discogs_id}")
async def get_cover(
    discogs_id: str,
    db: AsyncSession = Depends(get_db),
) -> RedirectResponse:
    """
    Вызывается nginx @covers_fallback когда файл не найден на диске.

    Если запись есть в БД — запускаем фоновое скачивание и возвращаем
    302 redirect на оригинальный Discogs URL (signed URL из БД).
    """
    # nginx проксирует полный путь `/covers/{discogs_id}.jpg` — снимаем суффикс.
    discogs_id = discogs_id.removesuffix(".jpg")

    def _safe(url: str | None) -> str | None:
        """Guard от редирект-петли: если в БД каким-то путём оказался URL
        нашего же зеркала — не редиректим сами на себя."""
        if url and url.startswith(get_settings().public_covers_base):
            return None
        return url

    # m{master_id} — обложка МАСТЕРА (сетка артиста): discogs_master_covers,
    # иначе лучшая обложка любой версии группы из dump-индекса.
    if discogs_id.startswith("m") and discogs_id[1:].isdigit():
        from sqlalchemy import text as _text

        mid = int(discogs_id[1:])
        url = _safe((await db.execute(
            _text("SELECT cover_image_url FROM discogs_master_covers WHERE master_id = :mid"),
            {"mid": mid},
        )).scalar())
        if not url:
            url = _safe((await db.execute(
                _text(
                    "SELECT cover_image_url FROM discogs_releases_index "
                    "WHERE master_id = :mid AND cover_image_url IS NOT NULL "
                    "ORDER BY year ASC NULLS LAST, discogs_id LIMIT 1"
                ),
                {"mid": mid},
            )).scalar())
        if not url:
            raise HTTPException(status_code=404, detail="Cover image not available")
        asyncio.create_task(_download_cover_background(discogs_id, url))
        return RedirectResponse(url=url, status_code=302)

    result = await db.execute(
        select(Record.discogs_id, Record.cover_image_url, Record.cover_local_path)
        .where(Record.discogs_id == discogs_id)
    )
    record = result.first()

    record_url = _safe(record.cover_image_url) if record is not None else None
    if record_url:
        # Запускаем фоновое скачивание если обложки нет локально
        if not record.cover_local_path:
            asyncio.create_task(_download_cover_background(discogs_id, record_url))
        # 302 redirect — клиент получит обложку немедленно через внешний URL
        return RedirectResponse(url=record_url, status_code=302)

    # Записи нет (или без обложки) — dump-индекс: сетка артиста, поиск,
    # версии отдают /covers/{discogs_id}.jpg для любых строк индекса.
    if discogs_id.isdigit():
        from sqlalchemy import text as _text

        url = _safe((await db.execute(
            _text(
                "SELECT cover_image_url FROM discogs_releases_index "
                "WHERE discogs_id = :did"
            ),
            {"did": int(discogs_id)},
        )).scalar())
        if url:
            asyncio.create_task(_download_cover_background(discogs_id, url))
            return RedirectResponse(url=url, status_code=302)

    raise HTTPException(status_code=404, detail="Cover image not available")


@router.post("/{discogs_id}/refresh", status_code=200)
async def refresh_cover(
    discogs_id: str,
    x_internal_token: str = Header(alias="X-Internal-Token"),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    Принудительно перекачивает обложку из Discogs.
    Требует заголовок X-Internal-Token.
    """
    settings = get_settings()
    if not settings.internal_api_token or x_internal_token != settings.internal_api_token:
        raise HTTPException(status_code=403, detail="Invalid token")

    result = await db.execute(
        select(Record).where(Record.discogs_id == discogs_id)
    )
    record = result.scalar_one_or_none()

    if record is None:
        raise HTTPException(status_code=404, detail="Record not found")

    if not record.cover_image_url:
        raise HTTPException(status_code=422, detail="No source cover URL in DB")

    service = CoverStorageService()

    # Удалить старый файл если есть
    if record.cover_local_path:
        old_path = Path("uploads") / record.cover_local_path
        if old_path.exists():
            old_path.unlink(missing_ok=True)

    # Скачать заново (cover_cached_at обновится внутри)
    rel_path = await service.download_and_store(discogs_id, record.cover_image_url, db)

    return {
        "discogs_id": discogs_id,
        "cover_local_path": rel_path,
        "refreshed": rel_path is not None,
    }
