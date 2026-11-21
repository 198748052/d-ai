from __future__ import annotations

import asyncio
import smtplib
from email.header import Header
from email.mime.text import MIMEText

from ..core.config import (
    SMTP_FROM,
    SMTP_HOST,
    SMTP_PASSWORD,
    SMTP_PORT,
    SMTP_USER,
)


class EmailError(Exception):
    pass


def configured() -> bool:
    return bool(SMTP_USER and SMTP_PASSWORD)


def _send_sync(to: str, subject: str, body: str) -> None:
    message = MIMEText(body, "plain", "utf-8")
    message["Subject"] = Header(subject, "utf-8")
    message["From"] = SMTP_FROM
    message["To"] = to
    if SMTP_PORT == 465:
        client = smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, timeout=20)
    else:
        client = smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=20)
    try:
        if SMTP_PORT != 465:
            client.starttls()
        client.login(SMTP_USER, SMTP_PASSWORD)
        client.sendmail(SMTP_FROM, [to], message.as_string())
    finally:
        try:
            client.quit()
        except Exception:  # noqa: BLE001
            pass


async def send_code(to: str, code: str, purpose: str) -> None:
    if not configured():
        raise EmailError("邮件服务未配置")
    action = "注册" if purpose == "register" else "重置密码"
    subject = f"【降 AI 味改写平台】{action}验证码"
    body = (
        f"你的{action}验证码是：{code}\n\n"
        "有效期 10 分钟，请勿转发给他人。\n"
        "如果这不是你本人的操作，请忽略本邮件。"
    )
    await asyncio.to_thread(_send_sync, to, subject, body)
