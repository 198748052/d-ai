export interface SentenceRisk {
  text: string;
  risk: number;
  hits: number;
  dominant?: string;
}

export interface ParagraphMetrics {
  sentences?: number;
  cv?: number;
  short_count?: number;
  long_count?: number;
  opening_repeats?: number;
  hedge_count?: number;
  coverage?: number;
  changed_sentences?: number;
  untouched_sentences?: number;
  sentence_risks?: SentenceRisk[];
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
  sentences?: number;
  rewritten_sentences?: number;
  coverage?: number;
}

export interface RewriteTiming {
  total_seconds: number;
  llm_calls: number;
  llm_seconds: number;
  ppl_calls: number;
  ppl_seconds: number;
  rule_seconds: number;
  rhythm_calls: number;
  coverage_passes: number;
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

export interface DiagnosisFlavor {
  count: number;
  per_1000: number;
  terms?: string[];
}

export interface DiagnosisPlanItem {
  priority: number;
  code: string;
  label: string;
  action: string;
  count?: number;
}

export interface DiagnosisResult {
  context?: string;
  context_label?: string;
  chars?: number;
  flavors?: Record<string, DiagnosisFlavor>;
  dominant?: string;
  dominant_label?: string;
  total_per_1000?: number;
  structure?: Record<string, number>;
  issues?: string[];
  leakage?: { id: string; category: string; count: number; matched: string; note: string }[];
  plan?: DiagnosisPlanItem[];
}

export interface DiagnosisCompare {
  before_total: number;
  after_total: number;
  drop: number;
  drop_ratio: number;
  before_dominant_label: string;
  after_dominant_label: string;
  improved: boolean;
  reached_target: boolean;
}

export interface ContentFact {
  kind: "data" | "citation" | "example" | "limitation" | "judgment" | "method" | "other";
  text: string;
  anchor?: string;
}

export interface ClarifyQuestion {
  id: string;
  paragraph: number;
  claim: string;
  question: string;
  kind: string;
  suggestions: string[];
}

export interface ClarifyResponse {
  questions: ClarifyQuestion[];
  content_density: Record<string, number>;
}

export interface ContentReport {
  facts_provided: number;
  facts_used: number;
  density_before: Record<string, number>;
  density_after: Record<string, number>;
  warnings: string[];
}

export interface CandidateScore {
  score: number;
  proxy: number;
  semantic: number;
  natural: number;
  content: number;
  ai_per_1000?: number;
  index?: number;
  paragraph?: number;
  chunk?: number;
}

export interface AuditResult {
  total: number;
  items: AuditItem[];
  metrics?: AuditMetrics;
  diagnosis?: DiagnosisResult;
  diagnosis_before?: DiagnosisResult;
  diagnosis_compare?: DiagnosisCompare;
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
  content_report?: ContentReport | null;
  structure_changes?: string[];
  candidate_scores?: CandidateScore[];
  timing?: RewriteTiming;
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
  content_report?: ContentReport | null;
  structure_changes?: string[];
  candidate_scores?: CandidateScore[];
  timing?: RewriteTiming | null;
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
  reasoning_effort: string;
  local_enabled: boolean;
  local_model: string;
  local_dtype: string;
  ppl_min: number;
  ppl_retry: number;
  ppl_severe: number;
  candidate_count: number;
  deep_rewrite: boolean;
  structure_mode: string;
}

export interface RewriteLesson {
  id: number;
  style: string;
  kind: string;
  sentence: string;
  pattern: string;
  template: string;
  category: string;
  outcome: string;
  status: string;
  scope: string;
  strategy: string;
  original: string;
  perplexity: number;
  threshold: number;
  hits: number;
  source_job_id?: number | null;
  note: string;
  last_seen_at?: string;
  created_at: string;
  updated_at: string;
}

export interface LessonStats {
  total: number;
  lexical_total: number;
  legacy: number;
  active: number;
  candidate: number;
  ignored: number;
  resolved: number;
  survived: number;
  fixed: number;
  pending: number;
  words: number;
  collocations: number;
  connectors: number;
  categories: Record<string, number>;
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

export interface UsageDay {
  date: string;
  chars: number;
  jobs: number;
}

export interface RuleAuditVariant {
  file: string;
  scope: string;
  category: string;
  replacements: string[];
}

export interface RuleAuditItem {
  pattern: string;
  count: number;
  variants: RuleAuditVariant[];
}

export interface RuleAuditReport {
  total: number;
  by_category: Record<string, number>;
  by_severity: Record<string, number>;
  by_scope: Record<string, number>;
  duplicate_patterns: RuleAuditItem[];
  conflicting_replacements: RuleAuditItem[];
  invalid_regex: { file: string; pattern: string; error: string }[];
  short_lexicon_patterns: { file: string; pattern: string; severity: string }[];
  high_severity_without_replacement: { file: string; pattern: string }[];
  summary: Record<string, number>;
}

export interface SentenceRewriteResult {
  original: string;
  rewritten: string;
  risk_before: number;
  risk_after: number;
  changed_ratio: number;
  warnings: string[];
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
  content_facts?: ContentFact[];
  candidate_count?: number;
  deep_rewrite?: boolean;
  structure_mode?: "preserve" | "flexible";
  rewrite_granularity?: "hybrid" | "document";
  rewrite_headings?: boolean;
}

export interface DetectorFeedback {
  id: number;
  created_at: string;
  user_id?: number | null;
  job_id?: number | null;
  detector: string;
  detector_version: string;
  checked_at?: string | null;
  score_before: number;
  score_after: number;
  red_sentences: string[];
  notes: string;
  proxy_total?: number | null;
  proxy_features: Record<string, number>;
}

export interface DetectorJob {
  id: number;
  created_at: string;
  status: string;
  preview: string;
  proxy_total?: number | null;
}

export interface CalibrationGroup {
  sample_count: number;
  correlations: Record<string, number>;
  weights: Record<string, unknown>;
  recommendation: string;
}

export interface CalibrationResult {
  sample_count: number;
  correlations: Record<string, number>;
  weights: Record<string, unknown>;
  recommendation: string;
  groups?: Record<string, CalibrationGroup>;
  active_group?: string;
}

export interface DetectorCluster {
  label: string;
  count: number;
  examples: string[];
}

export interface DetectorImportResult {
  imported: number;
  skipped: number;
}

export interface MiningCandidate {
  kind: string;
  pattern: string;
  note: string;
  replacements: string[];
  severity: string;
  high_count: number;
  low_count: number;
  high_per_1000: number;
  low_per_1000: number;
  lift: number;
  examples: string[];
}

export interface MiningResponse {
  summary: Record<string, unknown>;
  lexicon: MiningCandidate[];
  regex: MiningCandidate[];
  structure: MiningCandidate[];
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
  content_report?: ContentReport | null;
  structure_changes?: string[];
  candidate_scores?: CandidateScore[];
  timing?: RewriteTiming;
}

export interface JobDetail extends JobSummary {
  original: string;
  rewritten: string;
  result: JobResult | null;
}
