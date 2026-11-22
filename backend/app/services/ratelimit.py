from __future__ import annotations

import threading
import time

WINDOW_SECONDS = 600
MAX_FAILURES = 5

_LOCK = threading.Lock()
_FAILURES: dict[str, list[float]] = {}


class LoginBlocked(Exception):
    def __init__(self, retry_after: int):
        super().__init__("登录失败次数过多")
        self.retry_after = retry_after


def _key(ip: str, email: str) -> str:
    return f"{ip}|{email.strip().lower()}"


def _prune(times: list[float], now: float) -> list[float]:
    return [value for value in times if now - value < WINDOW_SECONDS]


def check_login_allowed(ip: str, email: str) -> None:
    now = time.monotonic()
    key = _key(ip, email)
    with _LOCK:
        times = _prune(_FAILURES.get(key, []), now)
        if times:
            _FAILURES[key] = times
        else:
            _FAILURES.pop(key, None)
        if len(times) >= MAX_FAILURES:
            retry_after = max(1, int(WINDOW_SECONDS - (now - times[0])))
            raise LoginBlocked(retry_after)


def record_login_failure(ip: str, email: str) -> None:
    now = time.monotonic()
    key = _key(ip, email)
    with _LOCK:
        times = _prune(_FAILURES.get(key, []), now)
        times.append(now)
        _FAILURES[key] = times


def clear_login_failures(ip: str, email: str) -> None:
    with _LOCK:
        _FAILURES.pop(_key(ip, email), None)
