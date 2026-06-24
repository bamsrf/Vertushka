#!/bin/bash
# SessionEnd hook: захватывает текст чата в gbrain как страницу chat/YYYY-MM-DD-<id>.
# Чистый текст реплик (user+assistant), без tool-шума и thinking. Min-length guard.
# Не блокирует выход, тихо падает при любой ошибке.

set -e
INPUT=$(cat)

export PATH="$HOME/.bun/bin:$PATH"
command -v gbrain >/dev/null 2>&1 || { echo '{}'; exit 0; }

# portable timeout: macOS has no `timeout` by default (coreutils). Fall back gracefully.
if command -v gtimeout >/dev/null 2>&1; then TO="gtimeout 25";
elif command -v timeout >/dev/null 2>&1; then TO="timeout 25";
else TO=""; fi

EXTRACT=$(python3 - "$INPUT" <<'PY'
import json, sys, re, datetime

try:
    inp = json.loads(sys.argv[1])
except Exception:
    print("__SKIP__"); sys.exit(0)

path = inp.get("transcript_path", "")
sid  = (inp.get("session_id") or "nosess")[:8]
if not path:
    print("__SKIP__"); sys.exit(0)

SYSNOISE = re.compile(r"<system-reminder>.*?</system-reminder>", re.S)
CMD      = re.compile(r"<(command-name|command-message|command-args|local-command[^>]*)>.*?</\1>", re.S)

TRIM = 4000  # cap per turn; long code/tool dumps get trimmed, dialogue flow kept

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
                # real typed messages are plain strings; list content = tool_result -> skip
                if not isinstance(c, str):
                    continue
                txt = clean(c)
                if not txt or txt.startswith("<"):
                    continue
                turns.append(("User", txt))
            else:  # assistant: list of blocks, keep text only
                if not isinstance(c, list):
                    continue
                parts = [b.get("text", "") for b in c if isinstance(b, dict) and b.get("type") == "text"]
                txt = clean("\n".join(p for p in parts if p))
                if txt:
                    turns.append(("Claude", txt))
except Exception:
    print("__SKIP__"); sys.exit(0)

# need real dialogue: at least one user + some substance
if not any(r == "User" for r, _ in turns):
    print("__SKIP__"); sys.exit(0)

body = "\n\n".join(f"**{r}:** {txt}" for r, txt in turns)
if len(body) < 500:
    print("__SKIP__"); sys.exit(0)

today = datetime.date.today().isoformat()
slug = f"chat/{today}-{sid}"
front = (
    "---\n"
    f"title: Chat {today} ({sid})\n"
    "type: chat\n"
    "tags: [chat, vertushka, auto-capture]\n"
    f"date: {today}\n"
    "---\n\n"
)
out = front + body

import tempfile
fd, tmp = tempfile.mkstemp(prefix="gbrain-chat-", suffix=".md")
with open(fd, "w", encoding="utf-8") as fh:
    fh.write(out)
# emit "slug<TAB>tmppath" (bash cannot hold NUL in $(...))
sys.stdout.write(slug + "\t" + tmp)
PY
)

# __SKIP__ -> nothing to capture
case "$EXTRACT" in
  __SKIP__*|"") echo '{}'; exit 0 ;;
esac

SLUG="${EXTRACT%%$'\t'*}"
TMP="${EXTRACT#*$'\t'}"

if [ -n "$TMP" ] && [ -f "$TMP" ]; then
  $TO gbrain capture --file "$TMP" --type chat --slug "$SLUG" --quiet >/dev/null 2>&1 || true
  rm -f "$TMP"
fi

echo '{}'
