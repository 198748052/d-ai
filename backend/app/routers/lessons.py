from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlmodel import Session, select

from ..db.database import get_session
from ..deps import require_admin
from ..models.models import RewriteLesson
from ..services.rewriter.lessons import list_lessons

router = APIRouter(prefix="/api/lessons", tags=["lessons"])


def _serialize(row: RewriteLesson) -> dict:
    return {
        "id": row.id,
        "style": row.style,
        "kind": row.kind,
        "sentence": row.sentence,
        "original": row.original,
        "perplexity": row.perplexity,
        "threshold": row.threshold,
        "hits": row.hits,
        "note": row.note,
        "created_at": row.created_at.isoformat() if row.created_at else "",
        "updated_at": row.updated_at.isoformat() if row.updated_at else "",
    }


@router.get("")
def read_lessons(
    style: str | None = None,
    limit: int = Query(100, ge=1, le=500),
):
    return [_serialize(row) for row in list_lessons(style=style, limit=limit)]


@router.get("/count")
def count_lessons(style: str | None = None):
    from ..db.database import engine

    with Session(engine) as session:
        query = select(RewriteLesson)
        if style:
            query = query.where(RewriteLesson.style == style)
        rows = session.exec(query).all()
    return {"count": len(rows)}


@router.delete("/{lesson_id}")
def delete_lesson(lesson_id: int, _: object = Depends(require_admin)):
    from ..db.database import engine

    with Session(engine) as session:
        row = session.get(RewriteLesson, lesson_id)
        if row is None:
            return {"ok": False}
        session.delete(row)
        session.commit()
    return {"ok": True}
