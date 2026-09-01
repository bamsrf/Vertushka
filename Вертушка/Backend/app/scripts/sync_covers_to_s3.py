"""Реконсилер зеркала обложек ↔ S3: заливает в бакет всё, чего там ещё нет.

Три роли:
1. Первичная миграция накопленного зеркала (разово, после создания бакета,
   ДО включения COVERS_S3_ENABLED).
2. Догон дыр dual-write (переполнение очереди, сетевые падения, рестарт
   контейнера с неразобранной очередью).
3. Аудит полноты: --dry-run считает недостающее, ничего не заливая.

Идемпотентен: сверка по ключам, существующие в бакете не перезаливаются.
Работает независимо от флага COVERS_S3_ENABLED — нужны только S3_-переменные
в окружении (эндпоинт, бакет, ключи).

Запуск (в контейнере):
    python -m app.scripts.sync_covers_to_s3 --dry-run
    python -m app.scripts.sync_covers_to_s3 --threads 8
"""
import argparse
import logging
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from app.config import get_settings
from app.services.s3_covers import (
    _config_problems,
    make_client,
    s3_key_for,
    upload_file_sync,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("sync_covers_to_s3")


def _list_remote_keys(client, bucket: str, prefix: str) -> set[str]:
    keys: set[str] = set()
    paginator = client.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
        for obj in page.get("Contents", []):
            keys.add(obj["Key"])
    return keys


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="только посчитать")
    parser.add_argument("--threads", type=int, default=8, help="потоков заливки")
    args = parser.parse_args()

    settings = get_settings()
    problems = _config_problems(settings)
    if problems:
        raise SystemExit(f"Не заданы переменные: {', '.join(problems)}")

    covers_dir = Path(settings.covers_dir)
    if not covers_dir.is_dir():
        raise SystemExit(f"Каталог зеркала не найден: {covers_dir}")

    # .tmp_* — недописанные файлы атомарного rename, их не трогаем.
    local: dict[str, Path] = {}
    for p in covers_dir.rglob("*"):
        if p.is_file() and not p.name.startswith(".tmp_"):
            local[s3_key_for(p)] = p

    client = make_client()
    bucket = settings.s3_bucket_covers
    remote = _list_remote_keys(client, bucket, f"{covers_dir.name}/")
    missing = {k: p for k, p in local.items() if k not in remote}
    total_mb = sum(p.stat().st_size for p in missing.values()) / 1024 / 1024
    logger.info(
        "локально %d файлов, в бакете %d, недостаёт %d (%.0f МБ)",
        len(local), len(remote), len(missing), total_mb,
    )
    if args.dry_run or not missing:
        return

    started = time.monotonic()
    done = 0
    errors = 0
    # Чанки, а не 63K футур разом: каждая future держит ссылки до самого
    # конца прогона, на 4 ГБ хоста это дорога к OOM («Killed», 28.08.2026).
    chunk_size = 1000
    items = list(missing.items())
    with ThreadPoolExecutor(max_workers=args.threads) as pool:
        for start in range(0, len(items), chunk_size):
            chunk = items[start:start + chunk_size]
            futures = {
                pool.submit(upload_file_sync, path, key, client): key
                for key, path in chunk
            }
            for fut in as_completed(futures):
                try:
                    fut.result()
                    done += 1
                except Exception:
                    errors += 1
                    logger.warning("заливка %s упала", futures[fut], exc_info=True)
            logger.info("прогресс: %d/%d (ошибок %d)", done + errors, len(items), errors)

    logger.info(
        "ГОТОВО: залито %d, ошибок %d, за %.0fs — при ошибках просто перезапустить",
        done, errors, time.monotonic() - started,
    )
    if errors:
        sys.exit(1)


if __name__ == "__main__":
    main()
