#!/bin/bash
# ===========================================
# Ставит/снимает крон-строку замера ресурсов.
#
# Отдельным скриптом, потому что то же самое одной ssh-командой не пережило
# вставку в терминал: перенос строки порвал кавычки, и cron молча не встал.
#
#   bash ~/metrics/install_metrics_cron.sh          # поставить
#   bash ~/metrics/install_metrics_cron.sh remove   # снять
# ===========================================
set -e

LINE='*/5 * * * * bash ~/metrics/resource_sample.sh >> ~/metrics/sample.log 2>&1'
TMP=$(mktemp)
trap 'rm -f "$TMP"' EXIT

crontab -l > "$TMP" 2>/dev/null || true
# Бэкап прежнего расписания рядом — откатиться можно без git.
cp "$TMP" ~/metrics/crontab.backup.$(date +%Y%m%d-%H%M)

if [ "${1:-install}" = "remove" ]; then
    grep -v 'resource_sample.sh' "$TMP" > "$TMP.new" || true
    crontab "$TMP.new"
    rm -f "$TMP.new"
    echo "✅ Замер снят. История в ~/metrics/resources.csv осталась."
    exit 0
fi

if grep -q 'resource_sample.sh' "$TMP"; then
    echo "ℹ️  Замер уже стоял — расписание не тронуто."
else
    printf '\n# Замер ресурсов раз в 5 минут: отличить плато памяти от ползучего роста.\n' >> "$TMP"
    printf '# Отчёт: bash ~/metrics/resource_sample.sh report | Снять: bash ~/metrics/install_metrics_cron.sh remove\n' >> "$TMP"
    printf '%s\n' "$LINE" >> "$TMP"
    crontab "$TMP"
    echo "✅ Замер поставлен."
fi

echo
echo "Строк замера в crontab: $(crontab -l | grep -c 'resource_sample.sh')"
echo "Следующая точка — в ближайшие 5 минут."
