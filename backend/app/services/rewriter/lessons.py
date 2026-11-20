from __future__ import annotations

from datetime import datetime, timezone

from sqlmodel import Session, select

from ...db.database import engine
from ...models.models import RewriteLesson


def record_lesson(
    style: str,
    sentence: str,
    original: str = "",
    perplexity: float = 0.0,
    threshold: float = 0.0,
    note: str = "",
) -> None:
    """Persist a low-perplexity sentence that survived every regeneration attempt."""
    text = (sentence or "").strip()
    if not text:
        return
    now = datetime.now(timezone.utc)
    try:
        with Session(engine) as session:
            row = session.exec(
                select(RewriteLesson).where(
                    RewriteLesson.style == style,
                    RewriteLesson.sentence == text,
                )
            ).first()
            if row is not None:
                row.hits += 1
                row.perplexity = round(min(row.perplexity or perplexity, perplexity), 2)
                row.updated_at = now
            else:
                session.add(
                    RewriteLesson(
                        style=style,
                        kind="low_perplexity",
                        sentence=text,
                        original=(original or "").strip(),
                        perplexity=round(perplexity, 2),
                        threshold=round(threshold, 2),
                        note=note,
                    )
                )
            session.commit()
    except Exception:  # noqa: BLE001
        pass


def recent_lessons(style: str, limit: int = 8) -> list[str]:
    """Return the most repeated low-perplexity sentences for a writing style."""
    try:
        with Session(engine) as session:
            rows = session.exec(
                select(RewriteLesson)
                .where(RewriteLesson.style == style)
                .order_by(RewriteLesson.hits.desc(), RewriteLesson.updated_at.desc())
                .limit(limit)
            ).all()
    except Exception:  # noqa: BLE001
        return []
    return [row.sentence for row in rows if row.sentence]


def list_lessons(style: str | None = None, limit: int = 100) -> list[RewriteLesson]:
    with Session(engine) as session:
        query = select(RewriteLesson)
        if style:
            query = query.where(RewriteLesson.style == style)
        query = query.order_by(RewriteLesson.hits.desc(), RewriteLesson.updated_at.desc())
        return list(session.exec(query.limit(limit)).all())
