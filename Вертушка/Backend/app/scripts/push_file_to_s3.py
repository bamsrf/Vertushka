"""Заливка одного файла в S3-бакет + ротация по префиксу.

Используется backup.sh: ночной дамп БД уезжает в вечный слой (offsite-копия;
до 28.08.2026 бэкапы жили на том же диске, что и база). Годится для любого
файла: content-type угадывается по расширению, ротация опциональна.

    python -m app.scripts.push_file_to_s3 /tmp/dump.sql.gz --prefix backups/ --keep 30

--keep N: после заливки удалить из бакета самые старые объекты под prefix,
оставив N новейших (по LastModified). Без --keep ничего не удаляется.
"""
import argparse
import logging
import mimetypes
from pathlib import Path

from app.services.s3_covers import _config_problems, make_client
from app.config import get_settings

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("push_file_to_s3")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("file", help="путь к файлу")
    parser.add_argument("--prefix", default="", help="префикс ключа в бакете, например backups/")
    parser.add_argument("--keep", type=int, default=0, help="оставить N новейших объектов под префиксом")
    args = parser.parse_args()

    settings = get_settings()
    problems = _config_problems(settings)
    if problems:
        raise SystemExit(f"Не заданы переменные: {', '.join(problems)}")
    path = Path(args.file)
    if not path.is_file():
        raise SystemExit(f"Файл не найден: {path}")

    client = make_client()
    bucket = settings.s3_bucket_covers
    key = f"{args.prefix}{path.name}"
    ctype = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    client.upload_file(str(path), bucket, key, ExtraArgs={"ContentType": ctype})
    logger.info("залит %s → s3://%s/%s (%.1f МБ)", path, bucket, key,
                path.stat().st_size / 1024 / 1024)

    if args.keep > 0 and args.prefix:
        objs = []
        paginator = client.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=bucket, Prefix=args.prefix):
            objs.extend(page.get("Contents", []))
        objs.sort(key=lambda o: o["LastModified"], reverse=True)
        stale = objs[args.keep:]
        for obj in stale:
            client.delete_object(Bucket=bucket, Key=obj["Key"])
        if stale:
            logger.info("ротация %s: удалено %d, осталось %d",
                        args.prefix, len(stale), min(len(objs), args.keep))


if __name__ == "__main__":
    main()
