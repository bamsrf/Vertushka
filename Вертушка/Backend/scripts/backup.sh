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
# URL обложек — их уже миллионы (drip + офлайн-каналы), и «переисчислятся сами»
# для drip-части означает месяцы; recovery-путь — CSV-срез
# ~/backups/covers_urls_YYYYMMDD.csv.gz (discogs_id,cover_image_url,
# cover_checked_at; ротация его не трогает — маска vertushka_*), переснимать
# после крупных прогонов каналов.
# mb_catno_covers / mb_mbid_rg — справочники catno-канала (27.08.2026, ~1.4 ГБ
# raw): пересоздаются из CSV при месячном MB-рефреше, в дампе им не место.
# catno_cover_audit НЕ исключать: это provenance применённых обложек, мал.
EXCLUDE_REF_TABLES=(
  discogs_releases_index discogs_release_formats discogs_release_tracklists
  discogs_artists discogs_artist_names discogs_master_covers
  discogs_dump_state mb_discogs_map mb_barcode_covers
  mb_catno_covers mb_mbid_rg
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

# Offsite-копия дампа в S3 (Beget, бакет обложек, префикс backups/).
# До 28.08.2026 бэкапы жили на том же диске, что и база — смерть диска
# уносила и данные, и их копии. Заливка через api-контейнер (там boto3 и
# S3_-креды из .env.prod), aws cli на хосте не нужен. Неуспех — только
# warning: локальный дамп цел, алёрт не шлём.
API_CONT=$(docker ps --format '{{.Names}}' | grep vertushka_api | head -1)
if [ -n "$API_CONT" ]; then
    BASE=$(basename "$BACKUP_FILE")
    if docker cp "$BACKUP_FILE" "$API_CONT:/tmp/$BASE" \
       && docker exec "$API_CONT" python -m app.scripts.push_file_to_s3 \
            "/tmp/$BASE" --prefix backups/ --keep 30 \
       && docker exec "$API_CONT" rm -f "/tmp/$BASE"; then
        echo "$(date): ☁️  Дамп залит в S3 (backups/, retention 30)"
    else
        echo -e "${RED}$(date): ⚠️  S3-копия дампа не залилась (локальный дамп цел)${NC}"
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
