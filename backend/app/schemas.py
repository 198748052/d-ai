from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, Field


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


class LLMSettingIn(BaseModel):
    provider: str = "openai"
    base_url: str = "https://api.openai.com/v1"
    model: str = "gpt-4o-mini"
    api_key: Optional[str] = None
    temperature: float = 1.2
    max_tokens: int = 4096
    concurrency: int = 3
    timeout: int = 120
    reasoning_effort: str = "medium"
    local_enabled: bool = False
    local_model: str = "Qwen/Qwen2.5-1.5B"
    local_dtype: str = "float16"
    ppl_min: float = 45.0
    ppl_retry: int = 2
    ppl_severe: float = 20.0


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


class PerplexityRequest(BaseModel):
    text: str
    max_sentences: int = 40


class PerplexityResult(BaseModel):
    average: float
    min: float
    max: float
    low_count: int
    sentences: list[dict] = Field(default_factory=list)
