from __future__ import annotations

import re
from datetime import datetime, timezone

from sqlalchemy import update
from sqlmodel import Session, select

from ..models.models import CreditLog, RedeemCode, User

FREE_SIGNUP_CREDITS = 100


class InsufficientCredits(Exception):
    def __init__(self, required: int, balance: int):
        super().__init__("额度不足")
        self.required = required
        self.balance = balance


class RedeemError(Exception):
    pass


def billable_chars(text: str) -> int:
    """Count characters that are charged: everything except whitespace."""
    return len(re.sub(r"\s", "", text or ""))


def _write_log(session: Session, user: User, delta: int, reason: str) -> CreditLog:
    log = CreditLog(
        user_id=user.id,
        delta=delta,
        reason=reason,
        balance_after=user.credits,
    )
    session.add(log)
    return log


def grant(session: Session, user: User, amount: int, reason: str) -> User:
    if amount == 0:
        return user
    user.credits = max(0, user.credits + amount)
    _write_log(session, user, amount, reason)
    session.add(user)
    return user


def charge(session: Session, user: User, amount: int, reason: str) -> User:
    if amount <= 0:
        return user
    # 原子扣减：并发请求同时扣费时，只有一个能成功，避免余额被扣成负数。
    result = session.exec(
        update(User)
        .where(User.id == user.id, User.credits >= amount)
        .values(credits=User.credits - amount)
    )
    if not getattr(result, "rowcount", 0):
        session.refresh(user)
        raise InsufficientCredits(amount, user.credits)
    session.flush()
    session.refresh(user)
    _write_log(session, user, -amount, reason)
    session.add(user)
    return user


def redeem(session: Session, user: User, code: str) -> int:
    normalized = (code or "").strip().upper()
    if not normalized:
        raise RedeemError("请输入兑换码")
    row = session.exec(select(RedeemCode).where(RedeemCode.code == normalized)).first()
    if row is None:
        raise RedeemError("兑换码不存在")
    if row.expires_at is not None:
        expires = row.expires_at
        if expires.tzinfo is None:
            expires = expires.replace(tzinfo=timezone.utc)
        if expires < datetime.now(timezone.utc):
            raise RedeemError("兑换码已过期")
    if row.used_count >= row.max_uses:
        raise RedeemError("兑换码已用尽")
    row.used_count += 1
    session.add(row)
    grant(session, user, row.credits, f"兑换码 {normalized}")
    session.commit()
    session.refresh(user)
    return row.credits


def logs(session: Session, user_id: int, limit: int = 50) -> list[CreditLog]:
    return list(
        session.exec(
            select(CreditLog)
            .where(CreditLog.user_id == user_id)
            .order_by(CreditLog.id.desc())
            .limit(limit)
        ).all()
    )
