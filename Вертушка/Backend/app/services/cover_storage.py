"""
Сервис для хранения обложек виниловых пластинок локально.

Скачивает обложки из Discogs, хранит на диске (uploads/covers/),
обновляет записи в БД. Redis lock предотвращает параллельное скачивание
одной обложки несколькими воркерами.
"""
import asyncio
import logging
import os
import re
import uuid
from datetime import date, datetime, timedelta
from io import BytesIO
from pathlib import Path
from urllib.parse import urlparse

import httpx
from PIL import Image
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.utils.url_guard import UnsafeUrlError, safe_image_get
from app.services.cache import cache
from app.services.cover_demand import TRIGGER_STORE, TRIGGER_USER
from app.services.cover_quality import (
    MASTER_MIN_SIDE,
    is_thumb_grade,
    min_side_from_url,
)

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

# ── Суточный бюджет скачиваний картинок с хостов Discogs ──────────────────
# У Discogs неофициальный потолок ~1000 изображений/сутки на IP, после — 403
# на всё. Прогрев/апгрейд/зеркалирование без учёта могли выесть его за часы,
# и остаток дня пользователи получали бы битые картинки. Считаем каждое
# скачивание с discogs-хоста, при исчерпании бюджета скачивание скипается.
_DISCOGS_IMG_NS = "discogs_img"
# 48ч: ключ суточный, живёт с запасом — вчерашний счётчик ещё читается
# метриками (/health/covers), позавчерашний уже никому не нужен.
_DISCOGS_IMG_TTL = 48 * 3600


def is_discogs_image_url(url: str | None) -> bool:
    """URL картинки на хосте Discogs (i.discogs.com, st.discogs.com, ...).

    По hostname, а не substring: 'discogs.com' в query-строке чужого CDN не
    должен списывать бюджет.
    """
    if not url:
        return False
    try:
        host = (urlparse(url).hostname or "").lower()
    except ValueError:
        return False
    return host == "discogs.com" or host.endswith(".discogs.com")


async def discogs_img_used_today() -> int | None:
    """Сколько картинок скачано с Discogs за сегодня. None — Redis недоступен."""
    return await cache.get_counter(_DISCOGS_IMG_NS, date.today().isoformat())


async def discogs_img_budget_exhausted() -> bool:
    """Исчерпан ли дневной бюджет. Redis недоступен → False: без учёта душить
    скачивания нечем, а ложный отказ хуже риска перебора (graceful, как везде).
    """
    used = await discogs_img_used_today()
    if used is None:
        return False
    return used >= get_settings().discogs_img_daily_budget


async def _count_discogs_img_download() -> None:
    await cache.incr(
        _DISCOGS_IMG_NS, date.today().isoformat(), ttl=_DISCOGS_IMG_TTL,
    )


def _compute_blurhash(img: "Image.Image") -> str | None:
    """blurhash из даунскейл-копии (~64px) для клиентского плейсхолдера.

    Lazy import + глотание любых ошибок: плейсхолдер необязателен, обложка
    важнее — если пакета нет или что-то падает, вернём None и обложка работает
    как прежде. Никогда не бросает. blurhash.encode ждёт numpy-массив пикселей
    (image[y][x]=[r,g,b]) — проверено на боевой библиотеке (1.1.4), file-like/
    PIL/путь она НЕ принимает.
    """
    try:
        import blurhash
        import numpy as np
        small = img.copy()
        small.thumbnail((64, 64), Image.LANCZOS)
        return blurhash.encode(np.array(small), 4, 3)
    except Exception:
        logger.debug("blurhash encode failed", exc_info=True)
        return None


def _encode_and_place(raw: bytes, tmp_path: Path, dest: Path) -> tuple[str | None, int]:
    """CPU-bound: decode → blurhash → resize (LANCZOS) → JPEG q85 → атомарный
    rename. Возвращает `(blurhash | None, min_side)`, где min_side — меньшая
    сторона УЖЕ УЛОЖЕННОГО файла (после даунскейла, но без апскейла).

    min_side — авторитетная проверка тира: формы URL у источников меняются, а
    пиксели не врут. Пишется в `records.cover_min_side`, по нему потом решается,
    можно ли перезаписать мастер лучшим источником (см. download_and_store).

    Pillow-ресайз 1000px + optimize=True — это 50-150мс чистого CPU на файл.
    В single-worker проде (--workers 1) вызов прямо в корутине морозил event
    loop на всю пачку прогрева (до 10 обложек = ~1.5с без обслуживания никого).
    Вынесено в отдельную sync-функцию: async-пути гоняют через asyncio.to_thread,
    sync-путь (store_user_cover) зовёт напрямую — он и так документирован как
    «вызывать из threadpool». blurhash считаем ДО ресайза дест-файла (из копии),
    качество самого файла не трогаем.
    """
    img = Image.open(BytesIO(raw)).convert("RGB")
    bhash = _compute_blurhash(img)
    if img.width > _MAX_SIDE or img.height > _MAX_SIDE:
        img.thumbnail((_MAX_SIDE, _MAX_SIDE), Image.LANCZOS)
    img.save(tmp_path, format="JPEG", quality=_JPEG_QUALITY, optimize=True)
    os.rename(tmp_path, dest)
    return bhash, min(img.width, img.height)


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
        *,
        trigger: str = "backfill",
    ) -> str | None:
        """
        Скачивает обложку из Discogs и сохраняет на диск.

        Возвращает относительный путь 'covers/{discogs_id}.jpg' или None при ошибке.

        `trigger` — кто инициировал добычу (см. cover_demand). Нужен, чтобы
        отделить рост зеркала от людей от роста от фоновых джоб: без этого
        разделения по одной лишь `cover_cached_at` нагрузку не спрогнозировать.
        Дефолт «backfill» намеренно консервативный — неразмеченный вызов не
        припишется пользователям и не завысит прогноз.
        """
        from app.models.record import Record  # отложенный импорт — нет циклов

        # Гейт «не мастер»: 150px-thumb Discogs увеличить нельзя (размер внутри
        # подписи HMAC), а уложенный на диск он навсегда становится мастером —
        # imgproxy режет из него, деталь-экран получает апскейл ×8. Дешёвый
        # пре-фильтр по URL до сети; неизвестный размер пропускаем.
        if is_thumb_grade(image_url):
            logger.info(
                "cover_storage: skip thumb-grade source for %s (min_side=%s) — %s",
                discogs_id, min_side_from_url(image_url), image_url,
            )
            return None

        rel_path = f"covers/{self._cover_filename(discogs_id)}"

        # Проверяем: возможно уже скачано другим воркером пока мы ждали
        dest = self._cover_path(discogs_id)
        if dest.exists():
            # Апгрейд, а не пропуск: если лежащий мастер заведомо мелкий, а
            # источник крупный — перекачиваем и перезаписываем. Так «плохая»
            # обложка лечится сама, когда бесплатная лестница (CAA-1200 →
            # Deezer xl → iTunes 600) наконец находит нормальную.
            #
            # NULL в cover_min_side = «не мерили» (все файлы до этой правки).
            # Такие НЕ трогаем: иначе первый же прогрев после деплоя устроил бы
            # массовую перекачку всех 13K зеркал. Их размеры проставит
            # heal-скрипт, и апгрейд включится точечно.
            stored_min_side = (
                await db.execute(
                    select(Record.cover_min_side).where(Record.discogs_id == discogs_id)
                )
            ).scalars().first()
            needs_upgrade = (
                stored_min_side is not None and stored_min_side < MASTER_MIN_SIDE
            )
            if not needs_upgrade:
                # Обновить БД-поля если файл уже есть, но cover_local_path не записан.
                # Размер меряем здесь же: иначе запись получала бы cover_local_path
                # без cover_min_side и навсегда выпадала и из метрики тира, и из
                # ночного перегрева (тот берёт только промеренных). Именно так
                # набежало 125 «непромеренных» после heal-скрипта.
                # Чтение заголовка JPEG — единицы миллисекунд, не ресайз.
                if stored_min_side is None:
                    try:
                        with Image.open(dest) as img:
                            measured = min(img.width, img.height)
                    except Exception:
                        measured = None
                else:
                    measured = stored_min_side
                values = {"cover_local_path": rel_path, "cover_cached_at": datetime.utcnow()}
                if measured is not None:
                    values["cover_min_side"] = measured
                await db.execute(
                    update(Record)
                    .where(Record.discogs_id == discogs_id, Record.cover_local_path.is_(None))
                    .values(**values)
                )
                await db.commit()
                return rel_path
            logger.info(
                "cover_storage: upgrading %s from min_side=%s via %s",
                discogs_id, stored_min_side, image_url,
            )

        # Бюджет-гейт для discogs-хостов — до лока и до сети. Скип, не ошибка:
        # обложка приедет завтра или из бесплатного источника, а вот сегодняшние
        # 403 на живых пользователей после перебора лимита — уже не лечатся.
        if is_discogs_image_url(image_url) and await discogs_img_budget_exhausted():
            logger.warning(
                "cover_storage: дневной бюджет Discogs-картинок исчерпан — скип %s (%s)",
                discogs_id, image_url,
            )
            return None

        if not await self._acquire_lock(discogs_id):
            logger.debug("cover_storage: lock busy for %s, skipping", discogs_id)
            return None

        tmp_path: Path | None = None
        try:
            self._ensure_covers_dir()
            tmp_path = self._tmp_path(discogs_id)

            # Считаем ПОПЫТКУ, а не успех: неудачный запрос всё равно ушёл на
            # хост Discogs и потратил их лимит.
            if is_discogs_image_url(image_url):
                await _count_discogs_img_download()
            try:
                resp = await safe_image_get(image_url, timeout=_DOWNLOAD_TIMEOUT)
            except UnsafeUrlError as exc:
                logger.warning(
                    "cover_storage: отказ качать %s для %s — %s", image_url, discogs_id, exc,
                )
                return None
            if resp.status_code in (403, 404, 410):
                logger.info(
                    "cover_storage: discogs returned %d for %s, skipping",
                    resp.status_code,
                    discogs_id,
                )
                return None
            resp.raise_for_status()
            raw = resp.content

            # Конвертация + resize + атомарный rename — CPU-bound, в threadpool,
            # иначе single-worker event loop морозится на всю пачку прогрева.
            bhash, min_side = await asyncio.to_thread(_encode_and_place, raw, tmp_path, dest)
            tmp_path = None  # переименован — не удалять в finally

            # Файл кладём даже если он оказался мелким (демоут, не удаление —
            # база обложек только накапливается). Но помечаем размером: пока он
            # ниже порога, апгрейд-ветка выше будет пускать перекачку с лучшего
            # источника, а мобильный отрисует его в плейсхолдер-тире.
            await db.execute(
                update(Record)
                .where(Record.discogs_id == discogs_id)
                .values(
                    cover_local_path=rel_path,
                    cover_cached_at=datetime.utcnow(),
                    blurhash=bhash,
                    cover_min_side=min_side,
                )
            )
            await db.commit()
            from app.services.cover_demand import record_acquisition
            await record_acquisition(trigger)
            if min_side < MASTER_MIN_SIDE:
                logger.warning(
                    "cover_storage: %s stored below master threshold (min_side=%d) from %s",
                    discogs_id, min_side, image_url,
                )
            else:
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
            # Синхронно: функция сама документирована как «вызывать из threadpool».
            _encode_and_place(raw, tmp_path, dest)
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
        Удаляет самые давние обложки пока кэш не уложится в target_size_mb.

        «Давность» — mtime файла, а не records.cover_cached_at. cover_cached_at —
        дата ДОБЫЧИ, то есть FIFO: файл, апгрейженный вчера лучшим источником,
        считался бы «старым» по дате первого скачивания и вылетал первым. mtime
        же ставится при зеркалировании и обновляется при апгрейде — это честный
        прокси «когда обложкой в последний раз занимались». Сигнала реального
        чтения нет вовсе (статику отдаёт nginx, noatime), так что лучшего
        приближения без учёта доступов в nginx-логах не существует.

        Кандидаты из ДВУХ источников: записи с cover_local_path и файлы-мастера
        m{gid}.jpg (см. _master_orphan_candidates — их records-выборка не видит
        в принципе). Обе группы выселяются одной очередью строго по mtime.

        Синхронизирует PostgreSQL с удалением файлов.
        Возвращает количество удалённых обложек.
        """
        from app.models.record import Record  # отложенный импорт
        from app.models.store_listing import StoreListing
        from app.models.collection import CollectionItem
        from app.models.wishlist import WishlistItem

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

        # В чьей-то коллекции или вишлисте — не трогаем. Это личная библиотека
        # человека и самый посещаемый экран приложения; терять там обложки
        # недопустимо, сколько бы места ни требовалось.
        in_library = (
            select(CollectionItem.id)
            .where(CollectionItem.record_id == Record.id)
            .exists()
        ) | (
            select(WishlistItem.id)
            .where(WishlistItem.record_id == Record.id)
            .exists()
        )

        # Выбираем старейшие записи с локальными обложками.
        #
        # ⚠️ НИКОГДА не эвиктим source='user' — это загруженное юзером фото,
        # НЕВОССТАНОВИМО.
        #
        # ⚠️ И НИКОГДА — записи с подписанной ссылкой Discogs. Здесь была
        # ошибка в допущении: «discogs/store обложки эвиктить можно, само-лечатся
        # из cover_image_url при next view». Для Discogs это неверно — их URL
        # подписаны и протухают, поэтому после эвикции self-heal получает 403,
        # и плитка остаётся пустой НАВСЕГДА.
        #
        # Инцидент 18.08.2026: в коллекции из 172 позиций 63 (37%) имели blurhash
        # при отсутствующем файле — то есть обложка была скачана, посчитана и
        # затем удалена. У всех 63 cover_image_url вёл на discogs.com. Юзер видел
        # размытые плитки и думал, что дело в интернете.
        #
        # Правило теперь простое: выселяем только то, что честно вернётся само.
        result = await db.execute(
            select(Record.id, Record.discogs_id, Record.cover_local_path)
            .where(
                Record.cover_local_path.isnot(None),
                ~active_in_stock,
                ~in_library,
                Record.source.is_distinct_from("user"),
                Record.cover_image_url.isnot(None),
                ~Record.cover_image_url.like("%discogs.com%"),
            )
        )
        candidates = result.all()

        # Единая очередь кандидатов: (mtime, size_mb, path, record_id | None).
        # Сортировка по mtime в Python, а не ORDER BY в SQL: порядок задаёт
        # файловая система, БД про mtime ничего не знает.
        entries: list[tuple[float, float, Path, object | None]] = []
        # Запись ссылается на файл, которого нет, — битый указатель: чистим
        # БД-поля независимо от того, сколько места надо освободить.
        stale_ids: list = []
        for row in candidates:
            if not row.cover_local_path:
                continue
            file_path = Path("uploads") / row.cover_local_path
            try:
                st = file_path.stat()
            except OSError:
                stale_ids.append(row.id)
                continue
            entries.append((st.st_mtime, st.st_size / 1024 / 1024, file_path, row.id))

        entries.extend(await self._master_orphan_candidates(db))
        entries.sort(key=lambda e: e[0])

        deleted = len(stale_ids)
        freed_mb = 0.0
        ids_to_clear: list = list(stale_ids)

        for _mtime, size_mb, file_path, record_id in entries:
            if freed_mb >= to_free_mb:
                break
            try:
                file_path.unlink()
                freed_mb += size_mb
                if record_id is not None:
                    ids_to_clear.append(record_id)
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
            "cover_storage: LRU cleanup deleted %d covers (%d stale DB pointers), freed %.1f MB",
            deleted,
            len(stale_ids),
            freed_mb,
        )
        return deleted

    # Файл мастера сетки артиста: m{gid}.jpg строго в корне covers_dir.
    _MASTER_FILE_RE = re.compile(r"^m(\d+)\.jpg$")

    async def _master_orphan_candidates(
        self, db: AsyncSession,
    ) -> list[tuple[float, float, Path, None]]:
        """Кандидаты на эвикцию среди мастер-зеркал m{gid}.jpg.

        Эти файлы живут ВНЕ таблицы records: их пишет _spawn_mirror из
        GET /covers/m{gid}, а UPDATE records WHERE discogs_id='m123' не матчит
        ни одной строки. records-выборка cleanup_lru их не видит, поэтому до
        этого скана мастер-зеркала не эвиктились никогда и копились до конца
        диска.

        Правило то же, что для записей («выселяем только то, что честно
        вернётся само»), источник — discogs_master_covers.cover_image_url:
          * URL с discogs.com — подписанный и протухает, self-heal после
            эвикции получит 403 → НЕ трогаем (урок инцидента 18.08);
          * строки нет или URL пуст — достоверного пути восстановления нет
            (фолбэк по releases_index может упереться в тот же discogs) →
            НЕ трогаем;
          * бесплатный URL (CAA/Deezer/iTunes/store) — вернётся при следующем
            просмотре через @covers_fallback → эвиктим по mtime.
        """
        from sqlalchemy import text as _text

        if not self.covers_dir.exists():
            return []

        by_mid: dict[int, Path] = {}
        for f in self.covers_dir.iterdir():
            m = self._MASTER_FILE_RE.match(f.name)
            if m and f.is_file():
                by_mid[int(m.group(1))] = f
        if not by_mid:
            return []

        evictable = (await db.execute(
            _text(
                "SELECT master_id FROM discogs_master_covers "
                "WHERE master_id = ANY(:mids) "
                "AND cover_image_url IS NOT NULL "
                "AND cover_image_url NOT LIKE '%discogs.com%'"
            ),
            {"mids": list(by_mid)},
        )).scalars().all()

        out: list[tuple[float, float, Path, None]] = []
        for mid in evictable:
            path = by_mid[mid]
            try:
                st = path.stat()
            except OSError:
                continue  # исчез между сканом и stat — уже не кандидат
            out.append((st.st_mtime, st.st_size / 1024 / 1024, path, None))
        return out

    def _walk_cover_files(self) -> "list[Path]":
        """Все файлы кэша, РЕКУРСИВНО — включая covers/store/ (store-native
        зеркала). Нерекурсивный iterdir() не видел подкаталоги, из-за чего
        лимит COVERS_MAX_CACHE_MB по факту был больше заявленного, а очистка
        стартовала позже, чем должна."""
        if not self.covers_dir.exists():
            return []
        out: list[Path] = []
        for root, _dirs, files in os.walk(self.covers_dir):
            for name in files:
                if name.startswith(".tmp_"):
                    continue
                out.append(Path(root) / name)
        return out

    def _get_cache_size_mb(self) -> float:
        """Суммарный размер всех файлов в covers_dir (с подкаталогами) в МБ."""
        total = 0
        for f in self._walk_cover_files():
            try:
                total += f.stat().st_size
            except OSError:
                continue
        return total / 1024 / 1024

    async def get_cache_stats(self) -> dict:
        """Статистика кэша обложек."""
        files = self._walk_cover_files()
        if not files:
            return {"files": 0, "size_mb": 0.0}
        total_bytes = 0
        for f in files:
            try:
                total_bytes += f.stat().st_size
            except OSError:
                continue
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

        # URL приходит из парсера чужого магазина, то есть по происхождению это
        # содержимое стороннего HTML. Гоняем через url_guard: скомпрометированная
        # или просто вредная витрина иначе направила бы нашу закачку внутрь
        # docker-сети. См. docs/plans/SECURITY_AUDIT_PRERELEASE.md §S2.
        try:
            resp = await safe_image_get(image_url, timeout=_DOWNLOAD_TIMEOUT)
        except UnsafeUrlError as exc:
            logger.warning(
                "cover_storage: отказ качать store-native обложку %s для %s — %s",
                image_url, record_id, exc,
            )
            return
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

        bhash, min_side = await asyncio.to_thread(_encode_and_place, raw, tmp_path, dest)
        tmp_path = None

        rel_path = f"{rel_subdir}/{filename}"
        async with async_session_maker() as db:
            await db.execute(
                update(Record)
                .where(Record.id == record_id)
                .values(
                    cover_local_path=rel_path,
                    cover_cached_at=datetime.utcnow(),
                    blurhash=bhash,
                    cover_min_side=min_side,
                )
            )
            await db.commit()
        from app.services.cover_demand import record_acquisition
        await record_acquisition(TRIGGER_STORE)
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
                # Единственный путь, запускаемый живым действием пользователя
                # (ensure_cover_cached зовётся из добавления в коллекцию/вишлист).
                await service.download_and_store(
                    discogs_id, image_url, db, trigger=TRIGGER_USER,
                )
    except Exception as exc:
        logger.warning("cover_storage: background download failed for %s: %s", discogs_id, exc)


def _looks_like_junk_cover(url: str | None) -> bool:
    """Явные не-обложки: пусто, не http, магазинные плейсхолдеры."""
    if not url or not url.startswith("http"):
        return True
    low = url.lower()
    return any(m in low for m in ("spacer.gif", "no-image", "no_image", "noimage", "placeholder", "default.jp"))


async def _release_cover_is_empty(discogs_id: str) -> bool:
    """True, если у discogs-релиза НЕТ ни своей обложки, ни зеркала на диске.

    Единственный рубеж приоритета источников для магазинного харвеста. Записи
    нет в БД (обложка живёт только в dump-индексе) — тоже True: перетирать
    нечего, а `discogs_releases_index` защищён своим `cover_image_url IS NULL`.
    Ошибку БД трактуем как «занято» — молчаливая порча дороже пропущенной
    бесплатной картинки, добор всё равно вернётся следующим прогоном.
    """
    from app.database import async_session_maker
    from sqlalchemy import text as _text

    try:
        async with async_session_maker() as db:
            row = (await db.execute(
                _text(
                    "SELECT cover_image_url, cover_local_path FROM records "
                    "WHERE discogs_id = :did"
                ),
                {"did": discogs_id},
            )).first()
    except Exception:
        logger.debug("harvest guard: lookup failed for %s", discogs_id, exc_info=True)
        return False

    if row is None:
        return True
    return not row.cover_image_url and not row.cover_local_path


async def _harvest_store_cover(
    discogs_id: str, master_id: str | None, image_url: str,
    *, await_downloads: bool = False,
) -> bool:
    """Осадить обложку из магазинного листинга в наш индекс/master_covers для
    непокрытого discogs-релиза + сразу скачать файл на диск.

    Магазин мы уже загрузили — обложка бесплатна (ноль внешних API). Хотлинк
    магазина протухает, поэтому eager-скачиваем: пишем covers/{id}.jpg (и
    covers/m{mid}.jpg для мастера), дальше nginx отдаёт статику навсегда.
    Заполняем ТОЛЬКО пустые (IS NULL / ON CONFLICT DO NOTHING) — не перетираем
    более каноничные источники.

    Магазин — источник ПОСЛЕДНЕЙ очереди: он закрывает дырку, но никогда не
    ложится поверх Discogs. Раньше это соблюдалось лишь для записей в БД, а
    скачивание файла шло мимо guard'а: `download_and_store` безусловно ставит
    `cover_local_path` + свежий `cover_cached_at` (cache-bust), и запись с
    дискогсовским `cover_image_url`, но ещё не зеркалированная, молча
    перекрашивалась магазинной картинкой. Так 12.08.2026 разовый добор
    `backfill_store_covers` подменил обложку у release 2875867 (Tim Maia 1980,
    master 805853): к нему fuzzy-матчем прилип листинг переиздания 2023 года
    из другого мастера (434521), трек-лист остался прежним — обложка чужая.
    Точечный фильтр в SQL добора этого не ловил: он про строки, а порча шла
    через файл. Guard здесь держится независимо от вызывающего.

    `await_downloads=True` — дождаться скачивания файлов вместо fire-and-forget.
    Нужно разовому добору (`backfill_store_covers`): он запускается через
    `asyncio.run`, и петля закроется раньше, чем отработают фоновые задачи.

    Возвращает True, если обложку взяли в работу (для счётчиков добора).
    """
    if _looks_like_junk_cover(image_url):
        return False
    from app.database import async_session_maker
    from sqlalchemy import text as _text

    if not await _release_cover_is_empty(discogs_id):
        return False

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
    jobs = []
    if discogs_id.isdigit():
        jobs.append(_download_cover_background(discogs_id, image_url))
    if master_id and master_id.isdigit() and master_id != "0":
        jobs.append(_download_cover_background(f"m{master_id}", image_url))

    if await_downloads:
        for job in jobs:
            await job
    else:
        for job in jobs:
            _retain(job)
    return True


def schedule_harvest_store_cover(
    discogs_id: str | None, master_id: str | None, image_url: str | None,
) -> None:
    """fire-and-forget харвест обложки магазина. Вызывается из _apply_match при
    матче листинга на discogs-релиз."""
    if not discogs_id or not image_url:
        return
    _retain(_harvest_store_cover(discogs_id, master_id, image_url))
