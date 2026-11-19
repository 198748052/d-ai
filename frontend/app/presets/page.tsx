"use client";

import { useCallback, useEffect, useState } from "react";
import { apiGet, apiSend } from "@/lib/api";
import type { Preset } from "@/lib/types";

interface PresetForm {
  strength: string;
  colloquial: number;
  length_ratio_min: number;
  length_ratio_max: number;
  protect_terms: string;
  banned_words: string;
  max_rounds: number;
  extra_prompt: string;
}

const EMPTY: PresetForm = {
  strength: "medium",
  colloquial: 0,
  length_ratio_min: 0.9,
  length_ratio_max: 1.1,
  protect_terms: "",
  banned_words: "",
  max_rounds: 2,
  extra_prompt: "",
};

const STRENGTHS = ["light", "medium", "strong"];

export default function PresetsPage() {
  const [preset, setPreset] = useState<Preset | null>(null);
  const [form, setForm] = useState<PresetForm>(EMPTY);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    try {
      const data = await apiGet<Preset[]>("/api/presets");
      const current = data[0] ?? null;
      setPreset(current);
      if (current) {
        setForm({
          strength: current.strength,
          colloquial: current.colloquial,
          length_ratio_min: current.length_ratio_min,
          length_ratio_max: current.length_ratio_max,
          protect_terms: current.protect_terms.join(", "),
          banned_words: current.banned_words.join(", "),
          max_rounds: current.max_rounds,
          extra_prompt: current.extra_prompt,
        });
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "加载失败");
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const update = <K extends keyof PresetForm>(key: K, value: PresetForm[K]) =>
    setForm((prev) => ({ ...prev, [key]: value }));

  const handleSave = async () => {
    if (!preset) return;
    setError("");
    setMessage("");
    try {
      await apiSend<Preset>(`/api/presets/${preset.id}`, "PUT", {
        name: "学术论文",
        style: "academic",
        lexicon_scope: "academic",
        strength: form.strength,
        person: "keep",
        colloquial: form.colloquial,
        length_ratio_min: form.length_ratio_min,
        length_ratio_max: form.length_ratio_max,
        protect_terms: form.protect_terms
          .split(",")
          .map((item) => item.trim())
          .filter(Boolean),
        banned_words: form.banned_words
          .split(",")
          .map((item) => item.trim())
          .filter(Boolean),
        use_rule_engine: true,
        use_llm: true,
        max_rounds: form.max_rounds,
        extra_prompt: form.extra_prompt,
      });
      setMessage("已保存");
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "保存失败");
    }
  };

  return (
    <div className="space-y-5">
      <section className="rounded-xl border border-ink-200 bg-white p-5 shadow-card">
        <h1 className="text-lg font-semibold tracking-tight text-ink-900">改写预设</h1>
        <p className="mt-1 text-sm text-ink-500">
          系统只维护「学术论文」这一个预设，改写固定使用规则 + LLM 混合模式。
        </p>
      </section>

      <section className="rounded-xl border border-ink-200 bg-white p-5 shadow-card">
        <div className="grid gap-4 md:grid-cols-3">
          <div>
            <label className="mb-1 block text-xs font-medium text-ink-500">预设名称</label>
            <div className="rounded-lg border border-ink-200 bg-ink-50 px-3 py-2 text-sm text-ink-600">
              学术论文
            </div>
          </div>
          <div>
            <label className="mb-1 block text-xs font-medium text-ink-500">语体</label>
            <div className="rounded-lg border border-ink-200 bg-ink-50 px-3 py-2 text-sm text-ink-600">
              academic
            </div>
          </div>
          <div>
            <label className="mb-1 block text-xs font-medium text-ink-500">改写方式</label>
            <div className="rounded-lg border border-ink-200 bg-ink-50 px-3 py-2 text-sm text-ink-600">
              规则 + LLM 混合
            </div>
          </div>

          <div>
            <label className="mb-1 block text-xs font-medium text-ink-500">强度</label>
            <select
              value={form.strength}
              onChange={(e) => update("strength", e.target.value)}
              className="w-full rounded-lg border border-ink-200 bg-white px-3 py-2 text-sm outline-none focus:border-accent-500"
            >
              {STRENGTHS.map((item) => (
                <option key={item} value={item}>
                  {item}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className="mb-1 block text-xs font-medium text-ink-500">
              口语化：{form.colloquial}
            </label>
            <input
              type="range"
              min={0}
              max={100}
              step={5}
              value={form.colloquial}
              onChange={(e) => update("colloquial", Number(e.target.value))}
              className="w-full accent-accent-600"
            />
          </div>
          <div>
            <label className="mb-1 block text-xs font-medium text-ink-500">最大改写轮次</label>
            <input
              type="number"
              min={1}
              max={5}
              value={form.max_rounds}
              onChange={(e) => update("max_rounds", Number(e.target.value))}
              className="w-full rounded-lg border border-ink-200 px-3 py-2 text-sm outline-none focus:border-accent-500"
            />
          </div>
          <div>
            <label className="mb-1 block text-xs font-medium text-ink-500">字数比下限</label>
            <input
              type="number"
              step={0.05}
              value={form.length_ratio_min}
              onChange={(e) => update("length_ratio_min", Number(e.target.value))}
              className="w-full rounded-lg border border-ink-200 px-3 py-2 text-sm outline-none focus:border-accent-500"
            />
          </div>
          <div>
            <label className="mb-1 block text-xs font-medium text-ink-500">字数比上限</label>
            <input
              type="number"
              step={0.05}
              value={form.length_ratio_max}
              onChange={(e) => update("length_ratio_max", Number(e.target.value))}
              className="w-full rounded-lg border border-ink-200 px-3 py-2 text-sm outline-none focus:border-accent-500"
            />
          </div>
          <div>
            <label className="mb-1 block text-xs font-medium text-ink-500">
              保护词（逗号分隔）
            </label>
            <input
              value={form.protect_terms}
              onChange={(e) => update("protect_terms", e.target.value)}
              className="w-full rounded-lg border border-ink-200 px-3 py-2 text-sm outline-none focus:border-accent-500"
            />
          </div>
          <div className="md:col-span-2">
            <label className="mb-1 block text-xs font-medium text-ink-500">
              禁用词（逗号分隔）
            </label>
            <input
              value={form.banned_words}
              onChange={(e) => update("banned_words", e.target.value)}
              className="w-full rounded-lg border border-ink-200 px-3 py-2 text-sm outline-none focus:border-accent-500"
            />
          </div>
          <div className="md:col-span-3">
            <label className="mb-1 block text-xs font-medium text-ink-500">
              额外要求（会写进 LLM 提示词）
            </label>
            <textarea
              value={form.extra_prompt}
              onChange={(e) => update("extra_prompt", e.target.value)}
              className="h-24 w-full rounded-lg border border-ink-200 px-3 py-2 text-sm outline-none focus:border-accent-500"
            />
          </div>
        </div>

        <div className="mt-4">
          <button
            type="button"
            onClick={handleSave}
            className="rounded-lg bg-accent-600 px-4 py-2 text-sm font-medium text-white hover:bg-accent-700"
          >
            保存
          </button>
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
    </div>
  );
}
