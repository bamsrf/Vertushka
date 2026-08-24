#!/bin/bash
# ===========================================
# Скрипт автоматического бэкапа PostgreSQL
# Вертушка API
# ===========================================

# Настройки
BACKUP_DIR="$HOME/backups"
CONTAINER_NAME="vertushka_db"
DB_USER="vertushka_user"
DB_NAME="vertushka"
DAYS_TO_KEEP=7

# Цвета для вывода
GREEN='\033[0;32m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Создать директорию если не существует
mkdir -p $BACKUP_DIR

# Имя файла с датой
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_FILE="$BACKUP_DIR/vertushka_${TIMESTAMP}.sql.gz"

echo "$(date): Начинаю бэкап базы данных..."

# pipefail чтобы поймать сбой pg_dump через pipe в gzip.
set -o pipefail

# Справочники Discogs/MusicBrainz (97% объёма БД) в дамп не тащим: они
# восстановимы из исходных дампов (см. memory vertushka-discogs-dump-refresh
# и docs/plans). Схема таблиц в бэкапе остаётся — исключаются только данные.
# Исключение из правила «восстановимы из дампов» — discogs_release_tracklists:
# повторный парсинг releases-дампа занимает часы и требует скачать ~12 ГБ,
# которые прод сам не вытянет (Cloudflare). Recovery-путь: разовый дамп
# ~/backups/ref_discogs_release_tracklists_YYYYMMDD.sql.gz (ротация его не
# трогает — маска vertushka_*) либо tracklists.csv + \copy, см.
# app/scripts/ingest_release_tracklists.py. После обновления Discogs-дампа
# переснять: pg_dump --table=discogs_release_tracklists.
# discogs_dump_state исключён сознательно: иначе после restore система считала
# бы дампы загруженными при пустых таблицах. discogs_price_jobs НЕ исключать —
# это пользовательская очередь, не справочник. Оговорка: releases_index копит
# URL, найденные живым резолвом обложек, — после restore они переисчислятся
# сами (negative-cache + лестница источников).
EXCLUDE_REF_TABLES=(
  discogs_releases_index discogs_release_formats discogs_release_tracklists
  discogs_artists discogs_artist_names discogs_master_covers
  discogs_dump_state mb_discogs_map mb_barcode_covers
)
EXCLUDE_ARGS=()
for t in "${EXCLUDE_REF_TABLES[@]}"; do
  EXCLUDE_ARGS+=(--exclude-table-data="$t")
done

# Создать бэкап и сжать
docker exec $CONTAINER_NAME pg_dump -U $DB_USER "${EXCLUDE_ARGS[@]}" $DB_NAME | gzip > $BACKUP_FILE
DUMP_EXIT=$?

if [ $DUMP_EXIT -ne 0 ] || [ ! -s "$BACKUP_FILE" ]; then
    echo -e "${RED}$(date): ❌ ОШИБКА создания бэкапа (exit=$DUMP_EXIT)!${NC}"
    [ -f "$BACKUP_FILE" ] && rm "$BACKUP_FILE"
    exit 1
fi

# Verify целостность gzip-архива. Бэкап без проверки = нет бэкапа.
if ! gunzip -t "$BACKUP_FILE" 2>/dev/null; then
    echo -e "${RED}$(date): ❌ Бэкап повреждён (gunzip -t failed): $BACKUP_FILE${NC}"
    rm -f "$BACKUP_FILE"
    exit 2
fi

SIZE=$(du -h "$BACKUP_FILE" | cut -f1)
echo -e "${GREEN}$(date): ✅ Бэкап создан и проверен: $BACKUP_FILE ($SIZE)${NC}"

# Опциональная отправка в Yandex Object Storage (S3-совместимый).
# Чтобы включить — экспортируй S3_BUCKET, S3_ENDPOINT, AWS_ACCESS_KEY_ID,
# AWS_SECRET_ACCESS_KEY перед запуском (например в cron-задании).
if [ -n "$S3_BUCKET" ] && command -v aws >/dev/null 2>&1; then
    if aws --endpoint-url="${S3_ENDPOINT:-https://storage.yandexcloud.net}" \
        s3 cp "$BACKUP_FILE" "s3://$S3_BUCKET/$(basename $BACKUP_FILE)" --quiet; then
        echo "$(date): ☁️  Загружено в s3://$S3_BUCKET/"
    else
        echo -e "${RED}$(date): ⚠️  Не удалось загрузить бэкап в S3${NC}"
    fi
fi

# Удалить старые бэкапы (старше DAYS_TO_KEEP дней)
DELETED=$(find $BACKUP_DIR -name "vertushka_*.sql.gz" -mtime +$DAYS_TO_KEEP -delete -print | wc -l)
if [ $DELETED -gt 0 ]; then
    echo "$(date): 🗑️  Удалено старых бэкапов: $DELETED"
fi

# Показать список текущих бэкапов
echo "$(date): 📁 Текущие бэкапы:"
ls -lh $BACKUP_DIR/vertushka_*.sql.gz 2>/dev/null | tail -5

exit 0
