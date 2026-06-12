#!/bin/bash
# Подключить Nginx Proxy Manager к сети бота и проверить доступность
set -euo pipefail
cd "$(dirname "$0")/.."

NET=skypath_bot_skypath_net
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'

find_npm() {
    local name
    name=$(docker ps --format '{{.Names}}' 2>/dev/null | grep -Ei \
        'nginx.?proxy.?manager|nginxproxymanager|^npm$|jc21.*npm|proxy-manager' | head -1 || true)
    if [ -n "$name" ]; then
        echo "$name"
        return
    fi
    docker ps --filter "publish=81" --format '{{.Names}}' 2>/dev/null | head -1
}

if ! docker network inspect "$NET" >/dev/null 2>&1; then
    docker network create "$NET"
    echo -e "${GREEN}✓ Создана сеть ${NET}${NC}"
fi

NPM=$(find_npm)
if [ -z "$NPM" ]; then
    echo -e "${RED}Контейнер NPM не найден. Запущенные контейнеры:${NC}"
    docker ps --format 'table {{.Names}}\t{{.Ports}}'
    exit 1
fi

echo -e "${YELLOW}NPM контейнер: ${NPM}${NC}"

if docker network connect "$NET" "$NPM" 2>/dev/null; then
    echo -e "${GREEN}✓ ${NPM} подключён к ${NET}${NC}"
else
    echo -e "${YELLOW}~ ${NPM} уже в сети ${NET} (или нет прав)${NC}"
fi

echo ""
echo "--- Участники сети ${NET} ---"
docker network inspect "$NET" --format '{{range .Containers}}{{.Name}} {{end}}' 2>/dev/null || true
echo ""

echo "--- Проверка из NPM → skypath_bot:8080 ---"
if docker exec "$NPM" curl -sf --max-time 5 http://skypath_bot:8080/health; then
    echo ""
    echo -e "${GREEN}✓ Бот доступен из NPM по имени skypath_bot:8080${NC}"
else
    echo -e "${RED}✗ skypath_bot:8080 недоступен из NPM${NC}"
    BOT_HP="${BOT_HOST_PORT:-8084}"
  echo "--- Проверка host-gateway:${BOT_HP} ---"
    GW=$(docker exec "$NPM" sh -c "ip route | awk '/default/ {print \$3}'" 2>/dev/null || echo "172.17.0.1")
    docker exec "$NPM" curl -sf --max-time 5 "http://${GW}:${BOT_HP}/health" && echo "" && \
        echo -e "${YELLOW}Используй в NPM: Forward ${GW} port ${BOT_HP}${NC}" || \
        echo -e "${RED}Gateway ${GW}:${BOT_HP} тоже недоступен${NC}"
fi

echo ""
echo -e "${YELLOW}Настройки NPM для bot.skypath.fun:${NC}"
echo "  Forward Hostname: skypath_bot"
echo "  Forward Port:     8080"
echo "  Scheme:           http"
echo "  Websockets:       ON"
