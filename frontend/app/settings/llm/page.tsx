"use client";

import { useCallback, useEffect, useState } from "react";
import { apiGet, apiSend } from "@/lib/api";
import type { LLMSetting, LocalModelStatus, RewriteLesson } from "@/lib/types";

interface FormState {
  provider: string;
  base_url: string;
  model: string;
  api_key: string;
  temperature: number;
  max_tokens: number;
  concurrency: number;
  timeout: number;
  local_enabled: boolean;
  local_model: string;
  local_dtype: string;
  ppl_min: number;
  ppl_retry: number;
  ppl_severe: number;
}

const EMPTY: FormState = {
  provider: "openai",
  base_url: "https://api.openai.com/v1",
  model: "gpt-4o-mini",
  api_key: "",
  temperature: 1.2,
  max_tokens: 4096,
  concurrency: 3,
  timeout: 120,
  local_enabled: false,
  local_model: "Qwen/Qwen2.5-1.5B",
  local_dtype: "float16",
  ppl_min: 60,
  ppl_retry: 2,
  ppl_severe: 25,
};

const PROVIDERS = [
  { value: "openai", label: "OpenAI 兼容" },
  { value: "deepseek", label: "DeepSeek" },
  { value: "ollama", label: "Ollama 本地" },
  { value: "custom", label: "自定义" },
];

export default function LLMSettingsPage() {
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

  const load = useCallback(async () => {
    try {
      const data = await apiGet<LLMSetting>("/api/settings/llm");
      setSetting(data);
      setForm((prev) => ({
        ...prev,
        provider: data.provider,
        base_url: data.base_url,
        model: data.model,
        temperature: data.temperature,
        max_tokens: data.max_tokens,
        concurrency: data.concurrency,
        timeout: data.timeout,
        local_enabled: data.local_enabled ?? false,
        local_model: data.local_model ?? "Qwen/Qwen2.5-1.5B",
        local_dtype: data.local_dtype ?? "float16",
        ppl_min: data.ppl_min ?? 60,
        ppl_retry: data.ppl_retry ?? 2,
        ppl_severe: data.ppl_severe ?? 25,
      }));
    } catch (err) {
      setError(err instanceof Error ? err.message : "加载失败");
    }
  }, []);

  const loadLessons = useCallback(async () => {
    try {
      const data = await apiGet<RewriteLesson[]>("/api/lessons?style=academic&limit=20");
      setLessons(data);
    } catch {
      setLessons([]);
    }
  }, []);

  useEffect(() => {
    load();
    loadLessons();
  }, [load, loadLessons]);

  const handleDeleteLesson = async (id: number) => {
    try {
      await apiSend<{ ok: boolean }>(`/api/lessons/${id}`, "DELETE");
      await loadLessons();
    } catch (err) {
      setError(err instanceof Error ? err.message : "删除失败");
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
        temperature: form.temperature,
        max_tokens: form.max_tokens,
        concurrency: form.concurrency,
        timeout: form.timeout,
        local_enabled: form.local_enabled,
        local_model: form.local_model,
        local_dtype: form.local_dtype,
        ppl_min: form.ppl_min,
        ppl_retry: form.ppl_retry,
        ppl_severe: form.ppl_severe,
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
    refreshLocalStatus();
    refreshLocalFiles();
  }, [refreshLocalStatus, refreshLocalFiles]);

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
      await apiSend<LocalModelStatus>("/api/settings/llm/local/load", "POST", {
        model: form.local_model,
        dtype: form.local_dtype,
      });
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

  return (
    <div className="space-y-5">
      <section className="rounded-xl border border-ink-200 bg-white p-5 shadow-card">
        <h1 className="text-lg font-semibold tracking-tight text-ink-900">LLM 设置</h1>
        <p className="mt-1 text-sm text-ink-500">
          API Key 会在服务端加密保存，读取时只返回掩码。混合改写和纯 LLM 模式会使用这里的配置。
        </p>
      </section>

      <section className="rounded-xl border border-ink-200 bg-white p-5 shadow-card">
        <div className="grid gap-4 md:grid-cols-2">
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
          <div>
            <label className="mb-1 block text-xs font-medium text-ink-500">
              Temperature：{form.temperature}
            </label>
            <input
              type="range"
              min={0}
              max={2}
              step={0.1}
              value={form.temperature}
              onChange={(e) => update("temperature", Number(e.target.value))}
              className="w-full accent-accent-600"
            />
          </div>
          <div>
            <label className="mb-1 block text-xs font-medium text-ink-500">最大输出 tokens</label>
            <input
              type="number"
              value={form.max_tokens}
              onChange={(e) => update("max_tokens", Number(e.target.value))}
              className="w-full rounded-lg border border-ink-200 px-3 py-2 text-sm outline-none focus:border-accent-500"
            />
          </div>
          <div>
            <label className="mb-1 block text-xs font-medium text-ink-500">并发数</label>
            <input
              type="number"
              min={1}
              max={16}
              value={form.concurrency}
              onChange={(e) => update("concurrency", Number(e.target.value))}
              className="w-full rounded-lg border border-ink-200 px-3 py-2 text-sm outline-none focus:border-accent-500"
            />
          </div>
          <div>
            <label className="mb-1 block text-xs font-medium text-ink-500">超时（秒）</label>
            <input
              type="number"
              min={5}
              value={form.timeout}
              onChange={(e) => update("timeout", Number(e.target.value))}
              className="w-full rounded-lg border border-ink-200 px-3 py-2 text-sm outline-none focus:border-accent-500"
            />
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

      <section className="rounded-xl border border-ink-200 bg-white p-5 shadow-card">
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
        <div className="mt-3 grid gap-3 md:grid-cols-3">
          <div className="md:col-span-2">
            <label className="mb-1 block text-xs font-medium text-ink-500">模型名称</label>
            <input
              value={form.local_model}
              onChange={(e) => update("local_model", e.target.value)}
              placeholder="Qwen/Qwen2.5-1.5B"
              className="w-full rounded-lg border border-ink-200 px-3 py-2 text-sm outline-none focus:border-accent-500"
            />
          </div>
          <div>
            <label className="mb-1 block text-xs font-medium text-ink-500">精度</label>
            <select
              value={form.local_dtype}
              onChange={(e) => update("local_dtype", e.target.value)}
              className="w-full rounded-lg border border-ink-200 bg-white px-3 py-2 text-sm outline-none focus:border-accent-500"
            >
              <option value="float32">float32（更稳，内存更大）</option>
              <option value="float16">float16（更省内存）</option>
              <option value="bfloat16">bfloat16</option>
            </select>
          </div>
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

      <section className="rounded-xl border border-ink-200 bg-white p-5 shadow-card">
        <h2 className="text-sm font-semibold text-ink-900">困惑度阈值与踩坑记录</h2>
        <p className="mt-1 text-sm text-ink-500">
          低于阈值的句子会触发整段重写；重写后仍低于严重阈值的句子会被记录，并在后续改写时写入提示词避开。
        </p>
        <div className="mt-4 grid gap-3 md:grid-cols-3">
          <div>
            <label className="mb-1 block text-xs font-medium text-ink-500">达标阈值</label>
            <input
              type="number"
              min={1}
              step={1}
              value={form.ppl_min}
              onChange={(e) => update("ppl_min", Number(e.target.value))}
              className="w-full rounded-lg border border-ink-200 px-3 py-2 text-sm outline-none focus:border-accent-500"
            />
          </div>
          <div>
            <label className="mb-1 block text-xs font-medium text-ink-500">重写次数</label>
            <input
              type="number"
              min={0}
              max={5}
              value={form.ppl_retry}
              onChange={(e) => update("ppl_retry", Number(e.target.value))}
              className="w-full rounded-lg border border-ink-200 px-3 py-2 text-sm outline-none focus:border-accent-500"
            />
          </div>
          <div>
            <label className="mb-1 block text-xs font-medium text-ink-500">严重标记阈值</label>
            <input
              type="number"
              min={1}
              step={1}
              value={form.ppl_severe}
              onChange={(e) => update("ppl_severe", Number(e.target.value))}
              className="w-full rounded-lg border border-ink-200 px-3 py-2 text-sm outline-none focus:border-accent-500"
            />
          </div>
        </div>
        <div className="mt-3 flex items-center gap-2">
          <button
            type="button"
            onClick={handleSave}
            disabled={busy}
            className="rounded-lg bg-accent-600 px-4 py-2 text-sm font-medium text-white hover:bg-accent-700 disabled:opacity-60"
          >
            保存阈值
          </button>
          <button
            type="button"
            onClick={loadLessons}
            className="rounded-lg border border-ink-200 px-4 py-2 text-sm text-ink-700 hover:bg-ink-50"
          >
            刷新记录
          </button>
          <span className="text-xs text-ink-400">共 {lessons.length} 条</span>
        </div>
        <div className="mt-4 space-y-2">
          {lessons.length === 0 && (
            <div className="rounded-lg bg-ink-50 px-3 py-2 text-xs text-ink-500">暂无踩坑记录</div>
          )}
          {lessons.map((item) => (
            <div
              key={item.id}
              className="flex items-start gap-3 rounded-lg border border-ink-100 px-3 py-2"
            >
              <div className="min-w-0 flex-1">
                <div className="text-sm text-ink-800">{item.sentence}</div>
                <div className="mt-1 text-xs text-ink-500">
                  困惑度 {item.perplexity} · 出现 {item.hits} 次
                  {item.note ? ` · ${item.note}` : ""}
                  {item.original ? ` · 原句：${item.original}` : ""}
                </div>
              </div>
              <button
                type="button"
                onClick={() => handleDeleteLesson(item.id)}
                className="shrink-0 rounded-md border border-ink-200 px-2 py-1 text-xs text-ink-600 hover:bg-ink-50"
              >
                删除
              </button>
            </div>
          ))}
        </div>
      </section>
    </div>
  );
}
