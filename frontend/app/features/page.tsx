"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { apiGet, apiSend } from "@/lib/api";
import type { FeatureRule } from "@/lib/types";

interface RuleForm {
  name: string;
  category: string;
  scope: string;
  pattern: string;
  replacements: string;
  severity: string;
  replaceMode: string;
  note: string;
  deleteMode: boolean;
}

const EMPTY_FORM: RuleForm = {
  name: "",
  category: "lexicon",
  scope: "general",
  pattern: "",
  replacements: "",
  severity: "medium",
  replaceMode: "all",
  note: "",
  deleteMode: false,
};

const SCOPES = ["general", "academic", "fiction"];
const CATEGORIES = ["lexicon", "regex"];
const SEVERITIES = ["high", "medium", "low"];

export default function FeaturesPage() {
  const [rules, setRules] = useState<FeatureRule[]>([]);
  const [form, setForm] = useState<RuleForm>(EMPTY_FORM);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [scopeFilter, setScopeFilter] = useState("");
  const [categoryFilter, setCategoryFilter] = useState("");
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const fileRef = useRef<HTMLInputElement>(null);

  const load = useCallback(async () => {
    try {
      const data = await apiGet<FeatureRule[]>("/api/features");
      setRules(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "加载失败");
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const filtered = useMemo(
    () =>
      rules.filter(
        (rule) =>
          (!scopeFilter || rule.scope === scopeFilter) &&
          (!categoryFilter || rule.category === categoryFilter)
      ),
    [rules, scopeFilter, categoryFilter]
  );

  const resetForm = () => {
    setForm(EMPTY_FORM);
    setEditingId(null);
  };

  const handleSubmit = async () => {
    setError("");
    setMessage("");
    if (!form.pattern.trim()) {
      setError("匹配内容不能为空");
      return;
    }
    const replacements = form.deleteMode
      ? [""]
      : form.replacements
          .split(",")
          .map((item) => item.trim())
          .filter(Boolean);
    const payload = {
      name: form.name || form.pattern.slice(0, 30),
      category: form.category,
      scope: form.scope,
      pattern: form.pattern,
      replacements,
      severity: form.severity,
      replace_mode: form.replaceMode,
      enabled: true,
      note: form.note,
    };
    try {
      if (editingId) {
        await apiSend<FeatureRule>(`/api/features/${editingId}`, "PUT", payload);
        setMessage("规则已更新");
      } else {
        await apiSend<FeatureRule>("/api/features", "POST", payload);
        setMessage("规则已新增");
      }
      resetForm();
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "保存失败");
    }
  };

  const handleEdit = (rule: FeatureRule) => {
    setEditingId(rule.id);
    setForm({
      name: rule.name,
      category: rule.category,
      scope: rule.scope,
      pattern: rule.pattern,
      replacements: rule.replacements.join(", "),
      severity: rule.severity,
      replaceMode: rule.replace_mode || "all",
      note: rule.note,
      deleteMode: rule.replacements.length === 1 && rule.replacements[0] === "",
    });
  };

  const handleToggle = async (rule: FeatureRule) => {
    try {
      await apiSend<FeatureRule>(`/api/features/${rule.id}`, "PUT", {
        name: rule.name,
        category: rule.category,
        scope: rule.scope,
        pattern: rule.pattern,
        replacements: rule.replacements,
        severity: rule.severity,
        replace_mode: rule.replace_mode || "all",
        enabled: !rule.enabled,
        note: rule.note,
      });
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "更新失败");
    }
  };

  const handleDelete = async (rule: FeatureRule) => {
    if (!window.confirm(`确定删除规则「${rule.pattern}」？`)) return;
    try {
      await apiSend(`/api/features/${rule.id}`, "DELETE");
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "删除失败");
    }
  };

  const handleExport = async () => {
    try {
      const data = await apiGet<FeatureRule[]>("/api/features/export");
      const blob = new Blob([JSON.stringify(data, null, 2)], {
        type: "application/json",
      });
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = "rewrite-rules.json";
      link.click();
      URL.revokeObjectURL(url);
    } catch (err) {
      setError(err instanceof Error ? err.message : "导出失败");
    }
  };

  const handleImport = async (file: File) => {
    setError("");
    setMessage("");
    try {
      const text = await file.text();
      const parsed = JSON.parse(text);
      const list = Array.isArray(parsed) ? parsed : parsed.rules;
      if (!Array.isArray(list)) throw new Error("文件格式应为规则数组");
      const result = await apiSend<{ imported: number; skipped: number }>(
        "/api/features/import",
        "POST",
        list
      );
      setMessage(`导入完成：新增 ${result.imported} 条，跳过 ${result.skipped} 条`);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "导入失败");
    }
  };

  return (
    <div className="space-y-5">
      <section className="rounded-xl border border-ink-200 bg-white p-5 shadow-card">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h1 className="text-lg font-semibold tracking-tight text-ink-900">改写规则库</h1>
            <p className="mt-1 text-sm text-ink-500">
              词表规则做精确替换，正则规则用来处理句首模板和对称句式。规则会在规则改写和混合改写中生效。
            </p>
          </div>
          <div className="flex gap-2">
            <button
              type="button"
              onClick={handleExport}
              className="rounded-lg border border-ink-200 px-3 py-1.5 text-sm text-ink-600 hover:bg-ink-50"
            >
              导出
            </button>
            <button
              type="button"
              onClick={() => fileRef.current?.click()}
              className="rounded-lg border border-ink-200 px-3 py-1.5 text-sm text-ink-600 hover:bg-ink-50"
            >
              导入
            </button>
            <input
              ref={fileRef}
              type="file"
              accept="application/json"
              className="hidden"
              onChange={(e) => {
                const file = e.target.files?.[0];
                if (file) handleImport(file);
                e.target.value = "";
              }}
            />
          </div>
        </div>
      </section>

      <section className="rounded-xl border border-ink-200 bg-white p-5 shadow-card">
        <h2 className="mb-3 text-sm font-semibold text-ink-800">
          {editingId ? `编辑规则 #${editingId}` : "新增规则"}
        </h2>
        <div className="grid gap-3 md:grid-cols-3">
          <div>
            <label className="mb-1 block text-xs font-medium text-ink-500">名称</label>
            <input
              value={form.name}
              onChange={(e) => setForm({ ...form, name: e.target.value })}
              placeholder="可留空"
              className="w-full rounded-lg border border-ink-200 px-3 py-2 text-sm outline-none focus:border-accent-500"
            />
          </div>
          <div>
            <label className="mb-1 block text-xs font-medium text-ink-500">类型</label>
            <select
              value={form.category}
              onChange={(e) => setForm({ ...form, category: e.target.value })}
              className="w-full rounded-lg border border-ink-200 bg-white px-3 py-2 text-sm outline-none focus:border-accent-500"
            >
              {CATEGORIES.map((item) => (
                <option key={item} value={item}>
                  {item === "lexicon" ? "词表（精确匹配）" : "正则（regex）"}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className="mb-1 block text-xs font-medium text-ink-500">适用范围</label>
            <select
              value={form.scope}
              onChange={(e) => setForm({ ...form, scope: e.target.value })}
              className="w-full rounded-lg border border-ink-200 bg-white px-3 py-2 text-sm outline-none focus:border-accent-500"
            >
              {SCOPES.map((item) => (
                <option key={item} value={item}>
                  {item}
                </option>
              ))}
            </select>
          </div>
          <div className="md:col-span-2">
            <label className="mb-1 block text-xs font-medium text-ink-500">
              匹配内容{form.category === "regex" ? "（正则表达式）" : ""}
            </label>
            <input
              value={form.pattern}
              onChange={(e) => setForm({ ...form, pattern: e.target.value })}
              placeholder={form.category === "regex" ? "^首先[，,]\\s*" : "值得注意的是"}
              className="w-full rounded-lg border border-ink-200 px-3 py-2 text-sm outline-none focus:border-accent-500"
            />
          </div>
          <div>
            <label className="mb-1 block text-xs font-medium text-ink-500">严重度</label>
            <select
              value={form.severity}
              onChange={(e) => setForm({ ...form, severity: e.target.value })}
              className="w-full rounded-lg border border-ink-200 bg-white px-3 py-2 text-sm outline-none focus:border-accent-500"
            >
              {SEVERITIES.map((item) => (
                <option key={item} value={item}>
                  {item}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className="mb-1 block text-xs font-medium text-ink-500">替换方式</label>
            <select
              value={form.replaceMode}
              onChange={(e) => setForm({ ...form, replaceMode: e.target.value })}
              className="w-full rounded-lg border border-ink-200 bg-white px-3 py-2 text-sm outline-none focus:border-accent-500"
            >
              <option value="all">全部替换</option>
              <option value="alternate">隔一个替换</option>
              <option value="first">只替换第一个</option>
            </select>
          </div>
          <div className="md:col-span-2">
            <label className="mb-1 block text-xs font-medium text-ink-500">
              替换候选（英文逗号分隔，会轮换使用）
            </label>
            <input
              value={form.replacements}
              onChange={(e) => setForm({ ...form, replacements: e.target.value })}
              disabled={form.deleteMode}
              placeholder="有意思的是, 值得一提的是"
              className="w-full rounded-lg border border-ink-200 px-3 py-2 text-sm outline-none focus:border-accent-500 disabled:bg-ink-100 disabled:text-ink-400"
            />
          </div>
          <div className="flex items-end">
            <label className="flex items-center gap-2 text-sm text-ink-600">
              <input
                type="checkbox"
                checked={form.deleteMode}
                onChange={(e) => setForm({ ...form, deleteMode: e.target.checked })}
                className="accent-accent-600"
              />
              删除匹配内容
            </label>
          </div>
          <div className="md:col-span-3">
            <label className="mb-1 block text-xs font-medium text-ink-500">备注</label>
            <input
              value={form.note}
              onChange={(e) => setForm({ ...form, note: e.target.value })}
              className="w-full rounded-lg border border-ink-200 px-3 py-2 text-sm outline-none focus:border-accent-500"
            />
          </div>
        </div>
        <div className="mt-3 flex gap-2">
          <button
            type="button"
            onClick={handleSubmit}
            className="rounded-lg bg-accent-600 px-4 py-2 text-sm font-medium text-white hover:bg-accent-700"
          >
            {editingId ? "保存修改" : "新增"}
          </button>
          {editingId && (
            <button
              type="button"
              onClick={resetForm}
              className="rounded-lg border border-ink-200 px-4 py-2 text-sm text-ink-600 hover:bg-ink-50"
            >
              取消
            </button>
          )}
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

      <section className="rounded-xl border border-ink-200 bg-white shadow-card">
        <div className="flex flex-wrap items-center gap-3 border-b border-ink-100 px-5 py-3">
          <span className="text-sm font-semibold text-ink-800">规则列表</span>
          <span className="text-xs text-ink-400">{filtered.length} 条</span>
          <div className="ml-auto flex gap-2">
            <select
              value={scopeFilter}
              onChange={(e) => setScopeFilter(e.target.value)}
              className="rounded-lg border border-ink-200 bg-white px-2 py-1 text-sm outline-none"
            >
              <option value="">全部范围</option>
              {SCOPES.map((item) => (
                <option key={item} value={item}>
                  {item}
                </option>
              ))}
            </select>
            <select
              value={categoryFilter}
              onChange={(e) => setCategoryFilter(e.target.value)}
              className="rounded-lg border border-ink-200 bg-white px-2 py-1 text-sm outline-none"
            >
              <option value="">全部类型</option>
              {CATEGORIES.map((item) => (
                <option key={item} value={item}>
                  {item}
                </option>
              ))}
            </select>
          </div>
        </div>
        <div className="max-h-[520px] overflow-auto">
          <table className="w-full text-left text-sm">
            <thead className="sticky top-0 bg-ink-50 text-xs text-ink-500">
              <tr>
                <th className="px-4 py-2 font-medium">匹配内容</th>
                <th className="px-4 py-2 font-medium">替换</th>
                <th className="px-4 py-2 font-medium">类型</th>
                <th className="px-4 py-2 font-medium">范围</th>
                <th className="px-4 py-2 font-medium">严重度</th>
                <th className="px-4 py-2 font-medium">状态</th>
                <th className="px-4 py-2 font-medium">操作</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((rule) => (
                <tr key={rule.id} className="border-t border-ink-100 hover:bg-ink-50/60">
                  <td className="px-4 py-2 font-mono text-xs text-ink-800">{rule.pattern}</td>
                  <td className="px-4 py-2 text-xs text-ink-600">
                    {rule.replacements.length === 0
                      ? "—"
                      : rule.replacements[0] === ""
                        ? "（删除）"
                        : rule.replacements.join(" / ")}
                  </td>
                  <td className="px-4 py-2 text-xs text-ink-500">{rule.category}</td>
                  <td className="px-4 py-2 text-xs text-ink-500">{rule.scope}</td>
                  <td className="px-4 py-2 text-xs text-ink-500">{rule.severity}</td>
                  <td className="px-4 py-2">
                    <button
                      type="button"
                      onClick={() => handleToggle(rule)}
                      className={
                        rule.enabled
                          ? "rounded-full bg-emerald-50 px-2 py-0.5 text-xs text-emerald-700"
                          : "rounded-full bg-ink-100 px-2 py-0.5 text-xs text-ink-500"
                      }
                    >
                      {rule.enabled ? "启用" : "停用"}
                    </button>
                  </td>
                  <td className="px-4 py-2">
                    <div className="flex gap-2 text-xs">
                      <button
                        type="button"
                        onClick={() => handleEdit(rule)}
                        className="text-accent-600 hover:underline"
                      >
                        编辑
                      </button>
                      <button
                        type="button"
                        onClick={() => handleDelete(rule)}
                        className="text-red-500 hover:underline"
                      >
                        删除
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
              {filtered.length === 0 && (
                <tr>
                  <td colSpan={7} className="px-4 py-8 text-center text-sm text-ink-400">
                    没有匹配的规则
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}
