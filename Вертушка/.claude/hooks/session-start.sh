#!/bin/bash
# SessionStart hook: пульс проекта при старте сессии.
# Инжектится в контекст БЕСПЛАТНО (system reminder), не из твоих токенов.

set -e
cd "$(dirname "$0")/../.." 2>/dev/null || exit 0

export PATH="$HOME/.bun/bin:$PATH"

# Быстрый snapshot: branch, recent commits, dirty status, gbrain inbox
BRANCH=$(git branch --show-current 2>/dev/null || echo "?")
LAST_3_COMMITS=$(git log --oneline -3 2>/dev/null | head -3)
DIRTY=$(git status --short 2>/dev/null | head -10)
DIRTY_COUNT=$(git status --short 2>/dev/null | wc -l | tr -d ' ')

# gbrain stats (не блокируем если упало)
# portable timeout: macOS has no `timeout` by default (coreutils).
if command -v gtimeout >/dev/null 2>&1; then TO="gtimeout 3";
elif command -v timeout >/dev/null 2>&1; then TO="timeout 3";
else TO=""; fi
GBRAIN_STATS=""
if command -v gbrain >/dev/null 2>&1; then
  STATS=$($TO gbrain stats 2>/dev/null | grep -E "(pages|inbox)" | head -3 || echo "")
  if [ -n "$STATS" ]; then
    GBRAIN_STATS=$'\n\ngbrain:\n'"$STATS"
  fi
fi

# Сборка summary
SUMMARY="Project pulse @ $(date +%H:%M)
branch: $BRANCH
dirty files: $DIRTY_COUNT
last commits:
$LAST_3_COMMITS"

if [ "$DIRTY_COUNT" -gt 0 ] && [ "$DIRTY_COUNT" -lt 15 ]; then
  SUMMARY="$SUMMARY

uncommitted:
$DIRTY"
fi

SUMMARY="$SUMMARY$GBRAIN_STATS"

# Экранирование для JSON
ESCAPED=$(printf '%s' "$SUMMARY" | python3 -c "import json,sys; print(json.dumps(sys.stdin.read()))")

cat <<EOF
{
  "hookSpecificOutput": {
    "hookEventName": "SessionStart",
    "additionalContext": $ESCAPED
  }
}
EOF
