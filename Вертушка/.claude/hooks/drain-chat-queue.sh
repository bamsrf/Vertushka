#!/bin/bash
# Дренит ~/.gbrain/chat-queue/*.md в gbrain (capture), затем gbrain dream.
# Запускается по расписанию (launchd com.vertushka.gbrain-dream).
# Lock-aware: если PGLite занят живым MCP `serve` — первый же lock-timeout
# прерывает прогон, файлы остаются в очереди до следующего раза. Идемпотентно
# (capture дедупит по content_hash). Не киллит ничего — нулевой риск corruption.

set -e
export PATH="$HOME/.bun/bin:$PATH"
command -v gbrain >/dev/null 2>&1 || exit 0

# brain resolution: gbrain `dream` needs explicit --dir (doesn't read config.json
# CWD-relative). Pass BRAIN to all gbrain calls so it works under launchd (CWD=`/`).
cd "$HOME/.gbrain" 2>/dev/null || true
BRAIN="$HOME/.gbrain/brain.pglite"

QUEUE_DIR="$HOME/.gbrain/chat-queue"
DONE_DIR="$QUEUE_DIR/processed"
LOG="$HOME/.gbrain/drain.log"

# portable timeout (macOS has no `timeout`).
if command -v gtimeout >/dev/null 2>&1; then TO="gtimeout 30";
elif command -v timeout >/dev/null 2>&1; then TO="timeout 30";
else TO=""; fi

ts() { date '+%Y-%m-%d %H:%M:%S'; }

# nothing queued -> still run dream below
mkdir -p "$DONE_DIR"

captured=0
locked=0
shopt -s nullglob
for f in "$QUEUE_DIR"/chat-*.md; do
  base=$(basename "$f" .md)            # chat-<date>-<sid>
  slug="chat/${base#chat-}"            # chat/<date>-<sid>
  OUT=$($TO gbrain capture --file "$f" --type chat --slug "$slug" --quiet 2>&1) || true
  if printf '%s' "$OUT" | grep -qi "lock"; then
    echo "$(ts) LOCK busy, deferring queue ($f)" >> "$LOG"
    locked=1
    break                              # serve holds lock; stop, retry next run
  fi
  # success (or idempotent re-capture) -> archive
  mv "$f" "$DONE_DIR/" 2>/dev/null || true
  captured=$((captured+1))
done

[ "$captured" -gt 0 ] && echo "$(ts) captured $captured chat(s)" >> "$LOG"

# consolidation: only if lock was free this run
if [ "$locked" -eq 0 ]; then
  $TO gbrain dream --dir "$BRAIN" >> "$LOG" 2>&1 || echo "$(ts) dream skipped (lock/err)" >> "$LOG"
fi

exit 0
