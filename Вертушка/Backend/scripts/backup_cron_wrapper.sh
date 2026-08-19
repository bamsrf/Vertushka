#!/bin/bash
# Обёртка для cron-бэкапа. Причина существования: с мая по август 2026 бэкапы
# молча падали (Permission denied после потери exec-бита), а ошибка уходила
# в лог, который никто не читал. Обёртка (1) зовёт backup.sh через bash, так
# что exec-бит больше не имеет значения, (2) при провале шлёт Telegram-алёрт
# тем же ботом, что и alerts.py.
set -u

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="$SCRIPT_DIR/../.env"
LOG_FILE="$HOME/backups/backup.log"
mkdir -p "$HOME/backups"

if bash "$SCRIPT_DIR/backup.sh" >> "$LOG_FILE" 2>&1; then
    exit 0
fi

RC=$?
echo "$(date): ❌ backup_cron_wrapper: backup.sh завершился с кодом $RC" >> "$LOG_FILE"

# Секреты читаются точечно из Backend/.env, значения не логируются.
env_var() { grep -E "^$1=" "$ENV_FILE" 2>/dev/null | tail -1 | cut -d= -f2- | tr -d '"' ; }
TOKEN="$(env_var TELEGRAM_BOT_TOKEN)"
CHAT_ID="$(env_var TELEGRAM_ALERT_CHAT_ID)"

if [ -n "$TOKEN" ] && [ -n "$CHAT_ID" ]; then
    curl -s -m 10 "https://api.telegram.org/bot${TOKEN}/sendMessage" \
        -d chat_id="$CHAT_ID" \
        -d text="🚨 Вертушка: ночной бэкап БД ПРОВАЛИЛСЯ (exit=$RC). Смотри ~/backups/backup.log" \
        > /dev/null 2>&1 || echo "$(date): не удалось отправить Telegram-алёрт" >> "$LOG_FILE"
else
    echo "$(date): TELEGRAM_BOT_TOKEN/TELEGRAM_ALERT_CHAT_ID не найдены в $ENV_FILE — алёрт не отправлен" >> "$LOG_FILE"
fi

exit "$RC"
