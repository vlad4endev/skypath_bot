#!/bin/bash
# Использование: ./scripts/logs.sh [bot|db|nginx|all]
SERVICE=${1:-bot}
if [ "$SERVICE" = "all" ]; then
    docker compose logs -f
else
    docker compose logs -f $SERVICE
fi
