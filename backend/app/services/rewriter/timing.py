from __future__ import annotations

import threading
import time
from contextvars import ContextVar
from dataclasses import asdict, dataclass


@dataclass
class RewriteTiming:
    total_seconds: float = 0.0
    llm_calls: int = 0
    llm_seconds: float = 0.0
    ppl_calls: int = 0
    ppl_seconds: float = 0.0
    rule_seconds: float = 0.0
    rhythm_calls: int = 0
    coverage_passes: int = 0

    def as_dict(self) -> dict:
        return asdict(self)


_CURRENT: ContextVar[RewriteTiming | None] = ContextVar("rewrite_timing", default=None)
_LOCK = threading.Lock()


def start_timing() -> RewriteTiming:
    timing = RewriteTiming()
    _CURRENT.set(timing)
    return timing


def current_timing() -> RewriteTiming | None:
    return _CURRENT.get()


def add_llm(seconds: float) -> None:
    timing = _CURRENT.get()
    if timing is not None:
        with _LOCK:
            timing.llm_calls += 1
            timing.llm_seconds += seconds


def add_ppl(seconds: float) -> None:
    timing = _CURRENT.get()
    if timing is not None:
        with _LOCK:
            timing.ppl_calls += 1
            timing.ppl_seconds += seconds


def add_rule(seconds: float) -> None:
    timing = _CURRENT.get()
    if timing is not None:
        with _LOCK:
            timing.rule_seconds += seconds


def add_rhythm() -> None:
    timing = _CURRENT.get()
    if timing is not None:
        with _LOCK:
            timing.rhythm_calls += 1


def add_coverage() -> None:
    timing = _CURRENT.get()
    if timing is not None:
        with _LOCK:
            timing.coverage_passes += 1


def finish_timing(timing: RewriteTiming, started: float) -> dict:
    with _LOCK:
        timing.total_seconds = round(time.perf_counter() - started, 2)
        return timing.as_dict()
