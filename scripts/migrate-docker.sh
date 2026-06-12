#!/usr/bin/env bash
# Импорт CSV из NocoDB через контейнер бота (на сервере без локального .venv).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

CSV1="${1:-data/nocodb_export/users_skypath.csv}"
CSV2="${2:-data/nocodb_export/super_vpn.csv}"
DRY_RUN="${DRY_RUN:-}"

for f in "$CSV1" "$CSV2"; do
  if [ ! -f "$f" ]; then
    echo "Файл не найден: $f"
    echo "Загрузите CSV на сервер, например:"
    echo "  scp Пользователи_exported_1.csv skyputh@server:~/skypath_bot/data/nocodb_export/users_skypath.csv"
    echo "  scp \"SUPER VPN_exported_1.csv\" skyputh@server:~/skypath_bot/data/nocodb_export/super_vpn.csv"
    exit 1
  fi
done

ARGS=(python scripts/migrate_skypath_csv.py)
if [ -n "$DRY_RUN" ]; then
  ARGS+=(--dry-run)
fi
ARGS+=("$CSV1" "$CSV2")

echo "==> Alembic migrations"
docker compose exec bot python -m alembic upgrade head

echo "==> Import CSV (dry-run=${DRY_RUN:-no})"
docker compose exec bot "${ARGS[@]}"
