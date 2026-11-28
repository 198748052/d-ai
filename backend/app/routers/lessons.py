from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from ..deps import require_admin
from ..models.models import RewriteLesson
from ..services.rewriter.lessons import (
    clear_lessons as clear_lessons_service,
    lesson_stats,
    list_lessons,
    update_lesson,
)

router = APIRouter(prefix="/api/lessons", tags=["lessons"])


class LessonUpdateIn(BaseModel):
    status: str | None = None
    category: str | None = None
    strategy: str | None = None
    note: str | None = None


def _serialize(row: RewriteLesson) -> dict:
    return {
        "id": row.id,
        "style": row.style,
        "kind": row.kind,
        "sentence": row.sentence,
        "pattern": row.pattern,
        "template": row.template,
        "category": row.category,
        "outcome": row.outcome,
        "status": row.status,
        "scope": row.scope,
        "strategy": row.strategy,
        "original": row.original,
        "perplexity": row.perplexity,
        "threshold": row.threshold,
        "hits": row.hits,
        "source_job_id": row.source_job_id,
        "note": row.note,
        "last_seen_at": row.last_seen_at.isoformat() if row.last_seen_at else "",
        "created_at": row.created_at.isoformat() if row.created_at else "",
        "updated_at": row.updated_at.isoformat() if row.updated_at else "",
    }


@router.get("")
def read_lessons(
    style: str | None = None,
    status: str | None = None,
    category: str | None = None,
    outcome: str | None = None,
    q: str | None = None,
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    _: object = Depends(require_admin),
):
    return [
        _serialize(row)
        for row in list_lessons(
            style=style,
            status=status,
            category=category,
            outcome=outcome,
            keyword=q,
            limit=limit,
            offset=offset,
        )
    ]


@router.get("/stats")
def read_stats(
    style: str | None = None,
    _: object = Depends(require_admin),
):
    return lesson_stats(style=style)


@router.get("/count")
def count_lessons(
    style: str | None = None,
    _: object = Depends(require_admin),
):
    return {"count": lesson_stats(style=style)["total"]}


@router.delete("")
def clear_all_lessons(
    style: str | None = None,
    _: object = Depends(require_admin),
):
    return {"ok": True, "deleted": clear_lessons_service(style=style)}


@router.put("/{lesson_id}")
def edit_lesson(
    lesson_id: int,
    payload: LessonUpdateIn,
    _: object = Depends(require_admin),
):
    row = update_lesson(
        lesson_id,
        status=payload.status,
        category=payload.category,
        strategy=payload.strategy,
        note=payload.note,
    )
    if row is None:
        return {"ok": False}
    return _serialize(row)


@router.delete("/{lesson_id}")
def delete_lesson(
    lesson_id: int,
    _: object = Depends(require_admin),
):
    from ..db.database import engine
    from sqlmodel import Session

    with Session(engine) as session:
        row = session.get(RewriteLesson, lesson_id)
        if row is None:
            return {"ok": False}
        session.delete(row)
        session.commit()
    return {"ok": True}
