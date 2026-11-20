#!/usr/bin/env bash
# Start backend and frontend with auto-restart.
# Used by scripts/update.sh: it kills the recorded PIDs and these loops bring them back.
set -uo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
RUN_DIR="$ROOT/.run"
mkdir -p "$RUN_DIR"

BACKEND_PORT="${BACKEND_PORT:-8000}"
FRONTEND_PORT="${FRONTEND_PORT:-3000}"

stop_existing() {
  for name in backend frontend; do
    pid_file="$RUN_DIR/$name.pid"
    if [ -f "$pid_file" ]; then
      pid="$(cat "$pid_file" 2>/dev/null || true)"
      if [ -n "${pid:-}" ] && kill -0 "$pid" 2>/dev/null; then
        kill -TERM "-$pid" 2>/dev/null || kill "$pid" 2>/dev/null || true
        sleep 1
      fi
      rm -f "$pid_file"
    fi
  done
}
stop_existing

backend_loop() {
  cd "$ROOT/backend" || exit 1
  while true; do
    echo "[serve] backend starting on :$BACKEND_PORT $(date -Is)"
    setsid python3 -m uvicorn app.main:app --host 0.0.0.0 --port "$BACKEND_PORT" &
    echo $! > "$RUN_DIR/backend.pid"
    wait $!
    echo "[serve] backend exited, restarting in 5s $(date -Is)"
    sleep 5
  done
}

frontend_loop() {
  cd "$ROOT/frontend" || exit 1
  while true; do
    echo "[serve] frontend starting on :$FRONTEND_PORT $(date -Is)"
    setsid npx next start -p "$FRONTEND_PORT" &
    echo $! > "$RUN_DIR/frontend.pid"
    wait $!
    echo "[serve] frontend exited, restarting in 5s $(date -Is)"
    sleep 5
  done
}

backend_loop &
frontend_loop &

wait
