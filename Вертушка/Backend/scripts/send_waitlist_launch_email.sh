#!/usr/bin/env bash
# Рассылка ссылки на App Store по waitlist. Аргументы прокидываются в питон-скрипт.
#
#   ./scripts/send_waitlist_launch_email.sh --dry-run
#   ./scripts/send_waitlist_launch_email.sh --only me@example.com --force
#   ./scripts/send_waitlist_launch_email.sh
#
# Запускается одноразовым контейнером из того же образа (run --rm), а не exec'ом
# в живой api: рассылка идёт минутами, и деплой/autoheal посередине её не срежут.
set -euo pipefail

cd "$(dirname "$0")/.."
docker compose -f docker-compose.prod.yml run --rm \
    -e PYTHONPATH=/app -w /app \
    api-blue python scripts/send_waitlist_launch_email.py "$@"
