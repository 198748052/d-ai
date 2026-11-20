#!/usr/bin/env bash
# Pull the latest code from origin/main, install what changed, rebuild the frontend,
# then restart services managed by scripts/serve.sh.
set -uo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT" || exit 1
RUN_DIR="$ROOT/.run"
mkdir -p "$RUN_DIR"

LOG="$RUN_DIR/update.log"
STATUS="$RUN_DIR/update.status"
LOCK="$RUN_DIR/update.lock"

log() {
  echo "[$(date -Is)] $*" | tee -a "$LOG"
}

fail() {
  log "FAILED: $*"
  echo "failed $(date -Is) $*" > "$STATUS"
  exit 1
}

if ! mkdir "$LOCK" 2>/dev/null; then
  echo "update already running"
  exit 1
fi
trap 'rmdir "$LOCK" 2>/dev/null' EXIT

: > "$LOG"
echo "running $(date -Is)" > "$STATUS"
log "update started in $ROOT"

BRANCH="${UPDATE_BRANCH:-main}"
BEFORE="$(git rev-parse HEAD)" || fail "not a git repository"
log "current commit: $BEFORE"

git fetch --prune origin || fail "git fetch failed"
TARGET="$(git rev-parse "origin/$BRANCH")" || fail "cannot resolve origin/$BRANCH"

if [ "$BEFORE" = "$TARGET" ]; then
  log "already up to date"
  echo "success $(date -Is) up-to-date" > "$STATUS"
  exit 0
fi

CHANGED="$(git diff --name-only "$BEFORE" "$TARGET")"
log "incoming changes:"
echo "$CHANGED" | tee -a "$LOG"

git merge --ff-only "$TARGET" >>"$LOG" 2>&1 || fail "git merge --ff-only failed, local commits diverged"
AFTER="$(git rev-parse --short HEAD)"
log "updated to $AFTER"

if echo "$CHANGED" | grep -q '^backend/requirements.txt$'; then
  log "installing python dependencies"
  (cd backend && python3 -m pip install --break-system-packages -r requirements.txt) >>"$LOG" 2>&1 \
    || fail "pip install failed"
fi

if echo "$CHANGED" | grep -q '^frontend/package'; then
  log "installing frontend dependencies"
  (cd frontend && npm install --no-audit --no-fund) >>"$LOG" 2>&1 \
    || fail "npm install failed"
fi

if echo "$CHANGED" | grep -q '^frontend/'; then
  log "stopping frontend before build"
  if [ -f "$RUN_DIR/frontend.pid" ]; then
    pid="$(cat "$RUN_DIR/frontend.pid" 2>/dev/null || true)"
    if [ -n "${pid:-}" ]; then
      kill -TERM "-$pid" 2>/dev/null || kill "$pid" 2>/dev/null || true
    fi
    sleep 2
  fi
  log "building frontend"
  (cd frontend && npm run build) >>"$LOG" 2>&1 || fail "frontend build failed"
fi

log "restarting services"
for name in backend frontend; do
  pid_file="$RUN_DIR/$name.pid"
  if [ -f "$pid_file" ]; then
    pid="$(cat "$pid_file" 2>/dev/null || true)"
    if [ -n "${pid:-}" ]; then
      kill -TERM "-$pid" 2>/dev/null || kill "$pid" 2>/dev/null || true
    fi
  fi
done

echo "success $(date -Is) $AFTER" > "$STATUS"
log "update finished, services restarting"
exit 0
