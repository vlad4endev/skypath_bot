#!/bin/bash
set -e

cd "$(dirname "$0")/.."

echo "=== SkyPath VPN Bot Deploy ==="

GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'

http_override() {
    cat > docker-compose.override.yml <<'YAML'
services:
  nginx:
    volumes:
      - ./nginx.http.conf:/etc/nginx/nginx.conf.template:ro
YAML
}

has_ssl_cert() {
    local vol
    vol=$(docker volume ls -q | grep certbot_data | head -1)
    [ -z "$vol" ] && return 1
    docker run --rm -v "${vol}:/etc/letsencrypt:ro" alpine \
        test -f "/etc/letsencrypt/live/${NGINX_DOMAIN}/fullchain.pem"
}

if [ ! -f .env ]; then
    ./scripts/bootstrap.sh
    exit 1
fi

check_var() {
    if ! grep -q "^$1=" .env || grep -q "^$1=$" .env; then
        echo -e "${RED}ОШИБКА: $1 не заполнен в .env${NC}"
        exit 1
    fi
}

check_var "BOT_TOKEN"
check_var "PLATEGA_MERCHANT_ID"
check_var "PLATEGA_SECRET"
check_var "XUI_HOST"
check_var "WEBHOOK_BASE_URL"
check_var "NGINX_DOMAIN"

echo -e "${GREEN}✓ .env проверен${NC}"

if ! command -v docker &> /dev/null; then
    echo -e "${YELLOW}Устанавливаем Docker...${NC}"
    curl -fsSL https://get.docker.com | sh
    usermod -aG docker "$USER" 2>/dev/null || true
fi

if ! docker compose version &> /dev/null; then
    echo -e "${YELLOW}Устанавливаем Docker Compose plugin...${NC}"
    apt-get update && apt-get install -y docker-compose-plugin
fi

chmod +x scripts/*.sh
echo -e "${GREEN}✓ Docker готов${NC}"

compose_services() {
    docker compose -f docker-compose.yml config --services 2>/dev/null
}

has_compose_service() {
    compose_services | grep -qx "$1"
}

restore_compose_file() {
    echo -e "${YELLOW}Восстанавливаем docker-compose.yml...${NC}"
    if git rev-parse --git-dir >/dev/null 2>&1; then
        git fetch origin main 2>/dev/null || true
        if git checkout origin/main -- docker-compose.yml 2>/dev/null; then
            echo -e "${GREEN}✓ docker-compose.yml из git${NC}"
            return 0
        fi
    fi
    if curl -fsSL \
        "https://raw.githubusercontent.com/vlad4endev/skypath_bot/main/docker-compose.yml" \
        -o docker-compose.yml; then
        echo -e "${GREEN}✓ docker-compose.yml с GitHub${NC}"
        return 0
    fi
    return 1
}

ensure_compose_file() {
    if [ ! -f docker-compose.yml ]; then
        restore_compose_file || {
            echo -e "${RED}ОШИБКА: нет docker-compose.yml${NC}"
            exit 1
        }
    fi

    if ! has_compose_service postgres; then
        echo -e "${YELLOW}В docker-compose.yml нет postgres (файл битый или устарел)${NC}"
        echo "Текущие сервисы: $(compose_services | tr '\n' ' ')"
        restore_compose_file || true
    fi

    if ! has_compose_service postgres; then
        echo -e "${RED}ОШИБКА: postgres всё ещё отсутствует${NC}"
        echo "Проверь COMPOSE_FILE и override-файлы:"
        echo "  ls -la docker-compose*.yml"
        echo "  echo \"\$COMPOSE_FILE\""
        echo "  head -20 docker-compose.yml"
        exit 1
    fi
}

ensure_compose_file

SKYPATH_NET=skypath_bot_skypath_net

ensure_docker_network() {
    if ! docker network inspect "$SKYPATH_NET" >/dev/null 2>&1; then
        docker network create "$SKYPATH_NET"
        echo -e "${GREEN}✓ Создана сеть ${SKYPATH_NET}${NC}"
    fi
    local npm
    npm=$(docker ps --format '{{.Names}}' 2>/dev/null | grep -Ei 'nginx.?proxy.?manager|^npm$' | head -1 || true)
    if [ -n "$npm" ]; then
        if docker network connect "$SKYPATH_NET" "$npm" 2>/dev/null; then
            echo -e "${GREEN}✓ NPM (${npm}) подключён к ${SKYPATH_NET}${NC}"
        fi
    fi
}

ensure_docker_network

# shellcheck disable=SC1091
source "$(dirname "$0")/load_env.sh"
load_env_file .env

# Не делаем «compose down» — сеть skypath_net может быть занята nginx-proxy-manager
rm -f docker-compose.override.yml

for svc in postgres redis bot nginx; do
    if ! has_compose_service "$svc"; then
        echo -e "${RED}ОШИБКА: нет сервиса «${svc}»${NC}"
        exit 1
    fi
done

echo -e "${GREEN}✓ docker-compose.yml OK ($(compose_services | tr '\n' ' '))${NC}"

echo -e "${YELLOW}Собираем образы...${NC}"
docker compose build bot

echo -e "${YELLOW}Запускаем postgres, redis, bot...${NC}"
docker compose up -d postgres redis bot

echo -e "${YELLOW}Ждём PostgreSQL...${NC}"
for _ in $(seq 1 30); do
    if docker compose exec -T postgres pg_isready -U vpnbot -d skypath >/dev/null 2>&1; then
        break
    fi
    sleep 1
done

echo -e "${YELLOW}Применяем миграции...${NC}"
docker compose exec -T bot alembic upgrade head

uses_external_proxy() {
    docker ps --format '{{.Names}}' 2>/dev/null | grep -Eiq 'nginx.?proxy.?manager|npm'
}

if uses_external_proxy; then
    echo -e "${YELLOW}Обнаружен Nginx Proxy Manager — встроенный nginx не запускаем${NC}"
    echo -e "В NPM добавь прокси на ${GREEN}skypath_bot:8080${NC} (внутри Docker-сети, не host:8080)"
    echo -e "Проверка health: ${GREEN}curl -s http://127.0.0.1:8082/health${NC}"
elif has_ssl_cert; then
    echo -e "${YELLOW}SSL найден — nginx с HTTPS${NC}"
    docker compose up -d nginx certbot
else
    echo -e "${YELLOW}SSL нет — nginx только HTTP (затем: ./scripts/ssl.sh)${NC}"
    http_override
    docker compose up -d nginx
fi

echo ""
echo "=== Статус контейнеров ==="
docker compose ps

BASE="${WEBHOOK_BASE_URL%/}"
echo ""
echo -e "${GREEN}=== Деплой завершён ===${NC}"
echo "Telegram webhook: ${BASE}/webhook/<BOT_TOKEN>"
echo "Platega webhook:   ${BASE}/webhook/platega"
echo "Mini App:          ${MINI_APP_URL:-${BASE}/app}"
echo "Health:            ${BASE}/health"
echo "Health (local):    curl -s http://127.0.0.1:8082/health"
echo ""
echo -e "Логи: ${YELLOW}./scripts/logs.sh bot${NC}"
