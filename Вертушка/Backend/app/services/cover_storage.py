"""
Сервис для хранения обложек виниловых пластинок локально.

Скачивает обложки из Discogs, хранит на диске (uploads/covers/),
обновляет записи в БД. Redis lock предотвращает параллельное скачивание
одной обложки несколькими воркерами.
"""
import asyncio
import logging
import os
import uuid
from datetime import datetime, timedelta
from io import BytesIO
from pathlib import Path

import httpx
from PIL import Image
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.services.cache import cache

logger = logging.getLogger(__name__)

_LOCK_PREFIX = "vertushka:cover_dl:"
_LOCK_TTL = 60  # секунд

# Сильные ссылки на fire-and-forget задачи. asyncio держит на задачи только
# weak reference — без удержания GC собирает корутину до завершения скачивания.
_bg_tasks: set[asyncio.Task] = set()


def _retain(coro) -> None:
    """Запустить корутину фоном, удержав ссылку до завершения."""
    task = asyncio.create_task(coro)
    _bg_tasks.add(task)
    task.add_done_callback(_bg_tasks.discard)
# 1000px: detail-экран рендерит обложку почти во всю ширину (~390pt → 1170px
# на 3x-ретине); 500px заметно пикселило. 1000px @ q85 ≈ 80-150KB на файл.
_MAX_SIDE = 1000
_JPEG_QUALITY = 85
_DOWNLOAD_TIMEOUT = 30  # секунд


class CoverStorageService:
    """Сервис хранения обложек на диске."""

    def __init__(self) -> None:
        self._settings = get_settings()

    @property
    def covers_dir(self) -> Path:
        return Path(self._settings.covers_dir)

    def _cover_filename(self, discogs_id: str) -> str:
        return f"{discogs_id}.jpg"

    def _cover_path(self, discogs_id: str) -> Path:
        return self.covers_dir / self._cover_filename(discogs_id)

    def _tmp_path(self, discogs_id: str) -> Path:
        return self.covers_dir / f".tmp_{discogs_id}_{uuid.uuid4().hex}.jpg"

    def _ensure_covers_dir(self) -> None:
        self.covers_dir.mkdir(parents=True, exist_ok=True)

    async def _acquire_lock(self, discogs_id: str) -> bool:
        """SET NX EX — returns True если lock получен."""
        if not cache.available:
            # Без Redis lock не работает корректно при нескольких воркерах,
            # но лучше скачать дважды, чем не скачать совсем.
            return True
        try:
            result = await cache._pool.set(
                f"{_LOCK_PREFIX}{discogs_id}",
                "1",
                nx=True,
                ex=_LOCK_TTL,
            )
            return result is True
        except Exception:
            logger.warning("cover_storage: redis lock error for %s", discogs_id)
            return True  # graceful fallback

    async def _release_lock(self, discogs_id: str) -> None:
        if not cache.available:
            return
        try:
            await cache._pool.delete(f"{_LOCK_PREFIX}{discogs_id}")
        except Exception:
            pass  # lock истечёт сам через TTL

    async def download_and_store(
        self,
        discogs_id: str,
        image_url: str,
        db: AsyncSession,
    ) -> str | None:
        """
        Скачивает обложку из Discogs и сохраняет на диск.

        Возвращает относительный путь 'covers/{discogs_id}.jpg' или None при ошибке.
        """
        from app.models.record import Record  # отложенный импорт — нет циклов

        # Проверяем: возможно уже скачано другим воркером пока мы ждали
        dest = self._cover_path(discogs_id)
        if dest.exists():
            # Обновить БД-поля если файл уже есть, но cover_local_path не записан
            rel_path = f"covers/{self._cover_filename(discogs_id)}"
            await db.execute(
                update(Record)
                .where(Record.discogs_id == discogs_id, Record.cover_local_path.is_(None))
                .values(cover_local_path=rel_path, cover_cached_at=datetime.utcnow())
            )
            await db.commit()
            return rel_path

        if not await self._acquire_lock(discogs_id):
            logger.debug("cover_storage: lock busy for %s, skipping", discogs_id)
            return None

        tmp_path: Path | None = None
        try:
            self._ensure_covers_dir()
            tmp_path = self._tmp_path(discogs_id)

            async with httpx.AsyncClient(timeout=_DOWNLOAD_TIMEOUT, follow_redirects=True) as client:
                resp = await client.get(image_url)
                if resp.status_code in (403, 404, 410):
                    logger.info(
                        "cover_storage: discogs returned %d for %s, skipping",
                        resp.status_code,
                        discogs_id,
                    )
                    return None
                resp.raise_for_status()
                raw = resp.content

            # Конвертация и resize через Pillow
            img = Image.open(BytesIO(raw)).convert("RGB")
            if img.width > _MAX_SIDE or img.height > _MAX_SIDE:
                img.thumbnail((_MAX_SIDE, _MAX_SIDE), Image.LANCZOS)
            img.save(tmp_path, format="JPEG", quality=_JPEG_QUALITY, optimize=True)

            # Атомарная запись: rename на том же volume
            os.rename(tmp_path, dest)
            tmp_path = None  # переименован — не удалять в finally

            rel_path = f"covers/{self._cover_filename(discogs_id)}"
            await db.execute(
                update(Record)
                .where(Record.discogs_id == discogs_id)
                .values(cover_local_path=rel_path, cover_cached_at=datetime.utcnow())
            )
            await db.commit()
            logger.info("cover_storage: saved cover for %s → %s", discogs_id, rel_path)
            return rel_path

        except Exception as exc:
            logger.warning("cover_storage: failed to download cover for %s: %s", discogs_id, exc)
            return None
        finally:
            # Удалить tmp-файл если rename не случился
            if tmp_path and tmp_path.exists():
                try:
                    tmp_path.unlink()
                except OSError:
                    pass
            await self._release_lock(discogs_id)

    def store_user_cover(self, key: str, raw: bytes) -> str | None:
        """
        Сохраняет user-uploaded обложку (raw bytes) на диск с тем же resize/качеством,
        что и discogs-обложки. key — стабильный идентификатор (напр. 'user_{record_id}').

        Возвращает относительный путь 'covers/{key}.jpg' или None при ошибке.
        Синхронный (Pillow CPU-bound) — вызывать из threadpool или быстрого пути.
        """
        tmp_path: Path | None = None
        try:
            self._ensure_covers_dir()
            dest = self._cover_path(key)
            tmp_path = self._tmp_path(key)
            img = Image.open(BytesIO(raw)).convert("RGB")
            if img.width > _MAX_SIDE or img.height > _MAX_SIDE:
                img.thumbnail((_MAX_SIDE, _MAX_SIDE), Image.LANCZOS)
            img.save(tmp_path, format="JPEG", quality=_JPEG_QUALITY, optimize=True)
            os.rename(tmp_path, dest)
            tmp_path = None
            return f"covers/{self._cover_filename(key)}"
        except Exception as exc:
            logger.warning("cover_storage: failed to store user cover %s: %s", key, exc)
            return None
        finally:
            if tmp_path and tmp_path.exists():
                try:
                    tmp_path.unlink()
                except OSError:
                    pass

    def get_cover_path(self, discogs_id: str) -> Path | None:
        """Возвращает Path к локальной обложке или None если не скачана."""
        p = self._cover_path(discogs_id)
        return p if p.exists() else None

    async def cleanup_lru(self, target_size_mb: int, db: AsyncSession) -> int:
        """
        Удаляет самые старые обложки пока кэш не уложится в target_size_mb.

        Синхронизирует PostgreSQL в одной транзакции с удалением файлов.
        Возвращает количество удалённых обложек.
        """
        from app.models.record import Record  # отложенный импорт
        from app.models.store_listing import StoreListing

        current_mb = self._get_cache_size_mb()
        if current_mb <= target_size_mb:
            return 0

        excess_mb = current_mb - target_size_mb
        # Берём с запасом 20% — чтобы не запускать очистку при каждом новом файле
        to_free_mb = excess_mb * 1.2

        # WS1.3: НЕ эвиктим зеркала записей, активно показываемых в Маркете
        # (есть свежий in_stock-листинг). Иначе серый квадрат: эвикция → next
        # view → self-heal бьёт в Discogs → возможный 403 на протухшем URL.
        cutoff = datetime.utcnow() - timedelta(days=7)
        active_in_stock = (
            select(StoreListing.id)
            .where(
                StoreListing.matched_record_id == Record.id,
                StoreListing.status == "in_stock",
                StoreListing.last_seen_at >= cutoff,
            )
            .exists()
        )

        # Выбираем старейшие записи с локальными обложками (кроме активных).
        # ⚠️ НИКОГДА не эвиктим source='user' — это загруженное юзером фото,
        # НЕВОССТАНОВИМО (не тянется из Discogs/Deezer как зеркала). discogs/store
        # обложки эвиктить можно — само-лечатся из cover_image_url при next view.
        result = await db.execute(
            select(Record.id, Record.discogs_id, Record.cover_local_path)
            .where(
                Record.cover_local_path.isnot(None),
                ~active_in_stock,
                Record.source.is_distinct_from("user"),
            )
            .order_by(Record.cover_cached_at.asc())
        )
        candidates = result.all()

        deleted = 0
        freed_mb = 0.0
        ids_to_clear: list = []

        for row in candidates:
            if freed_mb >= to_free_mb:
                break
            if not row.cover_local_path:
                continue
            file_path = Path("uploads") / row.cover_local_path
            # Пробуем удалить файл
            try:
                if file_path.exists():
                    size_mb = file_path.stat().st_size / 1024 / 1024
                    file_path.unlink()
                    freed_mb += size_mb
                # Даже если файла нет — обнуляем БД-поля
                ids_to_clear.append(row.id)
                deleted += 1
            except OSError as e:
                logger.warning("cover_storage: cleanup failed to delete %s: %s", file_path, e)

        if ids_to_clear:
            await db.execute(
                update(Record)
                .where(Record.id.in_(ids_to_clear))
                .values(cover_local_path=None, cover_cached_at=None)
            )
            await db.commit()

        logger.info(
            "cover_storage: LRU cleanup deleted %d covers, freed %.1f MB",
            deleted,
            freed_mb,
        )
        return deleted

    def _get_cache_size_mb(self) -> float:
        """Суммарный размер всех файлов в covers_dir в МБ."""
        if not self.covers_dir.exists():
            return 0.0
        total = sum(
            f.stat().st_size
            for f in self.covers_dir.iterdir()
            if f.is_file() and not f.name.startswith(".tmp_")
        )
        return total / 1024 / 1024

    async def get_cache_stats(self) -> dict:
        """Статистика кэша обложек."""
        if not self.covers_dir.exists():
            return {"files": 0, "size_mb": 0.0}
        files = [
            f for f in self.covers_dir.iterdir()
            if f.is_file() and not f.name.startswith(".tmp_")
        ]
        total_bytes = sum(f.stat().st_size for f in files)
        return {
            "files": len(files),
            "size_mb": round(total_bytes / 1024 / 1024, 1),
        }


def schedule_store_native_cover_cache(record_id: "uuid.UUID", image_url: str) -> None:
    """Фоновое скачивание обложки для store-native Record (нет discogs_id).

    Файл сохраняется как `covers/store/<record_uuid>.jpg`. Используется UUID
    вместо discogs_id, потому что у store-native записей discogs_id всегда NULL.
    Вызывается из listing_matcher.match_listing после создания store-native Record.
    fire-and-forget — ошибки скачивания не блокируют match-flow.
    """
    if not image_url:
        return
    _retain(_download_store_native_cover_background(record_id, image_url))


async def _download_store_native_cover_background(
    record_id: "uuid.UUID", image_url: str,
) -> None:
    """Фоновая задача: скачать обложку store-native записи в отдельной DB-сессии."""
    from app.database import async_session_maker
    from app.models.record import Record

    rel_subdir = "covers/store"
    filename = f"{record_id}.jpg"

    service = CoverStorageService()
    covers_root = service.covers_dir
    store_dir = covers_root / "store"
    dest = store_dir / filename

    if dest.exists():
        return

    tmp_path: Path | None = None
    try:
        store_dir.mkdir(parents=True, exist_ok=True)
        tmp_path = store_dir / f".tmp_{record_id}_{uuid.uuid4().hex}.jpg"

        async with httpx.AsyncClient(timeout=_DOWNLOAD_TIMEOUT, follow_redirects=True) as client:
            resp = await client.get(image_url)
            if resp.status_code in (403, 404, 410):
                # Магазин удалил товар → CDN навсегда возвращает 4xx.
                # Зануляем r.cover_image_url, фильтр /market/* отсеет запись
                # (COALESCE подставит raw_payload.image_url из листинга — он
                # обычно тот же мёртвый URL, но это уже не проблема Маркета,
                # а weekly_cleanup_stale пометит листинг как 'removed').
                logger.info(
                    "cover_storage: store-native cover unavailable (%d) for %s — nulling cover_image_url",
                    resp.status_code, record_id,
                )
                async with async_session_maker() as db:
                    await db.execute(
                        update(Record)
                        .where(Record.id == record_id)
                        .values(cover_image_url=None)
                    )
                    await db.commit()
                return
            resp.raise_for_status()
            raw = resp.content

        img = Image.open(BytesIO(raw)).convert("RGB")
        if img.width > _MAX_SIDE or img.height > _MAX_SIDE:
            img.thumbnail((_MAX_SIDE, _MAX_SIDE), Image.LANCZOS)
        img.save(tmp_path, format="JPEG", quality=_JPEG_QUALITY, optimize=True)

        os.rename(tmp_path, dest)
        tmp_path = None

        rel_path = f"{rel_subdir}/{filename}"
        async with async_session_maker() as db:
            await db.execute(
                update(Record)
                .where(Record.id == record_id)
                .values(cover_local_path=rel_path, cover_cached_at=datetime.utcnow())
            )
            await db.commit()
        logger.info("cover_storage: saved store-native cover for %s", record_id)
    except Exception as exc:
        logger.warning(
            "cover_storage: failed to download store-native cover for %s: %s",
            record_id, exc,
        )
    finally:
        if tmp_path and tmp_path.exists():
            try:
                tmp_path.unlink()
            except OSError:
                pass


async def ensure_cover_cached(discogs_id: str, image_url: str | None, db: AsyncSession) -> None:
    """
    Проверяет наличие локальной обложки. Если нет — запускает скачивание в фоне.

    Вызывать ТОЛЬКО из endpoint'ов добавления в коллекцию/вишлист.
    НЕ вызывается из get_or_create_record_by_discogs_id() — чтобы не
    создавать шквал скачиваний при импорте или обогащении данных.
    """
    if not discogs_id or not image_url:
        return

    service = CoverStorageService()
    if service.get_cover_path(discogs_id):
        return  # уже есть

    _retain(_download_cover_background(discogs_id, image_url))


# Холодная сетка артиста рождает до ~100 фоновых закачек разом (Redis-lock
# дедупит только одинаковые id) — семафор держит параллельность к внешним
# CDN и диску в рамках приличия.
_download_semaphore = asyncio.Semaphore(8)


async def _download_cover_background(discogs_id: str, image_url: str) -> None:
    """Фоновая задача — скачивает обложку с отдельной DB-сессией."""
    from app.database import async_session_maker

    try:
        async with _download_semaphore:
            async with async_session_maker() as db:
                service = CoverStorageService()
                await service.download_and_store(discogs_id, image_url, db)
    except Exception as exc:
        logger.warning("cover_storage: background download failed for %s: %s", discogs_id, exc)


def _looks_like_junk_cover(url: str | None) -> bool:
    """Явные не-обложки: пусто, не http, магазинные плейсхолдеры."""
    if not url or not url.startswith("http"):
        return True
    low = url.lower()
    return any(m in low for m in ("spacer.gif", "no-image", "no_image", "noimage", "placeholder", "default.jp"))


async def _harvest_store_cover(
    discogs_id: str, master_id: str | None, image_url: str,
) -> None:
    """Осадить обложку из магазинного листинга в наш индекс/master_covers для
    непокрытого discogs-релиза + сразу скачать файл на диск.

    Магазин мы уже загрузили — обложка бесплатна (ноль внешних API). Хотлинк
    магазина протухает, поэтому eager-скачиваем: пишем covers/{id}.jpg (и
    covers/m{mid}.jpg для мастера), дальше nginx отдаёт статику навсегда.
    Заполняем ТОЛЬКО пустые (IS NULL / ON CONFLICT DO NOTHING) — не перетираем
    более каноничные источники.
    """
    if _looks_like_junk_cover(image_url):
        return
    from app.database import async_session_maker
    from sqlalchemy import text as _text

    try:
        async with async_session_maker() as db:
            if discogs_id.isdigit():
                await db.execute(
                    _text(
                        "UPDATE discogs_releases_index SET cover_image_url = :url "
                        "WHERE discogs_id = :did AND cover_image_url IS NULL"
                    ),
                    {"url": image_url, "did": int(discogs_id)},
                )
            if master_id and master_id.isdigit() and master_id != "0":
                await db.execute(
                    _text(
                        "INSERT INTO discogs_master_covers (master_id, cover_image_url, source) "
                        "VALUES (:mid, :url, 'store') ON CONFLICT (master_id) DO NOTHING"
                    ),
                    {"mid": int(master_id), "url": image_url},
                )
            await db.commit()
    except Exception:
        logger.debug("harvest store cover failed: %s", discogs_id, exc_info=True)

    # Eager-зеркалирование: файл оседает сразу, до протухания хотлинка.
    if discogs_id.isdigit():
        _retain(_download_cover_background(discogs_id, image_url))
    if master_id and master_id.isdigit() and master_id != "0":
        _retain(_download_cover_background(f"m{master_id}", image_url))


def schedule_harvest_store_cover(
    discogs_id: str | None, master_id: str | None, image_url: str | None,
) -> None:
    """fire-and-forget харвест обложки магазина. Вызывается из _apply_match при
    матче листинга на discogs-релиз."""
    if not discogs_id or not image_url:
        return
    _retain(_harvest_store_cover(discogs_id, master_id, image_url))
