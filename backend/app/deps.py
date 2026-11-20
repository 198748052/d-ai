from __future__ import annotations

from datetime import datetime, timezone

from fastapi import Depends, HTTPException, Request
from sqlmodel import Session, select

from .core.security import token_digest
from .db.database import get_session
from .models.models import AuthSession, User

SESSION_COOKIE = "sid"
SESSION_DAYS = 30


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def current_user(
    request: Request,
    session: Session = Depends(get_session),
) -> User | None:
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        return None
    row = session.exec(
        select(AuthSession).where(AuthSession.token_hash == token_digest(token))
    ).first()
    if row is None:
        return None
    if _aware(row.expires_at) < datetime.now(timezone.utc):
        session.delete(row)
        session.commit()
        return None
    return session.get(User, row.user_id)


def require_user(user: User | None = Depends(current_user)) -> User:
    if user is None:
        raise HTTPException(status_code=401, detail="请先登录")
    return user


def require_admin(user: User = Depends(require_user)) -> User:
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="需要管理员权限")
    return user
