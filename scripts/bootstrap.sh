#!/bin/bash
# Первичная настройка на сервере после git clone
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo "=== SkyPath Bootstrap ==="

if [ ! -f .env ]; then
    cp .env.example .env
    echo -e "${YELLOW}Создан .env из .env.example — заполни секреты:${NC}"
    echo "  nano .env"
    echo ""
    echo "Обязательно: BOT_TOKEN, BRAND_NAME, PLATEGA_*, XUI_*, WEBHOOK_BASE_URL, NGINX_DOMAIN, CERTBOT_EMAIL"
    exit 0
fi

# Синхронизация NGINX_DOMAIN из WEBHOOK_BASE_URL
if grep -q '^WEBHOOK_BASE_URL=' .env && ! grep -q '^NGINX_DOMAIN=.' .env 2>/dev/null; then
    :
fi
if grep -q '^WEBHOOK_BASE_URL=https://' .env; then
    HOOK_URL=$(grep '^WEBHOOK_BASE_URL=' .env | cut -d= -f2- | tr -d '"' | tr -d "'")
    DOMAIN=$(echo "$HOOK_URL" | sed -E 's#https?://##' | cut -d/ -f1)
    if [ -n "$DOMAIN" ] && ! grep -q "^NGINX_DOMAIN=${DOMAIN}" .env; then
        if grep -q '^NGINX_DOMAIN=' .env; then
            sed -i.bak "s|^NGINX_DOMAIN=.*|NGINX_DOMAIN=${DOMAIN}|" .env
        else
            echo "NGINX_DOMAIN=${DOMAIN}" >> .env
        fi
        echo -e "${GREEN}✓ NGINX_DOMAIN=${DOMAIN}${NC}"
    fi
fi

chmod +x scripts/*.sh
echo -e "${GREEN}✓ Готово. Дальше: ./scripts/deploy.sh${NC}"
