from __future__ import annotations

import difflib
import re
from collections import Counter
from datetime import datetime, timezone

from sqlalchemy import or_
from sqlmodel import Session, select

from ...db.database import engine
from ...models.models import RewriteLesson
from .diagnosis import diagnose

CATEGORY_LABELS = {
    "low_perplexity": "低困惑度",
    "template": "模板句式",
    "high_freq": "高频套话",
    "hollow": "空洞升华",
    "register": "语体错位",
    "leakage": "过程痕迹",
    "structure": "结构问题",
}

DEFAULT_STRATEGIES = {
    "low_perplexity": "换语序、补限定条件或具体细节",
    "template": "删掉模板连接词，直接进入对象或结论",
    "high_freq": "换成具体动作、数据或案例",
    "hollow": "删掉拔高，写具体影响",
    "register": "改回学术语体",
    "leakage": "删除过程痕迹",
    "structure": "调整句子边界和长短节奏",
}

_NUMBER_RE = re.compile(r"\d+(?:\.\d+)?%?")
_DATE_RE = re.compile(
    r"\d{4}(?:[-/]\d{1,2}(?:[-/]\d{1,2})?|年(?:\d{1,2}月(?:\d{1,2}日)?)?)"
)
_QUOTE_RE = re.compile(r"“[^”]{1,40}”|「[^」]{1,40}」|『[^』]{1,40}』")
_LATIN_RE = re.compile(r"[A-Za-z][A-Za-z0-9_\-]{2,}")
_WS_RE = re.compile(r"\s+")
_SIMILARITY_THRESHOLD = 0.85


def _normalize_pattern(text: str) -> str:
    value = _QUOTE_RE.sub("{引文}", text or "")
    value = _DATE_RE.sub("{日期}", value)
    value = _NUMBER_RE.sub("{数字}", value)
    value = _LATIN_RE.sub("{术语}", value)
    value = _WS_RE.sub("", value)
    return value[:200]


def _similarity(left: str, right: str) -> float:
    if not left or not right:
        return 0.0
    return difflib.SequenceMatcher(None, left, right).ratio()


def _classify(text: str, style: str) -> str:
    try:
        result = diagnose(text, style)
        category = str(result.get("dominant") or "")
        if category in CATEGORY_LABELS:
            return category
    except Exception:  # noqa: BLE001
        pass
    return "low_perplexity"


def _find_existing(
    session: Session,
    style: str,
    pattern: str,
    sentence: str,
) -> RewriteLesson | None:
    row = session.exec(
        select(RewriteLesson).where(
            RewriteLesson.style == style,
            RewriteLesson.sentence == sentence,
        )
    ).first()
    if row is not None:
        return row
    if pattern:
        row = session.exec(
            select(RewriteLesson)
            .where(
                RewriteLesson.style == style,
                RewriteLesson.pattern == pattern,
            )
            .order_by(RewriteLesson.hits.desc())
        ).first()
        if row is not None:
            return row
    candidates = session.exec(
        select(RewriteLesson)
        .where(RewriteLesson.style == style)
        .order_by(RewriteLesson.last_seen_at.desc(), RewriteLesson.hits.desc())
        .limit(300)
    ).all()
    best: RewriteLesson | None = None
    best_score = 0.0
    for candidate in candidates:
        score = _similarity(pattern or sentence, candidate.pattern or candidate.sentence)
        if score >= _SIMILARITY_THRESHOLD and score > best_score:
            best = candidate
            best_score = score
    return best


def record_lesson(
    style: str,
    sentence: str,
    original: str = "",
    perplexity: float = 0.0,
    threshold: float = 0.0,
    note: str = "",
    outcome: str = "pending",
    scope: str = "sentence",
    source_job_id: int | None = None,
    increment_hits: bool = False,
    category: str = "",
    strategy: str = "",
) -> None:
    """Persist a low-perplexity sentence or clause in the avoidance library."""
    text = (sentence or "").strip()
    if not text or len(text) < 10:
        return
    pattern = _normalize_pattern(text)
    # 纯引用、纯数字或信息量过低的片段不适合作为避雷模式。
    if len(re.findall(r"[\u4e00-\u9fff]", pattern)) < 8:
        return
    resolved_category = category or _classify(text, style)
    resolved_strategy = strategy or DEFAULT_STRATEGIES.get(resolved_category, "")
    now = datetime.now(timezone.utc)
    try:
        with Session(engine) as session:
            row = _find_existing(session, style, pattern, text)
            if row is not None:
                old_job = row.source_job_id
                if increment_hits and (source_job_id is None or old_job != source_job_id):
                    row.hits += 1
                if perplexity > 0:
                    row.perplexity = round(
                        min(row.perplexity or perplexity, perplexity), 2
                    )
                if threshold > 0:
                    row.threshold = round(threshold, 2)
                if outcome == "survived":
                    row.outcome = "survived"
                elif row.outcome != "survived":
                    row.outcome = outcome
                if row.status != "ignored" and outcome == "survived":
                    row.status = "active"
                row.last_seen_at = now
                row.updated_at = now
                if source_job_id is not None:
                    row.source_job_id = source_job_id
                row.pattern = row.pattern or pattern
                if resolved_category and (
                    not row.category or row.category == "low_perplexity"
                ):
                    row.category = resolved_category
                row.strategy = row.strategy or resolved_strategy
                row.scope = row.scope or scope
                row.note = note or row.note
                session.add(row)
            else:
                session.add(
                    RewriteLesson(
                        style=style,
                        kind="low_perplexity",
                        sentence=text,
                        pattern=pattern,
                        category=resolved_category,
                        outcome=outcome,
                        status="active",
                        scope=scope,
                        strategy=resolved_strategy,
                        original=(original or "").strip(),
                        perplexity=round(perplexity, 2),
                        threshold=round(threshold, 2),
                        hits=1,
                        source_job_id=source_job_id,
                        last_seen_at=now,
                        note=note,
                    )
                )
            session.commit()
    except Exception:  # noqa: BLE001
        pass


def _format_hint(row: RewriteLesson) -> str:
    label = CATEGORY_LABELS.get(row.category, row.category or "低困惑度")
    pattern = (row.pattern or row.sentence or "").strip()[:90]
    strategy = (row.strategy or DEFAULT_STRATEGIES.get(row.category, "")).strip()
    return f"[{label}] {pattern}" + (f" → {strategy}" if strategy else "")


def recent_lessons(style: str, limit: int = 10) -> list[str]:
    """Return formatted avoidance hints for the prompt."""
    try:
        with Session(engine) as session:
            survived = session.exec(
                select(RewriteLesson)
                .where(
                    RewriteLesson.style == style,
                    RewriteLesson.status == "active",
                    RewriteLesson.outcome == "survived",
                )
                .order_by(RewriteLesson.hits.desc(), RewriteLesson.last_seen_at.desc())
                .limit(limit)
            ).all()
            rows = list(survived)
            if len(rows) < limit:
                fixed = session.exec(
                    select(RewriteLesson)
                    .where(
                        RewriteLesson.style == style,
                        RewriteLesson.status == "active",
                        RewriteLesson.outcome == "fixed",
                    )
                    .order_by(RewriteLesson.hits.desc(), RewriteLesson.last_seen_at.desc())
                    .limit(limit - len(rows))
                ).all()
                rows.extend(fixed)
    except Exception:  # noqa: BLE001
        return []
    return [_format_hint(row) for row in rows if row.sentence or row.pattern]


def list_lessons(
    style: str | None = None,
    status: str | None = None,
    category: str | None = None,
    outcome: str | None = None,
    keyword: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> list[RewriteLesson]:
    with Session(engine) as session:
        query = select(RewriteLesson)
        if style:
            query = query.where(RewriteLesson.style == style)
        if status:
            query = query.where(RewriteLesson.status == status)
        if category:
            query = query.where(RewriteLesson.category == category)
        if outcome:
            query = query.where(RewriteLesson.outcome == outcome)
        if keyword:
            value = f"%{keyword.strip()}%"
            query = query.where(
                or_(
                    RewriteLesson.sentence.like(value),
                    RewriteLesson.pattern.like(value),
                    RewriteLesson.note.like(value),
                )
            )
        query = query.order_by(
            RewriteLesson.hits.desc(),
            RewriteLesson.last_seen_at.desc(),
            RewriteLesson.updated_at.desc(),
        )
        return list(session.exec(query.offset(offset).limit(limit)).all())


def lesson_stats(style: str | None = None) -> dict:
    with Session(engine) as session:
        query = select(RewriteLesson)
        if style:
            query = query.where(RewriteLesson.style == style)
        rows = session.exec(query).all()
    return {
        "total": len(rows),
        "active": sum(1 for row in rows if row.status == "active"),
        "ignored": sum(1 for row in rows if row.status == "ignored"),
        "resolved": sum(1 for row in rows if row.status == "resolved"),
        "survived": sum(1 for row in rows if row.outcome == "survived"),
        "fixed": sum(1 for row in rows if row.outcome == "fixed"),
        "pending": sum(1 for row in rows if row.outcome == "pending"),
        "categories": dict(Counter(row.category for row in rows)),
    }


def update_lesson(
    lesson_id: int,
    status: str | None = None,
    category: str | None = None,
    strategy: str | None = None,
    note: str | None = None,
) -> RewriteLesson | None:
    with Session(engine) as session:
        row = session.get(RewriteLesson, lesson_id)
        if row is None:
            return None
        if status is not None:
            row.status = status
        if category is not None:
            row.category = category
        if strategy is not None:
            row.strategy = strategy
        if note is not None:
            row.note = note
        row.updated_at = datetime.now(timezone.utc)
        session.add(row)
        session.commit()
        session.refresh(row)
        return row
