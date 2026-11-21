export interface ParagraphMetrics {
  sentences?: number;
  cv?: number;
  short_count?: number;
  long_count?: number;
  opening_repeats?: number;
  hedge_count?: number;
}

export interface ParagraphResult {
  index: number;
  original: string;
  rewritten: string;
  changed_ratio: number;
  length_ratio: number;
  metrics?: ParagraphMetrics;
}

export interface RewriteStats {
  paragraphs: number;
  original_chars: number;
  rewritten_chars: number;
  avg_changed_ratio: number;
  avg_length_ratio: number;
}

export interface AuditItem {
  category: string;
  pattern: string;
  severity: string;
  count: number;
  note: string;
}

export interface AuditMetrics {
  sentences?: number;
  mean_len?: number;
  cv?: number;
  ttr?: number;
  repetition?: number;
  connector_density?: number;
  template_count?: number;
  adjacent_sim?: number;
  perplexity?: number;
  perplexity_min?: number;
  perplexity_max?: number;
  low_ppl_count?: number;
}

export interface AuditResult {
  total: number;
  items: AuditItem[];
  metrics?: AuditMetrics;
}

export interface PPLIssue {
  paragraph: number;
  sentence: string;
  perplexity: number;
  threshold: number;
  attempts: number;
}

export interface RewriteResponse {
  paragraphs: ParagraphResult[];
  rewritten_text: string;
  stats: RewriteStats;
  warnings: string[];
  ppl_issues: PPLIssue[];
  audit?: AuditResult | null;
}

export interface RewriteJobStatus {
  job_id: string;
  status: "running" | "done" | "error" | "canceled";
  total: number;
  completed: number;
  paragraphs: ParagraphResult[];
  stats: RewriteStats | null;
  audit?: AuditResult | null;
  warnings: string[];
  ppl_issues?: PPLIssue[];
  error: string | null;
}

export interface AdminStats {
  total_users: number;
  users_today: number;
  total_jobs: number;
  jobs_today: number;
  chars_today: number;
  active_users_7d: number;
  errors_24h: number;
  credits_total: number;
}

export interface ErrorItem {
  id: number;
  created_at: string;
  source: string;
  level: string;
  message: string;
  detail: string;
  path: string;
  user_id: number | null;
}

export interface Preset {
  id: number;
  name: string;
  style: string;
  lexicon_scope: string;
  strength: string;
  person: string;
  colloquial: number;
  length_ratio_min: number;
  length_ratio_max: number;
  protect_terms: string[];
  banned_words: string[];
  use_rule_engine: boolean;
  use_llm: boolean;
  max_rounds: number;
  extra_prompt: string;
  builtin: boolean;
}

export interface FeatureRule {
  id: number;
  name: string;
  category: string;
  scope: string;
  pattern: string;
  replacements: string[];
  severity: string;
  replace_mode: string;
  enabled: boolean;
  builtin: boolean;
  note: string;
}

export interface LLMSetting {
  provider: string;
  base_url: string;
  model: string;
  api_key_masked: string;
  has_key: boolean;
  temperature: number;
  max_tokens: number;
  concurrency: number;
  timeout: number;
  local_enabled: boolean;
  local_model: string;
  local_dtype: string;
  ppl_min: number;
  ppl_retry: number;
  ppl_severe: number;
}

export interface RewriteLesson {
  id: number;
  style: string;
  kind: string;
  sentence: string;
  original: string;
  perplexity: number;
  threshold: number;
  hits: number;
  note: string;
  created_at: string;
  updated_at: string;
}

export interface User {
  id: number;
  email: string;
  nickname: string;
  credits: number;
  is_admin: boolean;
}

export interface CreditLogItem {
  id: number;
  delta: number;
  reason: string;
  balance_after: number;
  created_at: string;
}

export interface AdminUser {
  id: number;
  email: string;
  nickname: string;
  credits: number;
  is_admin: boolean;
  created_at: string;
  last_login_at: string;
}

export interface RedeemCodeItem {
  id: number;
  code: string;
  credits: number;
  max_uses: number;
  used_count: number;
  expires_at?: string;
  created_at?: string;
}

export interface LocalModelStatus {
  loaded: boolean;
  loading: boolean;
  model?: string | null;
  dtype?: string | null;
  error?: string | null;
  progress?: string | null;
}

export type Mode = "rule" | "llm" | "hybrid";

export interface RewritePayload {
  text: string;
  mode: Mode;
  preset_id?: number;
  style?: string;
  lexicon_scope?: string;
  strength?: string;
  person?: string;
  colloquial?: number;
  protect_terms?: string[];
  banned_words?: string[];
  max_rounds?: number;
  extra_prompt?: string;
}


export interface JobSummary {
  id: number;
  created_at: string;
  updated_at: string;
  status: string;
  mode: string;
  style: string;
  strength: string;
  original_preview: string;
  progress_total: number;
  progress_completed: number;
  error: string;
}

export interface JobResult {
  paragraphs: ParagraphResult[];
  stats: RewriteStats;
  audit: AuditResult | null;
  warnings: string[];
  ppl_issues?: PPLIssue[];
}

export interface JobDetail extends JobSummary {
  original: string;
  rewritten: string;
  result: JobResult | null;
}
