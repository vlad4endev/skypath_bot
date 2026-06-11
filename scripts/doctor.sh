#!/bin/bash
# Диагностика окружения на VPS
set -euo pipefail
cd "$(dirname "$0")/.."

GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo "=== SkyPath Doctor ==="
echo "Папка: $(pwd)"
echo ""

echo "--- docker-compose.yml (первые 15 строк) ---"
head -15 docker-compose.yml 2>/dev/null || echo "ФАЙЛ НЕ НАЙДЕН"
echo ""

echo "--- compose-файлы ---"
ls -la docker-compose*.yml 2>/dev/null || echo "нет"
echo "COMPOSE_FILE=${COMPOSE_FILE:-<не задан>}"
echo ""

echo "--- сервисы в compose ---"
docker compose config --services 2>&1 || true
echo ""

echo "--- контейнеры проекта ---"
docker compose ps 2>&1 || true
echo ""

echo "--- порт 8080 / 8082 ---"
ss -tlnp 2>/dev/null | grep -E ':8080|:8082' || netstat -tlnp 2>/dev/null | grep -E ':8080|:8082' || echo "не удалось проверить"
echo ""

echo "--- health ---"
echo -n "8080: "; curl -s --max-time 2 http://127.0.0.1:8080/health 2>/dev/null || echo "нет ответа"
echo -n "8082: "; curl -s --max-time 2 http://127.0.0.1:8082/health 2>/dev/null || echo "нет ответа"
echo ""

if docker compose config --services 2>/dev/null | grep -qx postgres; then
    echo -e "${GREEN}✓ postgres в compose есть${NC}"
else
    echo -e "${RED}✗ postgres в compose НЕТ — выполни:${NC}"
    echo "  git fetch origin && git checkout origin/main -- docker-compose.yml scripts/deploy.sh"
    echo "  ./scripts/deploy.sh"
fi
