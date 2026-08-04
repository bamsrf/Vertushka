#!/usr/bin/env bash
#
# Чтение из базы GlitchTip (sentry.vinyl-vertushka.ru) — только SELECT.
#
# Зачем отдельный скрипт. Правило Bash(ssh deploy@85.198.85.12:*) разрешает
# по SSH что угодно, включая изменения прода. Вместо расширения прав здесь
# сужена задача: один инструмент, одна база, и запись невозможна в принципе.
#
# Как гарантируется read-only: PGOPTIONS выставляет default_transaction_read_only,
# то есть запрет накладывает сам PostgreSQL на уровне сессии. INSERT, UPDATE,
# DELETE, DDL и любая другая запись падают с ошибкой — это не проверка
# «на глазок» по тексту запроса, которую можно обойти хитрым SQL.
#
# Использование:
#   scripts/glitchtip-query.sh "select count(*) from issues_issue"
#   scripts/glitchtip-query.sh "\dt"
#
# SQL передаётся через stdin, а не аргументом psql -c: так не нужно экранировать
# кавычки через два уровня шелла (локальный → удалённый), где они регулярно
# ломаются и превращают запрос в нечто неожиданное.
#
set -euo pipefail

readonly SERVER="deploy@85.198.85.12"
readonly CONTAINER="glitchtip-postgres-1"

if [[ $# -lt 1 || -z "${1// }" ]]; then
  echo "Использование: $0 \"<SQL>\"" >&2
  echo "Пример:        $0 \"select count(*) from issues_issue\"" >&2
  exit 2
fi

printf '%s\n' "$1" | ssh -o ConnectTimeout=15 -o BatchMode=yes "$SERVER" \
  "docker exec -i -e PGOPTIONS='-c default_transaction_read_only=on' $CONTAINER \
     psql -U postgres -d postgres -P pager=off -f -"
