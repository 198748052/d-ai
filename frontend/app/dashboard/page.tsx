"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { apiGet } from "@/lib/api";
import { useAuth } from "@/components/AuthContext";
import { Icon, type IconName } from "@/components/Sidebar";
import type { FeatureRule, JobSummary } from "@/lib/types";

type QuickEntry = {
  href: string;
  label: string;
  desc: string;
  icon: IconName;
  adminOnly?: boolean;
};

const QUICK_ENTRIES: QuickEntry[] = [
  { href: "/", label: "开始改写", desc: "粘贴论文，全文逐段降低 AI 味", icon: "edit" },
  { href: "/history", label: "任务记录", desc: "查看进度、结果和失败原因", icon: "clock" },
  { href: "/account", label: "我的额度", desc: "余额、兑换码和近 7 天用量", icon: "wallet" },
  { href: "/features", label: "规则库", desc: "维护规则并运行健康检查", icon: "list", adminOnly: true },
  { href: "/mining", label: "规则挖掘", desc: "从样本中挖掘候选规则", icon: "list", adminOnly: true },
  { href: "/detector", label: "检测器反馈", desc: "录入检测结果并校准代理指标", icon: "list", adminOnly: true },
  { href: "/admin", label: "运营后台", desc: "用户、额度、错误与在线更新", icon: "shield", adminOnly: true },
  { href: "/settings/llm", label: "LLM 设置", desc: "网关、模型与本地困惑度模型", icon: "gear", adminOnly: true },
];

const STATUS_LABEL: Record<string, string> = {
  running: "进行中",
  done: "已完成",
  error: "失败",
  paused: "已暂停",
  canceled: "已取消",
};

const STATUS_CLASS: Record<string, string> = {
  done: "bg-emerald-50 text-emerald-700",
  running: "bg-accent-50 text-accent-700",
  paused: "bg-sky-50 text-sky-700",
  error: "bg-red-50 text-red-600",
  canceled: "bg-ink-100 text-ink-500",
};

export default function DashboardPage() {
  const { user, loading } = useAuth();
  const [jobs, setJobs] = useState<JobSummary[]>([]);
  const [ruleCount, setRuleCount] = useState<number | null>(null);
  const [jobsLoading, setJobsLoading] = useState(false);

  useEffect(() => {
    let cancelled = false;
    apiGet<FeatureRule[]>("/api/features")
      .then((data) => {
        if (!cancelled) setRuleCount(data.length);
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (!user) {
      setJobs([]);
      return;
    }
    let cancelled = false;
    setJobsLoading(true);
    apiGet<JobSummary[]>("/api/jobs?limit=5")
      .then((data) => {
        if (!cancelled) setJobs(data);
      })
      .catch(() => {
        if (!cancelled) setJobs([]);
      })
      .finally(() => {
        if (!cancelled) setJobsLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [user]);

  const quickEntries = useMemo(
    () => QUICK_ENTRIES.filter((entry) => !entry.adminOnly || user?.is_admin),
    [user]
  );

  if (loading) {
    return <div className="py-10 text-center text-sm text-ink-500">加载中…</div>;
  }

  return (
    <div className="space-y-5">
      <section className="rounded-xl border border-ink-200 bg-white p-5 shadow-card">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <div className="inline-flex items-center gap-2 rounded-full border border-accent-100 bg-accent-50 px-2.5 py-1 text-[11px] font-medium text-accent-700">
              <span className="h-1.5 w-1.5 rounded-full bg-accent-600" />
              降 AI 味改写平台
            </div>
            <h1 className="mt-3 text-2xl font-semibold tracking-tight text-ink-900">
              总览
            </h1>
            <p className="mt-2 max-w-2xl text-sm leading-6 text-ink-500">
              全文逐段改写，保留原意、段落结构、数字和引用；改写后给出覆盖率、句子级规则命中和审计结果。
            </p>
          </div>
          <div className="min-w-[180px] rounded-xl border border-ink-100 bg-ink-50 px-4 py-3 text-right">
            {user ? (
              <>
                <div className="text-xs text-ink-500">剩余额度</div>
                <div className="mt-1 text-2xl font-semibold text-ink-900">
                  {user.credits}
                  <span className="ml-1 text-sm font-normal text-ink-500">字</span>
                </div>
                <Link
                  href="/account"
                  className="mt-1 inline-block text-xs text-accent-700 hover:underline"
                >
                  查看用量 →
                </Link>
              </>
            ) : (
              <>
                <div className="text-xs text-ink-500">未登录</div>
                <Link
                  href="/login"
                  className="mt-2 inline-block rounded-lg bg-accent-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-accent-700"
                >
                  登录 / 注册
                </Link>
              </>
            )}
          </div>
        </div>
        <div className="mt-5 grid gap-3 border-t border-ink-100 pt-4 sm:grid-cols-3">
          <div className="rounded-lg bg-ink-50/70 px-3 py-2">
            <div className="text-xs text-ink-500">规则库</div>
            <div className="mt-1 text-lg font-semibold text-ink-900">
              {ruleCount ?? "—"} 条
            </div>
          </div>
          <div className="rounded-lg bg-ink-50/70 px-3 py-2">
            <div className="text-xs text-ink-500">改写策略</div>
            <div className="mt-1 text-lg font-semibold text-ink-900">全文逐句</div>
          </div>
          <div className="rounded-lg bg-ink-50/70 px-3 py-2">
            <div className="text-xs text-ink-500">覆盖率目标</div>
            <div className="mt-1 text-lg font-semibold text-ink-900">≥ 95%</div>
          </div>
        </div>
      </section>

      <section>
        <div className="mb-2 flex items-center justify-between">
          <h2 className="text-sm font-semibold text-ink-900">快捷入口</h2>
          <span className="text-xs text-ink-400">按 Ctrl/⌘ K 可快速跳转</span>
        </div>
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {quickEntries.map((entry) => (
            <Link
              key={entry.href}
              href={entry.href}
              className="group rounded-xl border border-ink-200 bg-white p-4 transition hover:border-accent-300 hover:bg-accent-50/30"
            >
              <div className="flex items-start gap-3">
                <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-accent-50 text-accent-700">
                  <Icon name={entry.icon} className="h-4 w-4" />
                </span>
                <div className="min-w-0">
                  <div className="flex items-center gap-2">
                    <span className="text-sm font-medium text-ink-900">
                      {entry.label}
                    </span>
                    {entry.adminOnly && (
                      <span className="rounded bg-ink-100 px-1.5 py-0.5 text-[10px] text-ink-500">
                        管理
                      </span>
                    )}
                  </div>
                  <p className="mt-1 text-xs text-ink-500">{entry.desc}</p>
                </div>
              </div>
            </Link>
          ))}
        </div>
      </section>

      <div className="grid gap-5 lg:grid-cols-2">
        <section className="rounded-xl border border-ink-200 bg-white p-5 shadow-card">
          <div className="flex items-center justify-between">
            <h2 className="text-sm font-semibold text-ink-900">最近任务</h2>
            <Link href="/history" className="text-xs text-accent-700 hover:underline">
              全部记录
            </Link>
          </div>
          {!user ? (
            <p className="mt-4 text-sm text-ink-500">登录后可以查看最近任务。</p>
          ) : jobsLoading ? (
            <p className="mt-4 text-sm text-ink-400">加载中…</p>
          ) : jobs.length === 0 ? (
            <div className="mt-4 rounded-lg bg-ink-50 px-3 py-6 text-center text-sm text-ink-500">
              还没有任务，去工作台提交第一篇文本。
            </div>
          ) : (
            <ul className="mt-3 space-y-2">
              {jobs.map((job) => (
                <li
                  key={job.id}
                  className="rounded-lg border border-ink-100 px-3 py-2"
                >
                  <div className="flex items-center justify-between gap-2">
                    <span className="truncate text-sm text-ink-800">
                      {job.original_preview || "（无预览）"}
                    </span>
                    <span
                      className={`shrink-0 rounded-full px-2 py-0.5 text-[11px] font-medium ${
                        STATUS_CLASS[job.status] ?? "bg-ink-100 text-ink-500"
                      }`}
                    >
                      {STATUS_LABEL[job.status] ?? job.status}
                    </span>
                  </div>
                  <div className="mt-1 flex items-center justify-between text-[11px] text-ink-400">
                    <span>{new Date(job.created_at).toLocaleString("zh-CN")}</span>
                    <span>
                      {job.progress_completed}/{job.progress_total} 段
                    </span>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </section>

        <section className="rounded-xl border border-ink-200 bg-white p-5 shadow-card">
          <h2 className="text-sm font-semibold text-ink-900">使用流程</h2>
          <ol className="mt-3 space-y-3 text-sm text-ink-600">
            {[
              ["粘贴文本", "在工作台粘贴论文正文，可选扫描内容缺口并补充真实数据。"],
              ["全文改写", "规则库先清理表层特征，LLM 再逐段逐句重写，覆盖率低于 95% 自动补写。"],
              ["检查结果", "查看覆盖率、句子级规则命中和审计分，必要时对单句重写。"],
              ["导出保存", "复制全文或导出 txt / md / docx。"],
            ].map(([title, desc], index) => (
              <li key={title} className="flex gap-3">
                <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-accent-50 text-xs font-medium text-accent-700">
                  {index + 1}
                </span>
                <div>
                  <div className="text-sm font-medium text-ink-800">{title}</div>
                  <p className="mt-0.5 text-xs text-ink-500">{desc}</p>
                </div>
              </li>
            ))}
          </ol>
          <Link
            href="/"
            className="mt-4 inline-block rounded-lg bg-accent-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-accent-700"
          >
            进入改写工作台
          </Link>
        </section>
      </div>
    </div>
  );
}
