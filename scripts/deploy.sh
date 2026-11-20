#!/usr/bin/env bash
# One-click deploy for the AI rewrite platform.
#
# Recommended:
#   sudo bash -c "$(curl -fsSL https://raw.githubusercontent.com/198748052/d-ai/main/scripts/deploy.sh)"
#
# Or from an existing clone:
#   sudo bash scripts/deploy.sh
#
# Optional env:
#   INSTALL_DIR=/opt/ai-rewrite   where the repo lives / will be cloned
#   REPO_URL=<git url>            repository to clone when not inside one
#   PORT=18437                    frontend port
#   SERVICE_NAME=ai-rewrite       systemd unit name
#   INSTALL_LOCAL_MODEL=0         skip torch/transformers (perplexity feature disabled)
#   GITHUB_WEBHOOK_SECRET=xx      enable GitHub push webhook
#   SKIP_INSTALL=1 SKIP_BUILD=1 NO_SERVICE=1 NO_START=1   for debugging
set -euo pipefail

REPO_URL="${REPO_URL:-https://github.com/198748052/d-ai.git}"
INSTALL_DIR="${INSTALL_DIR:-/opt/ai-rewrite}"
PORT="${PORT:-18437}"
SERVICE_NAME="${SERVICE_NAME:-ai-rewrite}"
INSTALL_LOCAL_MODEL="${INSTALL_LOCAL_MODEL:-1}"
SKIP_INSTALL="${SKIP_INSTALL:-0}"
SKIP_BUILD="${SKIP_BUILD:-0}"
NO_SERVICE="${NO_SERVICE:-0}"
NO_START="${NO_START:-0}"
LOCAL_MODEL="${LOCAL_MODEL:-Qwen/Qwen2.5-1.5B}"
LOCAL_ENABLED="${LOCAL_ENABLED:-1}"

log() { printf '\033[32m[deploy]\033[0m %s\n' "$*"; }
warn() { printf '\033[33m[deploy]\033[0m %s\n' "$*"; }
die() { printf '\033[31m[deploy]\033[0m %s\n' "$*" >&2; exit 1; }

need_cmd() { command -v "$1" >/dev/null 2>&1; }

install_packages() {
  if [ "$(id -u)" -ne 0 ]; then
    die "缺少 $*，请先用 root 安装，例如：apt-get install -y $*"
  fi
  if need_cmd apt-get; then
    log "安装系统依赖：$*"
    DEBIAN_FRONTEND=noninteractive apt-get update -y
    DEBIAN_FRONTEND=noninteractive apt-get install -y "$@"
  elif need_cmd dnf; then
    log "安装系统依赖：$*"
    dnf install -y "$@"
  elif need_cmd yum; then
    log "安装系统依赖：$*"
    yum install -y "$@"
  else
    die "未找到包管理器，请手动安装：$*"
  fi
}

if ! need_cmd git; then
  install_packages git
fi

APP_DIR="${APP_DIR:-}"
SELF="${BASH_SOURCE[0]:-}"
if [ -z "$APP_DIR" ] && [ -n "$SELF" ] && [ -f "$SELF" ]; then
  SELF_DIR="$(cd "$(dirname "$SELF")" && pwd)"
  if [ -f "$SELF_DIR/../backend/requirements.txt" ]; then
    APP_DIR="$(cd "$SELF_DIR/.." && pwd)"
  fi
fi
APP_DIR="${APP_DIR:-$INSTALL_DIR}"

if [ ! -f "$APP_DIR/backend/requirements.txt" ]; then
  log "克隆代码到 $APP_DIR"
  mkdir -p "$(dirname "$APP_DIR")"
  git clone "$REPO_URL" "$APP_DIR" || die "克隆失败，请检查网络或仓库地址"
fi

VENV_DIR="$APP_DIR/.venv"
RUN_DIR="$APP_DIR/.run"

log "部署目录：$APP_DIR"

if [ ! -d "$APP_DIR/.git" ]; then
  warn "当前目录不是 git 仓库，在线更新功能将不可用"
fi

missing=()
need_cmd python3 || missing+=(python3 python3-venv python3-pip)
need_cmd node || missing+=(nodejs)
need_cmd npm || missing+=(npm)
if [ "${#missing[@]}" -gt 0 ]; then
  install_packages "${missing[@]}"
fi

PY_OK=$(python3 -c 'import sys; print(1 if sys.version_info >= (3, 10) else 0)')
[ "$PY_OK" = "1" ] || die "需要 Python 3.10+，当前 $(python3 -V)"

NODE_MAJOR=$(node -v | sed 's/^v//' | cut -d. -f1)
if [ "$NODE_MAJOR" -lt 18 ]; then
  die "需要 Node.js 18+，当前 $(node -v)。请安装 Node 20（NodeSource 或 nvm）后重试"
fi

MEM_GB=$(( $(awk '/MemTotal/ {print $2}' /proc/meminfo) / 1024 / 1024 ))
log "内存：${MEM_GB}G"
if [ "$MEM_GB" -lt 9 ]; then
  warn "8G 机器跑 1.5B（float16 约 3.5G）可以，但构建前端前先停掉其它大内存进程；若频繁 OOM 可改用 Qwen/Qwen2.5-0.5B"
fi

if [ "$SKIP_INSTALL" != "1" ]; then
  if [ ! -x "$VENV_DIR/bin/python" ]; then
    if ! python3 -c 'import ensurepip' >/dev/null 2>&1; then
      if [ "$(id -u)" -eq 0 ]; then
        install_packages python3-venv || true
      fi
    fi
    log "创建 Python 虚拟环境：$VENV_DIR"
    if ! python3 -m venv "$VENV_DIR"; then
      warn "创建 venv 失败，改用系统 Python 安装依赖"
      VENV_DIR=""
    fi
  fi

  if [ -n "$VENV_DIR" ]; then
    PIP_CMD=("$VENV_DIR/bin/pip")
  else
    PIP_CMD=(python3 -m pip --break-system-packages)
  fi

  log "安装后端依赖"
  "${PIP_CMD[@]}" install --upgrade pip >/dev/null 2>&1 || true
  "${PIP_CMD[@]}" install -r "$APP_DIR/backend/requirements.txt" || die "后端依赖安装失败"

  if [ "$INSTALL_LOCAL_MODEL" = "1" ]; then
    log "安装本地困惑度模型依赖（torch CPU + transformers）"
    if ! "${PIP_CMD[@]}" install torch --index-url https://download.pytorch.org/whl/cpu; then
      warn "torch 安装失败，困惑度功能将不可用；可稍后手动安装"
    fi
    "${PIP_CMD[@]}" install transformers || warn "transformers 安装失败，困惑度功能将不可用"
  fi

  log "安装前端依赖"
  (cd "$APP_DIR/frontend" && (npm ci --no-audit --no-fund || npm install --no-audit --no-fund)) \
    || die "前端依赖安装失败"
fi

if [ "$SKIP_BUILD" != "1" ]; then
  log "构建前端"
  (cd "$APP_DIR/frontend" && npm run build) || die "前端构建失败"
fi

mkdir -p "$APP_DIR/data" "$RUN_DIR"
chmod +x "$APP_DIR/scripts/serve.sh" "$APP_DIR/scripts/update.sh" 2>/dev/null || true

if [ "$(id -u)" -eq 0 ] && [ -d "$APP_DIR/.git" ]; then
  git config --global --add safe.directory "$APP_DIR" 2>/dev/null || true
fi

if [ -n "$VENV_DIR" ] && [ -x "$VENV_DIR/bin/python" ]; then
  SERVICE_PATH="$VENV_DIR/bin:/usr/local/bin:/usr/bin:/bin"
else
  SERVICE_PATH="/usr/local/bin:/usr/bin:/bin"
fi
START_CMD="PATH=$SERVICE_PATH bash $APP_DIR/scripts/serve.sh"

if [ "$NO_START" = "1" ]; then
  log "已跳过启动（NO_START=1）"
elif [ "$NO_SERVICE" != "1" ] && [ "$(id -u)" -eq 0 ] && need_cmd systemctl; then
  UNIT="/etc/systemd/system/$SERVICE_NAME.service"
  log "写入 systemd 服务：$UNIT"
  {
    echo "[Unit]"
    echo "Description=AI rewrite platform"
    echo "After=network.target"
    echo ""
    echo "[Service]"
    echo "Type=simple"
    echo "WorkingDirectory=$APP_DIR"
    echo "ExecStart=/bin/bash $APP_DIR/scripts/serve.sh"
    echo "Restart=always"
    echo "RestartSec=5"
    echo "Environment=PATH=$SERVICE_PATH"
    echo "Environment=FRONTEND_PORT=$PORT"
    echo "Environment=BACKEND_PORT=${BACKEND_PORT:-18438}"
    echo "Environment=LOCAL_MODEL=$LOCAL_MODEL"
    echo "Environment=LOCAL_ENABLED=$LOCAL_ENABLED"
    if [ -n "${GITHUB_WEBHOOK_SECRET:-}" ]; then
      echo "Environment=GITHUB_WEBHOOK_SECRET=$GITHUB_WEBHOOK_SECRET"
    fi
    echo ""
    echo "[Install]"
    echo "WantedBy=multi-user.target"
  } > "$UNIT"
  systemctl daemon-reload
  systemctl enable "$SERVICE_NAME" >/dev/null 2>&1 || true
  systemctl restart "$SERVICE_NAME"
  sleep 3
  if systemctl is-active --quiet "$SERVICE_NAME"; then
    log "服务已启动：$SERVICE_NAME"
  else
    warn "服务未能启动，请查看：journalctl -u $SERVICE_NAME -n 100"
  fi
else
  log "未使用 systemd，后台启动服务"
  ( cd "$APP_DIR" && PATH="$SERVICE_PATH" LOCAL_MODEL="$LOCAL_MODEL" LOCAL_ENABLED="$LOCAL_ENABLED" nohup bash scripts/serve.sh >"$RUN_DIR/serve.log" 2>&1 & )
  sleep 2
fi

log "部署完成"
cat <<EOF

访问地址：http://<服务器IP>:$PORT
首次使用：注册第一个账号，该账号自动成为管理员
接下来：
  1. 进入「LLM 设置」填写 Base URL、模型和 API Key
  2. 默认使用 Qwen/Qwen2.5-1.5B（float16 约 3.5G），首次启动会从 ModelScope 下载；如遇 OOM 改用 0.5B
  3. 需要 GitHub 自动更新时，设置 GITHUB_WEBHOOK_SECRET 并配置仓库 Webhook
  4. 建议用 nginx 把 80/443 反代到 127.0.0.1:$PORT，只对外暴露 80/443

服务管理：
  systemctl status $SERVICE_NAME
  journalctl -u $SERVICE_NAME -f
  手动启动：$START_CMD

数据备份：$APP_DIR/data/（app.db、secret.key、models/）
EOF
