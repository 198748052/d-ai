"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/components/AuthContext";
import { Icon, type IconName } from "@/components/Sidebar";

type Entry = {
  href: string;
  label: string;
  hint: string;
  icon: IconName;
  adminOnly?: boolean;
};

const ENTRIES: Entry[] = [
  { href: "/dashboard", label: "总览", hint: "平台入口、最近任务与使用流程", icon: "home" },
  { href: "/", label: "改写工作台", hint: "提交文本，全文逐句降 AI 味", icon: "edit" },
  { href: "/history", label: "任务记录", hint: "查看历史任务、进度与结果", icon: "clock" },
  { href: "/account", label: "我的额度", hint: "余额、兑换码与近 7 天用量", icon: "wallet" },
  { href: "/admin", label: "运营后台", hint: "用户、额度、错误与在线更新", icon: "shield", adminOnly: true },
  { href: "/features", label: "规则库", hint: "规则维护与规则健康检查", icon: "list", adminOnly: true },
  { href: "/mining", label: "规则挖掘", hint: "从高 AI / 低 AI 样本挖掘候选规则", icon: "list", adminOnly: true },
  { href: "/detector", label: "检测器反馈", hint: "录入真实检测结果并校准代理指标", icon: "list", adminOnly: true },
  { href: "/presets", label: "改写预设", hint: "查看学术论文预设参数", icon: "sliders", adminOnly: true },
  { href: "/settings/llm", label: "LLM 设置", hint: "网关、模型与本地困惑度模型", icon: "gear", adminOnly: true },
];

export default function CommandPalette() {
  const router = useRouter();
  const { user } = useAuth();
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [activeIndex, setActiveIndex] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);

  const entries = useMemo(
    () => ENTRIES.filter((entry) => !entry.adminOnly || user?.is_admin),
    [user]
  );

  const filtered = useMemo(() => {
    const keyword = query.trim().toLowerCase();
    if (!keyword) return entries;
    return entries.filter((entry) =>
      `${entry.label} ${entry.hint} ${entry.href}`.toLowerCase().includes(keyword)
    );
  }, [entries, query]);

  const go = useCallback(
    (href: string) => {
      setOpen(false);
      setQuery("");
      router.push(href);
    },
    [router]
  );

  useEffect(() => {
    const onOpen = () => setOpen(true);
    window.addEventListener("open-command-palette", onOpen);
    return () => window.removeEventListener("open-command-palette", onOpen);
  }, []);

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        setOpen((value) => !value);
        return;
      }
      if (!open) return;
      if (event.key === "Escape") {
        setOpen(false);
      } else if (event.key === "ArrowDown") {
        event.preventDefault();
        setActiveIndex((index) => Math.min(filtered.length - 1, index + 1));
      } else if (event.key === "ArrowUp") {
        event.preventDefault();
        setActiveIndex((index) => Math.max(0, index - 1));
      } else if (event.key === "Enter") {
        const entry = filtered[activeIndex];
        if (entry) go(entry.href);
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [open, filtered, activeIndex, go]);

  useEffect(() => {
    if (!open) return;
    setActiveIndex(0);
    const timer = window.setTimeout(() => inputRef.current?.focus(), 0);
    return () => window.clearTimeout(timer);
  }, [open]);

  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-[60] flex items-start justify-center bg-black/30 px-4 pt-24 backdrop-blur-sm"
      onClick={() => setOpen(false)}
      role="dialog"
      aria-modal="true"
      aria-label="快速跳转"
    >
      <div
        className="w-full max-w-xl overflow-hidden rounded-xl border border-ink-200 bg-white shadow-2xl"
        onClick={(event) => event.stopPropagation()}
      >
        <div className="flex items-center gap-2 border-b border-ink-100 px-4 py-3">
          <Icon name="search" className="h-4 w-4 text-ink-400" />
          <input
            ref={inputRef}
            value={query}
            onChange={(event) => {
              setQuery(event.target.value);
              setActiveIndex(0);
            }}
            placeholder="搜索页面或功能…"
            className="flex-1 bg-transparent text-sm outline-none placeholder:text-ink-400"
          />
          <kbd className="rounded border border-ink-200 px-1.5 py-0.5 text-[10px] text-ink-400">
            ESC
          </kbd>
        </div>
        <ul className="max-h-80 overflow-y-auto p-2">
          {filtered.length === 0 && (
            <li className="px-3 py-6 text-center text-xs text-ink-400">
              没有匹配的入口
            </li>
          )}
          {filtered.map((entry, index) => (
            <li key={entry.href}>
              <button
                type="button"
                onMouseEnter={() => setActiveIndex(index)}
                onClick={() => go(entry.href)}
                className={
                  index === activeIndex
                    ? "flex w-full items-center justify-between gap-3 rounded-lg bg-accent-50 px-3 py-2 text-left"
                    : "flex w-full items-center justify-between gap-3 rounded-lg px-3 py-2 text-left hover:bg-ink-50"
                }
              >
                <span className="flex min-w-0 items-center gap-3">
                  <Icon
                    name={entry.icon}
                    className={
                      index === activeIndex ? "h-4 w-4 text-accent-600" : "h-4 w-4 text-ink-400"
                    }
                  />
                  <span className="min-w-0">
                    <span
                      className={
                        index === activeIndex
                          ? "block truncate text-sm font-medium text-accent-700"
                          : "block truncate text-sm text-ink-800"
                      }
                    >
                      {entry.label}
                    </span>
                    <span className="block truncate text-[11px] text-ink-400">
                      {entry.hint}
                    </span>
                  </span>
                </span>
                {entry.adminOnly && (
                  <span className="shrink-0 rounded bg-ink-100 px-1.5 py-0.5 text-[10px] text-ink-500">
                    管理
                  </span>
                )}
              </button>
            </li>
          ))}
        </ul>
        <div className="border-t border-ink-100 px-4 py-2 text-[11px] text-ink-400">
          ↑↓ 选择 · Enter 打开 · Ctrl/⌘ K 切换
        </div>
      </div>
    </div>
  );
}
