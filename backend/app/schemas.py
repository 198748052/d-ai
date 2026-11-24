from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, Field


class ContentFact(BaseModel):
    kind: Literal[
        "data", "citation", "example", "limitation", "judgment", "method", "other"
    ] = "other"
    text: str
    anchor: str = ""


class ClarifyQuestion(BaseModel):
    id: str
    paragraph: int
    claim: str
    question: str
    kind: str
    suggestions: list[str] = Field(default_factory=list)


class ClarifyRequest(BaseModel):
    text: str


class ClarifyResponse(BaseModel):
    questions: list[ClarifyQuestion] = Field(default_factory=list)
    content_density: dict = Field(default_factory=dict)


class ContentReport(BaseModel):
    facts_provided: int = 0
    facts_used: int = 0
    density_before: dict = Field(default_factory=dict)
    density_after: dict = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)


class RewriteRequest(BaseModel):
    text: str
    preset_id: Optional[int] = None
    mode: Literal["rule", "llm", "hybrid"] = "hybrid"
    style: str = "general"
    lexicon_scope: str = "general"
    strength: Literal["light", "medium", "strong"] = "medium"
    person: Literal["keep", "first", "third"] = "keep"
    colloquial: int = 20
    length_ratio_min: float = 0.85
    length_ratio_max: float = 1.15
    protect_terms: list[str] = Field(default_factory=list)
    banned_words: list[str] = Field(default_factory=list)
    max_rounds: int = 1
    extra_prompt: str = ""
    content_facts: list[ContentFact] = Field(default_factory=list)
    candidate_count: int = 1
    deep_rewrite: bool = False
    structure_mode: Literal["preserve", "flexible"] = "preserve"
    rewrite_granularity: Literal["hybrid", "document"] = "hybrid"
    rewrite_headings: bool = False


class ParagraphResult(BaseModel):
    index: int
    original: str
    rewritten: str
    changed_ratio: float
    length_ratio: float
    metrics: dict = Field(default_factory=dict)


class RewriteStats(BaseModel):
    paragraphs: int
    original_chars: int
    rewritten_chars: int
    avg_changed_ratio: float
    avg_length_ratio: float
    sentences: int = 0
    rewritten_sentences: int = 0
    coverage: float = 1.0


class AuditItem(BaseModel):
    category: str
    pattern: str
    severity: str
    count: int
    note: str = ""


class AuditResult(BaseModel):
    total: int
    items: list[AuditItem] = Field(default_factory=list)
    metrics: dict = Field(default_factory=dict)
    diagnosis: dict = Field(default_factory=dict)
    diagnosis_before: dict = Field(default_factory=dict)
    diagnosis_compare: dict = Field(default_factory=dict)


class AuditRequest(BaseModel):
    text: str
    preset_id: Optional[int] = None
    style: str = "academic"
    lexicon_scope: str = "academic"


class PPLIssue(BaseModel):
    paragraph: int
    sentence: str
    perplexity: float
    threshold: float
    attempts: int


class RewriteResponse(BaseModel):
    paragraphs: list[ParagraphResult]
    rewritten_text: str
    stats: RewriteStats
    warnings: list[str] = Field(default_factory=list)
    ppl_issues: list[PPLIssue] = Field(default_factory=list)
    audit: Optional[AuditResult] = None
    content_report: Optional[ContentReport] = None
    structure_changes: list[str] = Field(default_factory=list)
    candidate_scores: list[dict] = Field(default_factory=list)
    timing: dict = Field(default_factory=dict)


class SentenceRewriteRequest(BaseModel):
    text: str
    style: str = "academic"
    lexicon_scope: str = "academic"


class SentenceRewriteResponse(BaseModel):
    original: str
    rewritten: str
    risk_before: float = 0.0
    risk_after: float = 0.0
    changed_ratio: float = 0.0
    warnings: list[str] = Field(default_factory=list)


class LLMSettingIn(BaseModel):
    provider: str = "openai"
    base_url: str = "https://api.openai.com/v1"
    model: str = "gpt-4o-mini"
    api_key: Optional[str] = None
    local_enabled: bool = False


class LLMSettingOut(BaseModel):
    provider: str
    base_url: str
    model: str
    api_key_masked: str
    has_key: bool
    temperature: float
    max_tokens: int
    concurrency: int
    timeout: int
    reasoning_effort: str = "medium"
    local_enabled: bool = False
    local_model: str = "Qwen/Qwen2.5-1.5B"
    local_dtype: str = "float16"
    ppl_min: float = 45.0
    ppl_retry: int = 2
    ppl_severe: float = 20.0
    candidate_count: int = 1
    deep_rewrite: bool = False
    structure_mode: str = "preserve"


class LLMTestIn(BaseModel):
    provider: str = "openai"
    base_url: str = "https://api.openai.com/v1"
    model: str = "gpt-4o-mini"
    api_key: Optional[str] = None


class LLMTestOut(BaseModel):
    ok: bool
    latency_ms: int = 0
    message: str = ""


class FeatureRuleIn(BaseModel):
    name: str = ""
    category: str = "lexicon"
    scope: str = "general"
    pattern: str
    replacements: list[str] = Field(default_factory=list)
    severity: str = "medium"
    replace_mode: str = "all"
    enabled: bool = True
    note: str = ""


class FeatureRuleOut(BaseModel):
    id: int
    name: str
    category: str
    scope: str
    pattern: str
    replacements: list[str]
    severity: str
    replace_mode: str
    enabled: bool
    builtin: bool
    note: str


class PresetIn(BaseModel):
    name: str
    style: str = "general"
    lexicon_scope: str = "general"
    strength: str = "medium"
    person: str = "keep"
    colloquial: int = 20
    length_ratio_min: float = 0.85
    length_ratio_max: float = 1.15
    protect_terms: list[str] = Field(default_factory=list)
    banned_words: list[str] = Field(default_factory=list)
    use_rule_engine: bool = True
    use_llm: bool = True
    max_rounds: int = 1
    extra_prompt: str = ""


class PresetOut(BaseModel):
    id: int
    name: str
    style: str
    lexicon_scope: str
    strength: str
    person: str
    colloquial: int
    length_ratio_min: float
    length_ratio_max: float
    protect_terms: list[str]
    banned_words: list[str]
    use_rule_engine: bool
    use_llm: bool
    max_rounds: int
    extra_prompt: str
    builtin: bool


class ExportRequest(BaseModel):
    text: str
    format: Literal["txt", "md", "docx"] = "docx"
    filename: str = "rewritten"


class ImportResult(BaseModel):
    imported: int
    skipped: int


class GenericMessage(BaseModel):
    message: str
    data: Optional[Any] = None


class LocalModelLoadIn(BaseModel):
    model: Optional[str] = None
    dtype: Optional[str] = None


class LocalModelStatusOut(BaseModel):
    loaded: bool
    loading: bool = False
    model: Optional[str] = None
    dtype: Optional[str] = None
    error: Optional[str] = None
    progress: Optional[str] = None


class DetectorFeedbackIn(BaseModel):
    job_id: Optional[int] = None
    detector: str
    detector_version: str = ""
    checked_at: Optional[str] = None
    score_before: float = 0.0
    score_after: float = 0.0
    red_sentences: list[str] = Field(default_factory=list)
    notes: str = ""


class DetectorFeedbackOut(BaseModel):
    id: int
    created_at: str
    user_id: Optional[int] = None
    job_id: Optional[int] = None
    detector: str
    detector_version: str
    checked_at: Optional[str] = None
    score_before: float
    score_after: float
    red_sentences: list[str] = Field(default_factory=list)
    notes: str = ""
    proxy_total: Optional[float] = None
    proxy_features: dict = Field(default_factory=dict)


class CalibrationOut(BaseModel):
    sample_count: int
    correlations: dict = Field(default_factory=dict)
    weights: dict = Field(default_factory=dict)
    recommendation: str = ""
    groups: dict = Field(default_factory=dict)
    active_group: str = ""


class DetectorFeedbackImport(BaseModel):
    csv: str = ""


class DetectorClusterOut(BaseModel):
    label: str
    count: int
    examples: list[str] = Field(default_factory=list)


class MiningRequest(BaseModel):
    high_texts: list[str] = Field(default_factory=list)
    low_texts: list[str] = Field(default_factory=list)
    top_n: int = 30


class MiningCandidate(BaseModel):
    kind: str
    pattern: str
    note: str = ""
    replacements: list[str] = Field(default_factory=list)
    severity: str = "medium"
    high_count: int = 0
    low_count: int = 0
    high_per_1000: float = 0.0
    low_per_1000: float = 0.0
    lift: float = 0.0
    examples: list[str] = Field(default_factory=list)


class MiningResponse(BaseModel):
    summary: dict = Field(default_factory=dict)
    lexicon: list[MiningCandidate] = Field(default_factory=list)
    regex: list[MiningCandidate] = Field(default_factory=list)
    structure: list[MiningCandidate] = Field(default_factory=list)


class MiningApplyRequest(BaseModel):
    candidates: list[MiningCandidate] = Field(default_factory=list)


class PerplexityRequest(BaseModel):
    text: str
    max_sentences: int = 40


class PerplexityResult(BaseModel):
    average: float
    min: float
    max: float
    low_count: int
    sentences: list[dict] = Field(default_factory=list)
