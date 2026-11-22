from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func
from sqlmodel import Session, select

from ..core.security import new_redeem_code
from ..db.database import get_session
from ..deps import require_admin
from ..models.models import CreditLog, ErrorLog, RedeemCode, RewriteJob, User
from ..services.credits import grant
from ..services.rewriter.rule_audit import audit_rules

router = APIRouter(prefix="/api/admin", tags=["admin"])


class AdjustIn(BaseModel):
    delta: int
    reason: str = "管理员调整"


class CodeIn(BaseModel):
    credits: int
    max_uses: int = 1
    expires_at: datetime | None = None


def _user_row(user: User) -> dict:
    return {
        "id": user.id,
        "email": user.email,
        "nickname": user.nickname,
        "credits": user.credits,
        "is_admin": user.is_admin,
        "created_at": user.created_at.isoformat() if user.created_at else "",
        "last_login_at": user.last_login_at.isoformat() if user.last_login_at else "",
    }


@router.get("/stats")
def stats(
    _: User = Depends(require_admin),
    session: Session = Depends(get_session),
):
    now = datetime.now(timezone.utc)
    today = now.replace(hour=0, minute=0, second=0, microsecond=0)
    week_ago = now - timedelta(days=7)
    day_ago = now - timedelta(hours=24)

    total_users = session.exec(select(func.count()).select_from(User)).one()
    users_today = session.exec(
        select(func.count()).select_from(User).where(User.created_at >= today)
    ).one()
    total_jobs = session.exec(select(func.count()).select_from(RewriteJob)).one()
    jobs_today = session.exec(
        select(func.count()).select_from(RewriteJob).where(RewriteJob.created_at >= today)
    ).one()
    chars_today = session.exec(
        select(func.coalesce(func.sum(RewriteJob.charged_chars), 0)).where(
            RewriteJob.created_at >= today
        )
    ).one()
    active_users = session.exec(
        select(func.count(func.distinct(RewriteJob.user_id))).where(
            RewriteJob.created_at >= week_ago,
            RewriteJob.user_id.is_not(None),
        )
    ).one()
    errors_24h = session.exec(
        select(func.count()).select_from(ErrorLog).where(ErrorLog.created_at >= day_ago)
    ).one()
    credits_total = session.exec(
        select(func.coalesce(func.sum(User.credits), 0))
    ).one()

    return {
        "total_users": int(total_users or 0),
        "users_today": int(users_today or 0),
        "total_jobs": int(total_jobs or 0),
        "jobs_today": int(jobs_today or 0),
        "chars_today": int(chars_today or 0),
        "active_users_7d": int(active_users or 0),
        "errors_24h": int(errors_24h or 0),
        "credits_total": int(credits_total or 0),
    }


@router.get("/rules/audit")
def rules_audit(_: User = Depends(require_admin)):
    return audit_rules()


@router.get("/errors")
def list_errors(
    limit: int = 50,
    _: User = Depends(require_admin),
    session: Session = Depends(get_session),
):
    rows = session.exec(
        select(ErrorLog).order_by(ErrorLog.id.desc()).limit(min(max(limit, 1), 200))
    ).all()
    return [
        {
            "id": row.id,
            "created_at": row.created_at.isoformat(),
            "source": row.source,
            "level": row.level,
            "message": row.message,
            "detail": row.detail[:1000],
            "path": row.path,
            "user_id": row.user_id,
        }
        for row in rows
    ]


@router.get("/users")
def list_users(
    limit: int = 100,
    _: User = Depends(require_admin),
    session: Session = Depends(get_session),
):
    rows = session.exec(
        select(User).order_by(User.id.desc()).limit(min(max(limit, 1), 500))
    ).all()
    return [_user_row(row) for row in rows]


@router.post("/users/{user_id}/credits")
def adjust_credits(
    user_id: int,
    payload: AdjustIn,
    _: User = Depends(require_admin),
    session: Session = Depends(get_session),
):
    user = session.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="用户不存在")
    if payload.delta == 0:
        raise HTTPException(status_code=422, detail="调整值不能为 0")
    if user.credits + payload.delta < 0:
        raise HTTPException(status_code=422, detail="调整后余额不能为负")
    grant(session, user, payload.delta, payload.reason.strip()[:60] or "管理员调整")
    session.commit()
    session.refresh(user)
    return _user_row(user)


@router.get("/redeem-codes")
def list_codes(
    limit: int = 100,
    _: User = Depends(require_admin),
    session: Session = Depends(get_session),
):
    rows = session.exec(
        select(RedeemCode).order_by(RedeemCode.id.desc()).limit(min(max(limit, 1), 500))
    ).all()
    return [
        {
            "id": row.id,
            "code": row.code,
            "credits": row.credits,
            "max_uses": row.max_uses,
            "used_count": row.used_count,
            "expires_at": row.expires_at.isoformat() if row.expires_at else "",
            "created_at": row.created_at.isoformat(),
        }
        for row in rows
    ]


@router.post("/redeem-codes")
def create_code(
    payload: CodeIn,
    admin: User = Depends(require_admin),
    session: Session = Depends(get_session),
):
    if payload.credits <= 0:
        raise HTTPException(status_code=422, detail="面额必须大于 0")
    if payload.max_uses <= 0:
        raise HTTPException(status_code=422, detail="可用次数必须大于 0")
    expires = payload.expires_at
    if expires is not None and expires.tzinfo is None:
        expires = expires.replace(tzinfo=timezone.utc)
    for _ in range(5):
        code = new_redeem_code()
        if session.exec(select(RedeemCode).where(RedeemCode.code == code)).first() is None:
            break
    else:
        raise HTTPException(status_code=500, detail="生成兑换码失败，请重试")
    row = RedeemCode(
        code=code,
        credits=payload.credits,
        max_uses=payload.max_uses,
        expires_at=expires,
        created_by=admin.id,
    )
    session.add(row)
    session.commit()
    session.refresh(row)
    return {
        "id": row.id,
        "code": row.code,
        "credits": row.credits,
        "max_uses": row.max_uses,
        "used_count": row.used_count,
    }


@router.get("/credit-logs")
def list_credit_logs(
    limit: int = 100,
    _: User = Depends(require_admin),
    session: Session = Depends(get_session),
):
    rows = session.exec(
        select(CreditLog).order_by(CreditLog.id.desc()).limit(min(max(limit, 1), 500))
    ).all()
    return [
        {
            "id": row.id,
            "user_id": row.user_id,
            "delta": row.delta,
            "reason": row.reason,
            "balance_after": row.balance_after,
            "created_at": row.created_at.isoformat(),
        }
        for row in rows
    ]
