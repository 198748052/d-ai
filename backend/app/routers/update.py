from __future__ import annotations

import hashlib
import hmac
import os
import subprocess
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request

from ..deps import require_admin
from ..models.models import User

ROOT = Path(__file__).resolve().parents[3]
RUN_DIR = ROOT / ".run"
UPDATE_SCRIPT = ROOT / "scripts" / "update.sh"
SERVE_SCRIPT = ROOT / "scripts" / "serve.sh"
STATUS_FILE = RUN_DIR / "update.status"
LOG_FILE = RUN_DIR / "update.log"
LOCK_DIR = RUN_DIR / "update.lock"

router = APIRouter(prefix="/api/admin/update", tags=["update"])
webhook_router = APIRouter(prefix="/api/webhooks", tags=["webhooks"])


def _git(*args: str, timeout: int = 30) -> tuple[int, str]:
    try:
        proc = subprocess.run(
            ["git", *args],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except (subprocess.TimeoutExpired, OSError) as exc:
        return 1, str(exc)
    return proc.returncode, (proc.stdout or proc.stderr).strip()


def _read_status() -> dict:
    state = "idle"
    detail = ""
    if STATUS_FILE.exists():
        raw = STATUS_FILE.read_text(encoding="utf-8", errors="ignore").strip()
        parts = raw.split(" ", 2)
        state = parts[0] if parts else "idle"
        detail = raw
    return {
        "state": state,
        "detail": detail,
        "running": LOCK_DIR.exists(),
    }


@router.get("/check")
def check_update(_: User = Depends(require_admin)):
    code, current = _git("rev-parse", "HEAD")
    if code != 0:
        raise HTTPException(status_code=500, detail=f"读取版本失败：{current}")
    _, current_info = _git("log", "-1", "--format=%h %s (%ci)", "HEAD")
    fetch_code, fetch_out = _git("fetch", "--prune", "origin", timeout=60)
    if fetch_code != 0:
        return {
            "ok": False,
            "current": current,
            "current_info": current_info,
            "remote": "",
            "behind": 0,
            "commits": [],
            "message": f"拉取远端失败：{fetch_out[:300]}",
        }
    _, remote = _git("rev-parse", "origin/main")
    _, behind = _git("rev-list", "--count", "HEAD..origin/main")
    _, commits = _git("log", "--oneline", "--max-count=20", "HEAD..origin/main")
    return {
        "ok": True,
        "current": current,
        "current_info": current_info,
        "remote": remote,
        "behind": int(behind or 0),
        "commits": [line for line in commits.splitlines() if line],
        "message": "",
    }


@router.post("/run")
def run_update(_: User = Depends(require_admin)):
    if not UPDATE_SCRIPT.exists():
        raise HTTPException(status_code=500, detail="缺少 scripts/update.sh")
    if LOCK_DIR.exists():
        return {"started": False, "message": "已有更新正在进行"}
    RUN_DIR.mkdir(parents=True, exist_ok=True)
    subprocess.Popen(
        ["bash", str(UPDATE_SCRIPT)],
        cwd=str(ROOT),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    return {"started": True, "message": "更新已开始，服务会在完成后自动重启"}


@router.get("/status")
def update_status(_: User = Depends(require_admin)):
    info = _read_status()
    log_tail = ""
    if LOG_FILE.exists():
        try:
            lines = LOG_FILE.read_text(encoding="utf-8", errors="ignore").splitlines()
            log_tail = "\n".join(lines[-40:])
        except OSError:
            log_tail = ""
    info["log"] = log_tail
    return info


@router.get("/runtime")
def runtime_info(_: User = Depends(require_admin)):
    return {
        "root": str(ROOT),
        "has_update_script": UPDATE_SCRIPT.exists(),
        "has_serve_script": SERVE_SCRIPT.exists(),
        "lock": LOCK_DIR.exists(),
    }


@webhook_router.post("/github")
async def github_webhook(request: Request):
    secret = os.getenv("GITHUB_WEBHOOK_SECRET", "").strip()
    if not secret:
        raise HTTPException(status_code=503, detail="未配置 GITHUB_WEBHOOK_SECRET")
    body = await request.body()
    signature = request.headers.get("x-hub-signature-256", "")
    expected = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(signature, expected):
        raise HTTPException(status_code=401, detail="签名校验失败")
    event = request.headers.get("x-github-event", "")
    if event != "push":
        return {"ignored": f"event {event}"}
    try:
        import json

        payload = json.loads(body.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        raise HTTPException(status_code=400, detail="请求体解析失败")
    if payload.get("ref") != "refs/heads/main":
        return {"ignored": payload.get("ref")}
    if LOCK_DIR.exists():
        return {"started": False, "message": "已有更新正在进行"}
    RUN_DIR.mkdir(parents=True, exist_ok=True)
    subprocess.Popen(
        ["bash", str(UPDATE_SCRIPT)],
        cwd=str(ROOT),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    return {"started": True}
