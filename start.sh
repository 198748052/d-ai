#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

if [ ! -d frontend/node_modules ]; then
  echo "[setup] installing frontend dependencies"
  (cd frontend && npm install --no-audit --no-fund)
fi

echo "[start] backend on :18438"
(cd backend && python3 -m uvicorn app.main:app --host 0.0.0.0 --port 18438) &
BACKEND_PID=$!

cleanup() {
  kill "$BACKEND_PID" 2>/dev/null || true
}
trap cleanup EXIT INT TERM

echo "[start] frontend on :18437"
cd frontend
npm run dev
