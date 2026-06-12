#!/bin/bash
# Быстрая диагностика SkyPath бота на сервере
set -euo pipefail
cd "$(dirname "$0")/.."

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo "=== SkyPath Bot Doctor ==="

if [ ! -f .env ]; then
  echo -e "${RED}Нет .env — запустите scripts/bootstrap.sh${NC}"
  exit 1
fi

# shellcheck disable=SC1091
set -a && source .env && set +a

echo ""
echo "--- Docker ---"
if ! command -v docker >/dev/null 2>&1; then
  echo -e "${RED}Docker не установлен${NC}"
  exit 1
fi

docker compose ps -a 2>/dev/null || docker-compose ps -a

BOT_STATUS=$(docker compose ps bot --format '{{.Status}}' 2>/dev/null || echo "unknown")
echo "bot: $BOT_STATUS"

if echo "$BOT_STATUS" | grep -qi restart; then
  echo -e "${RED}Контейнер bot перезапускается — смотрите логи ниже${NC}"
fi

echo ""
echo "--- Последние логи bot (40 строк) ---"
docker compose logs bot --tail 40 2>/dev/null || true

echo ""
echo "--- Health ---"
PORT="${BOT_HOST_PORT:-8084}"
if curl -sf "http://127.0.0.1:${PORT}/health" >/dev/null 2>&1; then
  echo -e "${GREEN}✓ http://127.0.0.1:${PORT}/health OK${NC}"
else
  echo -e "${RED}✗ Бот не отвечает на :${PORT}/health${NC}"
fi

echo ""
echo "--- Версия кода (git pull недостаточно — нужен build bot) ---"
HOST_REV=$(git rev-parse --short HEAD 2>/dev/null || echo "?")
echo "хост:  $HOST_REV"
if docker compose ps bot --format '{{.State}}' 2>/dev/null | grep -q running; then
  CONTAINER_REV=$(docker compose exec -T bot sh -c 'grep -q SKYPATH_SKIP_ALEMBIC_FILECONFIG /app/database/migrate.py 2>/dev/null && echo ok || echo old' 2>/dev/null || echo "?")
  if [ "$CONTAINER_REV" = "ok" ]; then
    echo -e "${GREEN}✓ контейнер: образ с фиксом логов/polling (migrate.py)${NC}"
  else
    echo -e "${RED}✗ контейнер: старый образ — выполните: docker compose build bot && docker compose up -d --force-recreate bot${NC}"
  fi
fi

echo ""
echo "--- Telegram API (из контейнера bot) ---"
if docker compose ps bot --format '{{.State}}' 2>/dev/null | grep -q running; then
  TG=$(docker compose exec -T bot python -c "
import asyncio, os, sys
from aiogram import Bot
async def main():
    t = os.getenv('BOT_TOKEN','').strip()
    if not t:
        print('NO_TOKEN'); return
    try:
        me = await asyncio.wait_for(Bot(t).get_me(), timeout=15)
        print(f'OK @{me.username} id={me.id}')
    except Exception as e:
        print('FAIL', type(e).__name__, str(e)[:120])
asyncio.run(main())
" 2>/dev/null || echo "EXEC_FAIL")
  case "$TG" in
    OK*) echo -e "${GREEN}✓ $TG${NC}" ;;
    NO_TOKEN) echo -e "${RED}✗ BOT_TOKEN пуст в контейнере${NC}" ;;
    *) echo -e "${RED}✗ Telegram: $TG${NC}" ;;
  esac
else
  echo -e "${YELLOW}контейнер bot не running${NC}"
fi

echo ""
echo "--- Polling в логах (WARNING после миграций) ---"
if docker compose logs bot 2>/dev/null | grep -q "Telegram polling task started"; then
  echo -e "${GREEN}✓ polling task зарегистрирован${NC}"
elif [ "${BOT_MODE:-webhook}" = "polling" ]; then
  echo -e "${RED}✗ BOT_MODE=polling, но в логах нет «Telegram polling task started» — пересоберите образ${NC}"
else
  echo "режим webhook — polling-строки не ожидаются"
fi

echo ""
echo "--- Webhook / режим ---"
echo "BOT_MODE=${BOT_MODE:-webhook}"
echo "WEBHOOK_BASE_URL=${WEBHOOK_BASE_URL:-не задан}"

if [ "${BOT_MODE:-webhook}" = "webhook" ] && [ -n "${WEBHOOK_BASE_URL:-}" ]; then
  HOOK="${WEBHOOK_BASE_URL%/}/webhook"
  CODE=$(curl -s -o /dev/null -w "%{http_code}" -X POST "$HOOK" -d '{}' 2>/dev/null || echo "000")
  echo "POST $HOOK → HTTP $CODE (401/403/405 нормально без secret; 404/502 — проблема nginx)"
fi

echo ""
echo "--- Миграции ---"
if docker compose ps bot --format '{{.State}}' 2>/dev/null | grep -q running; then
  docker compose exec -T bot alembic current 2>/dev/null || echo -e "${YELLOW}alembic current недоступен${NC}"
else
  echo -e "${YELLOW}Контейнер bot не running — миграции: docker compose run --rm bot alembic upgrade head${NC}"
fi

echo ""
echo "--- Что делать ---"
cat <<'HELP'
1. Бот только в Docker — НЕ запускайте python3 -m bot.main на хосте.
2. Обновление (build обязателен — код не монтируется в контейнер):
     git pull && docker compose build bot && docker compose up -d --force-recreate bot
3. Если webhook 404 — перезагрузите nginx: docker compose restart nginx
4. Если Telegram не отвечает — временно в .env:
     BOT_MODE=polling
   затем: docker compose up -d --force-recreate bot
5. Логи в реальном времени:
     docker compose logs -f bot
HELP
