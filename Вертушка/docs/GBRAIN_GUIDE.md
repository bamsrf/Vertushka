# Гайд: gbrain для Вертушки

> **Кому это:** тебе и любому Claude-сессии, работающей с проектом. Объясняет что лежит в локальном «мозге», как им пользоваться и куда не лазить.

## TL;DR

- **gbrain** — локальная база знаний на PGLite (`~/.gbrain/brain.pglite`), куда засинкан весь markdown проекта (ROADMAP, планы, бриф, баги, runbooks).
- Доступ только через **MCP-инструменты `mcp__gbrain__*`** (внутри Claude). CLI `gbrain ...` сейчас не работает из-за PGLite-лока.
- **Семантика выключена** (нет embeddings). Работает FTS (keyword) — этого хватает для 90% сценариев.
- Обновлять: команда `/v-sync` (раз в день или после серии новых планов).

---

## 1. Что внутри (на 2026-05-26)

- **127 страниц / 1114 чанков** из markdown'а в `Cursor/` (git-root репозитория). Из них целевые для Вертушки:
  - `roadmap` ← `ROADMAP.md`
  - `readme` ← `README.md`
  - `claude` ← `CLAUDE.md` (навигатор)
  - `docs/bugs` ← `docs/BUGS.md`
  - `docs/plans/*` (~46 планов) — главное содержимое
  - `docs/briefs/*`, `docs/runbooks/*`, `docs/dev/*`
  - `mobile/*`, `mobile/docs/plans/*` — мобильные планы
  - `docs/_libraries_research` ← Deep Research по библиотекам
- **Соседние проекты** (PACE, Timestripe, rork-pace-app, boost-variations, yandex-jobs-bot) — тоже в брейне. Это by design (один brain на всё), фильтруй по slug-префиксу когда нужна именно Вертушка.

**Что НЕ попало (и не должно):**
- Код (`.py`, `.ts`, `.tsx`) — gbrain индексирует только markdown.
- `node_modules/`, `dist/`, `.expo/` — пропускаются.
- `Backend/venv/*/LICENSE` — удалены руками, при будущем sync вернутся, `/v-sync` чистит.

---

## 2. Чем gbrain отличается от `vertushka-docs` MCP

В проекте уже есть **второй retrieval-слой** — `vertushka-docs` (FTS5 поиск, см. `docs/plans/quality/CONTEXT_LAYER_V1.md`). Они не дублируют друг друга:

| | `vertushka-docs` | `gbrain` |
|---|---|---|
| Что индексирует | только `docs/plans/`, `ROADMAP.md`, `docs/BUGS.md` | весь markdown в репо + соседи |
| Поиск | FTS5 SQLite, точные термы | FTS + multi-query expansion + (опц.) embeddings |
| Граф связей | нет | да: `get_backlinks`, `traverse_graph` |
| Tags/Timeline | нет | да |
| Долговременная память | нет, тупо индекс | да: takes, facts, supersessions |
| Сценарий | «дай мне раздел про парсинг» | «что мы решили про монетизацию», «кто ссылается на этот план» |

**Когда что:**
- Хочешь найти **конкретный раздел/абзац плана** → `vertushka-docs` (`search_docs`, `get_section`).
- Хочешь **подытожить тему** через несколько планов, найти связи, узнать историю → `gbrain` (`query`, `think`).
- Хочешь **граф зависимостей плана** или backlinks → `gbrain`.

---

## 3. Базовые сценарии

### 3.1 Просто найти что-то

```
mcp__gbrain__search(query="rarity badges", limit=5)
```
Возвращает чанки с подсветкой релевантности. Хорошо для точных терминов.

```
mcp__gbrain__query(query="как мы планируем монетизировать", limit=5)
```
Multi-query expansion: автоматически переформулирует запрос, лучше работает на смысловых вопросах.

### 3.2 Прочитать страницу целиком

```
mcp__gbrain__get_page(slug="docs/plans/plan_notifications_v2")
```
Slug = путь без `Вертушка/` и без `.md`, в нижнем регистре. Если забыл — `mcp__gbrain__resolve_slugs(partial="notif")`.

### 3.3 Граф: кто ссылается на план

```
mcp__gbrain__get_backlinks(slug="docs/plans/plan_p2p_marketplace")
```
Сейчас вернёт 0 (линки не извлечены), но после первого `gbrain link` или auto-link prepass — будет жить.

### 3.4 Сложный вопрос с синтезом

```
mcp__gbrain__think(
  question="Что должно быть готово до релиза iOS?",
  anchor="docs/plans/plan_release_v2"
)
```
LLM-проход по релевантным чанкам с цитированием. Дороже остальных вызовов (модель), но даёт связный ответ.

### 3.5 Что недавно менялось

```
mcp__gbrain__list_pages(sort="updated_desc", limit=10)
mcp__gbrain__get_recent_salience(days=14, slugPrefix="docs/plans")
```

### 3.6 Сиротские планы (без входящих ссылок)

```
mcp__gbrain__find_orphans()
```
Полезно для гигиены: если план никто не упоминает — либо забыт, либо нужен бэк-линк.

---

## 4. Slug-conventions Вертушки

Sync режет префикс `Вертушка/` и приводит к lower-case:

| Файл | Slug |
|---|---|
| `Вертушка/ROADMAP.md` | `roadmap` |
| `Вертушка/README.md` | `readme` |
| `Вертушка/CLAUDE.md` | `claude` |
| `Вертушка/docs/BUGS.md` | `docs/bugs` |
| `Вертушка/docs/plans/social/PLAN_NOTIFICATIONS_V2.md` | `docs/plans/plan_notifications_v2` |
| `Вертушка/Mobile/docs/plans/PLAN_FOLDERS.md` | `mobile/docs/plans/plan_folders` |
| `Вертушка/docs/runbooks/discogs-dump-ingest.md` | `docs/runbooks/discogs-dump-ingest` |

Файлы с кириллицей в имени получают пустой/обрезанный slug — например, `ПЛАН_РЕФАКТОРИНГА_*.md` → `docs/plans/____`. По возможности именуй планы латиницей.

---

## 5. Sync — поддерживать в актуальном состоянии

### Быстро (рекомендуется)

В Claude Code набери:
```
/v-sync
```
Команда лежит в `.claude/commands/v-sync.md`. Делает:
1. Инкрементальный `mcp__gbrain__sync_brain` (видит diff по git с прошлого sync).
2. Чистит мусор, если вернулся `backend/venv/*` или `node_modules/*`.
3. Выводит одну строку: `🧠 gbrain: +3 ✎1 -0, всего 130 страниц`.

### Когда запускать
- После создания/правки плана и `git commit`.
- Раз в день автоматически — пока нельзя (Claude scheduled-tasks требуют интерактивного approve). Если очень нужно — настрой launchd-агент на `gbrain sync` **в момент когда Claude закрыт**, иначе PGLite-лок.

### Полный пере-сbnk (если что-то сломалось)
```
mcp__gbrain__sync_brain(repo="/Users/vladislavrumancev/Desktop/Cursor", no_embed=true, no_pull=false)
```
С `full: true` — переиндексирует всё с нуля.

---

## 6. Embeddings — когда и как включать

Сейчас в `~/.gbrain/config.json`:
```json
{ "embedding_disabled": true }
```

Это значит: `query` и `search` работают **только по тексту** (BM25/tsvector). Score'ы могут быть низкими если запрос не совпадает токенами с текстом. Для семантики:

1. Получить OpenAI API key (есть лимит, ~$0.02 на 1М токенов для `text-embedding-3-small`).
2. ```bash
   export OPENAI_API_KEY=sk-...
   gbrain config set embedding_disabled false
   gbrain config set embedding_model openai:text-embedding-3-small
   ```
3. Перегенерить:
   ```
   mcp__gbrain__submit_job(name="embed", data={"all": true})
   ```
   или CLI `gbrain embed --all` (когда MCP не активен).

После этого `query` начинает мёрджить keyword + vector через RRF — релевантность на смысловых запросах резко вырастет.

**Когда стоит включать:** если ловишь себя на том, что точный термин не помнишь, а помнишь смысл («там был план про подсветку редких пластинок, как это называлось»). Без embeddings такие запросы дают слабые результаты.

---

## 7. Линки и теги (мощная, но ручная фича)

Связи между страницами сейчас пустые (0 link_count). Если хочешь раскрыть граф:

```
mcp__gbrain__add_link(
  from="docs/plans/plan_release_v2",
  to="docs/plans/plan_notifications_v2",
  link_type="blocks"
)
```

Поддерживаемые типы — любые строки; полезные: `blocks`, `blocked_by`, `supersedes`, `relates_to`, `depends_on`.

Теги — то же, плоский namespace:
```
mcp__gbrain__add_tag(slug="docs/plans/plan_p2p_marketplace", tag="monetization")
mcp__gbrain__add_tag(slug="docs/plans/plan_monetization", tag="monetization")
mcp__gbrain__list_pages(tag="monetization")
```

Стоит ли возиться? — Если планов больше 50 и ты часто ищешь «всё про вишлисты» / «всё что блокирует релиз» — да. Иначе оставь.

---

## 8. Troubleshooting

### `GBrain: Timed out waiting for PGLite lock`
Лок держит MCP-сервер (`gbrain serve`). Используй MCP-инструменты внутри Claude, не CLI. Если очень нужен CLI — закрой Claude Code, сделай дело, запусти заново.

### Sync `Not a git repository: Вертушка`
Гит-корень — `Cursor/`, а не `Вертушка/`. Передавай `repo=/Users/vladislavrumancev/Desktop/Cursor`. В `/v-sync` это уже зашито.

### Поиск не находит свежий план
Запусти `/v-sync` — индекс отстал. Проверь свежесть: `mcp__gbrain__get_brain_identity()` → `last_sync_iso`.

### Появились пустые `LICENSE`-страницы в результатах
Это `Backend/venv/...` LICENSE-файлы вернулись после sync. Удаляй вручную через `mcp__gbrain__delete_page(slug="...")` или жди когда `/v-sync` это сделает сам.

### Slug плана с кириллицей сломан (`docs/plans/____`)
Переименуй файл на латиницу + сделай sync. Старая запись с битым slug-ом останется до явного `delete_page`.

### `mcp__gbrain__whoami` падает с `unknown_transport`
Известный баг MCP-транспорта в v0.41.4.0 — игнорируй, остальные инструменты работают.

---

## 9. Что НЕ делать

- ❌ **Не клади в gbrain personal stuff** — это командный/проектный brain. Личные заметки → `recall`/`extract_facts` отдельной сессией.
- ❌ **Не вызывай `gbrain init` / `migrate`** — потеряешь brain.
- ❌ **Не запускай `gbrain sync` из CLI пока Claude открыт** — упрёшься в лок и решишь что всё сломано.
- ❌ **Не удаляй `~/.gbrain/`** — там вся база.
- ❌ **Не индексируй venv/node_modules** — мусор. Если sync их затащил, чисти через `delete_page`.

---

## 10. Quick reference (cheat-sheet)

```
# Поиск
mcp__gbrain__search(query, limit=5)       # быстрый keyword
mcp__gbrain__query(query, limit=5)        # гибрид + expansion (лучше)
mcp__gbrain__think(question, anchor=...)  # LLM-синтез с цитатами

# Чтение
mcp__gbrain__get_page(slug)
mcp__gbrain__resolve_slugs(partial)       # «как звучит slug?»
mcp__gbrain__list_pages(sort, tag, type, limit)

# Граф / гигиена
mcp__gbrain__get_backlinks(slug)
mcp__gbrain__traverse_graph(slug, depth)
mcp__gbrain__find_orphans()
mcp__gbrain__get_recent_salience(days)

# Обслуживание
/v-sync                                   # инкрементальный sync + чистка
mcp__gbrain__get_brain_identity()         # версия + last_sync
mcp__gbrain__get_stats()                  # счётчики
mcp__gbrain__delete_page(slug)            # soft-delete (recover 72ч)
mcp__gbrain__restore_page(slug)
```

---

## 11. Связанные документы

- [CONTEXT_LAYER_V1](docs/plans/quality/CONTEXT_LAYER_V1.md) — соседний retrieval-слой (`vertushka-docs` MCP)
- [.claude/commands/v-sync.md](.claude/commands/v-sync.md) — slash-команда sync
- [.claude/commands/v-context.md](.claude/commands/v-context.md) — снапшот состояния проекта
- `~/.gbrain/config.json` — конфиг brain'а
- `~/.claude/projects/-Users-vladislavrumancev-Desktop-Cursor/memory/vertushka_gbrain.md` — заметка в auto-memory с особенностями setup
