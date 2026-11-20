from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlmodel import Field, SQLModel


class FeatureRule(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = ""
    category: str = "lexicon"  # lexicon | regex
    scope: str = "general"  # general | fiction | academic | media
    pattern: str
    replacements: str = "[]"  # JSON list of strings
    severity: str = "medium"  # high | medium | low
    replace_mode: str = "all"  # all | alternate | first
    enabled: bool = True
    builtin: bool = False
    note: str = ""


class LLMSetting(SQLModel, table=True):
    id: int = Field(default=1, primary_key=True)
    provider: str = "openai"
    base_url: str = "https://api.openai.com/v1"
    model: str = "gpt-4o-mini"
    api_key_enc: str = ""
    temperature: float = 1.2
    max_tokens: int = 4096
    concurrency: int = 3
    timeout: int = 120
    local_enabled: bool = False
    local_model: str = "uer/gpt2-chinese-cluecorpussmall"
    local_dtype: str = "float16"
    ppl_min: float = 60.0
    ppl_retry: int = 2
    ppl_severe: float = 25.0


class RewriteLesson(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    style: str = "academic"
    kind: str = "low_perplexity"  # low_perplexity
    sentence: str = ""
    original: str = ""
    perplexity: float = 0.0
    threshold: float = 0.0
    hits: int = 1
    note: str = ""


class Preset(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str
    style: str = "general"  # general | academic | media | fiction | official
    lexicon_scope: str = "general"
    strength: str = "medium"  # light | medium | strong
    person: str = "keep"  # keep | first | third
    colloquial: int = 20
    length_ratio_min: float = 0.85
    length_ratio_max: float = 1.15
    protect_terms: str = "[]"
    banned_words: str = "[]"
    use_rule_engine: bool = True
    use_llm: bool = True
    max_rounds: int = 1
    extra_prompt: str = ""
    builtin: bool = False


class RewriteJob(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    mode: str = "hybrid"
    style: str = "general"
    strength: str = "medium"
    original: str = ""
    rewritten: str = ""
    params_json: str = "{}"
    result_json: str = ""
    error: str = ""
    progress_total: int = 0
    progress_completed: int = 0
    status: str = "running"
