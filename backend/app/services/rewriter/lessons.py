from __future__ import annotations

import difflib
import re
from collections import Counter
from datetime import datetime, timezone

from sqlalchemy import delete, or_
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
_CONSECUTIVE_PLACEHOLDER_RE = re.compile(r"(?:\{[^}]+\}){2,}")

_KEEP_WORDS = {
    "首先", "其次", "再次", "最后", "此外", "与此同时", "综上所述", "总而言之",
    "总的来说", "由此可见", "值得注意的是", "值得一提的是", "需要指出的是",
    "需要强调的是", "基于此", "在此背景下", "换言之", "换句话说", "也就是说",
    "简而言之", "一方面", "另一方面", "因此", "然而", "从而", "进而", "同时",
    "而且", "并且", "但是", "不过", "所以", "因为", "随着", "通过", "在", "对",
    "为", "使", "由", "从", "向", "与", "和", "及", "以及", "或", "而", "是",
    "有", "具有", "成为", "作为", "存在", "属于", "可以", "能够", "应该", "必须",
    "将", "会", "已经", "正在", "方面", "作用", "意义", "背景", "发展", "过程",
    "问题", "挑战", "机遇", "影响", "关系", "机制", "路径", "模式", "体系", "能力",
    "水平", "程度", "范围", "条件", "结果", "原因", "目标", "方法", "内容", "观点",
    "结论", "建议", "措施", "政策", "技术", "数据", "案例", "理论", "实践", "研究",
    "分析", "探讨", "构建", "实现", "提升", "优化", "促进", "推动", "保障", "支撑",
    "发挥", "提供", "形成", "产生", "导致", "带来", "面临", "需要", "表明", "显示",
    "指出", "认为", "提出", "发现", "证明", "说明", "强调", "关注", "讨论", "比较",
    "验证", "评估", "解决", "支持", "研究显示", "数据显示", "专家指出", "学者认为",
    "普遍认为", "值得注意", "不容忽视", "显而易见", "毋庸置疑",
}


def _normalize_pattern(text: str) -> str:
    value = _QUOTE_RE.sub("{引文}", text or "")
    value = _DATE_RE.sub("{日期}", value)
    value = _NUMBER_RE.sub("{数字}", value)
    value = _LATIN_RE.sub("{术语}", value)
    value = _WS_RE.sub("", value)
    return value[:200]


def extract_template(text: str) -> str:
    """Abstract a normalized sentence into a reusable sentence template.

    Content words become placeholders while connectors, prepositions and
    structural academic phrases stay visible, e.g.
    ``首先，值得注意的是，{内容}在{内容}方面{动词}了{数量}。``
    """
    pattern = text if "{" in text else _normalize_pattern(text)
    if not pattern:
        return ""
    placeholders = re.findall(r"\{[^}]+\}", pattern)
    protected = pattern
    for index, placeholder in enumerate(placeholders):
        protected = protected.replace(placeholder, f"ZZPH{index}ZZ", 1)
    try:
        import jieba.posseg as pseg

        tokens = list(pseg.cut(protected))
    except Exception:  # noqa: BLE001
        return pattern[:120]

    parts: list[str] = []
    for word, flag in tokens:
        if not word.strip():
            continue
        sentinel = re.fullmatch(r"ZZPH(\d+)ZZ", word)
        if sentinel:
            mapped = placeholders[int(sentinel.group(1))]
            if mapped == "{数字}":
                mapped = "{数量}"
            elif mapped == "{日期}":
                mapped = "{时间}"
        elif word in _KEEP_WORDS:
            mapped = word
        elif flag.startswith(("x", "w", "u", "c", "d", "p", "f")):
            mapped = word
        elif flag.startswith(("m", "q")):
            mapped = "{数量}"
        elif flag.startswith("t"):
            mapped = "{时间}"
        elif flag.startswith("n"):
            mapped = "{名词}"
        elif flag.startswith("v"):
            mapped = "{动词}"
        elif flag.startswith("a"):
            mapped = "{形容词}"
        elif flag.startswith("r"):
            mapped = "{指代}"
        elif flag == "eng":
            mapped = "{术语}"
        else:
            mapped = "{内容}"
        if parts and mapped == parts[-1]:
            continue
        parts.append(mapped)

    template = "".join(parts)
    template = re.sub(r"\[\{数量\}\]", "", template)
    template = re.sub(r"[（(]\{数量\}[）)]", "", template)
    template = _CONSECUTIVE_PLACEHOLDER_RE.sub("{内容}", template)
    template = re.sub(r"[，,]{2,}", "，", template)
    template = re.sub(r"^[，,、；;：:]+|[，,、；;：:]+$", "", template).strip()
    if not template:
        return pattern[:120]
    if "{" not in template:
        template = pattern
    return template[:120]


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
    template: str,
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
    if template:
        row = session.exec(
            select(RewriteLesson)
            .where(
                RewriteLesson.style == style,
                RewriteLesson.template == template,
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
    left = template or pattern or sentence
    for candidate in candidates:
        right = candidate.template or candidate.pattern or candidate.sentence
        score = _similarity(left, right)
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
    template = extract_template(pattern)
    resolved_category = category or _classify(text, style)
    resolved_strategy = strategy or DEFAULT_STRATEGIES.get(resolved_category, "")
    now = datetime.now(timezone.utc)
    try:
        with Session(engine) as session:
            row = _find_existing(session, style, pattern, template, text)
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
                row.template = row.template or template
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
                        template=template,
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


def backfill_templates() -> int:
    """Generate templates for legacy rows that only have pattern/sentence."""
    with Session(engine) as session:
        rows = session.exec(select(RewriteLesson)).all()
        updated = 0
        for row in rows:
            source = row.pattern or row.sentence
            if not source:
                continue
            if row.template and row.template not in {row.pattern, row.sentence}:
                continue
            template = extract_template(source)
            if template and template != row.template:
                row.template = template
                row.updated_at = datetime.now(timezone.utc)
                session.add(row)
                updated += 1
        if updated:
            session.commit()
        return updated


def _format_hint(row: RewriteLesson) -> str:
    label = CATEGORY_LABELS.get(row.category, row.category or "低困惑度")
    pattern = (row.template or row.pattern or row.sentence or "").strip()[:90]
    strategy = (row.strategy or DEFAULT_STRATEGIES.get(row.category, "")).strip()
    return f"[{label}] {pattern}" + (f" → {strategy}" if strategy else "")


def _is_useful(row: RewriteLesson) -> bool:
    text = row.template or row.pattern or row.sentence
    return len(re.findall(r"[\u4e00-\u9fff]", text or "")) >= 8


def recent_lesson_rows(style: str, limit: int = 10) -> list[RewriteLesson]:
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
    return [
        row
        for row in rows
        if (row.sentence or row.pattern) and _is_useful(row)
    ]


def recent_lessons(style: str, limit: int = 10) -> list[str]:
    """Return formatted avoidance hints for the prompt."""
    return [_format_hint(row) for row in recent_lesson_rows(style, limit)]


def recent_forbidden_templates(style: str, limit: int = 10) -> list[str]:
    """Return raw templates that must not appear in the rewritten text."""
    return [
        (row.template or row.pattern or row.sentence).strip()
        for row in recent_lesson_rows(style, limit)
    ]


def match_forbidden_templates(text: str, templates: list[str]) -> list[str]:
    """Return templates that still appear in the generated text."""
    hits: list[str] = []
    for template in templates:
        if not template or len(template) < 8:
            continue
        parts = re.split(r"(\{[^}]+\})", template)
        regex = "".join(
            ".+?" if part.startswith("{") else re.escape(part) for part in parts
        )
        try:
            if re.search(regex, text or ""):
                hits.append(template)
        except re.error:
            continue
    return hits


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


def clear_lessons(style: str | None = None) -> int:
    """Delete every lesson row, optionally limited to one style."""
    with Session(engine) as session:
        statement = delete(RewriteLesson)
        if style:
            statement = statement.where(RewriteLesson.style == style)
        result = session.execute(statement)
        session.commit()
        return result.rowcount or 0


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
