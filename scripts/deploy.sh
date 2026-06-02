#!/bin/bash
set -e

echo "=== SkyPath VPN Bot Deploy ==="

# Цвета
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'

# Проверка .env
if [ ! -f .env ]; then
    echo -e "${RED}ОШИБКА: .env файл не найден${NC}"
    echo "Скопируй: cp .env.example .env и заполни"
    exit 1
fi

# Проверка обязательных переменных
check_var() {
    if ! grep -q "^$1=" .env || grep -q "^$1=$" .env; then
        echo -e "${RED}ОШИБКА: $1 не заполнен в .env${NC}"
        exit 1
    fi
}

check_var "BOT_TOKEN"
check_var "YOOKASSA_SHOP_ID"
check_var "XUI_HOST"
check_var "WEBHOOK_BASE_URL"

echo -e "${GREEN}✓ .env проверен${NC}"

# Проверка Docker
if ! command -v docker &> /dev/null; then
    echo -e "${YELLOW}Устанавливаем Docker...${NC}"
    curl -fsSL https://get.docker.com | sh
    usermod -aG docker $USER
    echo -e "${GREEN}✓ Docker установлен${NC}"
fi

if ! command -v docker compose &> /dev/null; then
    echo -e "${YELLOW}Устанавливаем Docker Compose...${NC}"
    apt-get install -y docker-compose-plugin
fi

echo -e "${GREEN}✓ Docker готов${NC}"

# Остановить старые контейнеры если есть
docker compose down 2>/dev/null || true

# Собрать и запустить
echo -e "${YELLOW}Собираем образы...${NC}"
docker compose build --no-cache

echo -e "${YELLOW}Запускаем контейнеры...${NC}"
docker compose up -d

# Ждём пока БД поднимется
echo -e "${YELLOW}Ждём запуска PostgreSQL...${NC}"
sleep 8

# Применяем миграции
echo -e "${YELLOW}Применяем миграции БД...${NC}"
docker compose exec bot alembic upgrade head

# Проверяем статус
echo ""
echo "=== Статус контейнеров ==="
docker compose ps

echo ""
echo -e "${GREEN}=== Деплой завершён ===${NC}"
echo -e "Бот запущен. Проверь логи: ${YELLOW}docker compose logs -f bot${NC}"
