from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, select

from ..db.database import get_session
from ..deps import require_user
from ..models.models import RewriteJob, User
from ..services.credits import RedeemError, logs, redeem

router = APIRouter(prefix="/api/credits", tags=["credits"])


class RedeemIn(BaseModel):
    code: str


@router.get("")
def read_balance(user: User = Depends(require_user)):
    return {"credits": user.credits, "email": user.email, "is_admin": user.is_admin}


@router.get("/usage")
def read_usage(
    days: int = 7,
    user: User = Depends(require_user),
    session: Session = Depends(get_session),
):
    days = min(max(days, 1), 30)
    now = datetime.now(timezone.utc)
    start = (now - timedelta(days=days - 1)).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    rows = session.exec(
        select(RewriteJob).where(
            RewriteJob.user_id == user.id,
            RewriteJob.created_at >= start,
        )
    ).all()
    buckets: dict[str, dict] = {}
    for offset in range(days):
        day = (start + timedelta(days=offset)).date().isoformat()
        buckets[day] = {"date": day, "chars": 0, "jobs": 0}
    for row in rows:
        created = row.created_at
        if created.tzinfo is None:
            created = created.replace(tzinfo=timezone.utc)
        key = created.date().isoformat()
        if key in buckets:
            buckets[key]["chars"] += int(row.charged_chars or 0)
            buckets[key]["jobs"] += 1
    return list(buckets.values())


@router.get("/logs")
def read_logs(
    limit: int = 50,
    user: User = Depends(require_user),
    session: Session = Depends(get_session),
):
    rows = logs(session, user.id, limit=min(max(limit, 1), 200))
    return [
        {
            "id": row.id,
            "delta": row.delta,
            "reason": row.reason,
            "balance_after": row.balance_after,
            "created_at": row.created_at.isoformat(),
        }
        for row in rows
    ]


@router.post("/redeem")
def redeem_code(
    payload: RedeemIn,
    user: User = Depends(require_user),
    session: Session = Depends(get_session),
):
    try:
        amount = redeem(session, user, payload.code)
    except RedeemError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"credits": user.credits, "added": amount}
