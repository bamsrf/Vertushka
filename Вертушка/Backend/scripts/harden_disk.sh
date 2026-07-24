#!/bin/bash
# ===========================================
# Disk hardening для Вертушка API
# ===========================================
# Применяет все системные защиты против разрастания диска:
# 1. Лимит логов Docker (daemon.json)
# 2. Лимит journald (systemd-journald.conf)
# 3. Weekly cron на чистку Docker (image/builder prune)
# 4. Disk-usage alert cron
#
# ВАЖНО: ни одна команда здесь не использует --volumes / -v и не трогает
# named volumes (postgres_data, uploads_data, redis_data, metabase_data).
# Данные пользователей сохранятся.
#
# Запуск:
#   sudo bash ~/vertushka/Вертушка/Backend/scripts/harden_disk.sh
#
# Идемпотентен — можно запускать повторно.
# ===========================================

set -e

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

if [ "$EUID" -ne 0 ]; then
    echo -e "${RED}Запусти под sudo: sudo bash $0${NC}"
    exit 1
fi

echo -e "${YELLOW}🔧 Disk hardening — старт${NC}"
echo ""

# ─── 1. Docker daemon: лимит контейнерных логов ────────────────────────
echo -e "${YELLOW}[1/4] Настраиваю /etc/docker/daemon.json (лимит логов)${NC}"

DAEMON_JSON=/etc/docker/daemon.json
mkdir -p /etc/docker

if [ -f "$DAEMON_JSON" ]; then
    cp "$DAEMON_JSON" "${DAEMON_JSON}.bak.$(date +%Y%m%d_%H%M%S)"
    echo "   Backup: ${DAEMON_JSON}.bak.*"
fi

cat > "$DAEMON_JSON" <<'EOF'
{
  "log-driver": "json-file",
  "log-opts": {
    "max-size": "10m",
    "max-file": "3"
  }
}
EOF

echo "   ✅ daemon.json: max-size=10m, max-file=3 (30 МБ rolling buffer на контейнер)"
echo "   ⚠️  Перезапуск Docker применит лимит к НОВЫМ контейнерам."
echo "      Существующие нужно пересоздать (см. финальные шаги ниже)."
echo ""

# ─── 2. journald: лимит системных логов ────────────────────────────────
echo -e "${YELLOW}[2/4] Настраиваю journald (лимит 200 МБ)${NC}"

JOURNALD_CONF=/etc/systemd/journald.conf
cp "$JOURNALD_CONF" "${JOURNALD_CONF}.bak.$(date +%Y%m%d_%H%M%S)"

# Удаляем старые SystemMaxUse/SystemKeepFree (если были) и добавляем заново
sed -i '/^SystemMaxUse=/d; /^SystemKeepFree=/d; /^#SystemMaxUse=/d; /^#SystemKeepFree=/d' "$JOURNALD_CONF"
echo "" >> "$JOURNALD_CONF"
echo "# Vertushka disk hardening" >> "$JOURNALD_CONF"
echo "SystemMaxUse=200M" >> "$JOURNALD_CONF"
echo "SystemKeepFree=500M" >> "$JOURNALD_CONF"

systemctl restart systemd-journald
echo "   ✅ journald: SystemMaxUse=200M, перезапущен"
echo ""

# ─── 3. Weekly cron: чистка Docker и apt ───────────────────────────────
echo -e "${YELLOW}[3/4] Устанавливаю weekly cron (Docker + apt cleanup)${NC}"

CRON_FILE=/etc/cron.d/vertushka-disk-cleanup
cat > "$CRON_FILE" <<'EOF'
# Vertushka — еженедельная чистка диска. Безопасно: без --volumes.
# image prune -af  — образы, не используемые ни одним контейнером, старше 14 дней
# builder prune    — кэш билда старше 14 дней, потолок 500 МБ
# apt-get clean    — закэшированные .deb из /var/cache/apt
SHELL=/bin/bash
PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin

0 4 * * 0 root docker system prune -af --filter "until=336h" >> /var/log/docker-cleanup.log 2>&1
5 4 * * 0 root docker builder prune -af --filter "until=336h" --keep-storage 500MB >> /var/log/docker-cleanup.log 2>&1
0 5 * * 0 root apt-get clean >> /var/log/apt-cleanup.log 2>&1
EOF
chmod 644 "$CRON_FILE"

echo "   ✅ /etc/cron.d/vertushka-disk-cleanup установлен"
echo "      Расписание: воскресенье 04:00 / 04:05 / 05:00 UTC"
echo ""

# ─── 4. Disk usage alert cron ──────────────────────────────────────────
echo -e "${YELLOW}[4/4] Устанавливаю disk usage alert (>80%)${NC}"

ALERT_CRON=/etc/cron.d/vertushka-disk-alert
cat > "$ALERT_CRON" <<'EOF'
# Каждые 30 минут пишет в лог если корневой раздел >80%
SHELL=/bin/bash
PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin

*/30 * * * * root USE=$(df / | awk 'NR==2{print $5}' | tr -d '%'); [ "$USE" -gt 80 ] && echo "[$(date -Iseconds)] / at $USE%" >> /var/log/disk-alert.log
EOF
chmod 644 "$ALERT_CRON"

echo "   ✅ /etc/cron.d/vertushka-disk-alert установлен"
echo "      Лог: /var/log/disk-alert.log"
echo ""

# ─── Финальные инструкции ──────────────────────────────────────────────
echo -e "${GREEN}✅ Hardening применён${NC}"
echo ""
echo -e "${YELLOW}Осталось вручную (требует короткого даунтайма):${NC}"
echo ""
echo "  1. Перезапустить Docker daemon (нужно для активации daemon.json):"
echo "       sudo systemctl restart docker"
echo ""
echo "  2. Пересоздать контейнеры чтобы они подхватили новый лимит логов."
echo "     По одному, чтобы не было полного даунтайма:"
echo "       cd ~/vertushka/Вертушка/Backend"
echo "       # api — blue-green: пересоздавай АКТИВНЫЙ цвет (см. nginx/.active_color)"
echo "       docker compose -f docker-compose.prod.yml --profile blue up -d --force-recreate api-blue   # или green"
echo "       docker compose -f docker-compose.prod.yml up -d --force-recreate scheduler"
echo "       docker compose -f docker-compose.prod.yml up -d --force-recreate nginx"
echo "       docker compose -f docker-compose.prod.yml up -d --force-recreate metabase"
echo "       docker compose -f docker-compose.prod.yml up -d --force-recreate db"
echo "       docker compose -f docker-compose.prod.yml up -d --force-recreate redis"
echo ""
echo "     Данные пользователей в volumes — пересоздание контейнеров их не трогает."
echo ""
echo "  3. (опционально) Однократная глубокая чистка прямо сейчас:"
echo "       sudo docker builder prune -af"
echo "       sudo docker image prune -af"
echo "       sudo docker container prune -f"
echo "       sudo journalctl --vacuum-size=100M"
echo "       sudo apt-get clean"
echo ""
echo "  4. Не забудь добавить в прод .env:"
echo "       COVERS_MAX_CACHE_MB=500"
echo "     И перезапустить api контейнер."
echo ""
