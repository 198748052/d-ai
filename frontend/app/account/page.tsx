"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { apiGet, apiSend } from "@/lib/api";
import { useAuth } from "@/components/AuthContext";
import type { CreditLogItem } from "@/lib/types";

export default function AccountPage() {
  const { user, loading, refresh } = useAuth();
  const [logs, setLogs] = useState<CreditLogItem[]>([]);
  const [code, setCode] = useState("");
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const loadLogs = useCallback(async () => {
    try {
      const data = await apiGet<CreditLogItem[]>("/api/credits/logs?limit=50");
      setLogs(data);
    } catch {
      setLogs([]);
    }
  }, []);

  useEffect(() => {
    if (user) loadLogs();
  }, [user, loadLogs]);

  const redeem = async (event: React.FormEvent) => {
    event.preventDefault();
    setBusy(true);
    setError("");
    setMessage("");
    try {
      const data = await apiSend<{ credits: number; added: number }>(
        "/api/credits/redeem",
        "POST",
        { code }
      );
      setMessage(`兑换成功，增加 ${data.added} 字，当前余额 ${data.credits} 字`);
      setCode("");
      await Promise.all([refresh(), loadLogs()]);
    } catch (err) {
      setError(err instanceof Error ? err.message : "兑换失败");
    } finally {
      setBusy(false);
    }
  };

  if (loading) {
    return <div className="py-10 text-center text-sm text-ink-500">加载中…</div>;
  }

  if (!user) {
    return (
      <div className="mx-auto max-w-md rounded-xl border border-ink-200 bg-white p-6 text-center shadow-card">
        <p className="text-sm text-ink-600">登录后可以查看额度与充值记录。</p>
        <Link
          href="/login"
          className="mt-4 inline-block rounded-lg bg-accent-600 px-4 py-2 text-sm font-medium text-white hover:bg-accent-700"
        >
          去登录
        </Link>
      </div>
    );
  }

  return (
    <div className="space-y-5">
      <section className="rounded-xl border border-ink-200 bg-white p-5 shadow-card">
        <div className="flex flex-wrap items-end justify-between gap-3">
          <div>
            <h1 className="text-lg font-semibold tracking-tight text-ink-900">我的额度</h1>
            <p className="mt-1 text-sm text-ink-500">
              按提交正文的实际字数扣费，失败任务自动退回。
            </p>
          </div>
          <div className="text-right">
            <div className="text-xs text-ink-500">剩余额度</div>
            <div className="text-2xl font-semibold text-accent-700">{user.credits} 字</div>
          </div>
        </div>
        <div className="mt-3 text-xs text-ink-500">账号：{user.email}</div>
      </section>

      <section className="rounded-xl border border-ink-200 bg-white p-5 shadow-card">
        <h2 className="text-sm font-semibold text-ink-900">兑换码充值</h2>
        <form onSubmit={redeem} className="mt-3 flex flex-col gap-2 sm:flex-row">
          <input
            value={code}
            onChange={(e) => setCode(e.target.value)}
            placeholder="输入兑换码，例如 AI-XXXX-XXXX"
            className="flex-1 rounded-lg border border-ink-200 px-3 py-2 text-sm outline-none focus:border-accent-500"
          />
          <button
            type="submit"
            disabled={busy || !code.trim()}
            className="rounded-lg bg-accent-600 px-4 py-2 text-sm font-medium text-white hover:bg-accent-700 disabled:opacity-60"
          >
            {busy ? "兑换中…" : "兑换"}
          </button>
        </form>
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
        <h2 className="text-sm font-semibold text-ink-900">额度流水</h2>
        <div className="mt-3 space-y-2">
          {logs.length === 0 && (
            <div className="rounded-lg bg-ink-50 px-3 py-2 text-xs text-ink-500">暂无记录</div>
          )}
          {logs.map((item) => (
            <div
              key={item.id}
              className="flex items-center justify-between gap-3 rounded-lg border border-ink-100 px-3 py-2 text-xs"
            >
              <div className="min-w-0">
                <div className="truncate text-ink-800">{item.reason}</div>
                <div className="text-ink-400">
                  {new Date(item.created_at).toLocaleString("zh-CN")}
                </div>
              </div>
              <div className="shrink-0 text-right">
                <div
                  className={item.delta >= 0 ? "font-medium text-emerald-600" : "font-medium text-ink-700"}
                >
                  {item.delta >= 0 ? "+" : ""}
                  {item.delta} 字
                </div>
                <div className="text-ink-400">余额 {item.balance_after}</div>
              </div>
            </div>
          ))}
        </div>
      </section>
    </div>
  );
}
