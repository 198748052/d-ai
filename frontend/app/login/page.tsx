"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { apiSend } from "@/lib/api";
import { useAuth } from "@/components/AuthContext";
import type { User } from "@/lib/types";

type Mode = "login" | "register" | "reset";

const QQ_RE = /^[A-Za-z0-9._%+-]+@qq\.com$/;

export default function LoginPage() {
  const router = useRouter();
  const { refresh } = useAuth();
  const [mode, setMode] = useState<Mode>("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [code, setCode] = useState("");
  const [nickname, setNickname] = useState("");
  const [agreed, setAgreed] = useState(false);
  const [countdown, setCountdown] = useState(0);
  const [busy, setBusy] = useState(false);
  const [sending, setSending] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    if (countdown <= 0) return;
    const timer = setTimeout(() => setCountdown((value) => value - 1), 1000);
    return () => clearTimeout(timer);
  }, [countdown]);

  const switchMode = (next: Mode) => {
    setMode(next);
    setError("");
    setMessage("");
    setCode("");
  };

  const sendCode = async () => {
    setError("");
    setMessage("");
    if (!QQ_RE.test(email.trim().toLowerCase())) {
      setError("目前仅支持 QQ 邮箱");
      return;
    }
    setSending(true);
    try {
      const data = await apiSend<{ sent: boolean; debug_code?: string }>(
        "/api/auth/send-code",
        "POST",
        { email: email.trim().toLowerCase(), purpose: mode === "reset" ? "reset" : "register" }
      );
      setCountdown(60);
      if (data.debug_code) {
        setCode(data.debug_code);
        setMessage(`测试环境验证码：${data.debug_code}`);
      } else {
        setMessage("验证码已发送，请查收 QQ 邮箱（注意垃圾箱）");
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "发送失败");
    } finally {
      setSending(false);
    }
  };

  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    setBusy(true);
    setError("");
    setMessage("");
    try {
      if (mode === "login") {
        await apiSend<User>("/api/auth/login", "POST", { email, password });
        await refresh();
        router.push("/dashboard");
        return;
      }
      if (mode === "register") {
        if (!agreed) {
          setError("请先阅读并同意用户协议和隐私政策");
          return;
        }
        await apiSend<User>("/api/auth/register", "POST", {
          email,
          password,
          code,
          nickname,
          agreed_terms: agreed,
        });
        await refresh();
        router.push("/dashboard");
        return;
      }
      await apiSend<{ ok: boolean }>("/api/auth/reset-password", "POST", {
        email,
        code,
        password,
      });
      setMessage("密码已重置，请使用新密码登录");
      setMode("login");
      setPassword("");
      setCode("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "操作失败");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="mx-auto max-w-md">
      <div className="mb-4 flex items-center gap-2.5 px-1">
        <span className="flex h-9 w-9 items-center justify-center rounded-xl bg-ink-900 text-sm font-semibold text-white">
          改
        </span>
        <div>
          <div className="text-sm font-semibold text-ink-900">降 AI 味改写平台</div>
          <div className="text-[11px] text-ink-400">学术论文改写</div>
        </div>
      </div>
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
              onClick={() => switchMode(item.value)}
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
          {mode === "login" ? "登录账号" : mode === "register" ? "注册新账号" : "重置密码"}
        </h1>
        <p className="mt-1 text-sm text-ink-500">
          {mode === "login"
            ? "登录后可查看任务记录与剩余额度。"
            : mode === "register"
              ? "仅支持 QQ 邮箱，验证码注册，注册即送 100 字。"
              : "通过 QQ 邮箱验证码重置密码。"}
        </p>

        <form onSubmit={submit} className="mt-5 space-y-4">
          <div>
            <label className="mb-1 block text-xs font-medium text-ink-500">QQ 邮箱</label>
            <input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
              placeholder="123456789@qq.com"
              className="w-full rounded-lg border border-ink-200 px-3 py-2 text-sm outline-none focus:border-accent-500"
            />
          </div>

          {mode !== "login" && (
            <div>
              <label className="mb-1 block text-xs font-medium text-ink-500">邮箱验证码</label>
              <div className="flex gap-2">
                <input
                  value={code}
                  onChange={(e) => setCode(e.target.value)}
                  required
                  placeholder="6 位验证码"
                  className="flex-1 rounded-lg border border-ink-200 px-3 py-2 text-sm outline-none focus:border-accent-500"
                />
                <button
                  type="button"
                  onClick={sendCode}
                  disabled={sending || countdown > 0}
                  className="shrink-0 rounded-lg border border-ink-200 px-3 py-2 text-sm text-ink-700 hover:bg-ink-50 disabled:opacity-60"
                >
                  {countdown > 0 ? `${countdown}s` : sending ? "发送中" : "发送验证码"}
                </button>
              </div>
            </div>
          )}

          <div>
            <label className="mb-1 block text-xs font-medium text-ink-500">
              {mode === "reset" ? "新密码（至少 8 位）" : "密码（至少 8 位）"}
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
              <label className="mb-1 block text-xs font-medium text-ink-500">昵称（可选）</label>
              <input
                value={nickname}
                onChange={(e) => setNickname(e.target.value)}
                placeholder="怎么称呼你"
                className="w-full rounded-lg border border-ink-200 px-3 py-2 text-sm outline-none focus:border-accent-500"
              />
            </div>
          )}

          {mode === "register" && (
            <label className="flex items-start gap-2 text-xs text-ink-600">
              <input
                type="checkbox"
                checked={agreed}
                onChange={(e) => setAgreed(e.target.checked)}
                className="mt-0.5 accent-accent-600"
              />
              <span>
                我已阅读并同意
                <Link href="/terms" className="mx-1 text-accent-700 hover:underline" target="_blank">
                  用户协议
                </Link>
                和
                <Link href="/privacy" className="mx-1 text-accent-700 hover:underline" target="_blank">
                  隐私政策
                </Link>
              </span>
            </label>
          )}

          {message && (
            <div className="rounded-lg border border-emerald-200 bg-emerald-50 px-3 py-2 text-sm text-emerald-700">
              {message}
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
            {busy
              ? "处理中…"
              : mode === "login"
                ? "登录"
                : mode === "register"
                  ? "注册并登录"
                  : "重置密码"}
          </button>

          <div className="text-center text-xs text-ink-500">
            {mode === "login" ? (
              <button type="button" onClick={() => switchMode("reset")} className="hover:text-ink-800">
                忘记密码？
              </button>
            ) : (
              <button type="button" onClick={() => switchMode("login")} className="hover:text-ink-800">
                返回登录
              </button>
            )}
          </div>
        </form>
      </section>
    </div>
  );
}
