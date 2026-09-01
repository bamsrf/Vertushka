# CONTEXT_LAYER_V1 — Локальный retrieval-слой для Claude Code

> Цель: сэкономить токены и держать Claude в контексте Вертушки между сессиями.
> Дата: 2026-05-19

---

## Проблема
1. Два `CLAUDE.md` (root + project) дублируются → ~2-3K токенов впустую на старте.
2. `vertushka_project.md` в памяти сухой — нет текущего milestone, фокусов, граблей.
3. Планы (`docs/plans/*.md`, 36+ файлов) перечитываются с нуля каждую сессию.
4. Дельта между сессиями (что изменилось в коде/планах) теряется.

## Решение (4 точки)
1. **Консолидация CLAUDE.md** — root слим до навигатора между PACE/Вертушка, всё специфичное → в project CLAUDE.md.
2. **Обогащение memory** — `vertushka_project.md` дополнить: текущий milestone, активные фокусы, грабли (IP dev API, prod deploy), ключевые архитектурные решения.
3. **MCP retrieval-слой** — SQLite FTS5 поверх `docs/plans/`, `ROADMAP.md`, `docs/BUGS.md`. Запрашиваем чанки вместо чтения файлов целиком.
4. **Auto-reindex + /v-context** — post-commit hook реиндексирует изменённые .md; slash-команда `/v-context` отдаёт снапшот состояния за один tool call.

## Стек
- Python 3.12 (stdlib `sqlite3` с FTS5)
- `mcp` SDK (pip)
- Bash post-commit hook
- `.mcp.json` для project-scoped регистрации

## Структура файлов
```
.claude/
├── mcp/
│   ├── server.py           # MCP entrypoint (FastMCP)
│   ├── indexer.py          # FTS5 builder/updater
│   ├── requirements.txt
│   ├── .venv/              # gitignored
│   └── index.db            # gitignored
├── commands/
│   └── v-context.md        # slash-команда
└── settings.local.json     # как было
.mcp.json                   # project-scoped MCP config
.git/hooks/post-commit      # auto-reindex
```

## MCP API
- `search_docs(query: str, top_k: int = 5)` — FTS5-поиск по чанкам, возвращает `[{path, heading, snippet, score}]`.
- `list_plans()` — список всех `docs/plans/*.md` + ROADMAP + BUGS.
- `get_section(path: str, heading: str)` — точечный фрагмент по заголовку.

## Slash-команда `/v-context`
Снапшот за один tool call:
- текущая ветка + последние 5 коммитов
- топ ROADMAP (1-50 строк) + активный milestone
- кол-во планов в `docs/plans/`
- статистика FTS-индекса
- открытые баги из `docs/BUGS.md`

## Чанкование
Markdown → split по `##`, при необходимости по `###`. Чанки до 2500 символов. Если больше — нарезка по параграфам. Heading стек хранится в `breadcrumb` (`H2 > H3`).

## Tokenizer FTS5
`unicode61 remove_diacritics 2` — нормальная работа с русским (без стемминга, но кириллица и латиница ок).

## Чек-лист готовности
- [x] План зафиксирован (этот документ)
- [ ] `CLAUDE.md` (root) сжат до навигатора
- [ ] `vertushka_project.md` (memory) обогащён
- [ ] `.claude/mcp/server.py` + `indexer.py` написаны
- [ ] `mcp` установлен в `.claude/mcp/.venv/`
- [ ] Индекс собран (`indexer.py --full`)
- [ ] `search_docs` возвращает результаты
- [ ] `.mcp.json` подхватывается Claude Code
- [ ] post-commit hook реиндексирует изменённые .md
- [ ] `/v-context` работает

## Что НЕ делаем (out of scope V1)
- Embeddings / semantic search (FTS5 хватит для соло-проекта).
- Граф связей между планами (можно дописать в V2 как `links` колонку).
- UI / dashboard (только CLI + MCP).
- Кросс-проектный индекс (только Вертушка; PACE при желании — копия).
