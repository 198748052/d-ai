"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { apiGet, exportDocument, fetchRewriteJob, startRewriteJob } from "@/lib/api";
import { useAuth } from "@/components/AuthContext";
import type {
  AuditResult,
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

  const handleRewrite = useCallback(async () => {
    if (!user) {
      router.push("/login");
      return;
    }
    if (!text.trim()) {
      setError("请先粘贴需要改写的文章");
      return;
    }
    if (text.length > 200000) {
      setError("文本过长，单次上限 20 万字符，请分段处理");
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
    setTotal(countParagraphs(text));

    try {
      const { job_id, total: jobTotal } = await startRewriteJob({
        text,
        mode: "hybrid",
        preset_id: preset?.id,
      });
      setTotal(jobTotal);

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
          setRewrittenText(job.paragraphs.map((item) => item.rewritten).join("\n\n"));
          break;
        }
        if (job.status === "error") {
          setError(job.error || "改写失败");
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
    }
  }, [text, preset]);

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
              onClick={() => setText("")}
              className="text-ink-500 hover:text-ink-800"
            >
              清空
            </button>
            <span className="text-ink-400">{text.length} 字</span>
          </div>
        </div>
        <textarea
          value={text}
          onChange={(e) => setText(e.target.value)}
          placeholder="把需要改写的论文段落粘贴到这里，段落之间用空行分隔。"
          className="h-56 w-full resize-y rounded-lg border border-ink-200 bg-ink-50/40 p-3 text-sm leading-7 text-ink-800 outline-none transition focus:border-accent-500 focus:bg-white focus:ring-2 focus:ring-accent-100"
        />

        <div className="mt-3 rounded-lg border border-accent-100 bg-accent-50/60 px-3 py-2 text-xs text-accent-700">
          学术模式：口语化已关闭。流程为「规则库删除/替换 → 按句分片交给 LLM → 逐片复检 → 段落级纠正 → 特征审计」。
        </div>

        <div className="mt-4 flex flex-wrap items-center gap-3">
          <button
            type="button"
            onClick={handleRewrite}
            disabled={running}
            className="rounded-lg bg-accent-600 px-4 py-2 text-sm font-medium text-white transition hover:bg-accent-700 disabled:cursor-not-allowed disabled:opacity-60"
          >
            {running ? "改写中…" : "开始改写"}
          </button>
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
