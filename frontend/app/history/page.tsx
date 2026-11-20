"use client";

import { useCallback, useEffect, useState } from "react";
import { apiGet, apiSend } from "@/lib/api";
import type { JobDetail, JobSummary } from "@/lib/types";

const STATUS_LABEL: Record<string, string> = {
  running: "进行中",
  done: "已完成",
  error: "失败",
  interrupted: "已中断",
  paused: "已暂停",
};

function statusClass(status: string): string {
  if (status === "done") return "bg-emerald-50 text-emerald-700";
  if (status === "running") return "bg-accent-50 text-accent-700";
  if (status === "paused") return "bg-sky-50 text-sky-700";
  if (status === "error") return "bg-red-50 text-red-600";
  return "bg-amber-50 text-amber-700";
}

function formatTime(value: string): string {
  try {
    return new Date(value).toLocaleString("zh-CN", { hour12: false });
  } catch {
    return value;
  }
}

export default function HistoryPage() {
  const [jobs, setJobs] = useState<JobSummary[]>([]);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [detail, setDetail] = useState<JobDetail | null>(null);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  const [copied, setCopied] = useState(false);

  const loadJobs = useCallback(async () => {
    try {
      const data = await apiGet<JobSummary[]>("/api/jobs?limit=50");
      setJobs(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "加载任务记录失败");
    }
  }, []);

  const loadDetail = useCallback(async (id: number) => {
    try {
      const data = await apiGet<JobDetail>(`/api/jobs/${id}`);
      setDetail(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "加载任务详情失败");
    }
  }, []);

  useEffect(() => {
    loadJobs();
  }, [loadJobs]);

  useEffect(() => {
    if (!jobs.some((job) => job.status === "running")) return;
    const timer = setInterval(loadJobs, 3000);
    return () => clearInterval(timer);
  }, [jobs, loadJobs]);

  useEffect(() => {
    if (selectedId !== null) loadDetail(selectedId);
  }, [selectedId, loadDetail]);

  const handleRerun = async (id: number) => {
    setBusy(true);
    setError("");
    setMessage("");
    try {
      const result = await apiSend<{ job_id: string; db_id: number; total: number }>(
        `/api/jobs/${id}/rerun`,
        "POST"
      );
      setMessage(`已重新发起任务 #${result.db_id}，共 ${result.total} 段`);
      await loadJobs();
    } catch (err) {
      setError(err instanceof Error ? err.message : "重新执行失败");
    } finally {
      setBusy(false);
    }
  };


  const handlePause = async (id: number) => {
    setError("");
    try {
      await apiSend(`/api/jobs/${id}/pause`, "POST");
      await loadJobs();
      if (selectedId === id) await loadDetail(id);
    } catch (err) {
      setError(err instanceof Error ? err.message : "暂停失败");
    }
  };

  const handleResume = async (id: number) => {
    setError("");
    try {
      await apiSend(`/api/jobs/${id}/resume`, "POST");
      await loadJobs();
      if (selectedId === id) await loadDetail(id);
    } catch (err) {
      setError(err instanceof Error ? err.message : "继续失败");
    }
  };

  const handleCopy = async () => {
    const text =
      detail?.rewritten ||
      detail?.result?.paragraphs?.map((item) => item.rewritten).join("\n\n") ||
      "";
    if (!text) return;
    await navigator.clipboard.writeText(text);
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  };

  return (
    <div className="space-y-5">
      <section className="rounded-xl border border-ink-200 bg-white p-5 shadow-card">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <h1 className="text-lg font-semibold tracking-tight text-ink-900">任务记录</h1>
            <p className="mt-1 text-sm text-ink-500">
              所有发起过的任务都会保存在这里。进行中的任务会实时更新进度，服务重启后未完成的任务会标记为已中断。
            </p>
          </div>
          <button
            type="button"
            onClick={loadJobs}
            className="rounded-lg border border-ink-200 px-3 py-1.5 text-sm text-ink-600 hover:bg-ink-50"
          >
            刷新
          </button>
        </div>
      </section>

      {message && (
        <div className="rounded-lg border border-emerald-200 bg-emerald-50 px-4 py-2 text-sm text-emerald-700">
          {message}
        </div>
      )}
      {error && (
        <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-2 text-sm text-red-700">
          {error}
        </div>
      )}

      <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.2fr)]">
        <section className="space-y-3">
          {jobs.map((job) => {
            const progress = job.progress_total
              ? Math.min(100, Math.round((job.progress_completed / job.progress_total) * 100))
              : 0;
            return (
              <article
                key={job.id}
                className={
                  selectedId === job.id
                    ? "cursor-pointer rounded-xl border border-accent-300 bg-white p-4 shadow-card"
                    : "cursor-pointer rounded-xl border border-ink-200 bg-white p-4 shadow-card hover:border-ink-300"
                }
                onClick={() => setSelectedId(job.id)}
              >
                <div className="flex items-center justify-between gap-3">
                  <div className="flex items-center gap-2">
                    <span className="text-sm font-semibold text-ink-900">#{job.id}</span>
                    <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${statusClass(job.status)}`}>
                      {STATUS_LABEL[job.status] ?? job.status}
                    </span>
                  </div>
                  <span className="text-xs text-ink-400">{formatTime(job.created_at)}</span>
                </div>
                <p className="mt-2 line-clamp-2 text-xs text-ink-500">{job.original_preview}</p>
                <div className="mt-3 flex items-center justify-between gap-2 text-xs text-ink-400">
                  <span>
                    {job.progress_completed}/{job.progress_total || "-"} 段
                  </span>
                  <div className="flex items-center gap-3">
                    {job.status === "running" && (
                      <button
                        type="button"
                        onClick={(event) => {
                          event.stopPropagation();
                          handlePause(job.id);
                        }}
                        className="text-sky-600 hover:underline"
                      >
                        暂停
                      </button>
                    )}
                    {job.status === "paused" && (
                      <button
                        type="button"
                        onClick={(event) => {
                          event.stopPropagation();
                          handleResume(job.id);
                        }}
                        className="text-emerald-600 hover:underline"
                      >
                        继续
                      </button>
                    )}
                    <button
                      type="button"
                      onClick={(event) => {
                        event.stopPropagation();
                        handleRerun(job.id);
                      }}
                      disabled={busy}
                      className="text-accent-600 hover:underline disabled:opacity-60"
                    >
                      重新执行
                    </button>
                  </div>
                </div>
                {job.status === "running" && (
                  <div className="mt-2 h-1.5 w-full overflow-hidden rounded-full bg-ink-100">
                    <div
                      className="h-full rounded-full bg-accent-500 transition-all"
                      style={{ width: `${progress}%` }}
                    />
                  </div>
                )}
                {job.error && (
                  <p className="mt-2 line-clamp-2 text-xs text-red-500">{job.error}</p>
                )}
              </article>
            );
          })}
          {jobs.length === 0 && (
            <div className="rounded-xl border border-ink-200 bg-white p-8 text-center text-sm text-ink-400">
              还没有任务记录
            </div>
          )}
        </section>

        <section className="rounded-xl border border-ink-200 bg-white p-5 shadow-card">
          {!detail && (
            <p className="text-sm text-ink-400">选择左侧任务查看详情</p>
          )}
          {detail && (
            <div className="space-y-4">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <h2 className="text-sm font-semibold text-ink-900">任务 #{detail.id}</h2>
                <div className="flex items-center gap-2">
                  <button
                    type="button"
                    onClick={handleCopy}
                    className="rounded-lg border border-ink-200 px-3 py-1 text-xs text-ink-600 hover:bg-ink-50"
                  >
                    {copied ? "已复制" : "复制结果"}
                  </button>
                  <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${statusClass(detail.status)}`}>
                    {STATUS_LABEL[detail.status] ?? detail.status}
                  </span>
                </div>
              </div>
              <p className="text-xs text-ink-400">
                创建 {formatTime(detail.created_at)} · 更新 {formatTime(detail.updated_at)}
              </p>
              {detail.error && (
                <div className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-xs text-red-600">
                  {detail.error}
                </div>
              )}

              {detail.result?.audit?.metrics && (
                <div className="flex flex-wrap gap-2 text-xs">
                  <span className="rounded-md bg-ink-100 px-2 py-1 text-ink-600">
                    句长CV <strong className="text-ink-900">{detail.result.audit.metrics.cv ?? "-"}</strong>
                  </span>
                  <span className="rounded-md bg-ink-100 px-2 py-1 text-ink-600">
                    连接词密度{" "}
                    <strong className="text-ink-900">
                      {detail.result.audit.metrics.connector_density ?? "-"}
                    </strong>
                  </span>
                  <span className="rounded-md bg-ink-100 px-2 py-1 text-ink-600">
                    规则命中{" "}
                    <strong className="text-ink-900">{detail.result.audit.total}</strong>
                  </span>
                  {detail.result.audit.metrics.perplexity !== undefined && (
                    <span className="rounded-md bg-ink-100 px-2 py-1 text-ink-600">
                      困惑度{" "}
                      <strong className="text-ink-900">
                        {detail.result.audit.metrics.perplexity}
                      </strong>
                    </span>
                  )}
                </div>
              )}

              <div>
                <div className="mb-1 text-xs font-medium text-ink-500">原文</div>
                <div className="max-h-48 overflow-auto whitespace-pre-wrap rounded-lg bg-ink-50 p-3 text-xs leading-6 text-ink-600">
                  {detail.original}
                </div>
              </div>

              {detail.result?.paragraphs?.length ? (
                <div>
                  <div className="mb-1 text-xs font-medium text-accent-600">改写结果</div>
                  <div className="max-h-80 space-y-2 overflow-auto">
                    {detail.result.paragraphs.map((paragraph) => (
                      <div key={paragraph.index} className="rounded-lg border border-ink-100 p-3">
                        <div className="mb-1 flex items-center justify-between text-xs text-ink-400">
                          <span>第 {paragraph.index + 1} 段</span>
                          <span>
                            CV {paragraph.metrics?.cv ?? "-"} · 短句{" "}
                            {paragraph.metrics?.short_count ?? 0} · 限定语{" "}
                            {paragraph.metrics?.hedge_count ?? 0}
                          </span>
                        </div>
                        <p className="whitespace-pre-wrap text-xs leading-6 text-ink-800">
                          {paragraph.rewritten}
                        </p>
                      </div>
                    ))}
                  </div>
                </div>
              ) : (
                detail.rewritten && (
                  <div>
                    <div className="mb-1 text-xs font-medium text-accent-600">改写结果</div>
                    <div className="max-h-80 overflow-auto whitespace-pre-wrap rounded-lg bg-accent-50/40 p-3 text-xs leading-6 text-ink-800">
                      {detail.rewritten}
                    </div>
                  </div>
                )
              )}

              {detail.result?.ppl_issues?.length ? (
                <div className="rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-800">
                  <div className="font-medium">
                    困惑度未达标 {detail.result.ppl_issues.length} 句：
                  </div>
                  <ul className="mt-2 space-y-2">
                    {detail.result.ppl_issues.map((item, index) => (
                      <li key={`${item.paragraph}-${index}`}>
                        <span className="text-amber-700">
                          第 {item.paragraph} 段 · 困惑度 {item.perplexity}：
                        </span>
                        <span className="ml-1 text-ink-800">{item.sentence}</span>
                      </li>
                    ))}
                  </ul>
                </div>
              ) : null}

              {detail.result?.warnings?.length ? (
                <details className="text-xs text-amber-700">
                  <summary className="cursor-pointer">回退提示 {detail.result.warnings.length} 条</summary>
                  <ul className="mt-2 list-inside list-disc space-y-1">
                    {detail.result.warnings.map((item, index) => (
                      <li key={index}>{item}</li>
                    ))}
                  </ul>
                </details>
              ) : null}
            </div>
          )}
        </section>
      </div>
    </div>
  );
}
