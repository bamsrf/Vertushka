"""Dual-write зеркала обложек в S3-совместимое хранилище (подготовка трека A,
см. docs/plans/COVERS_S3_IMGPROXY_MILESTONE.md и COVERS_STRATEGY.md).

Файловый слой обложек становится двухэтажным:
- локальный диск `uploads/covers/` — горячий кэш раздачи (nginx-статика);
- S3 — вечный слой: файл попадает сюда один раз и не удаляется никогда,
  LRU-эвикция локального кэша перестаёт быть потерей данных.

Пока `COVERS_S3_ENABLED=false` (дефолт) модуль — полный no-op: ни импорта
boto3, ни тредов, ни очередей. Включение = пять S3_-переменных в .env.prod +
флаг + рестарт контейнеров; деплой кода не нужен.

Точка записи всех зеркал — `_encode_and_place` (cover_storage). Она
вызывается из worker-тредов (`asyncio.to_thread`) и sync-путей, поэтому здесь
НЕ asyncio, а фоновый uploader-тред с bounded-очередью: горячий путь только
кладёт Path в очередь. Потерянное (переполнение, падение сети, рестарт до
разгрузки очереди) догоняет реконсилер `app/scripts/sync_covers_to_s3.py` —
идемпотентен, гонять можно когда угодно.
"""
import logging
import os
import queue
import re
import threading
import uuid
from pathlib import Path

from app.config import get_settings

logger = logging.getLogger(__name__)

# Очередь bounded: при S3-аварии бесконечная очередь копила бы Path'ы до OOM.
# Переполнение — не потеря (реконсилер), поэтому put_nowait + warning.
_QUEUE_MAX = 2000
_queue: "queue.Queue[Path]" = queue.Queue(maxsize=_QUEUE_MAX)
_worker_started = False
_worker_lock = threading.Lock()
_misconfig_logged = False


def _config_problems(settings) -> list[str]:
    """Имена незаполненных S3_-переменных. Пусто — конфиг полон."""
    problems: list[str] = []
    if not settings.s3_endpoint_url:
        problems.append("S3_ENDPOINT_URL")
    if not settings.s3_bucket_covers:
        problems.append("S3_BUCKET_COVERS")
    if not settings.s3_access_key_id:
        problems.append("S3_ACCESS_KEY_ID")
    if not settings.s3_secret_access_key:
        problems.append("S3_SECRET_ACCESS_KEY")
    return problems


def enabled() -> bool:
    """Флаг включён И конфиг полон.

    Неполный конфиг при включённом флаге НЕ роняет приложение (обложка на
    диске важнее дубля в S3): один error-лог и поведение «выключено» —
    graceful, как и остальные слои обложек.
    """
    global _misconfig_logged
    settings = get_settings()
    if not settings.covers_s3_enabled:
        return False
    problems = _config_problems(settings)
    if problems:
        if not _misconfig_logged:
            logger.error(
                "COVERS_S3_ENABLED=true, но не заданы: %s — dual-write выключен",
                ", ".join(problems),
            )
            _misconfig_logged = True
        return False
    return True


def s3_key_for(path: Path) -> str:
    """Ключ в бакете = путь относительно uploads/: «covers/123.jpg»,
    «covers/m456.jpg». Совпадает с rel_path в records.cover_local_path —
    будущий read-путь (imgproxy из S3, nginx-fallback) резолвится без
    таблицы соответствий. ValueError, если файл вне covers_dir — такое
    зеркалить нельзя, зовущий ошибся.
    """
    covers_dir = Path(get_settings().covers_dir).resolve()
    rel = Path(path).resolve().relative_to(covers_dir)
    return f"{covers_dir.name}/{rel.as_posix()}"


def make_client():
    """boto3-клиент по настройкам. Lazy import: пока S3 выключен, boto3 не
    импортируется вовсе. Клиент боты потокобезопасен — один на тред-воркер
    и один на весь реконсилер.
    """
    import boto3
    from botocore.config import Config as BotoConfig

    settings = get_settings()
    return boto3.client(
        "s3",
        endpoint_url=settings.s3_endpoint_url,
        region_name=settings.s3_region,
        aws_access_key_id=settings.s3_access_key_id,
        aws_secret_access_key=settings.s3_secret_access_key,
        config=BotoConfig(
            connect_timeout=10,
            read_timeout=30,
            retries={"max_attempts": 2, "mode": "standard"},
            # boto3 >= 1.36 по умолчанию шлёт streaming-чексуммы (aws-chunked
            # + x-amz-content-sha256=STREAMING-*), которые S3-совместимые
            # хранилища (Beget: XAmzContentSHA256Mismatch, 28.08.2026) не
            # понимают. when_required = как вели себя старые boto3.
            request_checksum_calculation="when_required",
            response_checksum_validation="when_required",
            # path-style — самый совместимый режим адресации у S3-клонов.
            s3={"addressing_style": "path"},
        ),
    )


# Раздача рано или поздно пойдёт прямо из бакета (imgproxy/CDN) — метаданные
# иммутабельности зашиваем при заливке. Апгрейд качества перезаписывает тот же
# ключ новой версией, клиентские кэши инвалидируются версией ?v= в URL.
_EXTRA_ARGS = {
    "ContentType": "image/jpeg",
    "CacheControl": "public, max-age=31536000",
}


def upload_file_sync(path: Path, key: str, client=None) -> None:
    """Синхронная заливка одного файла. Общая для uploader-треда и
    реконсилера."""
    if client is None:
        client = make_client()
    client.upload_file(
        str(path), get_settings().s3_bucket_covers, key, ExtraArgs=dict(_EXTRA_ARGS)
    )


def _worker_loop() -> None:
    client = None
    while True:
        path = _queue.get()
        try:
            # LRU или демоут успели удалить/переместить файл — заливать нечего,
            # и дыры нет: нет файла — нет и потери.
            if not path.exists():
                continue
            if client is None:
                client = make_client()
            upload_file_sync(path, s3_key_for(path), client)
        except Exception:
            logger.warning("s3_covers: заливка %s упала", path, exc_info=True)
            client = None  # соединение могло протухнуть — пересоздать
        finally:
            _queue.task_done()


# Имена, которые раздаёт /covers/: релиз ({id}.jpg) и мастер (m{gid}.jpg).
# Всё остальное (в т.ч. попытки traversalа из URL) restore не обслуживает.
_RESTORE_NAME_RE = re.compile(r"m?\d+")

# Отдельный кэшируемый клиент для restore-пути: он живёт в запросах API,
# создавать boto3-клиент на каждый промах слишком дорого.
_restore_client = None
_restore_client_lock = threading.Lock()


def _get_restore_client():
    global _restore_client
    if _restore_client is None:
        with _restore_client_lock:
            if _restore_client is None:
                _restore_client = make_client()
    return _restore_client


def restore_sync(name: str) -> bool:
    """Вернуть covers/{name}.jpg из вечного слоя в горячий кэш на диске.

    True — файл на диске (уже был или скачан из S3). False — в S3 его нет
    (не зеркалился никогда) или S3 выключен/недоступен: зовущий идёт по
    старой лестнице (redirect на внешний источник). Не бросает.
    """
    global _restore_client
    if not enabled() or not _RESTORE_NAME_RE.fullmatch(name):
        return False
    covers_dir = Path(get_settings().covers_dir)
    dest = covers_dir / f"{name}.jpg"
    if dest.exists():
        return True
    tmp = covers_dir / f".tmp_s3_{name}_{uuid.uuid4().hex}.jpg"
    try:
        client = _get_restore_client()
        client.download_file(
            get_settings().s3_bucket_covers, f"{covers_dir.name}/{name}.jpg", str(tmp)
        )
        os.rename(tmp, dest)
        return True
    except Exception as exc:
        tmp.unlink(missing_ok=True)
        # 404 (в S3 нет) — норма холодного пути, шумим только по-настоящему.
        if "404" in str(exc) or "Not Found" in str(exc):
            logger.debug("s3_covers: restore %s — в бакете нет", name)
        else:
            logger.warning("s3_covers: restore %s упал", name, exc_info=True)
            with _restore_client_lock:
                _restore_client = None  # пересоздать после сетевой ошибки
        return False


async def restore_cover(name: str) -> bool:
    """Async-обёртка restore_sync: сетевой I/O уводим из event loop."""
    import asyncio
    return await asyncio.to_thread(restore_sync, name)


def schedule_upload(path: Path) -> None:
    """Поставить свежезаписанный файл в очередь на заливку в S3.

    Зовётся из горячего пути записи зеркала (_encode_and_place), поэтому
    НИКОГДА не бросает и не блокирует: no-op при выключенном S3, warning при
    полной очереди — дыру закроет реконсилер.
    """
    global _worker_started
    try:
        if not enabled():
            return
        if not _worker_started:
            with _worker_lock:
                if not _worker_started:
                    threading.Thread(
                        target=_worker_loop, daemon=True, name="s3-covers-uploader"
                    ).start()
                    _worker_started = True
        _queue.put_nowait(Path(path))
    except queue.Full:
        logger.warning(
            "s3_covers: очередь заливки полна (%d) — %s догонит реконсилер",
            _QUEUE_MAX,
            path,
        )
    except Exception:
        logger.warning("s3_covers: schedule_upload(%s) упал", path, exc_info=True)
