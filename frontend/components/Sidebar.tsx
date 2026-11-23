"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useAuth } from "@/components/AuthContext";

type Item = { href: string; label: string; icon: IconName };

const PUBLIC_ITEMS: Item[] = [
  { href: "/dashboard", label: "总览", icon: "home" },
  { href: "/", label: "改写工作台", icon: "edit" },
  { href: "/history", label: "任务记录", icon: "clock" },
  { href: "/account", label: "我的额度", icon: "wallet" },
];

const MOBILE_ITEMS: Item[] = [
  { href: "/dashboard", label: "总览", icon: "home" },
  { href: "/", label: "改写", icon: "edit" },
  { href: "/history", label: "记录", icon: "clock" },
  { href: "/account", label: "我的", icon: "wallet" },
];

const ADMIN_SECTIONS: { title: string; items: Item[] }[] = [
  {
    title: "运营",
    items: [
      { href: "/admin", label: "运营后台", icon: "shield" },
      { href: "/detector", label: "检测器反馈", icon: "list" },
    ],
  },
  {
    title: "规则",
    items: [
      { href: "/features", label: "规则库", icon: "list" },
      { href: "/mining", label: "规则挖掘", icon: "list" },
      { href: "/presets", label: "改写预设", icon: "sliders" },
    ],
  },
  {
    title: "系统",
    items: [{ href: "/settings/llm", label: "LLM 设置", icon: "gear" }],
  },
];

export type IconName =
  | "home"
  | "edit"
  | "clock"
  | "wallet"
  | "shield"
  | "sliders"
  | "list"
  | "gear"
  | "search";

const ICON_PATHS: Record<IconName, string> = {
  home: "M3 11l9-8 9 8M5 10v10h5v-6h4v6h5V10",
  edit: "M12 20h9M16.5 3.5a2.1 2.1 0 013 3L7 19l-4 1 1-4z",
  clock: "M12 8v4l3 2M12 3a9 9 0 100 18 9 9 0 000-18z",
  wallet: "M3 7h15a3 3 0 013 3v7a2 2 0 01-2 2H5a2 2 0 01-2-2V7zm0 0a2 2 0 012-2h11M16 13h2",
  shield: "M12 3l7 3v6c0 4-3 7-7 9-4-2-7-5-7-9V6z",
  sliders: "M4 6h10M18 6h2M4 12h4M12 12h8M4 18h12M20 18h0M14 4v4M8 10v4M16 16v4",
  list: "M8 6h13M8 12h13M8 18h13M3 6h.01M3 12h.01M3 18h.01",
  gear: "M12 15a3 3 0 100-6 3 3 0 000 6zM19.4 15a1.7 1.7 0 00.3 1.9l.1.1a2 2 0 11-2.8 2.8l-.1-.1a1.7 1.7 0 00-2.9 1.2V21a2 2 0 11-4 0v-.1A1.7 1.7 0 005 19.4a2 2 0 11-2.8-2.8l.1-.1A1.7 1.7 0 003 13.6H3a2 2 0 110-4h.1A1.7 1.7 0 004.6 5a2 2 0 112.8-2.8l.1.1A1.7 1.7 0 0010.4 3V3a2 2 0 114 0v.1a1.7 1.7 0 002.9 1.2l.1-.1A2 2 0 1120.2 7l-.1.1a1.7 1.7 0 001.2 2.9H21a2 2 0 110 4h-.1a1.7 1.7 0 00-1.5 1z",
  search: "M21 21l-4.3-4.3M10.5 18a7.5 7.5 0 100-15 7.5 7.5 0 000 15z",
};

export function Icon({ name, className = "h-5 w-5" }: { name: IconName; className?: string }) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.7}
      strokeLinecap="round"
      strokeLinejoin="round"
      className={className}
      aria-hidden
    >
      <path d={ICON_PATHS[name]} />
    </svg>
  );
}

export default function Sidebar() {
  const pathname = usePathname();
  const router = useRouter();
  const { user, loading, logout } = useAuth();
  const [collapsed, setCollapsed] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);

  useEffect(() => {
    setCollapsed(localStorage.getItem("sidebar-collapsed") === "1");
  }, []);

  useEffect(() => {
    setMobileOpen(false);
  }, [pathname]);

  const toggle = () => {
    setCollapsed((prev) => {
      localStorage.setItem("sidebar-collapsed", prev ? "0" : "1");
      return !prev;
    });
  };

  const handleLogout = async () => {
    await logout();
    router.push("/login");
  };

  const sections: { title: string; items: Item[] }[] = [
    { title: "工作台", items: PUBLIC_ITEMS },
    ...(user?.is_admin ? ADMIN_SECTIONS : []),
  ];

  const renderItem = (item: Item, compact: boolean) => {
    const active = item.href === "/" ? pathname === "/" : pathname.startsWith(item.href);
    return (
      <Link
        key={item.href}
        href={item.href}
        title={compact ? item.label : undefined}
        className={
          active
            ? "flex items-center gap-3 rounded-lg bg-accent-50 px-3 py-2 text-sm font-medium text-accent-700 ring-1 ring-inset ring-accent-100"
            : "flex items-center gap-3 rounded-lg px-3 py-2 text-sm text-ink-600 hover:bg-ink-100/70 hover:text-ink-900"
        }
      >
        <Icon name={item.icon} />
        {!compact && <span className="truncate">{item.label}</span>}
      </Link>
    );
  };

  const accountBlock = (compact: boolean) => (
    <div className="space-y-2">
      <button
        type="button"
        onClick={() => window.dispatchEvent(new Event("open-command-palette"))}
        title="快速跳转（Ctrl+K）"
        className={
          compact
            ? "flex w-full items-center justify-center rounded-lg px-2 py-2 text-ink-500 hover:bg-ink-100"
            : "flex w-full items-center justify-between rounded-lg px-3 py-2 text-sm text-ink-600 hover:bg-ink-100"
        }
      >
        <span className="flex items-center gap-3">
          <Icon name="search" />
          {!compact && <span>快速跳转</span>}
        </span>
        {!compact && (
          <span className="rounded border border-ink-200 px-1.5 py-0.5 text-[10px] text-ink-400">
            ⌘K
          </span>
        )}
      </button>
      {user ? (
        <>
          {!compact && (
            <div className="rounded-lg border border-ink-100 bg-ink-50 px-3 py-2 text-xs text-ink-600">
              <div className="truncate text-ink-800">{user.nickname || user.email}</div>
              <div className="mt-1 font-medium text-accent-700">余额 {user.credits} 字</div>
            </div>
          )}
          <button
            type="button"
            onClick={handleLogout}
            title="退出登录"
            className={
              compact
                ? "flex w-full items-center justify-center rounded-lg px-2 py-2 text-ink-500 hover:bg-ink-100"
                : "w-full rounded-lg px-3 py-2 text-left text-sm text-ink-600 hover:bg-ink-100"
            }
          >
            {compact ? <Icon name="shield" /> : "退出登录"}
          </button>
        </>
      ) : (
        <Link
          href="/login"
          className={
            compact
              ? "flex items-center justify-center rounded-lg bg-accent-600 px-2 py-2 text-white"
              : "block rounded-lg bg-accent-600 px-3 py-2 text-center text-sm font-medium text-white hover:bg-accent-700"
          }
        >
          {compact ? "登" : "登录 / 注册"}
        </Link>
      )}
    </div>
  );

  const brand = (compact: boolean) => (
    <Link href="/dashboard" className="flex items-center gap-2 px-1">
      <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-ink-900 text-sm font-semibold text-white">
        改
      </span>
      {!compact && (
        <span className="truncate text-sm font-semibold tracking-tight text-ink-900">
          降 AI 味改写平台
        </span>
      )}
    </Link>
  );

  return (
    <>
      <header className="sticky top-0 z-30 flex h-14 items-center gap-3 border-b border-ink-200 bg-white/90 px-3 backdrop-blur md:hidden">
        <button
          type="button"
          onClick={() => setMobileOpen(true)}
          className="rounded-md p-2 text-ink-600 hover:bg-ink-100"
          aria-label="打开菜单"
        >
          <svg viewBox="0 0 24 24" className="h-5 w-5" fill="none" stroke="currentColor" strokeWidth={1.8}>
            <path d="M4 6h16M4 12h16M4 18h16" strokeLinecap="round" />
          </svg>
        </button>
        {brand(false)}
        {user && (
          <span className="ml-auto shrink-0 rounded-md bg-ink-100 px-2 py-1 text-xs text-ink-700">
            {user.credits} 字
          </span>
        )}
      </header>

      {mobileOpen && (
        <div className="fixed inset-0 z-50 md:hidden">
          <div
            className="absolute inset-0 bg-black/30"
            onClick={() => setMobileOpen(false)}
            aria-hidden
          />
          <aside className="absolute left-0 top-0 flex h-full w-64 flex-col border-r border-ink-200 bg-white p-3 shadow-xl">
            <div className="flex items-center justify-between">
              {brand(false)}
              <button
                type="button"
                onClick={() => setMobileOpen(false)}
                className="rounded-md p-1.5 text-ink-500 hover:bg-ink-100"
                aria-label="关闭菜单"
              >
                <svg viewBox="0 0 24 24" className="h-5 w-5" fill="none" stroke="currentColor" strokeWidth={1.8}>
                  <path d="M6 6l12 12M18 6L6 18" strokeLinecap="round" />
                </svg>
              </button>
            </div>
            <nav className="mt-4 flex-1 space-y-4 overflow-y-auto">
              {sections.map((section) => (
                <div key={section.title}>
                  <div className="px-3 pb-1 text-[10px] font-medium uppercase tracking-[0.12em] text-ink-400">
                    {section.title}
                  </div>
                  <div className="space-y-1">{section.items.map((item) => renderItem(item, false))}</div>
                </div>
              ))}
            </nav>
            <div className="border-t border-ink-200 pt-3">{accountBlock(false)}</div>
          </aside>
        </div>
      )}

      <aside
        className={
          "sticky top-0 hidden h-screen shrink-0 flex-col border-r border-ink-200 bg-white p-3 md:flex " +
          (collapsed ? "w-[76px]" : "w-60")
        }
      >
        <div className="flex items-center justify-between gap-2">
          {brand(collapsed)}
          <button
            type="button"
            onClick={toggle}
            className="rounded-md p-1.5 text-ink-400 hover:bg-ink-100 hover:text-ink-700"
            aria-label={collapsed ? "展开菜单" : "收起菜单"}
            title={collapsed ? "展开菜单" : "收起菜单"}
          >
            <svg viewBox="0 0 24 24" className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth={2}>
              <path
                d={collapsed ? "M9 6l6 6-6 6" : "M15 6l-6 6 6 6"}
                strokeLinecap="round"
                strokeLinejoin="round"
              />
            </svg>
          </button>
        </div>

        <nav className="mt-5 flex-1 space-y-4 overflow-y-auto">
          {sections.map((section) => (
            <div key={section.title}>
              {!collapsed && (
                <div className="px-3 pb-1 text-[10px] font-medium uppercase tracking-[0.12em] text-ink-400">
                  {section.title}
                </div>
              )}
              <div className="space-y-1">
                {section.items.map((item) => renderItem(item, collapsed))}
              </div>
            </div>
          ))}
        </nav>

        <div className="border-t border-ink-200 pt-3">{accountBlock(collapsed)}</div>
      </aside>

      <nav className="fixed bottom-0 left-0 right-0 z-40 grid grid-cols-4 border-t border-ink-200 bg-white/95 backdrop-blur md:hidden">
        {MOBILE_ITEMS.map((item) => {
          const active =
            item.href === "/" ? pathname === "/" : pathname.startsWith(item.href);
          return (
            <Link
              key={item.href}
              href={item.href}
              className={
                active
                  ? "flex flex-col items-center gap-0.5 py-2 text-[10px] font-medium text-accent-700"
                  : "flex flex-col items-center gap-0.5 py-2 text-[10px] text-ink-500"
              }
            >
              <Icon name={item.icon} className="h-5 w-5" />
              <span>{item.label}</span>
            </Link>
          );
        })}
      </nav>
    </>
  );
}
