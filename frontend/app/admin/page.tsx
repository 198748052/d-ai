"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { apiGet, apiSend } from "@/lib/api";
import { useAuth } from "@/components/AuthContext";
import type { AdminStats, AdminUser, ErrorItem, RedeemCodeItem } from "@/lib/types";

interface UpdateCheck {
  ok: boolean;
  current: string;
  current_info: string;
  remote: string;
  behind: number;
  commits: string[];
  message: string;
}

interface UpdateStatus {
  state: string;
  detail: string;
  running: boolean;
  log: string;
}

export default function AdminPage() {
  const { user, loading } = useAuth();
  const [users, setUsers] = useState<AdminUser[]>([]);
  const [stats, setStats] = useState<AdminStats | null>(null);
  const [errors, setErrors] = useState<ErrorItem[]>([]);
  const [codes, setCodes] = useState<RedeemCodeItem[]>([]);
  const [deltas, setDeltas] = useState<Record<number, string>>({});
  const [credits, setCredits] = useState("500");
  const [maxUses, setMaxUses] = useState("1");
  const [created, setCreated] = useState("");
  const [updateInfo, setUpdateInfo] = useState<UpdateCheck | null>(null);
  const [updateState, setUpdateState] = useState<UpdateStatus | null>(null);
  const [checking, setChecking] = useState(false);
  const [updating, setUpdating] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    try {
      const [u, c, st, errs] = await Promise.all([
        apiGet<AdminUser[]>("/api/admin/users"),
        apiGet<RedeemCodeItem[]>("/api/admin/redeem-codes"),
        apiGet<AdminStats>("/api/admin/stats"),
        apiGet<ErrorItem[]>("/api/admin/errors?limit=20"),
      ]);
      setUsers(u);
      setCodes(c);
      setStats(st);
      setErrors(errs);
    } catch (err) {
      setError(err instanceof Error ? err.message : "加载失败");
    }
  }, []);

  const loadUpdateStatus = useCallback(async () => {
    try {
      setUpdateState(await apiGet<UpdateStatus>("/api/admin/update/status"));
    } catch {
      setUpdateState(null);
    }
  }, []);

  useEffect(() => {
    if (user?.is_admin) {
      load();
      loadUpdateStatus();
    }
  }, [user, load, loadUpdateStatus]);

  useEffect(() => {
    if (!updateState?.running) return;
    const timer = setInterval(loadUpdateStatus, 3000);
    return () => clearInterval(timer);
  }, [updateState?.running, loadUpdateStatus]);

  const checkUpdate = async () => {
    setChecking(true);
    setError("");
    setMessage("");
    try {
      const data = await apiGet<UpdateCheck>("/api/admin/update/check");
      setUpdateInfo(data);
      if (!data.ok) setError(data.message);
      else if (data.behind === 0) setMessage("已是最新版本");
    } catch (err) {
      setError(err instanceof Error ? err.message : "检查更新失败");
    } finally {
      setChecking(false);
    }
  };

  const runUpdate = async () => {
    setUpdating(true);
    setError("");
    setMessage("");
    try {
      const data = await apiSend<{ started: boolean; message: string }>(
        "/api/admin/update/run",
        "POST"
      );
      setMessage(data.message);
      await loadUpdateStatus();
    } catch (err) {
      setError(err instanceof Error ? err.message : "启动更新失败");
    } finally {
      setUpdating(false);
    }
  };

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

      {stats && (
        <section className="grid grid-cols-2 gap-3 md:grid-cols-4">
          {[
            { label: "用户总数", value: stats.total_users },
            { label: "今日新增", value: stats.users_today },
            { label: "任务总数", value: stats.total_jobs },
            { label: "今日任务", value: stats.jobs_today },
            { label: "今日消耗字数", value: stats.chars_today },
            { label: "7 日活跃", value: stats.active_users_7d },
            { label: "24h 错误", value: stats.errors_24h },
            { label: "用户余额合计", value: stats.credits_total },
          ].map((item) => (
            <div
              key={item.label}
              className="rounded-xl border border-ink-200 bg-white p-4 shadow-card"
            >
              <div className="text-xs text-ink-500">{item.label}</div>
              <div className="mt-1 text-xl font-semibold text-ink-900">{item.value}</div>
            </div>
          ))}
        </section>
      )}

      <section className="rounded-xl border border-ink-200 bg-white p-5 shadow-card">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <h2 className="text-sm font-semibold text-ink-900">在线更新</h2>
            <p className="mt-1 text-xs text-ink-500">
              从 GitHub 拉取 main 分支最新代码，安装依赖、重新构建并重启服务。
            </p>
          </div>
          <div className="flex flex-wrap gap-2">
            <button
              type="button"
              onClick={checkUpdate}
              disabled={checking || updateState?.running}
              className="rounded-lg border border-ink-200 px-3 py-1.5 text-sm text-ink-700 hover:bg-ink-50 disabled:opacity-60"
            >
              {checking ? "检查中…" : "检查更新"}
            </button>
            <button
              type="button"
              onClick={runUpdate}
              disabled={updating || updateState?.running || (updateInfo ? updateInfo.behind === 0 : false)}
              className="rounded-lg bg-accent-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-accent-700 disabled:opacity-60"
            >
              {updateState?.running ? "更新中…" : "立即更新"}
            </button>
          </div>
        </div>

        {updateInfo && (
          <div className="mt-4 space-y-2 text-xs">
            <div className="rounded-lg bg-ink-50 px-3 py-2 text-ink-700">
              当前版本：{updateInfo.current_info || updateInfo.current.slice(0, 7)}
              {updateInfo.ok && (
                <span className="ml-2 text-ink-500">
                  {updateInfo.behind > 0
                    ? `落后 ${updateInfo.behind} 个提交`
                    : "已是最新"}
                </span>
              )}
            </div>
            {updateInfo.commits.length > 0 && (
              <ul className="space-y-1 rounded-lg border border-ink-100 px-3 py-2 text-ink-600">
                {updateInfo.commits.map((item) => (
                  <li key={item} className="truncate font-mono">
                    {item}
                  </li>
                ))}
              </ul>
            )}
          </div>
        )}

        {updateState && (
          <div className="mt-3 rounded-lg bg-ink-50 px-3 py-2 text-xs text-ink-600">
            更新状态：
            {updateState.running
              ? "进行中（服务会在完成后自动重启）"
              : updateState.detail || "空闲"}
          </div>
        )}
        {updateState?.log && (
          <pre className="mt-2 max-h-56 overflow-auto whitespace-pre-wrap rounded-lg bg-ink-900/95 p-3 text-[11px] leading-5 text-ink-100">
            {updateState.log}
          </pre>
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
              <div className="min-w-0 flex-1 basis-full sm:basis-auto">
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

      <section className="rounded-xl border border-ink-200 bg-white p-5 shadow-card">
        <h2 className="text-sm font-semibold text-ink-900">错误监控（最近 20 条）</h2>
        <p className="mt-1 text-xs text-ink-500">
          记录服务端异常、任务失败与前端报错。配置 ALERT_WEBHOOK_URL 后会同步推送到群机器人。
        </p>
        <div className="mt-3 space-y-2">
          {errors.length === 0 && (
            <div className="rounded-lg bg-ink-50 px-3 py-2 text-xs text-ink-500">暂无错误记录</div>
          )}
          {errors.map((item) => (
            <details key={item.id} className="rounded-lg border border-ink-100 px-3 py-2 text-xs">
              <summary className="cursor-pointer text-ink-700">
                <span className="mr-2 rounded bg-ink-100 px-1.5 py-0.5 text-[10px] text-ink-600">
                  {item.source}
                </span>
                {item.message}
              </summary>
              <div className="mt-2 space-y-1 text-ink-500">
                <div>{new Date(item.created_at).toLocaleString("zh-CN")}</div>
                {item.path && <div>路径：{item.path}</div>}
                {item.user_id && <div>用户 ID：{item.user_id}</div>}
                {item.detail && (
                  <pre className="max-h-40 overflow-auto whitespace-pre-wrap rounded bg-ink-50 p-2 text-[11px]">
                    {item.detail}
                  </pre>
                )}
              </div>
            </details>
          ))}
        </div>
      </section>
    </div>
  );
}
