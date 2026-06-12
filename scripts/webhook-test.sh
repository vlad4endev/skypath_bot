#!/bin/bash
# Проверка Telegram webhook (секрет берётся из контейнера бота)
set -euo pipefail
cd "$(dirname "$0")/.."

source "$(dirname "$0")/load_env.sh"
load_env_file .env

BASE="${WEBHOOK_BASE_URL%/}"
SECRET=$(docker exec skypath_bot python3 -c "from bot.config import Config; print(Config().WEBHOOK_SECRET)")

echo "=== health ==="
curl -sf "${BASE}/health"
echo ""

echo "=== POST ${BASE}/webhook ==="
curl -s -X POST "${BASE}/webhook" \
  -H "Content-Type: application/json" \
  -H "X-Telegram-Bot-Api-Secret-Token: ${SECRET}" \
  -d '{"update_id":1}' -w "\nHTTP %{http_code}\n"
echo ""

echo "=== getWebhookInfo ==="
curl -s "https://api.telegram.org/bot${BOT_TOKEN}/getWebhookInfo" | python3 -m json.tool
