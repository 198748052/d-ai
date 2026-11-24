"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { apiGet, apiSend } from "@/lib/api";
import { useAuth } from "@/components/AuthContext";
import type { CreditLogItem, UsageDay } from "@/lib/types";

export default function AccountPage() {
  const { user, loading, refresh } = useAuth();
  const [logs, setLogs] = useState<CreditLogItem[]>([]);
  const [usage, setUsage] = useState<UsageDay[]>([]);
  const [code, setCode] = useState("");
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [oldPassword, setOldPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [pwdMessage, setPwdMessage] = useState("");
  const [pwdError, setPwdError] = useState("");
  const [pwdBusy, setPwdBusy] = useState(false);

  const loadLogs = useCallback(async () => {
    try {
      const data = await apiGet<CreditLogItem[]>("/api/credits/logs?limit=50");
      setLogs(data);
    } catch {
      setLogs([]);
    }
  }, []);

  const loadUsage = useCallback(async () => {
    try {
      const data = await apiGet<UsageDay[]>("/api/credits/usage?days=7");
      setUsage(data);
    } catch {
      setUsage([]);
    }
  }, []);

  useEffect(() => {
    if (user) {
      loadLogs();
      loadUsage();
    }
  }, [user, loadLogs, loadUsage]);

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

  const changePassword = async (event: React.FormEvent) => {
    event.preventDefault();
    setPwdBusy(true);
    setPwdError("");
    setPwdMessage("");
    try {
      await apiSend<{ ok: boolean }>("/api/auth/change-password", "POST", {
        old_password: oldPassword,
        new_password: newPassword,
      });
      setOldPassword("");
      setNewPassword("");
      setPwdMessage("密码已修改，其他设备的登录已失效");
    } catch (err) {
      setPwdError(err instanceof Error ? err.message : "修改失败");
    } finally {
      setPwdBusy(false);
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

  const maxUsage = Math.max(1, ...usage.map((item) => item.chars));

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
        <h2 className="text-sm font-semibold text-ink-900">近 7 天用量</h2>
        <p className="mt-1 text-xs text-ink-500">按任务扣费字数统计，柱高表示当天消耗。</p>
        <div className="mt-4 flex h-28 items-end gap-1 sm:gap-2">
          {usage.map((day) => {
            const height = Math.max(4, Math.round((day.chars / maxUsage) * 100));
            return (
              <div
                key={day.date}
                className="flex h-full flex-1 flex-col items-center justify-end gap-1"
                title={`${day.date}：${day.chars} 字，${day.jobs} 个任务`}
              >
                <div className="text-[9px] text-ink-500 sm:text-[10px]">{day.chars}</div>
                <div
                  className="w-full rounded-t bg-accent-500"
                  style={{ height: `${height}%` }}
                />
                <div className="text-[9px] text-ink-400 sm:text-[10px]">
                  {day.date.slice(5)}
                </div>
              </div>
            );
          })}
          {usage.length === 0 && (
            <div className="pb-6 text-xs text-ink-400">暂无用量记录</div>
          )}
        </div>
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
        <h2 className="text-sm font-semibold text-ink-900">修改密码</h2>
        <form onSubmit={changePassword} className="mt-3 grid gap-3 sm:grid-cols-2">
          <div>
            <label className="mb-1 block text-xs font-medium text-ink-500">原密码</label>
            <input
              type="password"
              value={oldPassword}
              onChange={(e) => setOldPassword(e.target.value)}
              required
              className="w-full rounded-lg border border-ink-200 px-3 py-2 text-sm outline-none focus:border-accent-500"
            />
          </div>
          <div>
            <label className="mb-1 block text-xs font-medium text-ink-500">
              新密码（至少 8 位）
            </label>
            <input
              type="password"
              value={newPassword}
              onChange={(e) => setNewPassword(e.target.value)}
              required
              minLength={8}
              className="w-full rounded-lg border border-ink-200 px-3 py-2 text-sm outline-none focus:border-accent-500"
            />
          </div>
          <div className="sm:col-span-2">
            <button
              type="submit"
              disabled={pwdBusy}
              className="rounded-lg bg-accent-600 px-4 py-2 text-sm font-medium text-white hover:bg-accent-700 disabled:opacity-60"
            >
              {pwdBusy ? "提交中…" : "修改密码"}
            </button>
          </div>
        </form>
        {pwdMessage && (
          <div className="mt-3 rounded-lg border border-emerald-200 bg-emerald-50 px-3 py-2 text-sm text-emerald-700">
            {pwdMessage}
          </div>
        )}
        {pwdError && (
          <div className="mt-3 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">
            {pwdError}
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
