#!/usr/bin/env python3
"""One-shot backfill: past Claude-Code transcripts -> ~/.gbrain/chat-queue/.

Same extraction as capture-chat-to-gbrain.sh (clean text, trim @4k, >500 guard),
but walks an existing project transcript dir instead of a single SessionEnd.
The nightly drain (drain-chat-queue.sh) then captures the queue into gbrain.

Usage:
  backfill-chats-to-queue.py [TRANSCRIPT_DIR]
Defaults to the Вертушка project transcript dir.
"""
import json, os, re, sys, datetime, tempfile, glob

HOME = os.path.expanduser("~")
DEFAULT_DIR = os.path.join(
    HOME, ".claude/projects/-Users-vladislavrumancev-Desktop-Cursor---------"
)
TDIR = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_DIR
QUEUE = os.path.join(HOME, ".gbrain/chat-queue")
DONE = os.path.join(QUEUE, "processed")

SYSNOISE = re.compile(r"<system-reminder>.*?</system-reminder>", re.S)
CMD = re.compile(r"<(command-name|command-message|command-args|local-command[^>]*)>.*?</\1>", re.S)
TRIM = 4000

def clean(t):
    t = CMD.sub("", SYSNOISE.sub("", t)).strip()
    return t[:TRIM] + "\n…[trimmed]" if len(t) > TRIM else t

def extract(path):
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
                    x = clean(c)
                    if x and not x.startswith("<"):
                        turns.append(("User", x))
                else:
                    if not isinstance(c, list):
                        continue
                    x = clean("\n".join(b.get("text", "") for b in c
                                        if isinstance(b, dict) and b.get("type") == "text"))
                    if x:
                        turns.append(("Claude", x))
    except Exception:
        return None
    if not any(r == "User" for r, _ in turns):
        return None
    body = "\n\n".join(f"**{r}:** {t}" for r, t in turns)
    return body if len(body) >= 500 else None

def main():
    if not os.path.isdir(TDIR):
        print(f"transcript dir not found: {TDIR}")
        sys.exit(1)
    os.makedirs(QUEUE, exist_ok=True)
    os.makedirs(DONE, exist_ok=True)
    files = sorted(glob.glob(os.path.join(TDIR, "*.jsonl")))  # top-level only, skip subagents/
    queued = skipped = empty = 0
    for path in files:
        sid = os.path.splitext(os.path.basename(path))[0][:8]
        date = datetime.date.fromtimestamp(os.path.getmtime(path)).isoformat()
        fname = f"chat-{date}-{sid}.md"
        if os.path.exists(os.path.join(QUEUE, fname)) or os.path.exists(os.path.join(DONE, fname)):
            skipped += 1
            continue
        body = extract(path)
        if not body:
            empty += 1
            continue
        front = (f"---\ntitle: Chat {date} ({sid})\ntype: chat\n"
                 f"tags: [chat, vertushka, auto-capture, backfill]\ndate: {date}\n---\n\n")
        fd, tmp = tempfile.mkstemp(dir=QUEUE, prefix=".tmp-", suffix=".md")
        with open(fd, "w", encoding="utf-8") as fh:
            fh.write(front + body)
        os.replace(tmp, os.path.join(QUEUE, fname))
        queued += 1
    print(f"backfill done: {queued} queued, {skipped} already-present, {empty} empty/short "
          f"({len(files)} transcripts scanned in {TDIR})")

if __name__ == "__main__":
    main()
