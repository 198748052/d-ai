from __future__ import annotations

import time
from collections import defaultdict

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel

from ..deps import current_user
from ..models.models import User
from ..services.errors import record_error

router = APIRouter(prefix="/api/errors", tags=["errors"])

_hits: dict[str, list[float]] = defaultdict(list)
LIMIT_PER_MINUTE = 20


class ClientErrorIn(BaseModel):
    message: str
    detail: str = ""
    path: str = ""


@router.post("")
def report_client_error(
    payload: ClientErrorIn,
    request: Request,
    user: User | None = Depends(current_user),
):
    ip = request.client.host if request.client else "unknown"
    now = time.time()
    hits = [item for item in _hits[ip] if now - item < 60]
    if len(hits) >= LIMIT_PER_MINUTE:
        return {"ok": False}
    hits.append(now)
    _hits[ip] = hits

    record_error(
        f"前端错误：{payload.message}"[:500],
        detail=payload.detail,
        source="client",
        path=payload.path,
        user_id=user.id if user else None,
        notify=False,
    )
    return {"ok": True}
