---
description: Снапшот текущего состояния Вертушки — branch, последние коммиты, активный milestone, состояние FTS-индекса
---

Собери снапшот контекста проекта Вертушка за один проход. Выполни параллельно:

1. `git -C /Users/vladislavrumancev/Cursor/Вертушка branch --show-current`
2. `git -C /Users/vladislavrumancev/Cursor/Вертушка log --oneline -7`
3. `git -C /Users/vladislavrumancev/Cursor/Вертушка status --short`
4. Read `/Users/vladislavrumancev/Cursor/Вертушка/ROADMAP.md` (offset=0, limit=60) — топ + активный milestone
5. Через MCP `vertushka-docs.index_stats()` — состояние FTS-индекса (или fallback: `bash -lc 'cd /Users/vladislavrumancev/Cursor/Вертушка && .claude/mcp/.venv/bin/python .claude/mcp/indexer.py --stats'`)
6. `bash -lc 'ls /Users/vladislavrumancev/Cursor/Вертушка/docs/plans/*.md | wc -l'` — кол-во планов
7. Read `/Users/vladislavrumancev/Cursor/Вертушка/docs/BUGS.md` (offset=0, limit=80) — открытые баги

Выведи коротко, в формате:

```
🎯 Branch: <branch>
📍 Milestone: <текущий из ROADMAP, одной строкой>
📦 Планов: <N>
🔍 Индекс: <files=… chunks=… last_indexed_at=…>

📜 Последние коммиты:
  <hash> <subject>
  ...

🔧 Git status:
  <короткий список или "чисто">

🐛 Открытые баги:
  <выжимка из BUGS.md, не более 5 строк>
```

Без воды, только факты. Если FTS-индекс пустой — подскажи команду `bash -lc 'cd /Users/vladislavrumancev/Cursor/Вертушка && .claude/mcp/.venv/bin/python .claude/mcp/indexer.py --full'`.
