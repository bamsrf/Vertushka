---
description: Инкрементальный gbrain-sync — подтянуть свежий markdown Вертушки в локальный brain
---

Запусти инкрементальную синхронизацию gbrain. Шаги:

1. Вызови MCP `mcp__gbrain__sync_brain` с аргументами:
   - `repo`: `/Users/vladislavrumancev/Cursor` (фактический git-root репозитория Vertushka, несмотря на то что `Вертушка/` — подкаталог)
   - `no_embed`: `true` (embeddings выключены в `~/.gbrain/config.json`)
   - `no_pull`: `false` (gbrain сам сделает `git pull` перед синком)

2. Если в результате `added` или `modified` > 0 — проверь, не появились ли новые мусорные страницы. Запусти `mcp__gbrain__list_pages` с `sort=updated_desc` и просканируй слаги. Если что-то под `backend/venv/`, `mobile/node_modules/`, `*.dist-info/licenses/license` — удали через `mcp__gbrain__delete_page`.

3. Выведи короткую сводку (одну строку):
   ```
   🧠 gbrain: +<added> ✎<modified> -<deleted>, всего <page_count> страниц
   ```
   Где `page_count` берётся из `mcp__gbrain__get_stats`.

4. Если sync вернул ошибку — выведи её текстом и подскажи следующий шаг.

Без лишних подробностей. Если ничего не изменилось — просто `🧠 gbrain: без изменений`.
