"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { apiGet, apiSend } from "@/lib/api";
import { useAuth } from "@/components/AuthContext";
import type { JobSummary } from "@/lib/types";

const STATUS_LABEL: Record<string, string> = {
  running: "进行中",
  done: "已完成",
  error: "失败",
  interrupted: "已中断",
  paused: "已暂停",
  canceled: "已取消",
};

function statusClass(status: string): string {
  if (status === "done") return "bg-emerald-50 text-emerald-700";
  if (status === "running") return "bg-accent-50 text-accent-700";
  if (status === "paused") return "bg-sky-50 text-sky-700";
  if (status === "error") return "bg-red-50 text-red-600";
  if (status === "canceled") return "bg-ink-100 text-ink-500";
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
  const router = useRouter();
  const { user } = useAuth();
  const [jobs, setJobs] = useState<JobSummary[]>([]);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  const [query, setQuery] = useState("");
  const [statusFilter, setStatusFilter] = useState("");

  const loadJobs = useCallback(async () => {
    try {
      const data = await apiGet<JobSummary[]>("/api/jobs?limit=50");
      setJobs(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "加载任务记录失败");
    }
  }, []);

  useEffect(() => {
    if (user) loadJobs();
  }, [user, loadJobs]);

  useEffect(() => {
    if (!jobs.some((job) => job.status === "running")) return;
    const timer = setInterval(loadJobs, 3000);
    return () => clearInterval(timer);
  }, [jobs, loadJobs]);

  const openJob = (id: number) => {
    router.push(`/?job=${id}`);
  };

  const handleCancel = async (id: number) => {
    setBusy(true);
    setError("");
    setMessage("");
    try {
      const result = await apiSend<{ status: string; refunded: boolean }>(
        `/api/jobs/${id}/cancel`,
        "POST"
      );
      setMessage(result.refunded ? `任务 #${id} 已取消，本次额度已退回` : `任务 #${id} 已取消`);
      await loadJobs();
    } catch (err) {
      setError(err instanceof Error ? err.message : "取消失败");
    } finally {
      setBusy(false);
    }
  };

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
    } catch (err) {
      setError(err instanceof Error ? err.message : "暂停失败");
    }
  };

  const handleResume = async (id: number) => {
    setError("");
    try {
      await apiSend(`/api/jobs/${id}/resume`, "POST");
      await loadJobs();
    } catch (err) {
      setError(err instanceof Error ? err.message : "继续失败");
    }
  };

  const filteredJobs = useMemo(() => {
    const keyword = query.trim().toLowerCase();
    return jobs.filter((job) => {
      if (statusFilter && job.status !== statusFilter) return false;
      if (!keyword) return true;
      return `${job.id} ${job.original_preview}`.toLowerCase().includes(keyword);
    });
  }, [jobs, query, statusFilter]);

  return (
    <div className="space-y-5">
      <section className="rounded-xl border border-ink-200 bg-white p-5 shadow-card">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <h1 className="text-lg font-semibold tracking-tight text-ink-900">任务记录</h1>
            <p className="mt-1 text-sm text-ink-500">
              所有发起过的任务都会保存在这里。点击任意任务可进入完整详情页，进行中的任务会实时更新进度。
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
        <div className="mt-4 flex flex-wrap items-center gap-2">
          <input
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="搜索任务编号或原文…"
            className="min-w-[200px] flex-1 rounded-lg border border-ink-200 px-3 py-1.5 text-sm outline-none focus:border-accent-500"
          />
          <select
            value={statusFilter}
            onChange={(event) => setStatusFilter(event.target.value)}
            className="rounded-lg border border-ink-200 bg-white px-3 py-1.5 text-sm outline-none focus:border-accent-500"
          >
            <option value="">全部状态</option>
            <option value="running">进行中</option>
            <option value="done">已完成</option>
            <option value="error">失败</option>
            <option value="paused">已暂停</option>
            <option value="canceled">已取消</option>
          </select>
          <span className="text-xs text-ink-400">共 {filteredJobs.length} 条</span>
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

      <section className="space-y-3">
        {filteredJobs.map((job) => {
          const progress = job.progress_total
            ? Math.min(100, Math.round((job.progress_completed / job.progress_total) * 100))
            : 0;
          return (
            <article
              key={job.id}
              className="cursor-pointer rounded-xl border border-ink-200 bg-white p-4 shadow-card transition hover:border-accent-300"
              onClick={() => openJob(job.id)}
            >
              <div className="flex items-center justify-between gap-3">
                <div className="flex items-center gap-2">
                  <span className="text-sm font-semibold text-ink-900">#{job.id}</span>
                  <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${statusClass(job.status)}`}>
                    {STATUS_LABEL[job.status] ?? job.status}
                  </span>
                </div>
                <div className="flex items-center gap-3">
                  <span className="text-xs text-ink-400">{formatTime(job.created_at)}</span>
                  <span className="text-xs text-accent-600">查看详情</span>
                </div>
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
                  {(job.status === "running" || job.status === "paused") && (
                    <button
                      type="button"
                      onClick={(event) => {
                        event.stopPropagation();
                        handleCancel(job.id);
                      }}
                      disabled={busy}
                      className="text-red-500 hover:underline disabled:opacity-60"
                    >
                      取消
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
        {filteredJobs.length === 0 && (
          <div className="rounded-xl border border-ink-200 bg-white p-8 text-center text-sm text-ink-400">
            {jobs.length === 0 ? "还没有任务记录" : "没有匹配的任务"}
          </div>
        )}
      </section>
    </div>
  );
}
