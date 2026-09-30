#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if [[ ! -f .env ]]; then
  cp .env.example .env
  echo "Created .env from .env.example"
fi

API_DIR="$ROOT/apps/api"
WEB_DIR="$ROOT/apps/web"

if [[ ! -d "$API_DIR/.venv" ]]; then
  echo "Creating API virtualenv..."
  python3 -m venv "$API_DIR/.venv"
  "$API_DIR/.venv/bin/pip" install -r "$API_DIR/requirements.txt"
fi

PYTHON="$API_DIR/.venv/bin/python"
if [[ ! -x "$PYTHON" ]]; then
  PYTHON="$API_DIR/.venv/Scripts/python"
fi

echo "Running migrations..."
(cd "$API_DIR" && "$PYTHON" -m alembic upgrade head && "$PYTHON" -m app.db.seed)

if [[ ! -d "$WEB_DIR/node_modules" ]]; then
  echo "Installing web dependencies..."
  (cd "$WEB_DIR" && npm install)
fi

cleanup() {
  kill $API_PID $WEB_PID 2>/dev/null || true
}
trap cleanup EXIT INT TERM

echo "Starting API on http://localhost:8000 ..."
(cd "$API_DIR" && "$PYTHON" -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000) &
API_PID=$!

echo "Starting Web on http://localhost:3000 ..."
(cd "$WEB_DIR" && npm run dev) &
WEB_PID=$!

echo ""
echo "API: http://localhost:8000"
echo "Web: http://localhost:3000"
echo "Press Ctrl+C to stop."
wait
