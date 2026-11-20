from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session

from ..db.database import get_session
from ..deps import require_user
from ..models.models import User
from ..services.credits import RedeemError, logs, redeem

router = APIRouter(prefix="/api/credits", tags=["credits"])


class RedeemIn(BaseModel):
    code: str


@router.get("")
def read_balance(user: User = Depends(require_user)):
    return {"credits": user.credits, "email": user.email, "is_admin": user.is_admin}


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
