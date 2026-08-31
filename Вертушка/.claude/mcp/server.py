"""vertushka-docs MCP server.

FTS5-based retrieval over docs/plans/, ROADMAP.md, docs/BUGS.md.
Tools: search_docs, list_plans, get_section.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

from mcp.server.fastmcp import FastMCP

ROOT = Path(__file__).resolve().parents[2]
DB = Path(__file__).resolve().parent / "index.db"

mcp = FastMCP("vertushka-docs")


def _conn() -> sqlite3.Connection:
    return sqlite3.connect(DB)


@mcp.tool()
def search_docs(query: str, top_k: int = 5) -> list[dict]:
    """FTS5 search over project docs (plans, ROADMAP, BUGS, libraries research).

    Use this INSTEAD of reading whole files when you need to find something
    specific. Returns ranked chunks with file path, heading breadcrumb, and
    snippet. Pass FTS5 query syntax: phrases in quotes, AND/OR/NOT,
    column filters like 'heading:парсинг'.
    """
    if not DB.exists():
        return [
            {
                "error": (
                    "Index not built. Run from project root: "
                    "python .claude/mcp/indexer.py --full"
                )
            }
        ]
    try:
        with _conn() as conn:
            cur = conn.execute(
                """
                SELECT path,
                       heading,
                       snippet(docs, 2, '«', '»', ' … ', 24) AS snip,
                       bm25(docs) AS score
                FROM docs
                WHERE docs MATCH ?
                ORDER BY score
                LIMIT ?
                """,
                (query, top_k),
            )
            return [
                {
                    "path": path,
                    "heading": heading,
                    "snippet": snip,
                    "score": round(score, 3),
                }
                for path, heading, snip, score in cur.fetchall()
            ]
    except sqlite3.OperationalError as e:
        return [{"error": f"FTS5 query failed: {e}. Query was: {query!r}"}]


@mcp.tool()
def list_plans() -> list[dict]:
    """List all indexed doc files with chunk counts.

    Useful as a first step before search — gives you the corpus shape.
    """
    if not DB.exists():
        return [{"error": "Index not built. Run: python .claude/mcp/indexer.py --full"}]
    with _conn() as conn:
        cur = conn.execute(
            """
            SELECT path, COUNT(*) AS chunks
            FROM docs
            GROUP BY path
            ORDER BY path
            """
        )
        return [{"path": p, "chunks": c} for p, c in cur.fetchall()]


@mcp.tool()
def get_section(path: str, heading: str) -> str:
    """Return a specific section of a doc file by heading (case-insensitive substring).

    Path is relative to project root (e.g. 'docs/plans/market/PARSING.md' or 'ROADMAP.md').
    Heading is matched against the heading text (without #'s). Returns the section
    body including its own heading line, stopping at the next heading of equal or
    higher level.
    """
    p = ROOT / path
    if not p.exists():
        return f"File not found: {path}"
    try:
        text = p.read_text(encoding="utf-8")
    except OSError as e:
        return f"Read failed: {e}"

    target = heading.strip().lower()
    out: list[str] = []
    capturing = False
    start_level = 0

    for line in text.splitlines():
        stripped = line.lstrip()
        if stripped.startswith("#"):
            hashes = len(stripped) - len(stripped.lstrip("#"))
            title = stripped[hashes:].strip().lower()
            if capturing and hashes <= start_level:
                break
            if not capturing and target in title:
                capturing = True
                start_level = hashes
        if capturing:
            out.append(line)

    return "\n".join(out) if out else f"Section '{heading}' not found in {path}"


@mcp.tool()
def index_stats() -> dict:
    """Index health: number of files, chunks, last index time."""
    if not DB.exists():
        return {"status": "missing", "hint": "run: python .claude/mcp/indexer.py --full"}
    with _conn() as conn:
        files = conn.execute("SELECT COUNT(*) FROM files").fetchone()[0]
        chunks = conn.execute("SELECT COUNT(*) FROM docs").fetchone()[0]
        last = conn.execute("SELECT MAX(indexed_at) FROM files").fetchone()[0]
    return {"files": files, "chunks": chunks, "last_indexed_at": last}


if __name__ == "__main__":
    mcp.run()
