#!/bin/bash
# PostToolUse hook на Bash: после успешного git commit пишет timeline entry в gbrain.
# Это даёт долговременную память о том, какие изменения когда и почему делались.

set -e
INPUT=$(cat)

# Парсим что за команда выполнялась
COMMAND=$(echo "$INPUT" | python3 -c "import json,sys; d=json.load(sys.stdin); print(d.get('tool_input',{}).get('command',''))" 2>/dev/null)

# Срабатываем только на git commit (не на add/log/diff/status)
case "$COMMAND" in
  *"git commit"*)
    ;;
  *)
    echo '{}'
    exit 0
    ;;
esac

# Проверяем что коммит успешен (есть свежий HEAD коммит)
cd "$(dirname "$0")/../.." 2>/dev/null || { echo '{}'; exit 0; }

LAST_COMMIT_HASH=$(git rev-parse --short HEAD 2>/dev/null || echo "")
LAST_COMMIT_TIME=$(git log -1 --format=%ct 2>/dev/null || echo "0")
NOW=$(date +%s)

# Если последний коммит старше 60 секунд — наверное это не наш commit
if [ -z "$LAST_COMMIT_HASH" ] || [ $((NOW - LAST_COMMIT_TIME)) -gt 60 ]; then
  echo '{}'
  exit 0
fi

LAST_MSG=$(git log -1 --format=%s 2>/dev/null || echo "")
LAST_STAT=$(git show --stat --format= HEAD 2>/dev/null | tail -1 | xargs || echo "")
BRANCH=$(git branch --show-current 2>/dev/null || echo "?")
TODAY=$(date +%Y-%m-%d)

# Записываем в gbrain timeline (не блокируем если упало)
export PATH="$HOME/.bun/bin:$PATH"
# portable timeout: macOS has no `timeout` by default (coreutils).
if command -v gtimeout >/dev/null 2>&1; then TO="gtimeout 5";
elif command -v timeout >/dev/null 2>&1; then TO="timeout 5";
else TO=""; fi
if command -v gbrain >/dev/null 2>&1; then
  # Используем timeline-add: slug = ветка, дата = сегодня, текст = сообщение + статистика
  ENTRY="[$LAST_COMMIT_HASH] $LAST_MSG ($LAST_STAT)"
  $TO gbrain timeline-add "branch-$BRANCH" "$TODAY" "$ENTRY" >/dev/null 2>&1 || true
fi

echo '{}'
