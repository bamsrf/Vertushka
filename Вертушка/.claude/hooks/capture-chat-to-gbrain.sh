#!/bin/bash
# SessionEnd hook: пишет чистый текст чата ФАЙЛОМ в очередь ~/.gbrain/chat-queue/.
# НЕ трогает gbrain напрямую (PGLite single-writer lock конфликтует с живым MCP `serve`).
# Очередь дренит drain-chat-queue.sh по расписанию (launchd), когда lock свободен.
# Чистый текст реплик (user+assistant), без thinking/tool-шума. Trim @4k. Min-length guard.

set -e
INPUT=$(cat)

QUEUE_DIR="$HOME/.gbrain/chat-queue"

# Keep the launchd-run drain copy in sync with this repo's version.
# launchd (background agent) can't read ~/Desktop (macOS TCC), so the drain
# script must live outside it; this hook (run by Claude Code with the user's
# perms) refreshes that copy each session. Repo stays the source of truth.
HOOK_DIR="$(cd "$(dirname "$0")" && pwd)"
if [ -f "$HOOK_DIR/drain-chat-queue.sh" ]; then
  mkdir -p "$HOME/.gbrain"
  cp "$HOOK_DIR/drain-chat-queue.sh" "$HOME/.gbrain/drain-chat-queue.sh" 2>/dev/null || true
  chmod +x "$HOME/.gbrain/drain-chat-queue.sh" 2>/dev/null || true
fi

python3 - "$INPUT" "$QUEUE_DIR" <<'PY'
import json, sys, re, datetime, os, tempfile

try:
    inp = json.loads(sys.argv[1])
except Exception:
    sys.exit(0)
queue_dir = sys.argv[2]

path = inp.get("transcript_path", "")
sid  = (inp.get("session_id") or "nosess")[:8]
if not path or not os.path.exists(path):
    sys.exit(0)

SYSNOISE = re.compile(r"<system-reminder>.*?</system-reminder>", re.S)
CMD      = re.compile(r"<(command-name|command-message|command-args|local-command[^>]*)>.*?</\1>", re.S)
TRIM = 4000

def clean(t: str) -> str:
    t = SYSNOISE.sub("", t)
    t = CMD.sub("", t)
    t = t.strip()
    if len(t) > TRIM:
        t = t[:TRIM] + "\n…[trimmed]"
    return t

turns = []
try:
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                d = json.loads(line)
            except Exception:
                continue
            t = d.get("type")
            if t not in ("user", "assistant"):
                continue
            c = d.get("message", {}).get("content")
            if t == "user":
                if not isinstance(c, str):
                    continue
                txt = clean(c)
                if not txt or txt.startswith("<"):
                    continue
                turns.append(("User", txt))
            else:
                if not isinstance(c, list):
                    continue
                parts = [b.get("text", "") for b in c if isinstance(b, dict) and b.get("type") == "text"]
                txt = clean("\n".join(p for p in parts if p))
                if txt:
                    turns.append(("Claude", txt))
except Exception:
    sys.exit(0)

if not any(r == "User" for r, _ in turns):
    sys.exit(0)

body = "\n\n".join(f"**{r}:** {txt}" for r, txt in turns)
if len(body) < 500:
    sys.exit(0)

today = datetime.date.today().isoformat()
front = (
    "---\n"
    f"title: Chat {today} ({sid})\n"
    "type: chat\n"
    "tags: [chat, vertushka, auto-capture]\n"
    f"date: {today}\n"
    "---\n\n"
)
out = front + body

os.makedirs(queue_dir, exist_ok=True)
# filename encodes slug: chat-<date>-<sid>.md  ->  slug chat/<date>-<sid>
fname = f"chat-{today}-{sid}.md"
dest = os.path.join(queue_dir, fname)
# atomic write
fd, tmp = tempfile.mkstemp(dir=queue_dir, prefix=".tmp-", suffix=".md")
with open(fd, "w", encoding="utf-8") as fh:
    fh.write(out)
os.replace(tmp, dest)
PY

echo '{}'
