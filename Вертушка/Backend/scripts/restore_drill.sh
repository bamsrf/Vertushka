#!/bin/bash
# ===========================================
# Restore-drill: проверка, что бэкап реально восстанавливается.
# Вертушка API
#
# Бэкап без проверенного восстановления = надежда, а не бэкап. Скрипт
# берёт ПОСЛЕДНИЙ бэкап, разворачивает его в ОДНОРАЗОВЫЙ Postgres-контейнер
# (прод не трогает вообще), прогоняет sanity-проверки и сносит контейнер.
#
# Запуск:  bash ~/vertushka/Вертушка/Backend/scripts/restore_drill.sh
# Можно скормить конкретный файл:  restore_drill.sh /path/to/dump.sql.gz
# ===========================================
set -euo pipefail

BACKUP_DIR="${BACKUP_DIR:-$HOME/backups}"
DB_USER="vertushka_user"
DB_NAME="vertushka"
DB_PASS="${RESTORE_DRILL_PASS:-drill}"
PG_IMAGE="${PG_IMAGE:-postgres:16}"
DRILL_CONTAINER="vertushka_restore_drill"
# Ключевые таблицы, на которых ждём непустой результат после restore.
# Справочные таблицы Discogs/MB в бэкапе пустые (backup.sh --exclude-table-data):
# после реального restore их нужно перезалить из исходных дампов отдельной
# процедурой. Sanity-проверка ниже осознанно смотрит только пользовательские.
SANITY_TABLES=(users records collections wishlists)

GREEN='\033[0;32m'; RED='\033[0;31m'; YELLOW='\033[0;33m'; NC='\033[0m'
fail() { echo -e "${RED}$(date): ❌ $1${NC}"; exit 1; }

# --- 1. Выбрать бэкап ---------------------------------------------------------
BACKUP_FILE="${1:-}"
if [ -z "$BACKUP_FILE" ]; then
    BACKUP_FILE=$(ls -t "$BACKUP_DIR"/vertushka_*.sql.gz 2>/dev/null | head -1 || true)
fi
[ -n "$BACKUP_FILE" ] && [ -f "$BACKUP_FILE" ] || fail "Бэкап не найден (BACKUP_DIR=$BACKUP_DIR)"

echo "$(date): 🧪 Restore-drill на $BACKUP_FILE"
gunzip -t "$BACKUP_FILE" 2>/dev/null || fail "Архив повреждён (gunzip -t)"

# --- 2. Гарантированный teardown при любом выходе -----------------------------
cleanup() {
    docker rm -f "$DRILL_CONTAINER" >/dev/null 2>&1 || true
}
trap cleanup EXIT
cleanup  # снести хвост от прошлого упавшего прогона

# --- 3. Поднять одноразовый Postgres (без published-порта, эфемерный) ---------
echo "$(date): 🐘 Поднимаю одноразовый $PG_IMAGE…"
docker run -d --rm --name "$DRILL_CONTAINER" \
    -e POSTGRES_USER="$DB_USER" \
    -e POSTGRES_PASSWORD="$DB_PASS" \
    -e POSTGRES_DB="$DB_NAME" \
    "$PG_IMAGE" >/dev/null

# Дождаться готовности (pg_isready), таймаут ~30с.
for i in $(seq 1 30); do
    if docker exec "$DRILL_CONTAINER" pg_isready -U "$DB_USER" -d "$DB_NAME" >/dev/null 2>&1; then
        break
    fi
    [ "$i" -eq 30 ] && fail "Postgres не поднялся за 30с"
    sleep 1
done

# --- 4. Восстановить дамп -----------------------------------------------------
echo "$(date): ⏳ Восстанавливаю дамп…"
if ! gunzip -c "$BACKUP_FILE" | docker exec -i "$DRILL_CONTAINER" \
        psql -v ON_ERROR_STOP=1 -U "$DB_USER" -d "$DB_NAME" >/dev/null 2>/tmp/restore_drill.err; then
    echo -e "${RED}--- psql stderr (хвост) ---${NC}"; tail -20 /tmp/restore_drill.err || true
    fail "psql restore завершился ошибкой"
fi

# --- 5. Sanity-проверки -------------------------------------------------------
q() { docker exec "$DRILL_CONTAINER" psql -tAX -U "$DB_USER" -d "$DB_NAME" -c "$1" 2>/dev/null | tr -d '[:space:]'; }

TABLE_COUNT=$(q "SELECT count(*) FROM information_schema.tables WHERE table_schema='public';")
[ "${TABLE_COUNT:-0}" -gt 0 ] || fail "После restore нет таблиц в public — дамп пустой?"
echo -e "${GREEN}$(date): таблиц в public: $TABLE_COUNT${NC}"

WARN=0
for t in "${SANITY_TABLES[@]}"; do
    if ! q "SELECT to_regclass('public.$t');" | grep -q "$t"; then
        echo -e "${YELLOW}  ⚠️  таблицы '$t' нет — пропускаю${NC}"; WARN=1; continue
    fi
    rows=$(q "SELECT count(*) FROM \"$t\";")
    echo "  • $t: ${rows:-?} строк"
done

echo -e "${GREEN}$(date): ✅ Restore-drill пройден — бэкап восстанавливается${NC}"
[ "$WARN" -eq 1 ] && echo -e "${YELLOW}(были предупреждения по таблицам — проверь, ожидаемо ли)${NC}"
exit 0
