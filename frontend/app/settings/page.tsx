"use client";

import Link from "next/link";
import { useAuth } from "@/components/AuthContext";
import { Icon, type IconName } from "@/components/Sidebar";

type Entry = {
  href: string;
  label: string;
  desc: string;
  icon: IconName;
};

const PLATFORM_ENTRIES: Entry[] = [
  { href: "/dashboard", label: "总览", desc: "平台入口、最近任务与使用流程", icon: "home" },
];

const ADMIN_ENTRIES: Entry[] = [
  { href: "/admin", label: "运营后台", desc: "用户、额度、错误与在线更新", icon: "shield" },
  { href: "/features", label: "规则库", desc: "规则维护与规则健康检查", icon: "list" },
  { href: "/mining", label: "规则挖掘", desc: "从高 AI / 低 AI 样本挖掘候选规则", icon: "list" },
  { href: "/detector", label: "检测器反馈", desc: "录入真实检测结果并校准代理指标", icon: "list" },
  { href: "/presets", label: "改写预设", desc: "查看学术论文预设参数", icon: "sliders" },
  { href: "/settings/llm", label: "LLM 设置", desc: "网关、模型、本地困惑度模型与避雷库", icon: "gear" },
];

const ABOUT_ENTRIES: Entry[] = [
  { href: "/privacy", label: "隐私政策", desc: "数据收集、使用与保护说明", icon: "shield" },
  { href: "/terms", label: "用户协议", desc: "服务说明、账号与使用规范", icon: "list" },
];

function EntryGrid({ entries, admin }: { entries: Entry[]; admin?: boolean }) {
  return (
    <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
      {entries.map((entry) => (
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
                <span className="text-sm font-medium text-ink-900">{entry.label}</span>
                {admin && (
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
  );
}

export default function SettingsPage() {
  const { user, loading } = useAuth();

  if (loading) {
    return <div className="py-10 text-center text-sm text-ink-500">加载中…</div>;
  }

  return (
    <div className="space-y-5">
      <section className="rounded-xl border border-ink-200 bg-white p-5 shadow-card">
        <div className="inline-flex items-center gap-2 rounded-full border border-accent-100 bg-accent-50 px-2.5 py-1 text-[11px] font-medium text-accent-700">
          <span className="h-1.5 w-1.5 rounded-full bg-accent-600" />
          设置
        </div>
        <h1 className="mt-3 text-2xl font-semibold tracking-tight text-ink-900">设置</h1>
        <p className="mt-2 max-w-2xl text-sm leading-6 text-ink-500">
          平台总览、规则与管理功能、系统配置和政策说明都集中在这里。
        </p>
      </section>

      <section>
        <h2 className="mb-2 text-sm font-semibold text-ink-900">平台</h2>
        <EntryGrid entries={PLATFORM_ENTRIES} />
      </section>

      {user?.is_admin && (
        <section>
          <div className="mb-2 flex items-center justify-between">
            <h2 className="text-sm font-semibold text-ink-900">管理功能</h2>
            <span className="text-xs text-ink-400">仅管理员可见</span>
          </div>
          <EntryGrid entries={ADMIN_ENTRIES} admin />
        </section>
      )}

      <section>
        <h2 className="mb-2 text-sm font-semibold text-ink-900">关于</h2>
        <EntryGrid entries={ABOUT_ENTRIES} />
      </section>
    </div>
  );
}
