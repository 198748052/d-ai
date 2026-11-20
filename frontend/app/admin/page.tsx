"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { apiGet, apiSend } from "@/lib/api";
import { useAuth } from "@/components/AuthContext";
import type { AdminUser, RedeemCodeItem } from "@/lib/types";

export default function AdminPage() {
  const { user, loading } = useAuth();
  const [users, setUsers] = useState<AdminUser[]>([]);
  const [codes, setCodes] = useState<RedeemCodeItem[]>([]);
  const [deltas, setDeltas] = useState<Record<number, string>>({});
  const [credits, setCredits] = useState("500");
  const [maxUses, setMaxUses] = useState("1");
  const [created, setCreated] = useState("");
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    try {
      const [u, c] = await Promise.all([
        apiGet<AdminUser[]>("/api/admin/users"),
        apiGet<RedeemCodeItem[]>("/api/admin/redeem-codes"),
      ]);
      setUsers(u);
      setCodes(c);
    } catch (err) {
      setError(err instanceof Error ? err.message : "加载失败");
    }
  }, []);

  useEffect(() => {
    if (user?.is_admin) load();
  }, [user, load]);

  const adjust = async (target: AdminUser, sign: 1 | -1) => {
    const raw = deltas[target.id];
    const value = Math.abs(Number(raw || 0));
    if (!value) {
      setError("请输入调整字数");
      return;
    }
    setError("");
    setMessage("");
    try {
      await apiSend<AdminUser>(`/api/admin/users/${target.id}/credits`, "POST", {
        delta: sign * value,
        reason: sign > 0 ? "管理员增加额度" : "管理员扣减额度",
      });
      setDeltas((prev) => ({ ...prev, [target.id]: "" }));
      setMessage(`${target.email} 额度已调整 ${sign * value} 字`);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "调整失败");
    }
  };

  const createCode = async (event: React.FormEvent) => {
    event.preventDefault();
    setError("");
    setMessage("");
    try {
      const data = await apiSend<RedeemCodeItem>("/api/admin/redeem-codes", "POST", {
        credits: Number(credits),
        max_uses: Number(maxUses),
      });
      setCreated(data.code);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "生成失败");
    }
  };

  if (loading) {
    return <div className="py-10 text-center text-sm text-ink-500">加载中…</div>;
  }

  if (!user?.is_admin) {
    return (
      <div className="mx-auto max-w-md rounded-xl border border-ink-200 bg-white p-6 text-center shadow-card">
        <p className="text-sm text-ink-600">该页面仅管理员可访问。</p>
        <Link href="/" className="mt-4 inline-block text-sm text-accent-700 hover:underline">
          返回工作台
        </Link>
      </div>
    );
  }

  return (
    <div className="space-y-5">
      <section className="rounded-xl border border-ink-200 bg-white p-5 shadow-card">
        <h1 className="text-lg font-semibold tracking-tight text-ink-900">运营后台</h1>
        <p className="mt-1 text-sm text-ink-500">
          调整用户额度、生成兑换码。改写预设、规则库与 LLM 配置在对应页面维护。
        </p>
        <div className="mt-3 flex flex-wrap gap-2 text-xs">
          <Link href="/presets" className="rounded-md bg-ink-100 px-2 py-1 text-ink-700 hover:bg-ink-200">
            改写预设
          </Link>
          <Link href="/features" className="rounded-md bg-ink-100 px-2 py-1 text-ink-700 hover:bg-ink-200">
            规则库
          </Link>
          <Link
            href="/settings/llm"
            className="rounded-md bg-ink-100 px-2 py-1 text-ink-700 hover:bg-ink-200"
          >
            LLM 设置
          </Link>
        </div>
        {message && (
          <div className="mt-3 rounded-lg border border-emerald-200 bg-emerald-50 px-3 py-2 text-sm text-emerald-700">
            {message}
          </div>
        )}
        {error && (
          <div className="mt-3 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">
            {error}
          </div>
        )}
      </section>

      <section className="rounded-xl border border-ink-200 bg-white p-5 shadow-card">
        <h2 className="text-sm font-semibold text-ink-900">用户（{users.length}）</h2>
        <div className="mt-3 space-y-2">
          {users.map((item) => (
            <div
              key={item.id}
              className="flex flex-wrap items-center gap-2 rounded-lg border border-ink-100 px-3 py-2 text-xs"
            >
              <div className="min-w-0 flex-1">
                <div className="truncate text-sm text-ink-800">
                  {item.email}
                  {item.is_admin && (
                    <span className="ml-2 rounded bg-accent-50 px-1.5 py-0.5 text-[10px] text-accent-700">
                      管理员
                    </span>
                  )}
                </div>
                <div className="text-ink-400">余额 {item.credits} 字</div>
              </div>
              <input
                value={deltas[item.id] ?? ""}
                onChange={(e) => setDeltas((prev) => ({ ...prev, [item.id]: e.target.value }))}
                inputMode="numeric"
                placeholder="字数"
                className="w-20 rounded-md border border-ink-200 px-2 py-1 text-xs outline-none focus:border-accent-500"
              />
              <button
                type="button"
                onClick={() => adjust(item, 1)}
                className="rounded-md bg-accent-600 px-2 py-1 text-xs font-medium text-white hover:bg-accent-700"
              >
                增加
              </button>
              <button
                type="button"
                onClick={() => adjust(item, -1)}
                className="rounded-md border border-ink-200 px-2 py-1 text-xs text-ink-700 hover:bg-ink-50"
              >
                扣减
              </button>
            </div>
          ))}
        </div>
      </section>

      <section className="rounded-xl border border-ink-200 bg-white p-5 shadow-card">
        <h2 className="text-sm font-semibold text-ink-900">兑换码</h2>
        <form onSubmit={createCode} className="mt-3 flex flex-wrap items-end gap-2">
          <div>
            <label className="mb-1 block text-xs text-ink-500">面额（字）</label>
            <input
              value={credits}
              onChange={(e) => setCredits(e.target.value)}
              inputMode="numeric"
              className="w-24 rounded-md border border-ink-200 px-2 py-1.5 text-sm outline-none focus:border-accent-500"
            />
          </div>
          <div>
            <label className="mb-1 block text-xs text-ink-500">可用次数</label>
            <input
              value={maxUses}
              onChange={(e) => setMaxUses(e.target.value)}
              inputMode="numeric"
              className="w-20 rounded-md border border-ink-200 px-2 py-1.5 text-sm outline-none focus:border-accent-500"
            />
          </div>
          <button
            type="submit"
            className="rounded-lg bg-accent-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-accent-700"
          >
            生成
          </button>
          {created && (
            <div className="rounded-md bg-ink-100 px-2 py-1.5 text-xs text-ink-800">
              新兑换码：<span className="font-mono">{created}</span>
            </div>
          )}
        </form>
        <div className="mt-3 space-y-1">
          {codes.map((item) => (
            <div
              key={item.id}
              className="flex items-center justify-between gap-2 rounded-md bg-ink-50 px-3 py-1.5 text-xs"
            >
              <span className="font-mono text-ink-800">{item.code}</span>
              <span className="text-ink-500">
                {item.credits} 字 · 已用 {item.used_count}/{item.max_uses}
              </span>
            </div>
          ))}
        </div>
      </section>
    </div>
  );
}
