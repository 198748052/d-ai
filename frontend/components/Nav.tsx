"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useAuth } from "@/components/AuthContext";

const PUBLIC_ITEMS = [
  { href: "/", label: "改写工作台" },
  { href: "/history", label: "任务记录" },
  { href: "/account", label: "我的额度" },
];

const ADMIN_ITEMS = [
  { href: "/admin", label: "运营后台" },
  { href: "/presets", label: "改写预设" },
  { href: "/features", label: "规则库" },
  { href: "/settings/llm", label: "LLM 设置" },
];

export default function Nav() {
  const pathname = usePathname();
  const router = useRouter();
  const { user, loading, logout } = useAuth();
  const items = user?.is_admin ? [...PUBLIC_ITEMS, ...ADMIN_ITEMS] : PUBLIC_ITEMS;

  const handleLogout = async () => {
    await logout();
    router.push("/login");
  };

  return (
    <header className="sticky top-0 z-30 border-b border-ink-200 bg-white/90 backdrop-blur">
      <div className="mx-auto flex h-14 max-w-6xl items-center gap-3 px-3 sm:gap-6 sm:px-4">
        <Link href="/" className="flex items-center gap-2">
          <span className="flex h-7 w-7 items-center justify-center rounded-lg bg-accent-600 text-sm font-semibold text-white">
            改
          </span>
          <span className="hidden text-sm font-semibold tracking-tight text-ink-900 sm:inline">
            降 AI 味改写平台
          </span>
        </Link>
        <nav className="flex flex-1 items-center gap-1 overflow-x-auto whitespace-nowrap text-sm">
          {items.map((item) => {
            const active =
              item.href === "/"
                ? pathname === "/"
                : pathname.startsWith(item.href);
            return (
              <Link
                key={item.href}
                href={item.href}
                className={
                  active
                    ? "shrink-0 rounded-md bg-accent-50 px-2.5 py-1.5 font-medium text-accent-700 sm:px-3"
                    : "shrink-0 rounded-md px-2.5 py-1.5 text-ink-600 hover:bg-ink-100 hover:text-ink-900 sm:px-3"
                }
              >
                {item.label}
              </Link>
            );
          })}
        </nav>
        {loading ? null : user ? (
          <div className="flex shrink-0 items-center gap-2 text-xs">
            <span className="hidden rounded-md bg-ink-100 px-2 py-1 text-ink-700 sm:inline">
              余额 {user.credits} 字
            </span>
            <span className="hidden max-w-[160px] truncate text-ink-500 md:inline">
              {user.nickname || user.email}
            </span>
            <button
              type="button"
              onClick={handleLogout}
              className="rounded-md px-2 py-1 text-ink-600 hover:bg-ink-100"
            >
              退出
            </button>
          </div>
        ) : (
          <Link
            href="/login"
            className="shrink-0 rounded-md bg-accent-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-accent-700"
          >
            登录 / 注册
          </Link>
        )}
      </div>
    </header>
  );
}
