#!/bin/bash
# Deploy yandex-jobs-bot to server
# Usage: bash deploy.sh

set -e

SERVER="deploy@85.198.85.12"
REMOTE_DIR="/home/deploy/yandex-jobs-bot"
LOCAL_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "==> Copying bot files to server..."
scp "$LOCAL_DIR/bot.py" \
    "$LOCAL_DIR/scraper.py" \
    "$LOCAL_DIR/requirements.txt" \
    "$LOCAL_DIR/.env" \
    "$SERVER:$REMOTE_DIR/"

echo "==> Installing dependencies on server..."
ssh "$SERVER" << 'REMOTE'
cd /home/deploy/yandex-jobs-bot
python3 -m venv .venv
.venv/bin/pip install --upgrade pip
.venv/bin/pip install -r requirements.txt
REMOTE

echo "==> Restarting service..."
ssh "$SERVER" "sudo systemctl restart yandex-jobs-bot"

echo "==> Checking status..."
ssh "$SERVER" "sudo systemctl status yandex-jobs-bot --no-pager"

echo "==> Done!"
