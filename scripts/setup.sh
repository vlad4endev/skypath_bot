#!/usr/bin/env bash
# SkyPath VPN Bot — первичная настройка окружения
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

echo "==> SkyPath VPN Bot setup"

if [ ! -f .env ]; then
  cp .env.example .env
  echo "Created .env from .env.example — fill in BOT_TOKEN, DB_URL, Platega, 3X-UI"
else
  echo ".env already exists"
fi

if [ ! -d .venv ]; then
  python3 -m venv .venv
fi
# shellcheck disable=SC1091
source .venv/bin/activate

pip install --upgrade pip
pip install -r requirements.txt

export PYTHONPATH="$ROOT"

echo "==> Applying database migrations (requires running PostgreSQL)"
if command -v alembic >/dev/null 2>&1; then
  alembic upgrade head || echo "Alembic skipped — start Postgres and run: alembic upgrade head"
else
  python -m alembic upgrade head || echo "Alembic skipped — start Postgres and run: alembic upgrade head"
fi

echo ""
echo "Done. Next steps:"
echo "  1. Edit .env with real credentials"
echo "  2. docker compose up -d   # production"
echo "  3. Or: source .venv/bin/activate && python -m bot.main"
