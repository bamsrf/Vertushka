#!/bin/bash
# First-time server setup for yandex-jobs-bot
# Run this ONCE on the server (via SSH):
#   ssh deploy@85.198.85.12
#   bash setup-server.sh

set -e

REMOTE_DIR="/home/deploy/yandex-jobs-bot"

echo "==> Creating project directory..."
mkdir -p "$REMOTE_DIR"

echo "==> Setting up Python venv..."
cd "$REMOTE_DIR"
python3 -m venv .venv
.venv/bin/pip install --upgrade pip
.venv/bin/pip install -r requirements.txt

echo "==> Installing systemd service..."
sudo cp "$REMOTE_DIR/yandex-jobs-bot.service" /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable yandex-jobs-bot
sudo systemctl start yandex-jobs-bot

echo "==> Service status:"
sudo systemctl status yandex-jobs-bot --no-pager

echo ""
echo "==> Done! Bot is running."
echo "Useful commands:"
echo "  sudo systemctl status yandex-jobs-bot   # check status"
echo "  sudo systemctl restart yandex-jobs-bot   # restart"
echo "  sudo journalctl -u yandex-jobs-bot -f    # follow logs"
