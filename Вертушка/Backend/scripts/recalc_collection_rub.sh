#!/usr/bin/env bash
# Запуск пересчёта CollectionItem.estimated_price_rub на проде.
# Используется один раз после изменения pricing-формулы.
set -euo pipefail

cd "$(dirname "$0")/../.."
cd Backend
docker compose -f docker-compose.prod.yml exec -T -w /app -e PYTHONPATH=/app api python scripts/recalc_collection_rub.py
