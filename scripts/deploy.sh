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
check_var "YOOKASSA_SHOP_ID"
check_var "YOOKASSA_SECRET_KEY"
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

set -a
# shellcheck disable=SC1091
source .env
set +a

docker compose down 2>/dev/null || true
rm -f docker-compose.override.yml

echo -e "${YELLOW}Собираем образы...${NC}"
docker compose build

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

if has_ssl_cert; then
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
echo "YooKassa webhook:  ${BASE}/yookassa/webhook"
echo "Mini App:          ${MINI_APP_URL:-${BASE}/app}"
echo "Health:            ${BASE}/health"
echo ""
echo -e "Логи: ${YELLOW}./scripts/logs.sh bot${NC}"
