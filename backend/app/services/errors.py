from __future__ import annotations

import threading
import time

import httpx
from sqlmodel import Session

from ..core.config import ALERT_WEBHOOK_URL
from ..db.database import engine
from ..models.models import ErrorLog

_alert_lock = threading.Lock()
_last_alert: dict[str, float] = {}
ALERT_COOLDOWN_SECONDS = 60


def record_error(
    message: str,
    detail: str = "",
    source: str = "server",
    level: str = "error",
    path: str = "",
    user_id: int | None = None,
    notify: bool = True,
) -> None:
    try:
        with Session(engine) as session:
            session.add(
                ErrorLog(
                    source=source,
                    level=level,
                    message=message[:500],
                    detail=(detail or "")[:4000],
                    path=path[:300],
                    user_id=user_id,
                )
            )
            session.commit()
    except Exception:  # noqa: BLE001
        pass
    if notify:
        _alert(message, detail, path)


def _alert(message: str, detail: str, path: str) -> None:
    url = ALERT_WEBHOOK_URL
    if not url:
        return
    key = message[:120]
    now = time.time()
    with _alert_lock:
        if now - _last_alert.get(key, 0) < ALERT_COOLDOWN_SECONDS:
            return
        _last_alert[key] = now

    text = f"[降AI味改写] {message}\n路径：{path or '-'}\n{(detail or '')[:800]}"

    def _post() -> None:
        payload = {"msgtype": "text", "text": {"content": text[:1800]}}
        if "qyapi.weixin.qq.com" not in url:
            payload = {"text": text[:1800]}
        try:
            httpx.post(url, json=payload, timeout=5)
        except Exception:  # noqa: BLE001
            pass

    threading.Thread(target=_post, daemon=True).start()
