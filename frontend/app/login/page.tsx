"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { apiSend } from "@/lib/api";
import { useAuth } from "@/components/AuthContext";
import type { User } from "@/lib/types";

type Mode = "login" | "register";

export default function LoginPage() {
  const router = useRouter();
  const { refresh } = useAuth();
  const [mode, setMode] = useState<Mode>("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [nickname, setNickname] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      const path = mode === "login" ? "/api/auth/login" : "/api/auth/register";
      const body =
        mode === "login" ? { email, password } : { email, password, nickname };
      await apiSend<User>(path, "POST", body);
      await refresh();
      router.push("/");
    } catch (err) {
      setError(err instanceof Error ? err.message : "操作失败");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="mx-auto max-w-md">
      <section className="rounded-xl border border-ink-200 bg-white p-6 shadow-card">
        <div className="mb-5 flex rounded-lg bg-ink-100 p-1 text-sm">
          {(
            [
              { value: "login", label: "登录" },
              { value: "register", label: "注册" },
            ] as { value: Mode; label: string }[]
          ).map((item) => (
            <button
              key={item.value}
              type="button"
              onClick={() => {
                setMode(item.value);
                setError("");
              }}
              className={
                mode === item.value
                  ? "flex-1 rounded-md bg-white py-1.5 font-medium text-ink-900 shadow-sm"
                  : "flex-1 rounded-md py-1.5 text-ink-500 hover:text-ink-800"
              }
            >
              {item.label}
            </button>
          ))}
        </div>

        <h1 className="text-lg font-semibold tracking-tight text-ink-900">
          {mode === "login" ? "登录账号" : "注册新账号"}
        </h1>
        <p className="mt-1 text-sm text-ink-500">
          {mode === "login"
            ? "登录后可查看任务记录与剩余额度。"
            : "注册即送 100 字体验额度，按实际字数扣费。"}
        </p>

        <form onSubmit={submit} className="mt-5 space-y-4">
          <div>
            <label className="mb-1 block text-xs font-medium text-ink-500">邮箱</label>
            <input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
              placeholder="you@example.com"
              className="w-full rounded-lg border border-ink-200 px-3 py-2 text-sm outline-none focus:border-accent-500"
            />
          </div>
          <div>
            <label className="mb-1 block text-xs font-medium text-ink-500">
              密码（至少 8 位）
            </label>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
              minLength={8}
              placeholder="********"
              className="w-full rounded-lg border border-ink-200 px-3 py-2 text-sm outline-none focus:border-accent-500"
            />
          </div>
          {mode === "register" && (
            <div>
              <label className="mb-1 block text-xs font-medium text-ink-500">
                昵称（可选）
              </label>
              <input
                value={nickname}
                onChange={(e) => setNickname(e.target.value)}
                placeholder="怎么称呼你"
                className="w-full rounded-lg border border-ink-200 px-3 py-2 text-sm outline-none focus:border-accent-500"
              />
            </div>
          )}
          {error && (
            <div className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">
              {error}
            </div>
          )}
          <button
            type="submit"
            disabled={busy}
            className="w-full rounded-lg bg-accent-600 px-4 py-2.5 text-sm font-medium text-white hover:bg-accent-700 disabled:opacity-60"
          >
            {busy ? "处理中…" : mode === "login" ? "登录" : "注册并登录"}
          </button>
        </form>
      </section>
    </div>
  );
}
