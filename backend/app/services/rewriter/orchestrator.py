from __future__ import annotations

import asyncio
import difflib
import json
import re
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

from sqlmodel import Session, select

from ...models.models import FeatureRule, LLMSetting, Preset
from ...schemas import (
    AuditResult,
    ContentReport,
    PPLIssue,
    ParagraphResult,
    RewriteRequest,
    RewriteResponse,
    RewriteStats,
)
from ..protector import Protector
from ..segmenter import join_paragraphs, split_paragraphs, split_sentences
from .audit import audit_text, collect_hits
from .candidate import select_candidate
from .content import assign_facts, fact_used, unsourced_count, verify_content
from .context_guard import ReplacementGuard, Whitelist, load_blacklist, load_whitelist
from .diagnosis import compare as compare_diagnosis
from .diagnosis import diagnose
from .features import analyze, paragraph_metrics, uniform_runs
from .guards import (
    acceptable,
    clean_candidate,
    has_duplication,
    merge_short_runs,
    quality_compare,
)
from .leakage import clean as clean_leakage
from .lessons import (
    match_forbidden_templates,
    recent_forbidden_templates,
    recent_lessons,
    record_lesson,
)
from .structure import restructure
from .timing import (
    add_coverage,
    add_rhythm,
    add_rule,
    finish_timing,
    start_timing,
)
from .llm_engine import LLMContext, LLMEngine, LLMError
from .rule_engine import RewriteOptions, Rule, RuleEngine

EmitFn = Callable[[ParagraphResult], Awaitable[None]]


_HEADING_RE = re.compile(
    r"^\s*(?:[（(][一二三四五六七八九十\d]+[）)]|\d+[.、]|[一二三四五六七八九十]+[、.])[^\n]{0,40}$"
)

# 全文覆盖率目标：除标题外，至少这么多比例的句子必须真正被改写。
COVERAGE_TARGET = 0.95
COVERAGE_PASSES = 1
CV_TARGET_LOW = 0.45
CV_TARGET_HIGH = 0.6
CV_ACCEPT_HIGH = 0.7
_WS_RE = re.compile(r"\s+")


def _is_heading(text: str) -> bool:
    stripped = text.strip()
    return len(stripped) <= 40 and bool(_HEADING_RE.match(stripped))



def _clean_candidate(original: str, candidate: str) -> str:
    return clean_candidate(original, candidate)


def _acceptable(original: str, candidate: str, max_ratio: float = 1.5, min_ratio: float = 0.6) -> bool:
    ok, _reason = acceptable(original, candidate, max_ratio=max_ratio, min_ratio=min_ratio)
    return ok


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


def _normalize_sentence(text: str) -> str:
    return _WS_RE.sub("", text or "")


def _untouched_sentences(original: str, rewritten: str) -> list[str]:
    """Return original sentences that still appear verbatim in the rewrite."""
    rewritten_norm = _normalize_sentence(rewritten)
    untouched: list[str] = []
    for sentence in split_sentences(original):
        normalized = _normalize_sentence(sentence)
        if normalized and normalized in rewritten_norm:
            untouched.append(sentence.strip())
    return untouched


def _sentence_coverage(original: str, rewritten: str) -> tuple[float, int, int]:
    sentences = [s for s in split_sentences(original) if s.strip()]
    if not sentences:
        return 1.0, 0, 0
    untouched = len(_untouched_sentences(original, rewritten))
    changed = max(0, len(sentences) - untouched)
    return round(changed / len(sentences), 4), changed, untouched


def _sentence_risks(text: str, engine: RuleEngine, ctx: RewriteContext) -> list[dict]:
    """Per-sentence rule hits and proxy risk, used by the sentence heatmap."""
    risks: list[dict] = []
    for sentence in split_sentences(text):
        stripped = sentence.strip()
        if not stripped:
            continue
        hits = collect_hits(stripped, engine, whitelist=ctx.whitelist, limit=8)
        diagnosis = diagnose(stripped, ctx.style)
        risks.append(
            {
                "text": stripped,
                "risk": round(float(diagnosis.get("total_per_1000") or 0.0), 2),
                "hits": sum(int(hit.get("count") or 0) for hit in hits),
                "dominant": diagnosis.get("dominant_label") or "",
            }
        )
    return risks


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
    forbidden_templates: list[str] = field(default_factory=list)
    whitelist: Whitelist | None = None
    guard: ReplacementGuard | None = None
    diagnosis_before: dict = field(default_factory=dict)
    content_facts: list[dict] = field(default_factory=list)
    facts_by_paragraph: dict[int, list[dict]] = field(default_factory=dict)
    candidate_count: int = 1
    deep_rewrite: bool = False
    structure_mode: str = "preserve"
    rewrite_granularity: str = "hybrid"
    rewrite_headings: bool = False


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
    ctx.lessons = recent_lessons(ctx.style, limit=50)
    ctx.forbidden_templates = recent_forbidden_templates(ctx.style, limit=50)
    ctx.content_facts = [
        fact.model_dump() if hasattr(fact, "model_dump") else dict(fact)
        for fact in (req.content_facts or [])
    ]
    ctx.candidate_count = max(1, min(5, int(req.candidate_count or 1)))
    ctx.deep_rewrite = bool(req.deep_rewrite)
    ctx.structure_mode = req.structure_mode if req.structure_mode in {"preserve", "flexible"} else "preserve"
    ctx.rewrite_granularity = (
        req.rewrite_granularity if req.rewrite_granularity in {"hybrid", "document"} else "hybrid"
    )
    ctx.rewrite_headings = bool(req.rewrite_headings)
    if setting is not None:
        if not req.candidate_count:
            ctx.candidate_count = max(1, min(5, int(getattr(setting, "candidate_count", 1) or 1)))
        ctx.deep_rewrite = bool(getattr(setting, "deep_rewrite", False)) and bool(req.deep_rewrite)
        if req.structure_mode == "preserve":
            ctx.structure_mode = getattr(setting, "structure_mode", "preserve") or "preserve"

    ctx.whitelist = load_whitelist()
    ctx.guard = ReplacementGuard(load_blacklist())
    # 固定搭配整体占位保护，避免把“生态环境/控制闭环/数字化转型”机械替换掉。
    ctx.protect_terms = list(
        dict.fromkeys(ctx.protect_terms + ctx.whitelist.protect_terms())
    )

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
    whitelist: Whitelist | None = None,
    job_id: int | None = None,
) -> str:
    """Regenerate sentences whose local-model perplexity is too low."""
    if not ctx.use_local_model or llm is None or llm_ctx is None or len(current) < 60:
        return current
    from ..local_model import sentence_perplexities, status

    if not status().get("loaded"):
        return current

    def mark_fixed(items: list[dict]) -> None:
        for item in items:
            record_lesson(
                style=ctx.style,
                sentence=item["sentence"],
                original=original,
                perplexity=item["perplexity"],
                threshold=ctx.ppl_min,
                outcome="fixed",
                scope="sentence",
                source_job_id=job_id,
            )

    def mark_survived(items: list[dict], note: str, scope: str = "sentence") -> None:
        for item in items:
            record_lesson(
                style=ctx.style,
                sentence=item["sentence"],
                original=original,
                perplexity=item["perplexity"],
                threshold=ctx.ppl_min,
                outcome="survived",
                scope=scope,
                source_job_id=job_id,
                increment_hits=True,
                note=note,
            )

    previous_low: list[dict] = []
    for attempt in range(ctx.ppl_retry + 1):
        try:
            scored = protector.restore(current, spans)
            items = await asyncio.to_thread(sentence_perplexities, scored, 12)
        except Exception:  # noqa: BLE001
            return current
        low = [item for item in items if item["perplexity"] < ctx.ppl_min]
        if not low:
            mark_fixed(previous_low)
            return current
        if attempt == 0:
            for item in low:
                record_lesson(
                    style=ctx.style,
                    sentence=item["sentence"],
                    original=original,
                    perplexity=item["perplexity"],
                    threshold=ctx.ppl_min,
                    outcome="pending",
                    scope="sentence",
                    source_job_id=job_id,
                )
        current_low = {item["sentence"] for item in low}
        mark_fixed(
            [item for item in previous_low if item["sentence"] not in current_low]
        )
        if attempt >= ctx.ppl_retry:
            from ..local_model import clause_perplexities

            mark_survived(low, "重写后仍低于困惑度阈值")
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
                    mark_survived(
                        [target],
                        "严重：重写后仍远低于困惑度阈值"
                        if severe
                        else "重写后仍低于困惑度阈值",
                        scope="clause",
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
        previous_low = low
        try:
            candidate = await llm.rewrite_low_perplexity(current, low, llm_ctx)
        except LLMError as exc:
            warnings.append(f"第 {index + 1} 段低困惑度重写失败：{exc}")
            mark_survived(low, "重写失败，仍低于困惑度阈值")
            return current
        if not LLMEngine.placeholders_intact(masked, candidate):
            continue
        candidate = _clean_candidate(current, candidate)
        if not _acceptable(current, candidate, max_ratio=1.25, min_ratio=0.75):
            continue
        if len(collect_hits(candidate, audit_engine, whitelist=whitelist)) > len(
            collect_hits(current, audit_engine, whitelist=whitelist)
        ):
            continue
        current = candidate
    mark_survived(previous_low, "重写循环结束，仍低于困惑度阈值")
    return current


async def _ensure_coverage(
    index: int,
    masked_source: str,
    current: str,
    llm: LLMEngine | None,
    llm_ctx: LLMContext | None,
    warnings: list[str],
    max_passes: int = COVERAGE_PASSES,
) -> str:
    """Force another whole-paragraph rewrite when sentences were left untouched."""
    if llm is None or llm_ctx is None or not llm.configured:
        return current
    for _ in range(max_passes):
        coverage, _changed, _untouched_count = _sentence_coverage(masked_source, current)
        if coverage >= COVERAGE_TARGET:
            return current
        untouched = _untouched_sentences(masked_source, current)
        if not untouched:
            return current
        add_coverage()
        try:
            candidate = await llm.rewrite_unchanged(
                current, untouched, llm_ctx, context=masked_source
            )
        except LLMError as exc:
            warnings.append(f"第 {index + 1} 段补全覆盖失败：{exc}")
            return current
        if not candidate or not candidate.strip():
            return current
        if not LLMEngine.placeholders_intact(masked_source, candidate):
            warnings.append(f"第 {index + 1} 段补全覆盖后占位符未完整保留，已保留上一轮结果")
            return current
        candidate = _clean_candidate(current, candidate)
        ok, reason = acceptable(
            current, candidate, max_ratio=2.5, min_ratio=0.4, allow_overfit=True
        )
        if not ok or has_duplication(candidate):
            warnings.append(f"第 {index + 1} 段补全覆盖结果未通过（{reason or '结果重复'}）")
            return current
        current = candidate
    coverage, _changed, untouched_count = _sentence_coverage(masked_source, current)
    if untouched_count and coverage < COVERAGE_TARGET:
        warnings.append(
            f"第 {index + 1} 段仍有 {untouched_count} 句未改写，覆盖率 {coverage:.0%}"
        )
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
    candidate_scores: list[dict] | None = None,
    job_id: int | None = None,
) -> ParagraphResult:
    async with semaphore:
        if pause_event is not None:
            await pause_event.wait()
        heading = _is_heading(paragraph)
        if heading and not ctx.rewrite_headings:
            return ParagraphResult(
                index=index,
                original=paragraph,
                rewritten=paragraph,
                changed_ratio=0.0,
                length_ratio=1.0,
                metrics={"coverage": 1.0, "heading": True},
            )

        source, leak_hits = clean_leakage(paragraph)
        if leak_hits:
            warnings.append(
                f"第 {index + 1} 段清除了 {len(leak_hits)} 类过程痕迹："
                + "、".join(item["category"] for item in leak_hits)
            )
        diag_before = diagnose(source, ctx.style)
        paragraph_facts = list(ctx.facts_by_paragraph.get(index, []))

        protector = Protector(ctx.protect_terms)
        masked, spans = protector.protect(source)
        current = masked
        engine = RuleEngine(rules, ctx.whitelist, ctx.guard)
        audit_engine = RuleEngine(rules, ctx.whitelist, ctx.guard)
        options = RewriteOptions(
            strength=ctx.strength,
            style=ctx.style,
            person=ctx.person,
            colloquial=ctx.colloquial,
            deep=ctx.deep_rewrite,
        )

        if ctx.use_rule_engine and ctx.mode in {"rule", "hybrid"}:
            rule_started = time.perf_counter()
            current = await asyncio.to_thread(engine.rewrite, current, options)
            add_rule(time.perf_counter() - rule_started)

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
                issues=list(diag_before.get("issues") or []),
                plan=list(diag_before.get("plan") or []),
                content_facts=paragraph_facts,
                deep_rewrite=ctx.deep_rewrite,
                rewrite_headings=ctx.rewrite_headings,
            )
            academic = ctx.style in {"academic", "official"}
            chunks = _chunk_sentences(
                current,
                max_chars=220 if academic else 200,
                max_sentences=3,
            )
            rewritten_chunks: list[str] = []
            for chunk_index, chunk in enumerate(chunks):
                piece = chunk
                hits = collect_hits(piece, audit_engine, whitelist=ctx.whitelist)
                for round_index in range(ctx.max_rounds):
                    candidates: list[str] = []
                    variants = max(1, ctx.candidate_count) if round_index == 0 else 1
                    for variant in range(variants):
                        temperature = None
                        if academic:
                            temperature = min(1.7, 1.3 + 0.12 * variant)
                        try:
                            candidate = await llm.rewrite_paragraph(
                                piece,
                                llm_ctx,
                                round_index,
                                hits=hits,
                                context=current,
                                temperature=temperature,
                            )
                        except LLMError as exc:
                            if variant == 0:
                                warnings.append(f"第 {index + 1} 段 LLM 改写失败：{exc}")
                            continue
                        if not LLMEngine.placeholders_intact(piece, candidate):
                            continue
                        candidate = _clean_candidate(piece, candidate)
                        ok, reason = acceptable(
                            piece,
                            candidate,
                            max_ratio=2.5 if paragraph_facts else 1.5,
                            min_ratio=0.6,
                            allow_overfit=bool(paragraph_facts),
                        )
                        if not ok:
                            if variant == 0 and round_index >= ctx.max_rounds - 1:
                                warnings.append(
                                    f"第 {index + 1} 段候选未通过（{reason}），已保留上一轮结果"
                                )
                            continue
                        candidates.append(candidate)
                    if not candidates:
                        fallback = None
                        try:
                            fallback = await llm.rewrite_paragraph(
                                piece,
                                llm_ctx,
                                round_index,
                                hits=hits,
                                context=current,
                                temperature=min(1.7, 1.5 + 0.1 * round_index),
                            )
                        except LLMError as exc:
                            warnings.append(
                                f"第 {index + 1} 段第 {chunk_index + 1} 片降级改写失败：{exc}"
                            )
                        fallback_ratio = (
                            len(fallback) / max(1, len(piece)) if fallback else 0.0
                        )
                        if (
                            fallback
                            and fallback.strip()
                            and 0.3 <= fallback_ratio <= 3.0
                            and LLMEngine.placeholders_intact(piece, fallback)
                        ):
                            fallback = _clean_candidate(piece, fallback)
                            if fallback.strip() and not has_duplication(fallback):
                                piece = fallback
                                llm_used = True
                                warnings.append(
                                    f"第 {index + 1} 段第 {chunk_index + 1} 片候选未通过护栏，已采用降级改写结果"
                                )
                                hits = collect_hits(
                                    piece, audit_engine, whitelist=ctx.whitelist
                                )
                        else:
                            warnings.append(
                                f"第 {index + 1} 段第 {chunk_index + 1} 片未能改写，保留规则处理结果"
                            )
                        break
                    if len(candidates) == 1:
                        best = candidates[0]
                    else:
                        best, scores = select_candidate(
                            piece, candidates, diag_before, paragraph_facts
                        )
                        for score in scores:
                            score["paragraph"] = index + 1
                            score["chunk"] = chunk_index + 1
                            if candidate_scores is not None:
                                candidate_scores.append(score)
                    piece = best
                    llm_used = True
                    hits = collect_hits(piece, audit_engine, whitelist=ctx.whitelist)
                    if not hits:
                        break
                rewritten_chunks.append(piece)
            current = "".join(rewritten_chunks)

            for check_index in range(2):
                remaining = collect_hits(current, audit_engine, whitelist=ctx.whitelist)
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

            if academic and not heading:
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
                    structure = diag_before.get("structure") or {}
                    if structure.get("short_run", 0) > 0:
                        issues.append("连续短句过多，合并其中一两句")
                    if structure.get("long_nested", 0) > 0:
                        issues.append("长句嵌套过深，在语义切换点断句")
                    for item in (diag_before.get("issues") or [])[:3]:
                        if item not in issues:
                            issues.append(item)
                    cv = metrics.get("cv", 0)
                    if cv > CV_TARGET_HIGH:
                        issues.append("句长差异过大，合并部分短句或拆分过长句")
                    if (
                        CV_TARGET_LOW <= cv <= CV_TARGET_HIGH
                        and not runs
                        and not issues
                    ):
                        break
                    try:
                        add_rhythm()
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
                    new_cv = new_metrics.get("cv", 0)
                    in_range = CV_TARGET_LOW <= new_cv <= CV_TARGET_HIGH
                    toward = (
                        cv > CV_TARGET_HIGH and new_cv < cv
                    ) or (
                        cv < CV_TARGET_LOW and new_cv > cv
                    )
                    issue_fixed = (
                        new_pmetrics["short_count"] >= pmetrics["short_count"]
                        and new_pmetrics["long_count"] >= pmetrics["long_count"]
                        and new_pmetrics["hedge_count"] >= pmetrics["hedge_count"]
                        and new_pmetrics["opening_repeats"] <= pmetrics["opening_repeats"]
                    )
                    if new_cv > CV_ACCEPT_HIGH:
                        break
                    if (
                        cv < CV_TARGET_LOW
                        and new_cv > CV_TARGET_HIGH
                        and not issue_fixed
                    ):
                        break
                    if not (in_range or toward or issue_fixed):
                        break
                    current = candidate

                remaining = collect_hits(current, audit_engine, whitelist=ctx.whitelist)
                if remaining:
                    try:
                        candidate = await llm.correct_paragraph(current, remaining, llm_ctx)
                        if LLMEngine.placeholders_intact(masked, candidate) and _acceptable(current, candidate):
                            current = candidate
                    except LLMError:
                        pass

                before_metrics = analyze(current)
                if before_metrics.get("cv", 0) < CV_TARGET_LOW:
                    adjusted = await asyncio.to_thread(
                        engine.post_rhythm,
                        current,
                        CV_TARGET_LOW,
                        max_cv=CV_TARGET_HIGH,
                    )
                    if adjusted != current:
                        after_metrics = analyze(adjusted)
                        old_hits = len(collect_hits(current, audit_engine, whitelist=ctx.whitelist))
                        new_hits = len(collect_hits(adjusted, audit_engine, whitelist=ctx.whitelist))
                        if (
                            after_metrics.get("cv", 0) > before_metrics.get("cv", 0)
                            and after_metrics.get("cv", 0) <= CV_TARGET_HIGH
                            and new_hits <= old_hits
                        ):
                            current = adjusted

            current = await _ensure_coverage(
                index, masked, current, llm, llm_ctx, warnings
            )

        if ctx.use_rule_engine and ctx.mode == "hybrid":
            audit_started = time.perf_counter()
            current = await asyncio.to_thread(engine.audit, current, options)
            add_rule(time.perf_counter() - audit_started)

        current = await _enforce_perplexity(
            index,
            source,
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
            ctx.whitelist,
            job_id=job_id,
        )

        if llm is not None and llm_ctx is not None:
            remaining = collect_hits(current, audit_engine, whitelist=ctx.whitelist)
            if remaining:
                try:
                    candidate = await llm.correct_paragraph(current, remaining, llm_ctx)
                    if (
                        LLMEngine.placeholders_intact(masked, candidate)
                        and _acceptable(current, candidate)
                        and len(collect_hits(candidate, audit_engine, whitelist=ctx.whitelist))
                        <= len(remaining)
                    ):
                        current = candidate
                except LLMError:
                    pass

        if llm is not None and llm_ctx is not None and not heading:
            current = await _ensure_coverage(
                index, masked, current, llm, llm_ctx, warnings
            )

        restored = protector.restore(current, spans)
        restored, leak_after = clean_leakage(restored)
        if leak_after:
            warnings.append(f"第 {index + 1} 段改写后又出现过程痕迹，已再次清除")
        if not restored.strip():
            restored = source
            warnings.append(f"第 {index + 1} 段改写结果为空，已保留原文")

        forbidden_hits = match_forbidden_templates(restored, ctx.forbidden_templates)
        if forbidden_hits:
            warnings.append(
                f"第 {index + 1} 段仍出现避雷库禁用模板："
                + "；".join(hit[:40] for hit in forbidden_hits[:3])
            )

        content_report = verify_content(
            source,
            restored,
            paragraph_facts,
            unsourced_before=unsourced_count(source),
            unsourced_after=unsourced_count(restored),
        )
        if (
            paragraph_facts
            and llm is not None
            and llm_ctx is not None
            and content_report["facts_used"] < content_report["facts_provided"]
        ):
            unused = [
                fact
                for fact in paragraph_facts
                if not fact_used(str(fact.get("text") or ""), restored)
            ]
            try:
                integrated = await llm.integrate_facts(restored, unused, llm_ctx)
                if LLMEngine.placeholders_intact(masked, integrated):
                    integrated = _clean_candidate(restored, integrated)
                    ok, _reason = acceptable(
                        restored,
                        integrated,
                        max_ratio=2.0,
                        min_ratio=0.6,
                        allow_overfit=bool(paragraph_facts),
                    )
                    if ok:
                        integrated_report = verify_content(
                            source,
                            integrated,
                            paragraph_facts,
                            unsourced_before=unsourced_count(source),
                            unsourced_after=unsourced_count(integrated),
                        )
                        if integrated_report["facts_used"] >= content_report["facts_used"]:
                            restored = integrated
                            content_report = integrated_report
                            warnings.append(f"第 {index + 1} 段补充写入了用户提供的事实")
            except LLMError:
                pass
        for item in content_report.get("warnings") or []:
            warnings.append(f"第 {index + 1} 段：{item}")

        diag_after = diagnose(restored, ctx.style)
        quality = quality_compare(diag_before, diag_after)
        if "新增连续短句" in quality["regressions"]:
            merged = merge_short_runs(restored)
            if merged != restored:
                merged_diag = diagnose(merged, ctx.style)
                if merged_diag["total_per_1000"] <= diag_after["total_per_1000"]:
                    restored = merged
                    diag_after = merged_diag
                    quality = quality_compare(diag_before, diag_after)

        # 全文都要降：密度上升只提示复核，不再把整段退回原文。
        if diag_after["total_per_1000"] > diag_before["total_per_1000"] + 1.5:
            warnings.append(
                f"第 {index + 1} 段改写后 AI 特征密度上升，已保留改写结果，建议人工复核"
            )

        coverage, changed_sentences, untouched = _sentence_coverage(source, restored)
        if coverage < COVERAGE_TARGET and not heading:
            warnings.append(
                f"第 {index + 1} 段覆盖率 {coverage:.0%}，仍有 {untouched} 句接近原文"
            )

        metrics = paragraph_metrics(restored)
        metrics["ai_per_1000"] = diag_after.get("total_per_1000")
        metrics["coverage"] = coverage
        metrics["changed_sentences"] = changed_sentences
        metrics["untouched_sentences"] = untouched
        metrics["dominant"] = diag_after.get("dominant_label")
        metrics["sentence_risks"] = _sentence_risks(restored, audit_engine, ctx)
        metrics["diagnosis_issues"] = [
            item.get("label") for item in (diag_after.get("plan") or [])[:4]
        ]

        return ParagraphResult(
            index=index,
            original=paragraph,
            rewritten=restored,
            changed_ratio=_changed_ratio(paragraph, restored),
            length_ratio=_length_ratio(paragraph, restored),
            metrics=metrics,
        )


def _build_response(
    results: list[ParagraphResult],
    warnings: list[str],
    ppl_issues: list[dict] | None = None,
    content_report: dict | None = None,
    structure_changes: list[str] | None = None,
    candidate_scores: list[dict] | None = None,
) -> RewriteResponse:
    original_chars = sum(len(r.original) for r in results)
    rewritten_chars = sum(len(r.rewritten) for r in results)
    paragraphs = len(results)
    total_sentences = 0
    changed_sentences = 0
    for result in results:
        if _is_heading(result.original):
            continue
        total_sentences += len(
            [sentence for sentence in split_sentences(result.original) if sentence.strip()]
        )
        _coverage, changed, _untouched = _sentence_coverage(
            result.original, result.rewritten
        )
        changed_sentences += changed
    coverage = (
        round(changed_sentences / total_sentences, 4) if total_sentences else 1.0
    )
    if total_sentences and coverage < COVERAGE_TARGET:
        warnings.append(
            f"全文覆盖率 {coverage:.0%}，低于目标 {COVERAGE_TARGET:.0%}，部分句子仍接近原文"
        )
    stats = RewriteStats(
        paragraphs=paragraphs,
        original_chars=original_chars,
        rewritten_chars=rewritten_chars,
        avg_changed_ratio=round(sum(r.changed_ratio for r in results) / max(1, paragraphs), 4),
        avg_length_ratio=round(sum(r.length_ratio for r in results) / max(1, paragraphs), 4),
        sentences=total_sentences,
        rewritten_sentences=changed_sentences,
        coverage=coverage,
    )
    return RewriteResponse(
        paragraphs=results,
        rewritten_text=join_paragraphs([r.rewritten for r in results]),
        stats=stats,
        warnings=warnings,
        ppl_issues=[PPLIssue(**item) for item in (ppl_issues or [])],
        content_report=content_report,
        structure_changes=structure_changes or [],
        candidate_scores=candidate_scores or [],
    )


async def _rewrite_document_level(
    text: str,
    paragraphs: list[str],
    ctx: RewriteContext,
    rules: list[Rule],
    llm: LLMEngine,
    warnings: list[str],
) -> list[ParagraphResult] | None:
    """整篇改写：一次调用处理全文，失败或段落数不一致时回退混合粒度。"""
    if len(text) > 8000:
        warnings.append("文本超过 8000 字，文档级改写已回退到混合粒度")
        return None

    protector = Protector(ctx.protect_terms)
    masked, spans = protector.protect(text)
    masked_paragraphs = split_paragraphs(masked)
    if len(masked_paragraphs) != len(paragraphs):
        return None

    engine = RuleEngine(rules, ctx.whitelist, ctx.guard)
    options = RewriteOptions(
        strength=ctx.strength,
        style=ctx.style,
        person=ctx.person,
        colloquial=ctx.colloquial,
        deep=ctx.deep_rewrite,
    )
    rewritten_paragraphs: list[str] = []
    for paragraph in masked_paragraphs:
        if _is_heading(paragraph) and not ctx.rewrite_headings:
            rewritten_paragraphs.append(paragraph)
        else:
            rule_started = time.perf_counter()
            rewritten_paragraphs.append(
                await asyncio.to_thread(engine.rewrite, paragraph, options)
            )
            add_rule(time.perf_counter() - rule_started)
    masked_document = "\n\n".join(rewritten_paragraphs)
    hits = collect_hits(masked_document, engine, whitelist=ctx.whitelist, limit=40)
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
        issues=list(ctx.diagnosis_before.get("issues") or []),
        plan=list(ctx.diagnosis_before.get("plan") or []),
        content_facts=list(ctx.content_facts),
        deep_rewrite=ctx.deep_rewrite,
        rewrite_headings=ctx.rewrite_headings,
    )
    try:
        candidate = await llm.rewrite_document(masked_document, llm_ctx, hits, context=text)
    except LLMError as exc:
        warnings.append(f"文档级改写失败：{exc}")
        return None
    if not LLMEngine.placeholders_intact(masked_document, candidate):
        warnings.append("文档级改写占位符未完整保留")
        return None

    restored = protector.restore(candidate, spans)
    restored, leak_hits = clean_leakage(restored)
    if leak_hits:
        warnings.append("文档级改写后又出现过程痕迹，已再次清除")
    new_paragraphs = split_paragraphs(restored)
    if len(new_paragraphs) != len(paragraphs):
        warnings.append(
            f"文档级改写段落数不一致（{len(paragraphs)} → {len(new_paragraphs)}）"
        )
        return None

    total_sentences = 0
    changed_sentences = 0
    for original, rewritten in zip(paragraphs, new_paragraphs):
        if _is_heading(original) and not ctx.rewrite_headings:
            continue
        total_sentences += len(
            [sentence for sentence in split_sentences(original) if sentence.strip()]
        )
        _coverage, changed, _untouched = _sentence_coverage(original, rewritten)
        changed_sentences += changed
    document_coverage = (
        round(changed_sentences / total_sentences, 4) if total_sentences else 1.0
    )
    if total_sentences and document_coverage < COVERAGE_TARGET:
        warnings.append(
            f"文档级改写覆盖率 {document_coverage:.0%} 低于目标，回退混合粒度补写"
        )
        return None

    results: list[ParagraphResult] = []
    for index, (original, rewritten) in enumerate(zip(paragraphs, new_paragraphs)):
        if _is_heading(original) and not ctx.rewrite_headings:
            rewritten = original
        rewritten, _ = clean_leakage(rewritten)
        diag_after = diagnose(rewritten, ctx.style)
        forbidden_hits = match_forbidden_templates(rewritten, ctx.forbidden_templates)
        if forbidden_hits:
            warnings.append(
                f"第 {index + 1} 段仍出现避雷库禁用模板："
                + "；".join(hit[:40] for hit in forbidden_hits[:3])
            )
        coverage, changed, untouched = _sentence_coverage(original, rewritten)
        metrics = paragraph_metrics(rewritten)
        metrics["ai_per_1000"] = diag_after.get("total_per_1000")
        metrics["coverage"] = coverage
        metrics["changed_sentences"] = changed
        metrics["untouched_sentences"] = untouched
        metrics["dominant"] = diag_after.get("dominant_label")
        metrics["sentence_risks"] = _sentence_risks(rewritten, engine, ctx)
        metrics["diagnosis_issues"] = [
            item.get("label") for item in (diag_after.get("plan") or [])[:4]
        ]
        results.append(
            ParagraphResult(
                index=index,
                original=original,
                rewritten=rewritten,
                changed_ratio=_changed_ratio(original, rewritten),
                length_ratio=_length_ratio(original, rewritten),
                metrics=metrics,
            )
        )
    return results


async def _finalize_response(
    ordered: list[ParagraphResult],
    warnings: list[str],
    ppl_issues: list[dict],
    candidate_scores: list[dict],
    ctx: RewriteContext,
    rules: list[Rule],
    cleaned_text: str,
    structure_changes: list[str] | None = None,
) -> RewriteResponse:
    structure_changes = structure_changes or []
    if ctx.structure_mode == "flexible" and not structure_changes:
        ordered, structure_changes = restructure(ordered)
        for change in structure_changes:
            warnings.append(f"结构调整：{change}")

    response = _build_response(ordered, warnings, ppl_issues, candidate_scores=candidate_scores)
    content_report = verify_content(
        cleaned_text,
        response.rewritten_text,
        ctx.content_facts,
        unsourced_before=unsourced_count(cleaned_text),
        unsourced_after=unsourced_count(response.rewritten_text),
    )
    response.content_report = ContentReport(**content_report)
    for item in content_report.get("warnings") or []:
        response.warnings.append(f"内容核验：{item}")

    audit_result = await asyncio.to_thread(
        audit_text,
        response.rewritten_text,
        RuleEngine(rules, ctx.whitelist, ctx.guard),
        use_local=ctx.use_local_model,
        whitelist=ctx.whitelist,
        context=ctx.style,
    )
    audit_result["diagnosis_before"] = ctx.diagnosis_before
    audit_result["diagnosis_compare"] = compare_diagnosis(
        ctx.diagnosis_before, audit_result.get("diagnosis") or {}
    )
    comparison = audit_result["diagnosis_compare"]
    if not comparison["improved"] and ctx.diagnosis_before.get("chars"):
        response.warnings.append("全文 AI 特征密度未下降，建议补充具体数据或人工复核")
    elif comparison["improved"] and comparison["drop_ratio"] < 0.1:
        response.warnings.append(
            "本轮 AI 特征降幅不足 10%，继续改写收益有限，建议先人工复核"
        )
    response.audit = AuditResult(**audit_result)
    return response


async def rewrite_single(
    text: str,
    ctx: RewriteContext,
    rules: list[Rule],
    llm: LLMEngine | None,
) -> tuple[ParagraphResult, list[str]]:
    """Rewrite one sentence/paragraph for the sentence-level retry action."""
    warnings: list[str] = []
    result = await _rewrite_one(
        0,
        text,
        ctx,
        rules,
        llm,
        warnings,
        asyncio.Semaphore(1),
    )
    return result, warnings


async def rewrite_document(
    text: str,
    ctx: RewriteContext,
    rules: list[Rule],
    llm: LLMEngine | None,
    emit: EmitFn | None = None,
    pause_event: asyncio.Event | None = None,
    job_id: int | None = None,
) -> RewriteResponse:
    timing = start_timing()
    started = time.perf_counter()
    warnings: list[str] = []
    ppl_issues: list[dict] = []
    if ctx.use_llm and (llm is None or not llm.configured):
        raise LLMError("改写需要规则 + LLM 混合执行，请先在 LLM 设置页配置 Base URL、模型和 API Key")

    def finish(response: RewriteResponse) -> RewriteResponse:
        response.timing = finish_timing(timing, started)
        return response

    # Stage 4 前置：先把过程痕迹清掉，避免被当成正文改写或计费。
    cleaned_text, doc_leaks = clean_leakage(text)
    if doc_leaks:
        warnings.append(
            "全文清除了过程痕迹："
            + "、".join(item["category"] for item in doc_leaks)
        )
    ctx.diagnosis_before = diagnose(cleaned_text, ctx.style)

    paragraphs = split_paragraphs(cleaned_text)
    if not paragraphs:
        return finish(
            _build_response([], warnings or ["没有解析到任何段落，请检查输入内容"])
        )

    ctx.facts_by_paragraph = assign_facts(ctx.content_facts, paragraphs)
    candidate_scores: list[dict] = []

    if ctx.rewrite_granularity == "document" and llm is not None and llm.configured:
        document_results = await _rewrite_document_level(
            cleaned_text, paragraphs, ctx, rules, llm, warnings
        )
        if document_results is not None:
            return finish(
                await _finalize_response(
                    document_results, warnings, ppl_issues, [], ctx, rules, cleaned_text
                )
            )
        warnings.append("文档级改写未成功，已回退到混合粒度")

    semaphore = asyncio.Semaphore(max(1, ctx.concurrency))
    tasks = [
        asyncio.create_task(
            _rewrite_one(
                i,
                p,
                ctx,
                rules,
                llm,
                warnings,
                semaphore,
                pause_event,
                ppl_issues,
                candidate_scores,
                job_id=job_id,
            )
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
    return finish(
        await _finalize_response(
            ordered, warnings, ppl_issues, candidate_scores, ctx, rules, cleaned_text
        )
    )
