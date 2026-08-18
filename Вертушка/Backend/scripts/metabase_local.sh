#!/bin/bash
# ===========================================
# Локальный Metabase поверх боевой БД. См. docker-compose.metabase.yml.
#
#   bash scripts/metabase_local.sh setup-role   # один раз: роль metabase_ro на проде
#   bash scripts/metabase_local.sh up           # поднять туннель + Metabase
#   bash scripts/metabase_local.sh creds        # напомнить параметры подключения
#   bash scripts/metabase_local.sh down         # погасить
#   bash scripts/metabase_local.sh logs
# ===========================================

set -e

cd "$(dirname "$0")/.."

COMPOSE="docker compose -f docker-compose.metabase.yml"
PASS_FILE=".env.metabase"
VPS="deploy@85.198.85.12"
REMOTE_DIR='~/vertushka/Вертушка/Backend'

# Пароль metabase_ro лежит только здесь и в pg_authid на проде. Файл в
# .gitignore — в репозиторий такому значению не место.
ensure_password() {
    if [ ! -f "$PASS_FILE" ]; then
        echo "METABASE_RO_PASSWORD=$(openssl rand -base64 32 | tr -d '/+=' | head -c 32)" > "$PASS_FILE"
        chmod 600 "$PASS_FILE"
        # Строго в stderr: read_password() читает stdout этой функции через
        # $(...), и любой echo сюда уехал бы В САМ ПАРОЛЬ.
        echo "🔑 Сгенерирован пароль metabase_ro → $PASS_FILE (chmod 600)" >&2
    fi
}

read_password() {
    ensure_password
    grep '^METABASE_RO_PASSWORD=' "$PASS_FILE" | cut -d= -f2-
}

case "${1:-up}" in
    setup-role)
        PASS="$(read_password)"
        echo "🔧 Создаю read-only роль metabase_ro на проде…"
        # set -a: подтягиваем DB_USER/DB_PASSWORD из прод-окружения, они нужны
        # и compose'у (${DB_USER} в docker-compose.prod.yml), и самому psql.
        ssh "$VPS" "cd $REMOTE_DIR && set -a && . ./.env && set +a && \
            METABASE_RO_PASSWORD='$PASS' bash scripts/setup_metabase_role.sh"
        ;;
    up)
        ensure_password
        $COMPOSE up -d
        echo "⏳ Metabase поднимается (первый старт ~1-2 мин)…"
        for _ in $(seq 1 60); do
            if curl -sf http://127.0.0.1:3000/api/health >/dev/null 2>&1; then
                echo "✅ Metabase готов: http://localhost:3000"
                exit 0
            fi
            sleep 5
        done
        echo "⚠️ Не дождался хелсчека за 5 мин — смотри: bash scripts/metabase_local.sh logs" >&2
        exit 1
        ;;
    creds)
        cat <<TXT
Вход в Metabase — http://localhost:3000
  Email    : vladrum0310@gmail.com
  Пароль   : $(grep '^MB_ADMIN_PASSWORD=' "$PASS_FILE" | cut -d= -f2-)

Боевая БД уже подключена. Если понадобится завести заново
(Admin → Databases → Add):
  Display name : Вертушка (prod, read-only)
  Database type: PostgreSQL
  Host         : db-tunnel
  Port         : 5432
  Database name: vertushka
  Username     : metabase_ro
  Password     : $(read_password)
TXT
        ;;
    down)   $COMPOSE down ;;
    logs)   $COMPOSE logs --tail=80 -f ;;
    *)      echo "Неизвестная команда: $1" >&2; exit 1 ;;
esac
