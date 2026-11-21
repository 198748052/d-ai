from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta, timezone

from sqlmodel import Session, select

from ..models.models import EmailCode

CODE_TTL_MINUTES = 10
MAX_ATTEMPTS = 5
RESEND_SECONDS = 60
HOURLY_EMAIL_LIMIT = 5
HOURLY_IP_LIMIT = 20


class CodeError(Exception):
    pass


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def _digest(email: str, purpose: str, code: str) -> str:
    return hashlib.sha256(f"{email}:{purpose}:{code}".encode("utf-8")).hexdigest()


def _recent(
    session: Session,
    email: str,
    seconds: int,
    purpose: str | None = None,
) -> list[EmailCode]:
    since = _now() - timedelta(seconds=seconds)
    query = select(EmailCode).where(EmailCode.email == email)
    if purpose:
        query = query.where(EmailCode.purpose == purpose)
    rows = session.exec(query.order_by(EmailCode.id.desc())).all()
    return [row for row in rows if _aware(row.created_at) >= since]


def issue_code(session: Session, email: str, purpose: str, ip: str = "") -> str:
    recent = _recent(session, email, RESEND_SECONDS, purpose)
    if recent:
        raise CodeError(f"发送过于频繁，请 {RESEND_SECONDS} 秒后再试")
    if len(_recent(session, email, 3600)) >= HOURLY_EMAIL_LIMIT:
        raise CodeError("该邮箱今日验证码次数已达上限，请稍后再试")
    if ip:
        since = _now() - timedelta(hours=1)
        rows = session.exec(select(EmailCode).where(EmailCode.ip == ip)).all()
        if sum(1 for row in rows if _aware(row.created_at) >= since) >= HOURLY_IP_LIMIT:
            raise CodeError("请求过于频繁，请稍后再试")

    code = f"{secrets.randbelow(1_000_000):06d}"
    session.add(
        EmailCode(
            email=email,
            purpose=purpose,
            code_hash=_digest(email, purpose, code),
            expires_at=_now() + timedelta(minutes=CODE_TTL_MINUTES),
            ip=ip,
        )
    )
    session.commit()
    return code


def verify_code(session: Session, email: str, purpose: str, code: str) -> None:
    code = (code or "").strip()
    if not code:
        raise CodeError("请输入验证码")
    row = session.exec(
        select(EmailCode)
        .where(
            EmailCode.email == email,
            EmailCode.purpose == purpose,
            EmailCode.used == False,  # noqa: E712
        )
        .order_by(EmailCode.id.desc())
    ).first()
    if row is None:
        raise CodeError("请先获取验证码")
    if _aware(row.expires_at) < _now():
        raise CodeError("验证码已过期，请重新获取")
    if row.attempts >= MAX_ATTEMPTS:
        raise CodeError("验证码错误次数过多，请重新获取")
    if row.code_hash != _digest(email, purpose, code):
        row.attempts += 1
        session.add(row)
        session.commit()
        raise CodeError("验证码错误")
    row.used = True
    session.add(row)
    session.commit()
