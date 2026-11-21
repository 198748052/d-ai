from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel
from sqlmodel import Session, select

from ..core.config import EMAIL_CODE_ECHO
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
from ..services.emailer import EmailError, configured as email_configured, send_code
from ..services.verification import CodeError, issue_code, verify_code

router = APIRouter(prefix="/api/auth", tags=["auth"])

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_QQ_RE = re.compile(r"^[A-Za-z0-9._%+-]+@qq\.com$")


class RegisterIn(BaseModel):
    email: str
    password: str
    code: str = ""
    nickname: str = ""
    agreed_terms: bool = False


class LoginIn(BaseModel):
    email: str
    password: str


class SendCodeIn(BaseModel):
    email: str
    purpose: str = "register"  # register | reset


class ResetPasswordIn(BaseModel):
    email: str
    code: str
    password: str


class ChangePasswordIn(BaseModel):
    old_password: str
    new_password: str


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


@router.post("/send-code")
async def send_verification_code(
    payload: SendCodeIn,
    request: Request,
    session: Session = Depends(get_session),
):
    email = payload.email.strip().lower()
    if not _QQ_RE.match(email):
        raise HTTPException(status_code=422, detail="目前仅支持 QQ 邮箱注册")
    if payload.purpose not in {"register", "reset"}:
        raise HTTPException(status_code=422, detail="验证码用途不正确")

    user = session.exec(select(User).where(User.email == email)).first()
    if payload.purpose == "register" and user is not None:
        raise HTTPException(status_code=409, detail="该邮箱已注册，请直接登录")
    if payload.purpose == "reset" and user is None:
        raise HTTPException(status_code=404, detail="该邮箱尚未注册")

    if not email_configured() and not EMAIL_CODE_ECHO:
        raise HTTPException(
            status_code=503,
            detail="邮件服务未配置，请联系管理员设置 SMTP 后再试",
        )

    ip = request.client.host if request.client else ""
    try:
        code = issue_code(session, email, payload.purpose, ip=ip)
    except CodeError as exc:
        raise HTTPException(status_code=429, detail=str(exc)) from exc

    if EMAIL_CODE_ECHO:
        return {"sent": True, "debug_code": code}

    try:
        await send_code(email, code, payload.purpose)
    except EmailError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"验证码发送失败：{exc}") from exc
    return {"sent": True}


@router.post("/register")
def register(
    payload: RegisterIn,
    response: Response,
    session: Session = Depends(get_session),
):
    email = payload.email.strip().lower()
    if not _QQ_RE.match(email):
        raise HTTPException(status_code=422, detail="目前仅支持 QQ 邮箱注册")
    if len(payload.password) < 8:
        raise HTTPException(status_code=422, detail="密码至少 8 位")
    if not payload.agreed_terms:
        raise HTTPException(status_code=422, detail="请先阅读并同意用户协议和隐私政策")
    existing = session.exec(select(User).where(User.email == email)).first()
    if existing is not None:
        raise HTTPException(status_code=409, detail="该邮箱已注册，请直接登录")

    try:
        verify_code(session, email, "register", payload.code)
    except CodeError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

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


@router.post("/reset-password")
def reset_password(
    payload: ResetPasswordIn,
    session: Session = Depends(get_session),
):
    email = payload.email.strip().lower()
    if len(payload.password) < 8:
        raise HTTPException(status_code=422, detail="新密码至少 8 位")
    user = session.exec(select(User).where(User.email == email)).first()
    if user is None:
        raise HTTPException(status_code=404, detail="该邮箱尚未注册")
    try:
        verify_code(session, email, "reset", payload.code)
    except CodeError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    user.password_hash = hash_password(payload.password)
    session.add(user)
    for row in session.exec(select(AuthSession).where(AuthSession.user_id == user.id)).all():
        session.delete(row)
    session.commit()
    return {"ok": True}


@router.post("/change-password")
def change_password(
    payload: ChangePasswordIn,
    response: Response,
    user: User = Depends(require_user),
    session: Session = Depends(get_session),
):
    if not verify_password(payload.old_password, user.password_hash):
        raise HTTPException(status_code=422, detail="原密码不正确")
    if len(payload.new_password) < 8:
        raise HTTPException(status_code=422, detail="新密码至少 8 位")
    if payload.old_password == payload.new_password:
        raise HTTPException(status_code=422, detail="新密码不能与原密码相同")
    user.password_hash = hash_password(payload.new_password)
    session.add(user)
    for row in session.exec(select(AuthSession).where(AuthSession.user_id == user.id)).all():
        session.delete(row)
    session.commit()
    _start_session(session, user, response)
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
