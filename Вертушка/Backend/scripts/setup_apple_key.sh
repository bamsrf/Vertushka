#!/bin/bash
# ===========================================
# Заведение ключа Sign in with Apple (.p8) на проде
# ===========================================
# Отзыв токена при удалении аккаунта (App Store Guideline 5.1.1(v)) включается
# только когда заполнены ВСЕ четыре переменные: APPLE_CLIENT_ID, APPLE_TEAM_ID,
# APPLE_KEY_ID, APPLE_PRIVATE_KEY (см. apple_auth.is_configured). Иначе
# revoke_refresh_token молча возвращает False, а в review notes у нас написано,
# что отзыв работает — именно это расхождение ловят по 5.1.1(v).
#
# Запускать С МАКА (не на сервере): .p8 остаётся у тебя, на сервер уходит
# только содержимое, через stdin ssh — не через argv, чтобы ключ не светился
# в `ps` на сервере.
#
#   bash Backend/scripts/setup_apple_key.sh ~/Downloads/AuthKey_ABC1234567.p8 TEAMID1234 ABC1234567
#
# Идемпотентен: повторный запуск заменяет прежние строки, а не плодит дубли.
# ===========================================

set -euo pipefail

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

SERVER="${VERTUSHKA_SSH:-deploy@85.198.85.12}"

if [ $# -ne 3 ]; then
    echo "Использование: bash $0 <путь к AuthKey_XXXX.p8> <TEAM_ID> <KEY_ID>"
    echo ""
    echo "  TEAM_ID — developer.apple.com → Membership details (10 символов)"
    echo "  KEY_ID  — страница ключа, он же в имени файла AuthKey_<KEY_ID>.p8"
    exit 1
fi

P8_PATH="$1"
TEAM_ID="$2"
KEY_ID="$3"

# ─── Проверки до того, как трогать прод ────────────────────────────────
if [ ! -f "$P8_PATH" ]; then
    echo -e "${RED}❌ Файл не найден: $P8_PATH${NC}"
    exit 1
fi

if ! head -1 "$P8_PATH" | grep -q "BEGIN PRIVATE KEY"; then
    echo -e "${RED}❌ Это не похоже на .p8: первая строка без BEGIN PRIVATE KEY.${NC}"
    echo "   Нужен файл, скачанный из developer.apple.com → Keys."
    exit 1
fi

for pair in "TEAM_ID:$TEAM_ID" "KEY_ID:$KEY_ID"; do
    name="${pair%%:*}"; value="${pair#*:}"
    if ! printf '%s' "$value" | grep -qE '^[A-Z0-9]{10}$'; then
        echo -e "${YELLOW}⚠️  $name=\"$value\" не похож на идентификатор Apple"
        echo -e "   (ожидается 10 символов A-Z0-9). Проверь и запусти снова.${NC}"
        exit 1
    fi
done

echo "🔑 Ключ:    $(basename "$P8_PATH")"
echo "🏢 Team ID: $TEAM_ID"
echo "🆔 Key ID:  $KEY_ID"
echo "🖥  Сервер:  $SERVER"
echo ""

# ─── Однострочник PEM ───────────────────────────────────────────────────
# В .env многострочные значения не живут, а PEM без настоящих переносов не
# парсится — поэтому переносы экранируются как \n, а apple_auth._private_key_pem
# разворачивает их обратно.
PAYLOAD=$(
    printf 'APPLE_TEAM_ID=%s\n' "$TEAM_ID"
    printf 'APPLE_KEY_ID=%s\n' "$KEY_ID"
    printf 'APPLE_PRIVATE_KEY=%s\n' "$(awk '{printf "%s\\n", $0}' "$P8_PATH")"
)

# ─── Запись на сервер ───────────────────────────────────────────────────
printf '%s\n' "$PAYLOAD" | ssh "$SERVER" 'bash -s' <<'REMOTE'
set -euo pipefail
cd ~/vertushka/Вертушка/Backend

TMP=$(mktemp)
trap 'rm -f "$TMP" "$TMP.env"' EXIT
cat > "$TMP"

BACKUP=~/env.prod.bak.$(date +%Y%m%d_%H%M%S)
cp .env.prod "$BACKUP"
echo "   Бэкап: $BACKUP"

# Старые значения выкидываем — иначе при повторном запуске в файле окажется
# два APPLE_PRIVATE_KEY, и какое подхватит docker compose, зависит от порядка.
grep -vE '^(APPLE_TEAM_ID|APPLE_KEY_ID|APPLE_PRIVATE_KEY)=' .env.prod > "$TMP.env"
cat "$TMP" >> "$TMP.env"
mv "$TMP.env" .env.prod
chmod 600 .env.prod

if ! grep -q '^APPLE_CLIENT_ID=' .env.prod; then
    echo "   ⚠️  APPLE_CLIENT_ID отсутствует — добавь его (= com.vertushka.app),"
    echo "      без него is_configured() всё равно вернёт False."
fi
echo "   ✅ .env.prod обновлён"
REMOTE

echo ""
echo -e "${GREEN}✅ Переменные записаны.${NC}"
echo ""
echo -e "${YELLOW}Дальше — два шага:${NC}"
echo ""
echo "  1. Перезапустить контейнеры, чтобы они увидели окружение:"
echo "       ssh $SERVER 'bash ~/vertushka/Вертушка/Backend/scripts/deploy.sh'"
echo ""
echo "  2. Боевая проверка (нужен СВЕЖИЙ вход — refresh_token добывается только"
echo "     в момент логина, у вошедших раньше его нет):"
echo "       войти в приложении через Apple → удалить аккаунт →"
echo "       ssh $SERVER \"docker logs vertushka_api_blue --since 10m 2>&1 | grep apple_token_revoke\""
echo "     Ожидаемое: revoked=True"
