#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"

if [ ! -d "$ROOT/backend/.venv" ]; then
  python3 -m venv "$ROOT/backend/.venv"
  "$ROOT/backend/.venv/bin/pip" install -r "$ROOT/backend/requirements.txt"
fi

if [ ! -d "$ROOT/frontend/node_modules" ]; then
  (cd "$ROOT/frontend" && npm install)
fi

"$ROOT/backend/.venv/bin/uvicorn" app:app --app-dir "$ROOT/backend" --host 0.0.0.0 --port 8765 &
BACK_PID=$!
trap 'kill "$BACK_PID" 2>/dev/null || true' EXIT

cd "$ROOT/frontend"
npm run dev -- --host 0.0.0.0 --port 5174
