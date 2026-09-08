#!/usr/bin/env bash
#
# Настройка Telegram-канала алармов на проде: токен бота, chat_id, секрет
# webhook'а GlitchTip, доступ к ящику поддержки.
#
# Почему скрипт, а не «допиши три строки в .env.prod»: дописывание руками
# уже один раз молча порвалось о перенос строки (crontab, 03.09.2026).
# Здесь ключи ставятся идемпотентно (повторный запуск не плодит дубли),
# файл бэкапится, а результат проверяется живой отправкой в чат.
#
# Запускать НА ПРОДЕ из каталога Backend:
#   bash scripts/setup_alerts.sh
#
# См. docs/plans/quality/TELEGRAM_ALERTS_PLAN.md
set -euo pipefail

# sed -i здесь GNU-шный: скрипт для прода (Linux), на macOS не запускать.
ENV_FILE=".env.prod"
GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; NC='\033[0m'

if [ ! -f "$ENV_FILE" ]; then
    echo -e "${RED}Нет $ENV_FILE — запусти из каталога Backend на проде.${NC}"
    exit 1
fi

BACKUP="${ENV_FILE}.bak.$(date +%Y%m%d_%H%M%S)"
cp "$ENV_FILE" "$BACKUP"
echo "Бэкап: $BACKUP"

# Файл мог остаться без финального перевода строки — тогда первый же
# дописанный ключ склеится с последней строкой и молча пропадёт.
if [ -n "$(tail -c1 "$ENV_FILE")" ]; then
    echo >> "$ENV_FILE"
fi

upsert() {
    local key="$1" value="$2"
    sed -i "/^${key}=/d" "$ENV_FILE"
    printf '%s=%s\n' "$key" "$value" >> "$ENV_FILE"
}

current() {
    sed -n "s/^${1}=//p" "$ENV_FILE" | tail -1
}

ask() {
    # ask ПЕРЕМЕННАЯ "подсказка" [--secret]
    local var="$1" prompt="$2" secret="${3:-}" existing answer
    existing="$(current "$var")"
    if [ -n "$existing" ]; then
        echo -e "${YELLOW}$var уже задан${NC} — Enter, чтобы оставить как есть."
    fi
    if [ "$secret" = "--secret" ]; then
        read -r -s -p "$prompt: " answer; echo
    else
        read -r -p "$prompt: " answer
    fi
    if [ -n "$answer" ]; then
        upsert "$var" "$answer"
    elif [ -z "$existing" ]; then
        echo -e "${RED}$var пуст — этот канал работать не будет.${NC}"
    fi
}

echo
echo "── 1/4 Бот ──────────────────────────────────────────────────────────"
ask TELEGRAM_BOT_TOKEN "Токен от @BotFather" --secret

TOKEN="$(current TELEGRAM_BOT_TOKEN)"
if [ -z "$TOKEN" ]; then
    echo -e "${RED}Без токена дальше бессмысленно. Файл не тронут: $BACKUP${NC}"
    exit 1
fi

BOT_NAME="$(curl -s --max-time 10 "https://api.telegram.org/bot${TOKEN}/getMe" \
    | sed -n 's/.*"username":"\([^"]*\)".*/\1/p')"
if [ -z "$BOT_NAME" ]; then
    echo -e "${RED}Telegram не признал токен (или сеть недоступна). Проверь и запусти снова.${NC}"
    exit 1
fi
echo -e "${GREEN}Бот на связи: @${BOT_NAME}${NC}"

echo
echo "── 2/4 Чат ──────────────────────────────────────────────────────────"
echo "Напиши боту (или в группу с ботом) любое сообщение и нажми Enter."
read -r _

CHAT_ID="$(curl -s --max-time 10 "https://api.telegram.org/bot${TOKEN}/getUpdates" \
    | tr ',' '\n' | sed -n 's/.*"id":\(-\{0,1\}[0-9]\{5,\}\).*/\1/p' | tail -1)"

if [ -n "$CHAT_ID" ]; then
    echo -e "Нашёл chat_id: ${GREEN}${CHAT_ID}${NC}"
    read -r -p "Использовать его? [Y/n]: " confirm
    if [ "${confirm:-y}" = "n" ]; then
        CHAT_ID=""
    fi
fi

if [ -n "$CHAT_ID" ]; then
    upsert TELEGRAM_ALERT_CHAT_ID "$CHAT_ID"
else
    echo "Не удалось определить автоматически."
    echo "Открой https://api.telegram.org/bot<ТОКЕН>/getUpdates и возьми chat.id"
    echo "(у групп он отрицательный — минус часть числа, не опечатка)."
    ask TELEGRAM_ALERT_CHAT_ID "chat_id"
fi

echo
echo "── 3/4 GlitchTip ────────────────────────────────────────────────────"
if [ -n "$(current GLITCHTIP_WEBHOOK_SECRET)" ]; then
    echo "Секрет уже есть — оставляю."
else
    upsert GLITCHTIP_WEBHOOK_SECRET "$(openssl rand -hex 32)"
    echo -e "${GREEN}Секрет сгенерирован.${NC}"
fi
echo "URL для GlitchTip → Alerts → Webhook:"
echo -e "${YELLOW}https://api.vinyl-vertushka.ru/api/internal/glitchtip/$(current GLITCHTIP_WEBHOOK_SECRET)${NC}"

echo
echo "── 4/4 Почта support@ ───────────────────────────────────────────────"
echo "Пароль от самого ящика на Beget, не от панели. Enter — пропустить."
if [ -z "$(current MAILBOX_IMAP_USER)" ]; then
    upsert MAILBOX_IMAP_USER "support@vinyl-vertushka.store"
fi
if [ -z "$(current MAILBOX_IMAP_HOST)" ]; then
    upsert MAILBOX_IMAP_HOST "imap.beget.com"
fi
echo "Ящик: $(current MAILBOX_IMAP_USER) на $(current MAILBOX_IMAP_HOST)"
ask MAILBOX_IMAP_PASSWORD "Пароль ящика" --secret

if [ -n "$(current MAILBOX_IMAP_PASSWORD)" ]; then
    echo "Проверяю вход в ящик..."
    if python3 - "$(current MAILBOX_IMAP_HOST)" "$(current MAILBOX_IMAP_USER)" "$(current MAILBOX_IMAP_PASSWORD)" <<'PY'
import imaplib, sys
host, user, password = sys.argv[1:4]
try:
    connection = imaplib.IMAP4_SSL(host, 993, timeout=15)
    connection.login(user, password)
    connection.select("INBOX")
    connection.logout()
except Exception as error:
    print(f"  {error}")
    sys.exit(1)
PY
    then
        echo -e "${GREEN}Ящик открывается.${NC}"
    else
        echo -e "${RED}Ящик не открылся — проверь адрес и пароль (канал почты работать не будет).${NC}"
    fi
fi

echo
echo "── Проверка ─────────────────────────────────────────────────────────"
CHAT_ID="$(current TELEGRAM_ALERT_CHAT_ID)"
STATUS="$(curl -s --max-time 10 -o /dev/null -w '%{http_code}' \
    -X POST "https://api.telegram.org/bot${TOKEN}/sendMessage" \
    -d "chat_id=${CHAT_ID}" \
    --data-urlencode "text=✅ Канал алармов Вертушки настроен. Это сообщение отправил setup_alerts.sh")"

if [ "$STATUS" = "200" ]; then
    echo -e "${GREEN}Тестовое сообщение доставлено — проверь чат.${NC}"
else
    echo -e "${RED}Telegram ответил $STATUS. Скорее всего неверный chat_id или боту не писали.${NC}"
fi

echo
echo "Осталось применить конфиг (env_file читается при СОЗДАНИИ контейнера,"
echo "поэтому restart не годится — нужен полный деплой):"
echo -e "  ${YELLOW}bash scripts/deploy.sh${NC}"
echo "Откатить правки .env.prod: cp $BACKUP $ENV_FILE"
