"""FTS5 indexer for Вертушка docs.

Usage:
    python .claude/mcp/indexer.py --full        # rebuild from scratch
    python .claude/mcp/indexer.py --files A B   # reindex specific files (rel paths)
    python .claude/mcp/indexer.py --stats       # show counts
"""
from __future__ import annotations

import re
import sqlite3
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DB = Path(__file__).resolve().parent / "index.db"

INDEX_FILES = [
    "ROADMAP.md",
    "README.md",
    "docs/BUGS.md",
    "docs/ВЕРТУШКА_LIBRARIES_RESEARCH.md",
    "docs/СТРУКТУРА_ПРОЕКТА.md",
]
INDEX_GLOBS = ["docs/plans/*.md", "docs/plans/*/*.md"]

MAX_CHUNK = 2500
HEADING_RE = re.compile(r"^(#{1,4})\s+(.+?)\s*$")


def _conn() -> sqlite3.Connection:
    DB.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB)
    conn.execute(
        """
        CREATE VIRTUAL TABLE IF NOT EXISTS docs USING fts5(
            path UNINDEXED,
            heading,
            body,
            tokenize = 'unicode61 remove_diacritics 2'
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS files (
            path TEXT PRIMARY KEY,
            mtime REAL,
            indexed_at REAL
        )
        """
    )
    return conn


def _chunks_for(text: str) -> list[tuple[str, str]]:
    """Split markdown into (heading_breadcrumb, body) chunks.

    Splits on H1-H3 headings. Bodies over MAX_CHUNK chars are further split
    on paragraph boundaries.
    """
    lines = text.splitlines()
    chunks: list[tuple[str, str]] = []
    stack: list[tuple[int, str]] = []  # (level, title)
    buf: list[str] = []

    def flush() -> None:
        nonlocal buf
        body = "\n".join(buf).strip()
        buf = []
        if not body:
            return
        breadcrumb = " > ".join(t for _, t in stack) or "(intro)"
        if len(body) <= MAX_CHUNK:
            chunks.append((breadcrumb, body))
            return
        # split big chunks by paragraph
        cur: list[str] = []
        cur_len = 0
        for para in body.split("\n\n"):
            if cur and cur_len + len(para) > MAX_CHUNK:
                chunks.append((breadcrumb, "\n\n".join(cur)))
                cur, cur_len = [para], len(para)
            else:
                cur.append(para)
                cur_len += len(para) + 2
        if cur:
            chunks.append((breadcrumb, "\n\n".join(cur)))

    for line in lines:
        m = HEADING_RE.match(line)
        if m and len(m.group(1)) <= 3:
            level = len(m.group(1))
            title = m.group(2).strip()
            flush()
            stack[:] = [(l, t) for l, t in stack if l < level]
            stack.append((level, title))
            buf.append(line)
        else:
            buf.append(line)
    flush()
    return chunks


def _resolve_targets() -> list[str]:
    out: list[str] = []
    for rel in INDEX_FILES:
        if (ROOT / rel).exists():
            out.append(rel)
    for pat in INDEX_GLOBS:
        for p in sorted(ROOT.glob(pat)):
            out.append(str(p.relative_to(ROOT)))
    return out


def index_one(conn: sqlite3.Connection, rel: str) -> int:
    """(Re)index a single file. Returns chunk count. Removes from index if missing."""
    abs_p = ROOT / rel
    conn.execute("DELETE FROM docs WHERE path = ?", (rel,))
    if not abs_p.exists():
        conn.execute("DELETE FROM files WHERE path = ?", (rel,))
        return 0
    try:
        text = abs_p.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return 0
    chunks = _chunks_for(text)
    conn.executemany(
        "INSERT INTO docs (path, heading, body) VALUES (?, ?, ?)",
        [(rel, h, b) for h, b in chunks],
    )
    conn.execute(
        "INSERT OR REPLACE INTO files (path, mtime, indexed_at) VALUES (?, ?, ?)",
        (rel, abs_p.stat().st_mtime, time.time()),
    )
    return len(chunks)


def _is_indexable(rel: str) -> bool:
    if rel in INDEX_FILES:
        return True
    return any(Path(rel).match(g) for g in INDEX_GLOBS)


def main(argv: list[str]) -> int:
    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__)
        return 0
    conn = _conn()
    if argv[0] == "--full":
        conn.execute("DELETE FROM docs")
        conn.execute("DELETE FROM files")
        targets = _resolve_targets()
        total = 0
        for rel in targets:
            total += index_one(conn, rel)
        conn.commit()
        print(f"Indexed {len(targets)} files, {total} chunks → {DB}")
        return 0
    if argv[0] == "--files":
        targets = [t for t in argv[1:] if _is_indexable(t)]
        skipped = [t for t in argv[1:] if not _is_indexable(t)]
        total = 0
        for rel in targets:
            total += index_one(conn, rel)
        conn.commit()
        msg = f"Reindexed {len(targets)} files, {total} chunks"
        if skipped:
            msg += f" (skipped {len(skipped)} non-indexable)"
        print(msg)
        return 0
    if argv[0] == "--stats":
        files = conn.execute("SELECT COUNT(*) FROM files").fetchone()[0]
        chunks = conn.execute("SELECT COUNT(*) FROM docs").fetchone()[0]
        last = conn.execute("SELECT MAX(indexed_at) FROM files").fetchone()[0]
        print(f"files={files} chunks={chunks} last_indexed_at={last}")
        return 0
    print(f"Unknown command: {argv[0]}")
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
