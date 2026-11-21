from __future__ import annotations

import asyncio
import time
import uuid
from dataclasses import dataclass, field


@dataclass
class Job:
    id: str
    total: int
    status: str = "running"  # running | done | error
    completed: int = 0
    paragraphs: dict[int, dict] = field(default_factory=dict)
    stats: dict | None = None
    audit: dict | None = None
    warnings: list[str] = field(default_factory=list)
    ppl_issues: list[dict] = field(default_factory=list)
    content_report: dict | None = None
    structure_changes: list[str] = field(default_factory=list)
    candidate_scores: list[dict] = field(default_factory=list)
    error: str | None = None
    created_at: float = field(default_factory=time.time)
    finished_at: float | None = None
    task: object | None = None
    db_id: int | None = None
    user_id: int | None = None
    charged: int = 0
    pause_event: asyncio.Event = field(default_factory=asyncio.Event)


JOBS: dict[str, Job] = {}


def _cleanup() -> None:
    if len(JOBS) <= 80:
        return
    finished = sorted(
        (job for job in JOBS.values() if job.status in {"done", "error"}),
        key=lambda job: job.created_at,
    )
    for job in finished[: len(JOBS) - 60]:
        JOBS.pop(job.id, None)


def new_job(total: int) -> Job:
    job = Job(id=uuid.uuid4().hex, total=total)
    job.pause_event.set()
    JOBS[job.id] = job
    _cleanup()
    return job


def get_job(job_id: str) -> Job | None:
    return JOBS.get(job_id)
