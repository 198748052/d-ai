"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const NAV_ITEMS = [
  { href: "/", label: "改写工作台" },
  { href: "/history", label: "任务记录" },
  { href: "/presets", label: "改写预设" },
  { href: "/features", label: "规则库" },
  { href: "/settings/llm", label: "LLM 设置" },
];

export default function Nav() {
  const pathname = usePathname();

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
          {NAV_ITEMS.map((item) => {
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
      </div>
    </header>
  );
}
