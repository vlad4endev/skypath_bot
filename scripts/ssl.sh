#!/bin/bash
set -e

cd "$(dirname "$0")/.."

GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'

if [ ! -f .env ]; then
    echo -e "${RED}ОШИБКА: нет .env${NC}"
    exit 1
fi

set -a
# shellcheck disable=SC1091
source .env
set +a

if [ -z "${NGINX_DOMAIN:-}" ] || [ "$NGINX_DOMAIN" = "your-domain.com" ]; then
    echo -e "${RED}ОШИБКА: задай NGINX_DOMAIN в .env${NC}"
    exit 1
fi

if [ -z "${CERTBOT_EMAIL:-}" ]; then
    echo -e "${RED}ОШИБКА: задай CERTBOT_EMAIL в .env${NC}"
    exit 1
fi

echo -e "${YELLOW}=== SSL для ${NGINX_DOMAIN} ===${NC}"

cat > docker-compose.override.yml <<'YAML'
services:
  nginx:
    volumes:
      - ./nginx.http.conf:/etc/nginx/nginx.conf.template:ro
YAML

docker compose up -d nginx

echo -e "${YELLOW}Запрашиваем сертификат Let's Encrypt...${NC}"
docker compose run --rm certbot certonly \
    --webroot -w /var/www/certbot \
    --email "$CERTBOT_EMAIL" \
    --agree-tos \
    --no-eff-email \
    -d "$NGINX_DOMAIN"

rm -f docker-compose.override.yml

docker compose up -d nginx certbot --force-recreate

echo -e "${GREEN}✓ SSL готов${NC}"
echo "curl -sI https://${NGINX_DOMAIN}/health"
