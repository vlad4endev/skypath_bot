#!/bin/bash
# Использование: ./scripts/logs.sh [bot|postgres|nginx|all]
SERVICE=${1:-bot}
case "$SERVICE" in
  db) SERVICE=postgres ;;
esac
if [ "$SERVICE" = "all" ]; then
    docker compose logs -f
else
    docker compose logs -f "$SERVICE"
fi
