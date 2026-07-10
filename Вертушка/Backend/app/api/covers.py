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

# Сильные ссылки на фоновые задачи зеркалирования. asyncio держит на задачи
# только weak reference — bare create_task в обработчике, который сразу
# возвращает 302, GC-шится ДО запуска скачивания → файл m{gid}.jpg не пишется,
# и каждый заход снова падает в 302 на Discogs (баг «обложки грузятся заново»).
_mirror_tasks: set[asyncio.Task] = set()


def _spawn_mirror(discogs_id: str, url: str) -> None:
    """Fire-and-forget зеркалирование с удержанием ссылки до завершения."""
    task = asyncio.create_task(_download_cover_background(discogs_id, url))
    _mirror_tasks.add(task)
    task.add_done_callback(_mirror_tasks.discard)


async def _resolve_cover_live(
    db, discogs_id: str, artist: str | None, title: str | None,
    year: int | None, barcode: str | None,
) -> str | None:
    """Синхронный резолв обложки для release без URL в индексе — показать
    реальную обложку вместо заглушки (первый заход). Порядок по цене:
    CAA-оффлайн (бесплатно, mb_discogs_map) → Deezer (бесплатно) → Discogs
    (последним, под лимитером 60/мин + interactive-reserve). Найденное пишем в
    индекс → следующий заход отдаёт 302 из БД без повторного резолва.
    """
    url = None
    try:
        from app.services.cover_fallback import cover_url_by_discogs_id
        url = await cover_url_by_discogs_id(db, discogs_id)
    except Exception:
        pass
    if not url and artist and title:
        try:
            from app.services.deezer import cover_by_meta
            dz = await cover_by_meta(artist, title, year=year)
            if dz:
                url = dz.url
        except Exception:
            pass
    if not url:
        try:
            from app.services.discogs import DiscogsService
            url = await DiscogsService().get_release_cover(discogs_id)
        except Exception:
            pass

    if url and str(discogs_id).isdigit():
        from sqlalchemy import text as _t
        try:
            await db.execute(
                _t("UPDATE discogs_releases_index SET cover_image_url = :u, "
                   "cover_checked_at = now() WHERE discogs_id = :d "
                   "AND cover_image_url IS NULL"),
                {"u": url, "d": int(discogs_id)},
            )
            await db.commit()
        except Exception:
            await db.rollback()
    return url


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
        """Guard: не редиректим на собственное зеркало (петля) и на no-image
        заглушку Discogs (st.discogs.com/.../spacer.gif)."""
        if not url:
            return None
        if url.startswith(get_settings().public_covers_base):
            return None
        if "spacer.gif" in url or "st.discogs.com" in url:
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
        _spawn_mirror(discogs_id, url)
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
            _spawn_mirror(discogs_id, record_url)
        # 302 redirect — клиент получит обложку немедленно через внешний URL
        return RedirectResponse(url=record_url, status_code=302)

    # Записи нет (или без обложки) — dump-индекс: сетка артиста, поиск,
    # версии отдают /covers/{discogs_id}.jpg для любых строк индекса.
    if discogs_id.isdigit():
        from sqlalchemy import text as _text

        row = (await db.execute(
            _text(
                "SELECT cover_image_url, artist, title, year, barcode_norm "
                "FROM discogs_releases_index WHERE discogs_id = :did"
            ),
            {"did": int(discogs_id)},
        )).mappings().first()
        if row:
            url = _safe(row["cover_image_url"])
            if url:
                _spawn_mirror(discogs_id, url)
                return RedirectResponse(url=url, status_code=302)

            # Нет URL в индексе → живой резолв (мин заглушек). Bounded таймаутом,
            # чтобы /covers не висел; на промах/таймаут — 404 (клиент заглушку).
            resolved = None
            try:
                resolved = _safe(await asyncio.wait_for(
                    _resolve_cover_live(
                        db, discogs_id, row["artist"], row["title"],
                        row["year"], row["barcode_norm"],
                    ),
                    timeout=6,
                ))
            except Exception:
                resolved = None
            if resolved:
                _spawn_mirror(discogs_id, resolved)
                return RedirectResponse(url=resolved, status_code=302)

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
