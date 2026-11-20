from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel
from sqlmodel import Session, select

from ..core.security import (
    hash_password,
    new_session_token,
    token_digest,
    verify_password,
)
from ..db.database import get_session
from ..deps import SESSION_COOKIE, SESSION_DAYS, current_user, require_user
from ..models.models import AuthSession, User
from ..services.credits import FREE_SIGNUP_CREDITS, grant

router = APIRouter(prefix="/api/auth", tags=["auth"])

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class RegisterIn(BaseModel):
    email: str
    password: str
    nickname: str = ""


class LoginIn(BaseModel):
    email: str
    password: str


def _profile(user: User) -> dict:
    return {
        "id": user.id,
        "email": user.email,
        "nickname": user.nickname,
        "credits": user.credits,
        "is_admin": user.is_admin,
    }


def _start_session(session: Session, user: User, response: Response) -> None:
    token = new_session_token()
    expires = datetime.now(timezone.utc) + timedelta(days=SESSION_DAYS)
    session.add(
        AuthSession(
            user_id=user.id,
            token_hash=token_digest(token),
            expires_at=expires,
        )
    )
    session.commit()
    response.set_cookie(
        SESSION_COOKIE,
        token,
        max_age=SESSION_DAYS * 24 * 3600,
        httponly=True,
        samesite="lax",
        path="/",
    )


@router.post("/register")
def register(
    payload: RegisterIn,
    response: Response,
    session: Session = Depends(get_session),
):
    email = payload.email.strip().lower()
    if not _EMAIL_RE.match(email):
        raise HTTPException(status_code=422, detail="邮箱格式不正确")
    if len(payload.password) < 8:
        raise HTTPException(status_code=422, detail="密码至少 8 位")
    existing = session.exec(select(User).where(User.email == email)).first()
    if existing is not None:
        raise HTTPException(status_code=409, detail="该邮箱已注册，请直接登录")

    is_first = session.exec(select(User)).first() is None
    user = User(
        email=email,
        password_hash=hash_password(payload.password),
        nickname=payload.nickname.strip()[:32],
        credits=0,
        is_admin=is_first,
        last_login_at=datetime.now(timezone.utc),
    )
    session.add(user)
    session.commit()
    session.refresh(user)
    grant(session, user, FREE_SIGNUP_CREDITS, "注册赠送")
    session.commit()
    session.refresh(user)
    _start_session(session, user, response)
    return _profile(user)


@router.post("/login")
def login(
    payload: LoginIn,
    response: Response,
    session: Session = Depends(get_session),
):
    email = payload.email.strip().lower()
    user = session.exec(select(User).where(User.email == email)).first()
    if user is None or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=401, detail="邮箱或密码错误")
    user.last_login_at = datetime.now(timezone.utc)
    session.add(user)
    session.commit()
    _start_session(session, user, response)
    return _profile(user)


@router.post("/logout")
def logout(
    request: Request,
    response: Response,
    session: Session = Depends(get_session),
):
    token = request.cookies.get(SESSION_COOKIE)
    if token:
        row = session.exec(
            select(AuthSession).where(AuthSession.token_hash == token_digest(token))
        ).first()
        if row is not None:
            session.delete(row)
            session.commit()
    response.delete_cookie(SESSION_COOKIE, path="/")
    return {"ok": True}


@router.get("/me")
def me(user: User | None = Depends(current_user)):
    if user is None:
        return {"user": None}
    return {"user": _profile(user)}


@router.put("/profile")
def update_profile(
    payload: dict,
    user: User = Depends(require_user),
    session: Session = Depends(get_session),
):
    nickname = str(payload.get("nickname") or "").strip()[:32]
    user.nickname = nickname
    session.add(user)
    session.commit()
    session.refresh(user)
    return _profile(user)
