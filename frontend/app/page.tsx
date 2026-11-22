"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { apiGet, apiSend, exportDocument, fetchRewriteJob, startRewriteJob } from "@/lib/api";
import { useAuth } from "@/components/AuthContext";
import type {
  AuditResult,
  ClarifyQuestion,
  ClarifyResponse,
  ContentFact,
  ContentReport,
  PPLIssue,
  ParagraphResult,
  Preset,
  RewriteJobStatus,
  RewriteStats,
} from "@/lib/types";

const SAMPLE = `首先，值得注意的是，人工智能技术正在快速发展。其次，综上所述，这一技术在各行各业都具有重要意义。随着数字化进程的不断推进，越来越多的企业开始积极探索智能化转型路径。

此外，由此可见，我们需要进一步深入研究相关技术。与此同时，不可否认的是，人工智能在提升效率的同时，也带来了一系列新的挑战。因此，如何在发展与规范之间取得平衡，成为当前亟需解决的重要问题。`;

function countParagraphs(text: string): number {
  const normalized = text.replace(/\r\n?/g, "\n").trim();
  if (!normalized) return 0;
  const blocks = normalized
    .split(/\n[ \t]*\n+/)
    .map((b) => b.trim())
    .filter(Boolean);
  if (blocks.length <= 1 && normalized.includes("\n")) {
    const lines = normalized.split("\n").filter((l) => l.trim());
    if (lines.length > 1) return lines.length;
  }
  return blocks.length;
}

function percent(value: number): string {
  return `${Math.round(value * 100)}%`;
}

const FLAVOR_LABELS: Record<string, string> = {
  hollow: "空洞升华",
  template: "模板句式",
  high_freq: "高频套话",
  register: "语体错位",
  leakage: "思维链泄露",
};

export default function WorkspacePage() {
  const router = useRouter();
  const { user } = useAuth();
  const [text, setText] = useState("");
  const [preset, setPreset] = useState<Preset | null>(null);
  const [ruleCount, setRuleCount] = useState(0);

  const [running, setRunning] = useState(false);
  const [paragraphs, setParagraphs] = useState<ParagraphResult[]>([]);
  const [stats, setStats] = useState<RewriteStats | null>(null);
  const [audit, setAudit] = useState<AuditResult | null>(null);
  const [rewrittenText, setRewrittenText] = useState("");
  const [warnings, setWarnings] = useState<string[]>([]);
  const [pplIssues, setPplIssues] = useState<PPLIssue[]>([]);
  const [error, setError] = useState("");
  const [total, setTotal] = useState(0);
  const [copied, setCopied] = useState(false);
  const [jobDbId, setJobDbId] = useState<number | null>(null);
  const [draftSavedAt, setDraftSavedAt] = useState("");
  const [clarifyQuestions, setClarifyQuestions] = useState<ClarifyQuestion[]>([]);
  const [clarifyAnswers, setClarifyAnswers] = useState<Record<string, string>>({});
  const [contentFacts, setContentFacts] = useState<ContentFact[]>([]);
  const [clarifyLoading, setClarifyLoading] = useState(false);
  const [showClarify, setShowClarify] = useState(false);
  const [contentReport, setContentReport] = useState<ContentReport | null>(null);
  const [structureChanges, setStructureChanges] = useState<string[]>([]);
  const [rewriteGranularity, setRewriteGranularity] = useState<"hybrid" | "document">(
    "hybrid"
  );

  useEffect(() => {
    try {
      const raw = localStorage.getItem("rewrite-draft");
      if (!raw) return;
      const draft = JSON.parse(raw) as { text?: string; savedAt?: string };
      if (draft.text) {
        setText(draft.text);
        setDraftSavedAt(draft.savedAt ?? "");
      }
    } catch {
      // ignore broken draft
    }
  }, []);

  useEffect(() => {
    if (!text) return;
    const timer = setTimeout(() => {
      const savedAt = new Date().toLocaleTimeString("zh-CN", {
        hour: "2-digit",
        minute: "2-digit",
      });
      try {
        localStorage.setItem("rewrite-draft", JSON.stringify({ text, savedAt }));
        setDraftSavedAt(savedAt);
      } catch {
        // ignore quota errors
      }
    }, 600);
    return () => clearTimeout(timer);
  }, [text]);

  useEffect(() => {
    apiGet<Preset[]>("/api/presets")
      .then((data) => setPreset(data[0] ?? null))
      .catch(() => undefined);
    apiGet<unknown[]>("/api/features")
      .then((data) => setRuleCount(data.length))
      .catch(() => undefined);
  }, []);

  const doneCount = paragraphs.length;
  const progress = total ? Math.min(100, Math.round((doneCount / total) * 100)) : 0;

  const warningSummary = useMemo(() => {
    let empty = 0;
    let abnormal = 0;
    let other = 0;
    for (const item of warnings) {
      if (item.includes("返回空内容")) empty += 1;
      else if (item.includes("长度异常") || item.includes("重复")) abnormal += 1;
      else other += 1;
    }
    return { empty, abnormal, other };
  }, [warnings]);

  const handleClarify = useCallback(async () => {
    if (!user) {
      router.push("/login");
      return;
    }
    if (!text.trim()) {
      setError("请先粘贴需要改写的文章");
      return;
    }
    setClarifyLoading(true);
    setError("");
    try {
      const result = await apiSend<ClarifyResponse>(
        "/api/rewrite/clarify",
        "POST",
        { text }
      );
      setClarifyQuestions(result.questions);
      setClarifyAnswers({});
      setShowClarify(true);
      if (!result.questions.length) {
        setError("没有扫描到明显的内容缺口，可以直接开始改写");
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "扫描内容缺口失败");
    } finally {
      setClarifyLoading(false);
    }
  }, [text, user, router]);

  const handleApplyFacts = useCallback(() => {
    const facts: ContentFact[] = [];
    for (const question of clarifyQuestions) {
      const value = (clarifyAnswers[question.id] ?? "").trim();
      if (!value) continue;
      facts.push({
        kind: question.kind as ContentFact["kind"],
        text: value,
        anchor: `第${question.paragraph}段`,
      });
    }
    setContentFacts(facts);
    setShowClarify(false);
    if (!facts.length) {
      setError("还没有填写任何补充内容");
    }
  }, [clarifyQuestions, clarifyAnswers]);

  const handleRewrite = useCallback(async () => {
    if (!user) {
      router.push("/login");
      return;
    }
    if (!text.trim()) {
      setError("请先粘贴需要改写的文章");
      return;
    }
    if (text.length > 30000) {
      setError("文本过长，单次上限 30000 字，请分段处理");
      return;
    }
    setRunning(true);
    setError("");
    setWarnings([]);
    setPplIssues([]);
    setParagraphs([]);
    setStats(null);
    setAudit(null);
    setRewrittenText("");
    setContentReport(null);
    setStructureChanges([]);
    setTotal(countParagraphs(text));

    try {
      const { job_id, db_id, total: jobTotal } = await startRewriteJob({
        text,
        mode: "hybrid",
        preset_id: preset?.id,
        content_facts: contentFacts,
        candidate_count: 1,
        deep_rewrite: false,
        structure_mode: "preserve",
        rewrite_granularity: rewriteGranularity,
      });
      setTotal(jobTotal);
      setJobDbId(db_id);

      let failures = 0;
      for (;;) {
        await new Promise((resolve) => setTimeout(resolve, 700));
        let job: RewriteJobStatus;
        try {
          job = await fetchRewriteJob(job_id);
          failures = 0;
        } catch (err) {
          failures += 1;
          if (failures >= 5) throw err;
          continue;
        }

        setParagraphs(job.paragraphs);
        setWarnings(job.warnings ?? []);
        setPplIssues(job.ppl_issues ?? []);

        if (job.status === "done") {
          setStats(job.stats);
          setAudit(job.audit ?? null);
          setContentReport(job.content_report ?? null);
          setStructureChanges(job.structure_changes ?? []);
          setRewrittenText(job.paragraphs.map((item) => item.rewritten).join("\n\n"));
          break;
        }
        if (job.status === "error") {
          setError(job.error || "改写失败");
          break;
        }
        if (job.status === "canceled") {
          setError("任务已取消");
          break;
        }
      }
    } catch (err) {
      const message = err instanceof Error ? err.message : "改写失败";
      if (message.includes("请先登录")) {
        router.push("/login");
        return;
      }
      setError(message);
    } finally {
      setRunning(false);
      setJobDbId(null);
    }
  }, [text, preset, user, router, contentFacts, rewriteGranularity]);

  const handleCancel = useCallback(async () => {
    if (!jobDbId) return;
    try {
      await apiSend<{ status: string; refunded: boolean }>(
        `/api/jobs/${jobDbId}/cancel`,
        "POST"
      );
      setError("任务已取消");
    } catch (err) {
      setError(err instanceof Error ? err.message : "取消失败");
    }
  }, [jobDbId]);

  const handleCopy = useCallback(async () => {
    if (!rewrittenText) return;
    await navigator.clipboard.writeText(rewrittenText);
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  }, [rewrittenText]);

  const handleExport = useCallback(
    async (format: "txt" | "md" | "docx") => {
      if (!rewrittenText) return;
      try {
        await exportDocument(rewrittenText, format);
      } catch (err) {
        setError(err instanceof Error ? err.message : "导出失败");
      }
    },
    [rewrittenText]
  );

  return (
    <div className="space-y-5">
      <section className="rounded-xl border border-ink-200 bg-white p-5 shadow-card">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h1 className="text-lg font-semibold tracking-tight text-ink-900">
              学术论文 AI 特征改写
            </h1>
            <p className="mt-1 text-sm text-ink-500">
              段落数量、顺序和主题保持不变。先按规则库删除或替换 AI 特征，再用 LLM 分片改写并复检。
            </p>
            <p className="mt-2 text-xs text-ink-400">
              当前预设：{preset?.name ?? "学术论文"} · 规则 + LLM 混合改写 · 规则库 {ruleCount || "—"} 条
            </p>
          </div>
          {user?.is_admin && (
            <Link
              href="/settings/llm"
              className="rounded-lg border border-ink-200 px-3 py-1.5 text-sm text-ink-600 hover:bg-ink-50"
            >
              LLM 配置
            </Link>
          )}
        </div>
      </section>

      <section className="rounded-xl border border-ink-200 bg-white p-5 shadow-card">
        <div className="mb-2 flex items-center justify-between">
          <label className="text-sm font-medium text-ink-800">原文</label>
          <div className="flex items-center gap-3 text-sm">
            <button
              type="button"
              onClick={() => setText(SAMPLE)}
              className="text-ink-500 hover:text-ink-800"
            >
              填入示例
            </button>
            <button
              type="button"
              onClick={() => {
                setText("");
                setDraftSavedAt("");
                try {
                  localStorage.removeItem("rewrite-draft");
                } catch {
                  // ignore
                }
              }}
              className="text-ink-500 hover:text-ink-800"
            >
              清空
            </button>
            <span className={text.length > 30000 ? "text-red-500" : "text-ink-400"}>
              {text.length} / 30000 字
            </span>
            {draftSavedAt && (
              <span className="text-xs text-ink-400">草稿已保存 {draftSavedAt}</span>
            )}
          </div>
        </div>
        <textarea
          value={text}
          onChange={(e) => setText(e.target.value)}
          placeholder="把需要改写的论文段落粘贴到这里，段落之间用空行分隔。"
          className="h-56 w-full resize-y rounded-lg border border-ink-200 bg-ink-50/40 p-3 text-sm leading-7 text-ink-800 outline-none transition focus:border-accent-500 focus:bg-white focus:ring-2 focus:ring-accent-100"
        />

        <div className="mt-3 rounded-lg border border-accent-100 bg-accent-50/60 px-3 py-2 text-xs text-accent-700">
          学术模式：口语化已关闭。流程为「内容缺口扫描 → 规则库删除/替换 → 多候选 LLM 改写 → 复检与结构复核 → 特征审计」。
        </div>

        <div className="mt-3 flex flex-wrap items-center gap-3 text-xs text-ink-500">
          <span className="rounded-md bg-ink-100 px-2 py-1">
            稳定模式：单候选 · 保留段落 · 关闭深度改写
          </span>
          <label className="flex items-center gap-1.5">
            改写粒度
            <select
              value={rewriteGranularity}
              onChange={(e) =>
                setRewriteGranularity(e.target.value === "document" ? "document" : "hybrid")
              }
              className="rounded-md border border-ink-200 bg-white px-2 py-1"
            >
              <option value="hybrid">混合（句 + 段，默认）</option>
              <option value="document">文档级</option>
            </select>
          </label>
          {contentFacts.length > 0 && (
            <span className="rounded-full bg-emerald-50 px-2 py-0.5 text-emerald-700">
              已补充 {contentFacts.length} 条事实
            </span>
          )}
        </div>
        {rewriteGranularity === "document" && (
          <p className="mt-2 text-[11px] text-ink-400">
            文档级适合 8000 字以内的文本；段落数不一致时会自动回退混合模式。
          </p>
        )}

        <div className="mt-4 flex flex-wrap items-center gap-3">
          <button
            type="button"
            onClick={handleRewrite}
            disabled={running}
            className="rounded-lg bg-accent-600 px-4 py-2 text-sm font-medium text-white transition hover:bg-accent-700 disabled:cursor-not-allowed disabled:opacity-60"
          >
            {running ? "改写中…" : "开始改写"}
          </button>
          <button
            type="button"
            onClick={handleClarify}
            disabled={running || clarifyLoading}
            className="rounded-lg border border-accent-200 px-3 py-2 text-sm text-accent-700 hover:bg-accent-50 disabled:cursor-not-allowed disabled:opacity-60"
          >
            {clarifyLoading ? "扫描中…" : "扫描内容缺口"}
          </button>
          {running && (
            <button
              type="button"
              onClick={handleCancel}
              className="rounded-lg border border-ink-200 px-3 py-2 text-sm text-ink-600 hover:bg-ink-50"
            >
              取消任务
            </button>
          )}
          {running && (
            <span className="text-sm text-ink-500">
              已处理 {doneCount}/{total || "?"} 段
            </span>
          )}
          {user ? (
            <span className="text-xs text-ink-500">
              本次预计消耗 {text.replace(/\s/g, "").length} 字 · 余额 {user.credits} 字
            </span>
          ) : (
            <Link href="/login" className="text-xs text-accent-700 hover:underline">
              登录后可提交改写
            </Link>
          )}
          {running && (
            <div className="h-1.5 w-40 overflow-hidden rounded-full bg-ink-100">
              <div
                className="h-full rounded-full bg-accent-500 transition-all"
                style={{ width: `${progress}%` }}
              />
            </div>
          )}
        </div>
      </section>

      {showClarify && (
        <section className="rounded-xl border border-accent-200 bg-white p-5 shadow-card">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <h2 className="text-sm font-semibold text-ink-900">补充具体内容（选填）</h2>
              <p className="mt-1 text-xs text-ink-500">
                只填写你确认过的真实信息。数字、样本量、引用、失败案例会原样写入，模型不会自行编造。不填也可以直接开始改写。
              </p>
            </div>
            <button
              type="button"
              onClick={() => setShowClarify(false)}
              className="text-xs text-ink-400 hover:text-ink-700"
            >
              关闭
            </button>
          </div>
          {clarifyQuestions.length === 0 ? (
            <p className="mt-3 text-sm text-ink-500">没有扫描到明显的内容缺口。</p>
          ) : (
            <div className="mt-3 space-y-3">
              {clarifyQuestions.map((question) => (
                <div key={question.id} className="rounded-lg border border-ink-200 p-3">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="rounded-md bg-ink-100 px-2 py-0.5 text-xs text-ink-600">
                      第 {question.paragraph} 段 · {question.kind}
                    </span>
                    <span className="text-xs text-ink-400">命中：{question.claim}</span>
                  </div>
                  <p className="mt-1.5 text-sm text-ink-800">{question.question}</p>
                  <textarea
                    value={clarifyAnswers[question.id] ?? ""}
                    onChange={(e) =>
                      setClarifyAnswers((prev) => ({
                        ...prev,
                        [question.id]: e.target.value,
                      }))
                    }
                    placeholder={`例如：${question.suggestions.join("、")}`}
                    className="mt-2 h-20 w-full resize-y rounded-lg border border-ink-200 bg-ink-50/40 p-2 text-sm leading-6 text-ink-800 outline-none focus:border-accent-500 focus:bg-white"
                  />
                </div>
              ))}
              <div className="flex items-center gap-3">
                <button
                  type="button"
                  onClick={handleApplyFacts}
                  className="rounded-lg bg-accent-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-accent-700"
                >
                  保存补充内容
                </button>
                <span className="text-xs text-ink-400">
                  没填的问题会跳过，原文保持原有概括程度。
                </span>
              </div>
            </div>
          )}
        </section>
      )}

      {error && (
        <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
          {error}
        </div>
      )}
      {warnings.length > 0 && (
        <div className="rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800">
          <p>
            部分段落使用了回退结果，最终文本仍然可用：
            {warningSummary.empty > 0 && ` LLM 返回空内容 ${warningSummary.empty} 次；`}
            {warningSummary.abnormal > 0 && ` 长度异常或重复 ${warningSummary.abnormal} 次；`}
            {warningSummary.other > 0 && ` 其他 ${warningSummary.other} 次；`}
          </p>
          <details className="mt-2">
            <summary className="cursor-pointer text-xs text-amber-700">查看明细</summary>
            <ul className="mt-2 list-inside list-disc space-y-1 text-xs">
              {warnings.map((item, index) => (
                <li key={index}>{item}</li>
              ))}
            </ul>
          </details>
        </div>
      )}

      {pplIssues.length > 0 && (
        <div className="rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800">
          <p className="font-medium">
            以下 {pplIssues.length} 句重写后困惑度仍未达标，建议手动修改：
          </p>
          <ul className="mt-2 space-y-2">
            {pplIssues.map((item, index) => (
              <li
                key={`${item.paragraph}-${index}`}
                className="rounded-md border border-amber-200 bg-white/60 px-3 py-2 text-xs"
              >
                <div className="mb-1 text-amber-700">
                  第 {item.paragraph} 段 · 困惑度 {item.perplexity}（阈值 {item.threshold}）
                </div>
                <div className="select-text text-ink-800">{item.sentence}</div>
              </li>
            ))}
          </ul>
        </div>
      )}

      {stats && (
        <section className="rounded-xl border border-ink-200 bg-white p-5 shadow-card">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div className="flex flex-wrap gap-x-6 gap-y-2 text-sm">
              <span className="text-ink-500">
                段落 <strong className="text-ink-900">{stats.paragraphs}</strong>
              </span>
              <span className="text-ink-500">
                字数 <strong className="text-ink-900">{stats.original_chars}</strong> →{" "}
                <strong className="text-ink-900">{stats.rewritten_chars}</strong>
              </span>
              <span className="text-ink-500">
                平均改写率{" "}
                <strong className="text-ink-900">{percent(stats.avg_changed_ratio)}</strong>
              </span>
              <span className="text-ink-500">
                字数比{" "}
                <strong className="text-ink-900">{percent(stats.avg_length_ratio)}</strong>
              </span>
            </div>
            <div className="flex items-center gap-2">
              <button
                type="button"
                onClick={handleCopy}
                className="rounded-lg border border-ink-200 px-3 py-1.5 text-sm text-ink-600 hover:bg-ink-50"
              >
                {copied ? "已复制" : "复制全文"}
              </button>
              {(["txt", "md", "docx"] as const).map((format) => (
                <button
                  key={format}
                  type="button"
                  onClick={() => handleExport(format)}
                  className="rounded-lg border border-ink-200 px-3 py-1.5 text-sm text-ink-600 hover:bg-ink-50"
                >
                  {format.toUpperCase()}
                </button>
              ))}
            </div>
          </div>
        </section>
      )}

      {audit && (
        <section className="rounded-xl border border-ink-200 bg-white p-5 shadow-card">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <h2 className="text-sm font-semibold text-ink-900">AI 特征审计</h2>
              <p className="mt-1 text-xs text-ink-500">
                按规则库复查改写结果，剩余命中 {audit.total} 处，数值越低说明已知特征残留越少
              </p>
            </div>
            <span
              className={
                audit.total === 0
                  ? "rounded-full bg-emerald-50 px-3 py-1 text-xs font-medium text-emerald-700"
                  : "rounded-full bg-amber-50 px-3 py-1 text-xs font-medium text-amber-700"
              }
            >
              {audit.total === 0 ? "未发现明显特征" : `剩余 ${audit.total} 处`}
            </span>
          </div>
          {audit.metrics && (
            <div className="mt-3 flex flex-wrap gap-2 text-xs">
              <span className="rounded-md bg-ink-100 px-2 py-1 text-ink-600">
                平均句长{" "}
                <strong className="text-ink-900">{audit.metrics.mean_len ?? "-"}</strong>
              </span>
              <span className="rounded-md bg-ink-100 px-2 py-1 text-ink-600">
                句长CV{" "}
                <strong
                  className={
                    (audit.metrics.cv ?? 0) < 0.3 ? "text-amber-600" : "text-emerald-600"
                  }
                >
                  {audit.metrics.cv ?? "-"}
                </strong>
              </span>
              <span className="rounded-md bg-ink-100 px-2 py-1 text-ink-600">
                连接词密度{" "}
                <strong
                  className={
                    (audit.metrics.connector_density ?? 0) > 5
                      ? "text-amber-600"
                      : "text-emerald-600"
                  }
                >
                  {audit.metrics.connector_density ?? "-"}
                </strong>
              </span>
              <span className="rounded-md bg-ink-100 px-2 py-1 text-ink-600">
                词汇多样性{" "}
                <strong
                  className={
                    (audit.metrics.ttr ?? 1) < 0.45 ? "text-amber-600" : "text-emerald-600"
                  }
                >
                  {audit.metrics.ttr ?? "-"}
                </strong>
              </span>
              <span className="rounded-md bg-ink-100 px-2 py-1 text-ink-600">
                相邻句相似度{" "}
                <strong
                  className={
                    (audit.metrics.adjacent_sim ?? 0) > 0.2
                      ? "text-amber-600"
                      : "text-emerald-600"
                  }
                >
                  {audit.metrics.adjacent_sim ?? "-"}
                </strong>
              </span>
              {audit.metrics.perplexity !== undefined && (
                <span className="rounded-md bg-ink-100 px-2 py-1 text-ink-600">
                  平均困惑度{" "}
                  <strong className="text-ink-900">{audit.metrics.perplexity}</strong>
                </span>
              )}
              {audit.metrics.low_ppl_count !== undefined && (
                <span className="rounded-md bg-ink-100 px-2 py-1 text-ink-600">
                  低困惑度句{" "}
                  <strong
                    className={
                      (audit.metrics.low_ppl_count ?? 0) > 0
                        ? "text-amber-600"
                        : "text-emerald-600"
                    }
                  >
                    {audit.metrics.low_ppl_count}
                  </strong>
                </span>
              )}
            </div>
          )}
          {audit.diagnosis && (
            <div className="mt-4 rounded-lg border border-ink-100 bg-ink-50/50 p-3">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <span className="text-xs font-medium text-ink-700">
                  AI 味诊断（每千字）
                </span>
                {audit.diagnosis_compare && (
                  <span
                    className={
                      audit.diagnosis_compare.improved
                        ? "text-xs text-emerald-700"
                        : "text-xs text-amber-700"
                    }
                  >
                    {audit.diagnosis_compare.before_total} →{" "}
                    {audit.diagnosis_compare.after_total}
                    （{audit.diagnosis_compare.improved ? "下降" : "未下降"}{" "}
                    {Math.abs(Math.round(audit.diagnosis_compare.drop_ratio * 100))}%）
                  </span>
                )}
              </div>
              <div className="mt-2 flex flex-wrap gap-2 text-xs">
                {Object.entries(audit.diagnosis.flavors ?? {}).map(([key, value]) => (
                  <span
                    key={key}
                    className={
                      key === audit.diagnosis?.dominant
                        ? "rounded-md bg-amber-100 px-2 py-1 text-amber-800"
                        : "rounded-md bg-white px-2 py-1 text-ink-600"
                    }
                  >
                    {FLAVOR_LABELS[key] ?? key}{" "}
                    <strong className="text-ink-900">{value.per_1000}</strong>
                  </span>
                ))}
              </div>
              {audit.diagnosis.issues && audit.diagnosis.issues.length > 0 && (
                <ul className="mt-2 list-inside list-disc space-y-0.5 text-xs text-ink-600">
                  {audit.diagnosis.issues.slice(0, 6).map((item, index) => (
                    <li key={index}>{item}</li>
                  ))}
                </ul>
              )}
              {audit.diagnosis.plan && audit.diagnosis.plan.length > 0 && (
                <div className="mt-2 flex flex-wrap gap-1.5 text-xs">
                  {audit.diagnosis.plan.slice(0, 8).map((item, index) => (
                    <span
                      key={`${item.code}-${index}`}
                      className="rounded-md border border-ink-200 bg-white px-2 py-0.5 text-ink-600"
                      title={item.action}
                    >
                      {item.code} {item.label}
                    </span>
                  ))}
                </div>
              )}
              <p className="mt-2 text-[11px] text-ink-400">
                诊断是离线代理指标，目标是让中文读者读起来更像人写的；检测分数不是质量指标。
              </p>
            </div>
          )}
          {audit.items.length > 0 && (
            <ul className="mt-3 grid gap-2 md:grid-cols-2">
              {audit.items.slice(0, 20).map((item, index) => (
                <li
                  key={`${item.pattern}-${index}`}
                  className="flex items-center justify-between gap-2 rounded-lg bg-ink-50 px-3 py-2 text-xs"
                >
                  <span className="truncate text-ink-700" title={item.pattern}>
                    {item.note || item.pattern}
                  </span>
                  <span
                    className={
                      item.severity === "high"
                        ? "shrink-0 font-medium text-red-500"
                        : item.severity === "medium"
                          ? "shrink-0 font-medium text-amber-600"
                          : "shrink-0 text-ink-400"
                    }
                  >
                    {item.count}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </section>
      )}

      {(contentReport || structureChanges.length > 0) && (
        <section className="rounded-xl border border-ink-200 bg-white p-5 shadow-card">
          <h2 className="text-sm font-semibold text-ink-900">内容与结构核验</h2>
          {contentReport && (
            <div className="mt-2 flex flex-wrap gap-2 text-xs">
              <span className="rounded-md bg-ink-100 px-2 py-1 text-ink-600">
                补充事实{" "}
                <strong className="text-ink-900">
                  {contentReport.facts_used}/{contentReport.facts_provided}
                </strong>
              </span>
              <span className="rounded-md bg-ink-100 px-2 py-1 text-ink-600">
                数字{" "}
                <strong className="text-ink-900">
                  {contentReport.density_before.numbers ?? 0} →{" "}
                  {contentReport.density_after.numbers ?? 0}
                </strong>
              </span>
              <span className="rounded-md bg-ink-100 px-2 py-1 text-ink-600">
                引用{" "}
                <strong className="text-ink-900">
                  {contentReport.density_before.citations ?? 0} →{" "}
                  {contentReport.density_after.citations ?? 0}
                </strong>
              </span>
              <span className="rounded-md bg-ink-100 px-2 py-1 text-ink-600">
                局限/案例{" "}
                <strong className="text-ink-900">
                  {(contentReport.density_before.limitations ?? 0) +
                    (contentReport.density_before.examples ?? 0)}{" "}
                  →{" "}
                  {(contentReport.density_after.limitations ?? 0) +
                    (contentReport.density_after.examples ?? 0)}
                </strong>
              </span>
            </div>
          )}
          {contentReport?.warnings && contentReport.warnings.length > 0 && (
            <ul className="mt-2 list-inside list-disc space-y-0.5 text-xs text-amber-700">
              {contentReport.warnings.slice(0, 6).map((item, index) => (
                <li key={index}>{item}</li>
              ))}
            </ul>
          )}
          {structureChanges.length > 0 && (
            <ul className="mt-2 list-inside list-disc space-y-0.5 text-xs text-ink-600">
              {structureChanges.map((item, index) => (
                <li key={index}>{item}</li>
              ))}
            </ul>
          )}
        </section>
      )}

      <section className="space-y-3">
        {paragraphs.map((paragraph) => (
          <article
            key={paragraph.index}
            className="rounded-xl border border-ink-200 bg-white p-4 shadow-card"
          >
            <header className="mb-3 flex items-center justify-between">
              <span className="rounded-md bg-ink-100 px-2 py-0.5 text-xs font-medium text-ink-600">
                第 {paragraph.index + 1} 段
              </span>
              <span className="text-xs text-ink-400">
                改写率 {percent(paragraph.changed_ratio)} · 字数比{" "}
                {percent(paragraph.length_ratio)}
              </span>
            </header>
            {paragraph.metrics && paragraph.metrics.sentences ? (
              <div className="mb-3 flex flex-wrap gap-2 text-xs">
                <span className="rounded bg-ink-50 px-2 py-0.5 text-ink-500">
                  句长CV{" "}
                  <strong
                    className={
                      (paragraph.metrics.cv ?? 0) < 0.4
                        ? "text-amber-600"
                        : "text-emerald-600"
                    }
                  >
                    {paragraph.metrics.cv ?? "-"}
                  </strong>
                </span>
                <span className="rounded bg-ink-50 px-2 py-0.5 text-ink-500">
                  短句{" "}
                  <strong
                    className={
                      (paragraph.metrics.short_count ?? 0) === 0
                        ? "text-amber-600"
                        : "text-emerald-600"
                    }
                  >
                    {paragraph.metrics.short_count ?? 0}
                  </strong>
                </span>
                <span className="rounded bg-ink-50 px-2 py-0.5 text-ink-500">
                  长句{" "}
                  <strong
                    className={
                      (paragraph.metrics.long_count ?? 0) === 0
                        ? "text-amber-600"
                        : "text-emerald-600"
                    }
                  >
                    {paragraph.metrics.long_count ?? 0}
                  </strong>
                </span>
                <span className="rounded bg-ink-50 px-2 py-0.5 text-ink-500">
                  限定语{" "}
                  <strong
                    className={
                      (paragraph.metrics.hedge_count ?? 0) === 0
                        ? "text-amber-600"
                        : "text-emerald-600"
                    }
                  >
                    {paragraph.metrics.hedge_count ?? 0}
                  </strong>
                </span>
              </div>
            ) : null}
            <div className="grid gap-3 md:grid-cols-2">
              <div>
                <div className="mb-1 text-xs font-medium text-ink-400">原文</div>
                <p className="whitespace-pre-wrap text-sm leading-7 text-ink-500">
                  {paragraph.original}
                </p>
              </div>
              <div>
                <div className="mb-1 text-xs font-medium text-accent-600">改写后</div>
                <p className="whitespace-pre-wrap text-sm leading-7 text-ink-900">
                  {paragraph.rewritten}
                </p>
              </div>
            </div>
          </article>
        ))}
      </section>
    </div>
  );
}
