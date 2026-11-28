"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { apiGet, apiSend } from "@/lib/api";
import { useAuth } from "@/components/AuthContext";
import type {
  LessonStats,
  LLMSetting,
  LocalModelStatus,
  RewriteLesson,
} from "@/lib/types";

interface FormState {
  provider: string;
  base_url: string;
  model: string;
  api_key: string;
  local_enabled: boolean;
}

const EMPTY: FormState = {
  provider: "openai",
  base_url: "https://api.openai.com/v1",
  model: "gpt-4o-mini",
  api_key: "",
  local_enabled: false,
};

const PROVIDERS = [
  { value: "openai", label: "OpenAI 兼容" },
  { value: "deepseek", label: "DeepSeek" },
  { value: "ollama", label: "Ollama 本地" },
  { value: "custom", label: "自定义" },
];

const LESSON_CATEGORIES: Record<string, string> = {
  word: "词语",
  collocation: "搭配",
  connector: "连词",
  low_perplexity: "低困惑度",
  template: "模板句式",
  high_freq: "高频套话",
  hollow: "空洞升华",
  register: "语体错位",
  leakage: "过程痕迹",
  structure: "结构问题",
};

const LESSON_OUTCOMES: Record<string, string> = {
  survived: "仍不达标",
  fixed: "已修复",
  pending: "待定",
};

const LESSON_STATUSES: Record<string, string> = {
  active: "启用",
  candidate: "观察中",
  ignored: "已忽略",
  resolved: "已解决",
};

function outcomeClass(outcome: string): string {
  if (outcome === "survived") return "rounded bg-amber-50 px-1.5 py-0.5 text-amber-700";
  if (outcome === "fixed") return "rounded bg-emerald-50 px-1.5 py-0.5 text-emerald-700";
  return "rounded bg-ink-100 px-1.5 py-0.5 text-ink-500";
}

export default function LLMSettingsPage() {
  const { user, loading: authLoading } = useAuth();
  const [form, setForm] = useState<FormState>(EMPTY);
  const [setting, setSetting] = useState<LLMSetting | null>(null);
  const [models, setModels] = useState<string[]>([]);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [localStatus, setLocalStatus] = useState<LocalModelStatus | null>(null);
  const [localBusy, setLocalBusy] = useState(false);
  const [localFiles, setLocalFiles] = useState<{
    path: string;
    exists: boolean;
    size_mb: number;
  } | null>(null);
  const [lessons, setLessons] = useState<RewriteLesson[]>([]);
  const [lessonStats, setLessonStats] = useState<LessonStats | null>(null);
  const [lessonStatus, setLessonStatus] = useState("");
  const [lessonOutcome, setLessonOutcome] = useState("");
  const [lessonCategory, setLessonCategory] = useState("");
  const [lessonQuery, setLessonQuery] = useState("");
  const [clearingLessons, setClearingLessons] = useState(false);
  const [lessonNotice, setLessonNotice] = useState("");

  const load = useCallback(async () => {
    try {
      const data = await apiGet<LLMSetting>("/api/settings/llm");
      setSetting(data);
      setForm((prev) => ({
        ...prev,
        provider: data.provider,
        base_url: data.base_url,
        model: data.model,
        local_enabled: data.local_enabled ?? false,
      }));
    } catch (err) {
      setError(err instanceof Error ? err.message : "加载失败");
    }
  }, []);

  const loadLessons = useCallback(async () => {
    try {
      const params = new URLSearchParams({ style: "academic", limit: "50" });
      if (lessonStatus) params.set("status", lessonStatus);
      if (lessonOutcome) params.set("outcome", lessonOutcome);
      if (lessonCategory) params.set("category", lessonCategory);
      if (lessonQuery.trim()) params.set("q", lessonQuery.trim());
      const data = await apiGet<RewriteLesson[]>(`/api/lessons?${params.toString()}`);
      setLessons(data);
    } catch {
      setLessons([]);
    }
  }, [lessonStatus, lessonOutcome, lessonCategory, lessonQuery]);

  const loadLessonStats = useCallback(async () => {
    try {
      const data = await apiGet<LessonStats>("/api/lessons/stats?style=academic");
      setLessonStats(data);
    } catch {
      setLessonStats(null);
    }
  }, []);

  useEffect(() => {
    if (!user?.is_admin) return;
    load();
  }, [user, load]);

  useEffect(() => {
    if (!user?.is_admin) return;
    loadLessons();
    loadLessonStats();
  }, [user, loadLessons, loadLessonStats]);

  const handleDeleteLesson = async (id: number) => {
    try {
      await apiSend<{ ok: boolean }>(`/api/lessons/${id}`, "DELETE");
      await Promise.all([loadLessons(), loadLessonStats()]);
    } catch (err) {
      setError(err instanceof Error ? err.message : "删除失败");
    }
  };

  const handleClearLessons = async () => {
    const total = lessonStats?.total ?? lessons.length;
    if (total === 0) {
      setLessonNotice("避雷库已经是空的");
      return;
    }
    if (!window.confirm(`确定清空避雷库的全部 ${total} 条记录？该操作不可恢复。`)) {
      return;
    }
    setClearingLessons(true);
    setLessonNotice("");
    try {
      const result = await apiSend<{ ok: boolean; deleted: number }>("/api/lessons", "DELETE");
      await Promise.all([loadLessons(), loadLessonStats()]);
      setLessonNotice(`已清空 ${result.deleted} 条避雷记录`);
    } catch (err) {
      setLessonNotice(err instanceof Error ? err.message : "清空失败");
    } finally {
      setClearingLessons(false);
    }
  };

  const handleLessonStatus = async (id: number, status: string) => {
    try {
      await apiSend<RewriteLesson>(`/api/lessons/${id}`, "PUT", { status });
      await Promise.all([loadLessons(), loadLessonStats()]);
    } catch (err) {
      setError(err instanceof Error ? err.message : "更新失败");
    }
  };

  const update = <K extends keyof FormState>(key: K, value: FormState[K]) =>
    setForm((prev) => ({ ...prev, [key]: value }));

  const handleSave = async () => {
    setBusy(true);
    setError("");
    setMessage("");
    try {
      const payload: Record<string, unknown> = {
        provider: form.provider,
        base_url: form.base_url,
        model: form.model,
        local_enabled: form.local_enabled,
      };
      if (form.api_key.trim()) payload.api_key = form.api_key.trim();
      await apiSend<LLMSetting>("/api/settings/llm", "PUT", payload);
      setForm((prev) => ({ ...prev, api_key: "" }));
      setMessage("已保存");
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "保存失败");
    } finally {
      setBusy(false);
    }
  };

  const handleTest = async () => {
    setBusy(true);
    setError("");
    setMessage("");
    try {
      const payload: Record<string, unknown> = {
        provider: form.provider,
        base_url: form.base_url,
        model: form.model,
      };
      if (form.api_key.trim()) payload.api_key = form.api_key.trim();
      const result = await apiSend<{ ok: boolean; latency_ms: number; message: string }>(
        "/api/settings/llm/test",
        "POST",
        payload
      );
      if (result.ok) setMessage(`连接成功，耗时 ${result.latency_ms} ms`);
      else setError(result.message || "连接失败");
    } catch (err) {
      setError(err instanceof Error ? err.message : "测试失败");
    } finally {
      setBusy(false);
    }
  };

  const handleModels = async () => {
    setBusy(true);
    setError("");
    try {
      const data = await apiGet<{ models: string[] }>("/api/settings/llm/models");
      setModels(data.models);
      setMessage(`获取到 ${data.models.length} 个模型`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "获取模型失败");
    } finally {
      setBusy(false);
    }
  };

  const handleClearKey = async () => {
    setBusy(true);
    setError("");
    setMessage("");
    try {
      await apiSend<LLMSetting>("/api/settings/llm/key", "DELETE");
      setMessage("已清除 API Key");
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "清除失败");
    } finally {
      setBusy(false);
    }
  };


  const refreshLocalStatus = useCallback(async () => {
    try {
      setLocalStatus(await apiGet<LocalModelStatus>("/api/settings/llm/local/status"));
    } catch {
      // ignore
    }
  }, []);

  const refreshLocalFiles = useCallback(async () => {
    try {
      setLocalFiles(
        await apiGet<{ path: string; exists: boolean; size_mb: number }>(
          "/api/settings/llm/local/files"
        )
      );
    } catch {
      // ignore
    }
  }, []);

  useEffect(() => {
    if (!user?.is_admin) return;
    refreshLocalStatus();
    refreshLocalFiles();
  }, [user, refreshLocalStatus, refreshLocalFiles]);

  useEffect(() => {
    if (!localStatus?.loading) return;
    const timer = setInterval(refreshLocalStatus, 2000);
    return () => clearInterval(timer);
  }, [localStatus?.loading, refreshLocalStatus]);

  const handleLocalLoad = async () => {
    setLocalBusy(true);
    setError("");
    setMessage("");
    try {
      await apiSend<LocalModelStatus>("/api/settings/llm/local/load", "POST", {});
      setMessage("模型开始加载，首次需要下载，可能要几分钟");
      await refreshLocalStatus();
    } catch (err) {
      setError(err instanceof Error ? err.message : "加载失败");
    } finally {
      setLocalBusy(false);
    }
  };

  const handleLocalUnload = async () => {
    setLocalBusy(true);
    setError("");
    setMessage("");
    try {
      await apiSend<LocalModelStatus>("/api/settings/llm/local/unload", "POST");
      setMessage("已卸载本地模型");
      await refreshLocalStatus();
    } catch (err) {
      setError(err instanceof Error ? err.message : "卸载失败");
    } finally {
      setLocalBusy(false);
    }
  };

  if (authLoading) {
    return <div className="py-10 text-center text-sm text-ink-500">加载中…</div>;
  }

  if (!user?.is_admin) {
    return (
      <div className="mx-auto max-w-md rounded-xl border border-ink-200 bg-white p-6 text-center shadow-card">
        <p className="text-sm text-ink-600">LLM 配置仅管理员可访问。</p>
        <Link
          href="/"
          className="mt-4 inline-block rounded-lg bg-accent-600 px-4 py-2 text-sm font-medium text-white hover:bg-accent-700"
        >
          返回工作台
        </Link>
      </div>
    );
  }

  return (
    <div className="space-y-5">
      <section className="rounded-xl border border-ink-200 bg-white p-5 shadow-card">
        <h1 className="text-lg font-semibold tracking-tight text-ink-900">LLM 设置</h1>
        <p className="mt-1 text-sm text-ink-500">
          API Key 会在服务端加密保存，读取时只返回掩码。混合改写和纯 LLM 模式会使用这里的配置。
        </p>
      </section>

      <nav className="flex gap-2 overflow-x-auto rounded-xl border border-ink-200 bg-white p-2 shadow-card">
        {[
          ["model", "模型配置"],
          ["local", "本地模型"],
          ["lessons", "避雷库"],
        ].map(([id, label]) => (
          <a
            key={id}
            href={`#${id}`}
            className="shrink-0 rounded-lg px-3 py-1.5 text-sm text-ink-600 hover:bg-ink-50 hover:text-ink-900"
          >
            {label}
          </a>
        ))}
      </nav>

      <section
        id="model"
        className="scroll-mt-20 rounded-xl border border-ink-200 bg-white p-5 shadow-card"
      >
        <h2 className="text-sm font-semibold text-ink-900">模型配置</h2>
        <p className="mt-1 text-xs text-ink-500">
          填写 OpenAI 兼容网关地址、模型名和 API Key。Key 只在服务端加密保存。
        </p>
        <div className="mt-4 grid gap-4 md:grid-cols-2">
          <div>
            <label className="mb-1 block text-xs font-medium text-ink-500">提供商</label>
            <select
              value={form.provider}
              onChange={(e) => update("provider", e.target.value)}
              className="w-full rounded-lg border border-ink-200 bg-white px-3 py-2 text-sm outline-none focus:border-accent-500"
            >
              {PROVIDERS.map((item) => (
                <option key={item.value} value={item.value}>
                  {item.label}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className="mb-1 block text-xs font-medium text-ink-500">Base URL</label>
            <input
              value={form.base_url}
              onChange={(e) => update("base_url", e.target.value)}
              placeholder="https://api.openai.com/v1"
              className="w-full rounded-lg border border-ink-200 px-3 py-2 text-sm outline-none focus:border-accent-500"
            />
          </div>
          <div>
            <label className="mb-1 block text-xs font-medium text-ink-500">模型</label>
            <input
              value={form.model}
              onChange={(e) => update("model", e.target.value)}
              placeholder="gpt-4o-mini"
              className="w-full rounded-lg border border-ink-200 px-3 py-2 text-sm outline-none focus:border-accent-500"
            />
          </div>
          <div>
            <label className="mb-1 block text-xs font-medium text-ink-500">
              API Key
              {setting?.has_key && (
                <span className="ml-2 text-ink-400">已保存 {setting.api_key_masked}</span>
              )}
            </label>
            <input
              type="password"
              value={form.api_key}
              onChange={(e) => update("api_key", e.target.value)}
              placeholder={setting?.has_key ? "留空则沿用已保存的 Key" : "sk-..."}
              className="w-full rounded-lg border border-ink-200 px-3 py-2 text-sm outline-none focus:border-accent-500"
            />
          </div>
          <div className="md:col-span-2 rounded-lg bg-ink-50 px-3 py-2 text-xs text-ink-500">
            生成参数已固定：温度 1.2、最大输出 4096 tokens、推理强度 medium、并发 3、超时 120 秒。
          </div>
        </div>

        {models.length > 0 && (
          <div className="mt-4">
            <div className="mb-1 text-xs font-medium text-ink-500">可用模型</div>
            <div className="flex flex-wrap gap-2">
              {models.map((model) => (
                <button
                  key={model}
                  type="button"
                  onClick={() => update("model", model)}
                  className={
                    model === form.model
                      ? "rounded-md bg-accent-50 px-2 py-1 text-xs font-medium text-accent-700"
                      : "rounded-md bg-ink-100 px-2 py-1 text-xs text-ink-600 hover:bg-ink-200"
                  }
                >
                  {model}
                </button>
              ))}
            </div>
          </div>
        )}

        <div className="mt-5 flex flex-wrap items-center gap-2">
          <button
            type="button"
            onClick={handleSave}
            disabled={busy}
            className="rounded-lg bg-accent-600 px-4 py-2 text-sm font-medium text-white hover:bg-accent-700 disabled:opacity-60"
          >
            保存
          </button>
          <button
            type="button"
            onClick={handleTest}
            disabled={busy}
            className="rounded-lg border border-ink-200 px-4 py-2 text-sm text-ink-700 hover:bg-ink-50 disabled:opacity-60"
          >
            测试连接
          </button>
          <button
            type="button"
            onClick={handleModels}
            disabled={busy}
            className="rounded-lg border border-ink-200 px-4 py-2 text-sm text-ink-700 hover:bg-ink-50 disabled:opacity-60"
          >
            拉取模型
          </button>
          {setting?.has_key && (
            <button
              type="button"
              onClick={handleClearKey}
              disabled={busy}
              className="rounded-lg border border-red-200 px-4 py-2 text-sm text-red-600 hover:bg-red-50 disabled:opacity-60"
            >
              清除 Key
            </button>
          )}
        </div>

        {message && (
          <div className="mt-4 rounded-lg border border-emerald-200 bg-emerald-50 px-4 py-2 text-sm text-emerald-700">
            {message}
          </div>
        )}
        {error && (
          <div className="mt-4 rounded-lg border border-red-200 bg-red-50 px-4 py-2 text-sm text-red-700">
            {error}
          </div>
        )}
      </section>

      <section
        id="local"
        className="scroll-mt-20 rounded-xl border border-ink-200 bg-white p-5 shadow-card"
      >
        <h2 className="text-sm font-semibold text-ink-900">本地模型评分（调试）</h2>
        <p className="mt-1 text-sm text-ink-500">
          用于计算逐句困惑度，辅助判断词级可预测性。模型从 hf-mirror 下载，启用后会增加改写耗时。
        </p>
        <label className="mt-4 flex items-center gap-2 text-sm text-ink-700">
          <input
            type="checkbox"
            checked={form.local_enabled}
            onChange={(e) => update("local_enabled", e.target.checked)}
            className="accent-accent-600"
          />
          启用本地模型评分
        </label>
        <div className="mt-3 rounded-lg bg-ink-50 px-3 py-2 text-xs text-ink-500">
          本地模型已固定为 Qwen/Qwen2.5-1.5B + float16，避免误改导致内存溢出。
        </div>
        <div className="mt-3 flex flex-wrap items-center gap-2">
          <button
            type="button"
            onClick={handleSave}
            disabled={busy}
            className="rounded-lg bg-accent-600 px-4 py-2 text-sm font-medium text-white hover:bg-accent-700 disabled:opacity-60"
          >
            保存设置
          </button>
          <button
            type="button"
            onClick={handleLocalLoad}
            disabled={localBusy || localStatus?.loading}
            className="rounded-lg border border-ink-200 px-4 py-2 text-sm text-ink-700 hover:bg-ink-50 disabled:opacity-60"
          >
            {localStatus?.loading ? "加载中…" : "加载模型"}
          </button>
          <button
            type="button"
            onClick={handleLocalUnload}
            disabled={localBusy}
            className="rounded-lg border border-ink-200 px-4 py-2 text-sm text-ink-700 hover:bg-ink-50 disabled:opacity-60"
          >
            卸载模型
          </button>
          <button
            type="button"
            onClick={refreshLocalStatus}
            className="rounded-lg border border-ink-200 px-4 py-2 text-sm text-ink-700 hover:bg-ink-50"
          >
            刷新状态
          </button>
        </div>
        <div className="mt-3 rounded-lg bg-ink-50 px-3 py-2 text-xs text-ink-600">
          {localStatus
            ? `状态：${
                localStatus.loading
                  ? "加载中"
                  : localStatus.loaded
                    ? `已加载 ${localStatus.model ?? ""} (${localStatus.dtype ?? ""})`
                    : "未加载"
              }${localStatus.progress ? ` · ${localStatus.progress}` : ""}${localStatus.error ? ` · 错误：${localStatus.error}` : ""}`
            : "状态：读取中"}
        </div>
        {localFiles && (
          <div className="mt-2 text-xs text-ink-500">
            模型文件：
            {localFiles.exists ? `已缓存 ${localFiles.size_mb} MB` : "未下载"} · {localFiles.path}
          </div>
        )}
        <p className="mt-2 text-xs text-ink-400">
          参考：Qwen/Qwen2.5-0.5B 约 1GB；Qwen/Qwen2.5-1.5B 约 3~4GB。模型文件会保存在本地，重启后自动从缓存加载，不会重复下载。
        </p>
      </section>

      <section
        id="lessons"
        className="scroll-mt-20 rounded-xl border border-ink-200 bg-white p-5 shadow-card"
      >
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h2 className="text-sm font-semibold text-ink-900">避雷库</h2>
            <p className="mt-1 text-sm text-ink-500">
              每次改写用本地模型逐句算困惑度，从低困惑度句子里提取 AI 高频词语、固定搭配和连接词；同一表达重复出现后才启用，作为禁用词写入提示词（最多 50 条）。
            </p>
          </div>
          <div className="flex flex-wrap gap-2">
            <button
              type="button"
              onClick={() => {
                loadLessons();
                loadLessonStats();
              }}
              className="rounded-lg border border-ink-200 px-3 py-1.5 text-sm text-ink-700 hover:bg-ink-50"
            >
              刷新
            </button>
            <button
              type="button"
              onClick={handleClearLessons}
              disabled={clearingLessons}
              className="rounded-lg border border-red-200 px-3 py-1.5 text-sm text-red-600 hover:bg-red-50 disabled:opacity-50"
            >
              {clearingLessons ? "清空中…" : "清空避雷库"}
            </button>
          </div>
        </div>
        {lessonNotice && (
          <div className="mt-3 rounded-lg border border-ink-200 bg-ink-50 px-3 py-2 text-xs text-ink-600">
            {lessonNotice}
          </div>
        )}
        <div className="mt-4 rounded-lg bg-ink-50 px-3 py-2 text-xs text-ink-500">
          阈值已固定：达标 45、重写 2 次、严重标记 20。同一词语、搭配或连词出现在 2 个以上低困惑度句子后才启用；只出现一次时先进入观察中。
        </div>
        {lessonStats && (
          <div className="mt-3 flex flex-wrap gap-2 text-xs">
            <span className="rounded-md bg-ink-100 px-2 py-1 text-ink-600">
              总条目 <strong className="text-ink-900">{lessonStats.total}</strong>
            </span>
            <span className="rounded-md bg-emerald-50 px-2 py-1 text-emerald-700">
              已启用 {lessonStats.active}
            </span>
            <span className="rounded-md bg-amber-50 px-2 py-1 text-amber-700">
              观察中 {lessonStats.candidate}
            </span>
            <span className="rounded-md bg-ink-100 px-2 py-1 text-ink-500">
              已忽略 {lessonStats.ignored}
            </span>
            <span className="rounded-md bg-sky-50 px-2 py-1 text-sky-700">
              词语 {lessonStats.words}
            </span>
            <span className="rounded-md bg-sky-50 px-2 py-1 text-sky-700">
              搭配 {lessonStats.collocations}
            </span>
            <span className="rounded-md bg-sky-50 px-2 py-1 text-sky-700">
              连词 {lessonStats.connectors}
            </span>
            {lessonStats.legacy > 0 && (
              <span className="rounded-md bg-amber-50 px-2 py-1 text-amber-700">
                旧模板 {lessonStats.legacy}
              </span>
            )}
          </div>
        )}
        <div className="mt-3 flex flex-wrap gap-2">
          <input
            value={lessonQuery}
            onChange={(event) => setLessonQuery(event.target.value)}
            placeholder="搜索词语、搭配或连词…"
            className="min-w-[180px] flex-1 rounded-lg border border-ink-200 px-3 py-1.5 text-sm outline-none focus:border-accent-500"
          />
          <select
            value={lessonStatus}
            onChange={(event) => setLessonStatus(event.target.value)}
            className="rounded-lg border border-ink-200 bg-white px-2 py-1.5 text-sm"
          >
            <option value="">全部状态</option>
            {Object.entries(LESSON_STATUSES).map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </select>
          <select
            value={lessonOutcome}
            onChange={(event) => setLessonOutcome(event.target.value)}
            className="rounded-lg border border-ink-200 bg-white px-2 py-1.5 text-sm"
          >
            <option value="">全部结果</option>
            {Object.entries(LESSON_OUTCOMES).map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </select>
          <select
            value={lessonCategory}
            onChange={(event) => setLessonCategory(event.target.value)}
            className="rounded-lg border border-ink-200 bg-white px-2 py-1.5 text-sm"
          >
            <option value="">全部类型</option>
            {Object.entries(LESSON_CATEGORIES).map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </select>
        </div>
        <div className="mt-3 space-y-2">
          {lessons.length === 0 && (
            <div className="rounded-lg bg-ink-50 px-3 py-2 text-xs text-ink-500">
              暂无避雷记录
            </div>
          )}
          {lessons.map((item) => (
            <div key={item.id} className="rounded-lg border border-ink-100 px-3 py-2">
              <div className="flex flex-wrap items-start justify-between gap-2">
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-center gap-2 text-[11px] text-ink-400">
                    <span className="rounded bg-ink-100 px-1.5 py-0.5 text-ink-600">
                      {LESSON_CATEGORIES[item.category] ?? item.category}
                    </span>
                    {item.kind !== "lexical" && (
                      <span className="rounded bg-amber-50 px-1.5 py-0.5 text-amber-700">
                        旧模板
                      </span>
                    )}
                    <span>{LESSON_STATUSES[item.status] ?? item.status}</span>
                    {item.kind === "lexical" ? (
                      <span>出现 {item.hits} 次</span>
                    ) : (
                      <span className={outcomeClass(item.outcome)}>
                        {LESSON_OUTCOMES[item.outcome] ?? item.outcome}
                      </span>
                    )}
                    <span>困惑度 {item.perplexity}</span>
                    {item.last_seen_at && (
                      <span>最近 {new Date(item.last_seen_at).toLocaleString("zh-CN")}</span>
                    )}
                  </div>
                  <div className="mt-1 text-sm font-medium text-ink-800">
                    {item.kind === "lexical"
                      ? item.pattern
                      : item.template || item.pattern || item.sentence}
                  </div>
                  {item.kind === "lexical" && item.sentence && (
                    <div className="mt-1 line-clamp-2 text-xs text-ink-400">
                      例句：{item.sentence}
                    </div>
                  )}
                  {item.strategy && (
                    <div className="mt-1 text-xs text-accent-700">
                      策略：{item.strategy}
                    </div>
                  )}
                  {item.note && <div className="mt-1 text-xs text-ink-400">{item.note}</div>}
                </div>
                <div className="flex shrink-0 gap-2">
                  {item.status === "active" ? (
                    <button
                      type="button"
                      onClick={() => handleLessonStatus(item.id, "ignored")}
                      className="rounded-md border border-ink-200 px-2 py-1 text-xs text-ink-600 hover:bg-ink-50"
                    >
                      忽略
                    </button>
                  ) : (
                    <button
                      type="button"
                      onClick={() => handleLessonStatus(item.id, "active")}
                      className="rounded-md border border-ink-200 px-2 py-1 text-xs text-ink-600 hover:bg-ink-50"
                    >
                      启用
                    </button>
                  )}
                  <button
                    type="button"
                    onClick={() => handleDeleteLesson(item.id)}
                    className="rounded-md border border-ink-200 px-2 py-1 text-xs text-ink-600 hover:bg-ink-50"
                  >
                    删除
                  </button>
                </div>
              </div>
            </div>
          ))}
        </div>
      </section>
    </div>
  );
}
