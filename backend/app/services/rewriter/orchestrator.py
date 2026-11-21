from __future__ import annotations

import asyncio
import difflib
import json
import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

from sqlmodel import Session, select

from ...models.models import FeatureRule, LLMSetting, Preset
from ...schemas import (
    AuditResult,
    PPLIssue,
    ParagraphResult,
    RewriteRequest,
    RewriteResponse,
    RewriteStats,
)
from ..protector import Protector
from ..segmenter import join_paragraphs, split_paragraphs, split_sentences
from .audit import audit_text, collect_hits
from .features import ai_likeness, analyze, paragraph_metrics, uniform_runs
from .lessons import recent_lessons, record_lesson
from .llm_engine import LLMContext, LLMEngine, LLMError
from .rule_engine import RewriteOptions, Rule, RuleEngine

EmitFn = Callable[[ParagraphResult], Awaitable[None]]


_HEADING_RE = re.compile(
    r"^\s*(?:[（(][一二三四五六七八九十\d]+[）)]|\d+[.、]|[一二三四五六七八九十]+[、.])[^\n]{0,40}$"
)


def _is_heading(text: str) -> bool:
    stripped = text.strip()
    return len(stripped) <= 40 and bool(_HEADING_RE.match(stripped))



def _has_duplication(text: str, window: int = 40, step: int = 10) -> bool:
    seen: set[str] = set()
    for index in range(0, max(1, len(text) - window), step):
        chunk = text[index : index + window]
        if chunk in seen:
            return True
        seen.add(chunk)
    return False



def _clean_candidate(original: str, candidate: str) -> str:
    text = (candidate or "").strip()
    if not text:
        return text
    if original and original in text and len(text) > len(original) * 1.2:
        text = text.replace(original, "", 1).strip()
    half = len(text) // 2
    if half > 20 and text[:half].strip() == text[half:].strip():
        text = text[:half].strip()
    return text


def _acceptable(original: str, candidate: str, max_ratio: float = 1.5, min_ratio: float = 0.6) -> bool:
    if not candidate or not candidate.strip():
        return False
    ratio = len(candidate) / max(1, len(original))
    delta = abs(len(candidate) - len(original))
    if delta > 30 and (ratio > max_ratio or ratio < min_ratio):
        return False
    return not _has_duplication(candidate)


def _chunk_sentences(text: str, max_chars: int = 200, max_sentences: int = 3) -> list[str]:
    sentences = [sentence for sentence in split_sentences(text) if sentence.strip()]
    if not sentences:
        return [text]
    chunks: list[str] = []
    buffer = ""
    count = 0
    for sentence in sentences:
        if buffer and (len(buffer) + len(sentence) > max_chars or count >= max_sentences):
            chunks.append(buffer)
            buffer = sentence
            count = 1
        else:
            buffer += sentence
            count += 1
    if buffer:
        chunks.append(buffer)
    return chunks


@dataclass
class RewriteContext:
    mode: str = "hybrid"
    style: str = "general"
    lexicon_scope: str = "general"
    strength: str = "medium"
    person: str = "keep"
    colloquial: int = 20
    length_ratio_min: float = 0.85
    length_ratio_max: float = 1.15
    protect_terms: list[str] = field(default_factory=list)
    banned_words: list[str] = field(default_factory=list)
    max_rounds: int = 1
    extra_prompt: str = ""
    use_rule_engine: bool = True
    use_llm: bool = True
    use_local_model: bool = False
    concurrency: int = 3
    ppl_min: float = 60.0
    ppl_retry: int = 2
    ppl_severe: float = 25.0
    lessons: list[str] = field(default_factory=list)


def load_rules(session: Session, lexicon_scope: str, style: str = "general") -> list[Rule]:
    rows = session.exec(select(FeatureRule).where(FeatureRule.enabled == True)).all()  # noqa: E712
    # More specific scope wins when the same pattern exists in both general and a style scope.
    selected: dict[tuple[str, str], FeatureRule] = {}
    for row in rows:
        if row.scope not in ("general", lexicon_scope):
            continue
        if style in {"academic", "official"} and row.scope == "general" and row.severity == "low":
            continue
        key = (row.pattern, row.category)
        current = selected.get(key)
        if current is None or row.scope == lexicon_scope:
            selected[key] = row

    rules: list[Rule] = []
    for row in selected.values():
        try:
            replacements = json.loads(row.replacements or "[]")
        except json.JSONDecodeError:
            replacements = []
        rules.append(
            Rule(
                pattern=row.pattern,
                replacements=[str(r) for r in replacements],
                category=row.category,
                severity=row.severity,
                replace_mode=getattr(row, "replace_mode", "all") or "all",
                note=row.note or "",
            )
        )
    return rules


def build_context(req: RewriteRequest, session: Session) -> RewriteContext:
    """Always use the single academic preset and force rule + LLM hybrid mode."""
    preset = session.exec(select(Preset).where(Preset.name == "学术论文")).first()
    if preset is None:
        preset = session.exec(select(Preset).order_by(Preset.id)).first()

    ctx = RewriteContext(
        mode="hybrid",
        style="academic",
        lexicon_scope="academic",
        strength="medium",
        person="keep",
        colloquial=0,
        length_ratio_min=0.9,
        length_ratio_max=1.1,
        protect_terms=list(req.protect_terms),
        banned_words=list(req.banned_words),
        max_rounds=2,
        extra_prompt="",
        use_rule_engine=True,
        use_llm=True,
    )

    if preset is not None:
        ctx.style = preset.style
        ctx.lexicon_scope = preset.lexicon_scope
        ctx.strength = preset.strength
        ctx.person = preset.person
        ctx.colloquial = preset.colloquial
        ctx.length_ratio_min = preset.length_ratio_min
        ctx.length_ratio_max = preset.length_ratio_max
        ctx.max_rounds = max(1, preset.max_rounds)
        ctx.extra_prompt = preset.extra_prompt
        try:
            ctx.protect_terms = list(
                dict.fromkeys(ctx.protect_terms + json.loads(preset.protect_terms or "[]"))
            )
        except json.JSONDecodeError:
            pass
        try:
            ctx.banned_words = list(
                dict.fromkeys(ctx.banned_words + json.loads(preset.banned_words or "[]"))
            )
        except json.JSONDecodeError:
            pass

    setting = session.get(LLMSetting, 1)
    ctx.use_local_model = bool(setting and getattr(setting, "local_enabled", False))
    if setting:
        ctx.concurrency = min(3, max(1, setting.concurrency))
        ctx.ppl_min = float(getattr(setting, "ppl_min", 60.0) or 60.0)
        ctx.ppl_retry = max(0, int(getattr(setting, "ppl_retry", 2) or 0))
        ctx.ppl_severe = float(getattr(setting, "ppl_severe", 25.0) or 25.0)
    ctx.lessons = recent_lessons(ctx.style)

    ctx.mode = "hybrid"
    ctx.use_rule_engine = True
    ctx.use_llm = True
    return ctx

def _changed_ratio(original: str, rewritten: str) -> float:
    if not original:
        return 0.0
    matcher = difflib.SequenceMatcher(None, original, rewritten)
    return round(1.0 - matcher.ratio(), 4)


def _length_ratio(original: str, rewritten: str) -> float:
    if not original:
        return 1.0
    return round(len(rewritten) / max(1, len(original)), 4)


async def _enforce_perplexity(
    index: int,
    original: str,
    current: str,
    ctx: RewriteContext,
    llm: LLMEngine | None,
    llm_ctx: LLMContext | None,
    warnings: list[str],
    masked: str,
    protector: Protector,
    spans: list[str],
    ppl_issues: list[dict],
    audit_engine: RuleEngine,
) -> str:
    """Regenerate sentences whose local-model perplexity is too low."""
    if not ctx.use_local_model or llm is None or llm_ctx is None or len(current) < 60:
        return current
    from ..local_model import sentence_perplexities, status

    if not status().get("loaded"):
        return current

    for attempt in range(ctx.ppl_retry + 1):
        try:
            scored = protector.restore(current, spans)
            items = await asyncio.to_thread(sentence_perplexities, scored, 12)
        except Exception:  # noqa: BLE001
            return current
        low = [item for item in items if item["perplexity"] < ctx.ppl_min]
        if not low:
            return current
        if attempt >= ctx.ppl_retry:
            from ..local_model import clause_perplexities

            for item in low:
                targets = [item]
                try:
                    clauses = await asyncio.to_thread(
                        clause_perplexities, item["sentence"], 12
                    )
                except Exception:  # noqa: BLE001
                    clauses = []
                picked = [
                    clause
                    for clause in clauses
                    if clause["perplexity"] < ctx.ppl_min
                ]
                if picked:
                    picked.sort(key=lambda clause: clause["perplexity"])
                    targets = picked[:2]
                for target in targets:
                    severe = target["perplexity"] < ctx.ppl_severe
                    record_lesson(
                        style=ctx.style,
                        sentence=target["sentence"],
                        original=original,
                        perplexity=target["perplexity"],
                        threshold=ctx.ppl_min,
                        note="严重：重写后仍远低于困惑度阈值"
                        if severe
                        else "重写后仍低于困惑度阈值",
                    )
            for item in low:
                ppl_issues.append(
                    {
                        "paragraph": index + 1,
                        "sentence": item["sentence"].strip(),
                        "perplexity": item["perplexity"],
                        "threshold": ctx.ppl_min,
                        "attempts": ctx.ppl_retry,
                    }
                )
            if ctx.ppl_retry > 0:
                reason = f"重写 {ctx.ppl_retry} 次仍未达标"
            else:
                reason = "未重写"
            warnings.append(
                f"第 {index + 1} 段有 {len(low)} 句困惑度低于 {ctx.ppl_min:g}，{reason}"
            )
            return current
        try:
            candidate = await llm.rewrite_low_perplexity(current, low, llm_ctx)
        except LLMError as exc:
            warnings.append(f"第 {index + 1} 段低困惑度重写失败：{exc}")
            return current
        if not LLMEngine.placeholders_intact(masked, candidate):
            continue
        candidate = _clean_candidate(current, candidate)
        if not _acceptable(current, candidate, max_ratio=1.25, min_ratio=0.75):
            continue
        if len(collect_hits(candidate, audit_engine)) > len(collect_hits(current, audit_engine)):
            continue
        current = candidate
    return current


async def _rewrite_one(
    index: int,
    paragraph: str,
    ctx: RewriteContext,
    rules: list[Rule],
    llm: LLMEngine | None,
    warnings: list[str],
    semaphore: asyncio.Semaphore,
    pause_event: asyncio.Event | None = None,
    ppl_issues: list[dict] | None = None,
) -> ParagraphResult:
    async with semaphore:
        if pause_event is not None:
            await pause_event.wait()
        if _is_heading(paragraph):
            return ParagraphResult(
                index=index,
                original=paragraph,
                rewritten=paragraph,
                changed_ratio=0.0,
                length_ratio=1.0,
                metrics={},
            )

        protector = Protector(ctx.protect_terms)
        masked, spans = protector.protect(paragraph)
        current = masked
        engine = RuleEngine(rules)
        audit_engine = RuleEngine(rules)
        options = RewriteOptions(
            strength=ctx.strength,
            style=ctx.style,
            person=ctx.person,
            colloquial=ctx.colloquial,
        )

        if ctx.use_rule_engine and ctx.mode in {"rule", "hybrid"}:
            current = await asyncio.to_thread(engine.rewrite, current, options)

        llm_used = False
        llm_ctx = None
        if ctx.use_llm and llm is not None and llm.configured:
            llm_ctx = LLMContext(
                style=ctx.style,
                strength=ctx.strength,
                person=ctx.person,
                colloquial=ctx.colloquial,
                length_ratio_min=ctx.length_ratio_min,
                length_ratio_max=ctx.length_ratio_max,
                banned_words=ctx.banned_words,
                extra_prompt=ctx.extra_prompt,
                lessons=list(ctx.lessons),
            )
            academic = ctx.style in {"academic", "official"}
            chunks = _chunk_sentences(
                current,
                max_chars=220 if academic else 200,
                max_sentences=3,
            )
            rewritten_chunks: list[str] = []
            for chunk in chunks:
                piece = chunk
                hits = collect_hits(piece, audit_engine)
                for round_index in range(ctx.max_rounds):
                    try:
                        candidate = await llm.rewrite_paragraph(
                            piece,
                            llm_ctx,
                            round_index,
                            hits=hits,
                            context=current,
                        )
                    except LLMError as exc:
                        warnings.append(f"第 {index + 1} 段 LLM 改写失败：{exc}")
                        break
                    if not LLMEngine.placeholders_intact(piece, candidate):
                        warnings.append(f"第 {index + 1} 段占位符未完整保留，已保留上一轮结果")
                        break
                    candidate = _clean_candidate(piece, candidate)
                    if not _acceptable(piece, candidate):
                        if round_index >= ctx.max_rounds - 1:
                            warnings.append(f"第 {index + 1} 段改写结果长度异常或重复，已保留上一轮结果")
                        continue
                    piece = candidate
                    llm_used = True
                    hits = collect_hits(piece, audit_engine)
                    if not hits:
                        break
                rewritten_chunks.append(piece)
            current = "".join(rewritten_chunks)

            for check_index in range(2):
                remaining = collect_hits(current, audit_engine)
                if not remaining:
                    break
                try:
                    candidate = await llm.correct_paragraph(current, remaining, llm_ctx)
                except LLMError as exc:
                    warnings.append(f"第 {index + 1} 段 LLM 复检纠正失败：{exc}")
                    break
                if not LLMEngine.placeholders_intact(masked, candidate):
                    warnings.append(f"第 {index + 1} 段复检后占位符未完整保留，已保留上一轮结果")
                    break
                candidate = _clean_candidate(current, candidate)
                if not _acceptable(current, candidate):
                    if check_index >= 1:
                        warnings.append(f"第 {index + 1} 段复检结果长度异常或重复，已保留上一轮结果")
                    continue
                current = candidate

            if academic:
                for _ in range(2 if len(current) >= 60 else 0):
                    metrics = analyze(current)
                    runs = uniform_runs(current)
                    pmetrics = paragraph_metrics(current)
                    issues: list[str] = []
                    if pmetrics["short_count"] == 0:
                        issues.append("缺少 15 字以内的短句")
                    if pmetrics["long_count"] == 0:
                        issues.append("缺少 40 字以上的长句")
                    if pmetrics["opening_repeats"] > 0:
                        issues.append("连续三句开头相同，改掉其中两句")
                    if pmetrics["hedge_count"] == 0:
                        issues.append("缺少限定表述，至少加一处")
                    if metrics.get("cv", 0) >= 0.42 and not runs and not issues:
                        break
                    try:
                        candidate = await llm.adjust_rhythm(current, metrics, llm_ctx, issues)
                    except LLMError as exc:
                        warnings.append(f"第 {index + 1} 段节奏调整失败：{exc}")
                        break
                    if not LLMEngine.placeholders_intact(masked, candidate):
                        warnings.append(f"第 {index + 1} 段节奏调整后占位符未完整保留")
                        break
                    candidate = _clean_candidate(current, candidate)
                    if not _acceptable(current, candidate, max_ratio=1.8, min_ratio=0.5):
                        warnings.append(f"第 {index + 1} 段节奏调整结果长度异常或重复")
                        break
                    new_metrics = analyze(candidate)
                    new_pmetrics = paragraph_metrics(candidate)
                    improved = new_metrics.get("cv", 0) > metrics.get("cv", 0)
                    issue_fixed = (
                        new_pmetrics["short_count"] >= pmetrics["short_count"]
                        and new_pmetrics["long_count"] >= pmetrics["long_count"]
                        and new_pmetrics["hedge_count"] >= pmetrics["hedge_count"]
                        and new_pmetrics["opening_repeats"] <= pmetrics["opening_repeats"]
                    )
                    if not improved and not issue_fixed:
                        break
                    current = candidate

                remaining = collect_hits(current, audit_engine)
                if remaining:
                    try:
                        candidate = await llm.correct_paragraph(current, remaining, llm_ctx)
                        if LLMEngine.placeholders_intact(masked, candidate) and _acceptable(current, candidate):
                            current = candidate
                    except LLMError:
                        pass

                before_metrics = analyze(current)
                if before_metrics.get("cv", 0) < 0.5:
                    adjusted = await asyncio.to_thread(engine.post_rhythm, current, 0.5)
                    if adjusted != current:
                        after_metrics = analyze(adjusted)
                        old_hits = len(collect_hits(current, audit_engine))
                        new_hits = len(collect_hits(adjusted, audit_engine))
                        if (
                            after_metrics.get("cv", 0) > before_metrics.get("cv", 0)
                            and new_hits <= old_hits
                        ):
                            current = adjusted

        if ctx.use_rule_engine and ctx.mode == "hybrid":
            current = await asyncio.to_thread(engine.audit, current, options)

        current = await _enforce_perplexity(
            index,
            paragraph,
            current,
            ctx,
            llm,
            llm_ctx,
            warnings,
            masked,
            protector,
            spans,
            ppl_issues if ppl_issues is not None else [],
            audit_engine,
        )

        if llm is not None and llm_ctx is not None:
            remaining = collect_hits(current, audit_engine)
            if remaining:
                try:
                    candidate = await llm.correct_paragraph(current, remaining, llm_ctx)
                    if (
                        LLMEngine.placeholders_intact(masked, candidate)
                        and _acceptable(current, candidate)
                        and len(collect_hits(candidate, audit_engine))
                        <= len(remaining)
                    ):
                        current = candidate
                except LLMError:
                    pass

        restored = protector.restore(current, spans)
        if not restored.strip():
            restored = paragraph
            warnings.append(f"第 {index + 1} 段改写结果为空，已保留原文")

        if not llm_used and restored != paragraph:
            before = ai_likeness(analyze(paragraph))
            after = ai_likeness(analyze(restored))
            if after > before + 0.5:
                warnings.append(f"第 {index + 1} 段改写后特征未改善，已保留原文")
                restored = paragraph

        return ParagraphResult(
            index=index,
            original=paragraph,
            rewritten=restored,
            changed_ratio=_changed_ratio(paragraph, restored),
            length_ratio=_length_ratio(paragraph, restored),
            metrics=paragraph_metrics(restored),
        )


def _build_response(
    results: list[ParagraphResult],
    warnings: list[str],
    ppl_issues: list[dict] | None = None,
) -> RewriteResponse:
    original_chars = sum(len(r.original) for r in results)
    rewritten_chars = sum(len(r.rewritten) for r in results)
    paragraphs = len(results)
    stats = RewriteStats(
        paragraphs=paragraphs,
        original_chars=original_chars,
        rewritten_chars=rewritten_chars,
        avg_changed_ratio=round(sum(r.changed_ratio for r in results) / max(1, paragraphs), 4),
        avg_length_ratio=round(sum(r.length_ratio for r in results) / max(1, paragraphs), 4),
    )
    return RewriteResponse(
        paragraphs=results,
        rewritten_text=join_paragraphs([r.rewritten for r in results]),
        stats=stats,
        warnings=warnings,
        ppl_issues=[PPLIssue(**item) for item in (ppl_issues or [])],
    )


async def rewrite_document(
    text: str,
    ctx: RewriteContext,
    rules: list[Rule],
    llm: LLMEngine | None,
    emit: EmitFn | None = None,
    pause_event: asyncio.Event | None = None,
) -> RewriteResponse:
    paragraphs = split_paragraphs(text)
    if not paragraphs:
        return _build_response([], ["没有解析到任何段落，请检查输入内容"])

    warnings: list[str] = []
    ppl_issues: list[dict] = []
    if ctx.use_llm and (llm is None or not llm.configured):
        raise LLMError("改写需要规则 + LLM 混合执行，请先在 LLM 设置页配置 Base URL、模型和 API Key")

    semaphore = asyncio.Semaphore(max(1, ctx.concurrency))
    tasks = [
        asyncio.create_task(
            _rewrite_one(i, p, ctx, rules, llm, warnings, semaphore, pause_event, ppl_issues)
        )
        for i, p in enumerate(paragraphs)
    ]

    results: list[ParagraphResult | None] = [None] * len(paragraphs)
    for coro in asyncio.as_completed(tasks):
        result = await coro
        results[result.index] = result
        if emit is not None:
            await emit(result)

    ordered = [r for r in results if r is not None]
    response = _build_response(ordered, warnings, ppl_issues)
    audit_result = await asyncio.to_thread(
        audit_text,
        response.rewritten_text,
        RuleEngine(rules),
        use_local=ctx.use_local_model,
    )
    response.audit = AuditResult(**audit_result)
    return response
